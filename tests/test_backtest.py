"""Engine arithmetic, costs, execution timing, and the metric definitions."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest import metrics as M
from src.backtest.engine import (
    BacktestConfig, apply_trailing_stop, buy_and_hold_result, run_backtest, volatility_target,
)


@pytest.fixture
def straight_line():
    """A single asset rising exactly 1% per bar. Every number is checkable by hand."""
    index = pd.bdate_range("2024-01-01", periods=100)
    close = 100.0 * (1.01 ** np.arange(100))
    return {"A": pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1e6},
        index=index,
    )}


def _always_long(prices, weight=1.0):
    index = next(iter(prices.values())).index
    return pd.DataFrame({sym: weight for sym in prices}, index=index)


def test_fully_invested_captures_every_move_after_the_first_bar(straight_line):
    """The weight set at bar 0's close earns the move into bar 1 and every move
    after it. With 100 bars there are 99 moves, so the strategy compounds 99 of
    them: an always-invested book gives up nothing but the bar it started on."""
    cfg = BacktestConfig(commission_bps=0, slippage_bps=0, cash_yield=0)
    result = run_backtest(straight_line, _always_long(straight_line), cfg)
    expected = 1.01 ** 99 - 1.0
    assert result.performance.total_return == pytest.approx(expected, rel=1e-9)


def test_execution_lag_is_honoured(straight_line):
    slow = run_backtest(straight_line, _always_long(straight_line),
                        BacktestConfig(commission_bps=0, slippage_bps=0, execution_lag=5))
    fast = run_backtest(straight_line, _always_long(straight_line),
                        BacktestConfig(commission_bps=0, slippage_bps=0, execution_lag=1))
    assert slow.performance.total_return < fast.performance.total_return


def test_costs_are_charged_on_traded_notional(straight_line):
    """One round trip at 10 bps should cost 10 bps of the notional traded."""
    index = next(iter(straight_line.values())).index
    weights = pd.DataFrame({"A": 0.0}, index=index)
    weights.iloc[10:20] = 1.0
    cfg = BacktestConfig(commission_bps=5.0, slippage_bps=5.0)
    result = run_backtest(straight_line, weights, cfg)
    # In and out is two units of turnover at 10 bps each.
    assert result.costs.sum() == pytest.approx(2 * 0.0010, rel=1e-9)


def test_zero_weights_give_exactly_zero_return(straight_line):
    index = next(iter(straight_line.values())).index
    flat = pd.DataFrame({"A": 0.0}, index=index)
    result = run_backtest(straight_line, flat, BacktestConfig(cash_yield=0.0))
    assert result.returns.abs().sum() == 0.0


def test_cash_yield_accrues_only_while_flat(straight_line):
    index = next(iter(straight_line.values())).index
    flat = pd.DataFrame({"A": 0.0}, index=index)
    cfg = BacktestConfig(cash_yield=0.0252, periods_per_year=252)
    result = run_backtest(straight_line, flat, cfg)
    assert result.returns.iloc[-1] == pytest.approx(0.0001, rel=1e-9)


def test_gross_exposure_is_capped(straight_line):
    index = next(iter(straight_line.values())).index
    greedy = pd.DataFrame({"A": 5.0}, index=index)
    cfg = BacktestConfig(max_leverage=1.5, commission_bps=0, slippage_bps=0)
    result = run_backtest(straight_line, greedy, cfg)
    assert result.gross_exposure.max() == pytest.approx(1.5, rel=1e-9)


def test_short_position_profits_when_price_falls():
    index = pd.bdate_range("2024-01-01", periods=50)
    close = 100.0 * (0.99 ** np.arange(50))
    prices = {"A": pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1e6}, index=index)}
    weights = pd.DataFrame({"A": -1.0}, index=index)
    result = run_backtest(prices, weights, BacktestConfig(commission_bps=0, slippage_bps=0))
    assert result.performance.total_return > 0


def test_weights_for_an_unpriced_symbol_are_rejected(straight_line):
    index = next(iter(straight_line.values())).index
    weights = pd.DataFrame({"B": 1.0}, index=index)
    with pytest.raises(ValueError, match="no prices"):
        run_backtest(straight_line, weights)


def test_rebalance_threshold_reduces_turnover(panel):
    index = next(iter(panel.values())).index
    rng = np.random.default_rng(3)
    jittery = pd.DataFrame(
        rng.normal(0.1, 0.01, size=(len(index), len(panel))), index=index, columns=list(panel)
    )
    loose = run_backtest(panel, jittery, BacktestConfig(rebalance_threshold=0.05))
    tight = run_backtest(panel, jittery, BacktestConfig(rebalance_threshold=0.0))
    assert loose.performance.annual_turnover < tight.performance.annual_turnover


def test_volatility_target_moves_toward_the_target(panel):
    closes = pd.DataFrame({s: df["close"] for s, df in panel.items()})
    weights = pd.DataFrame(1.0 / len(panel), index=closes.index, columns=closes.columns)
    scaled = volatility_target(weights, closes, target_vol=0.10, window=20)
    plain_vol = (weights * closes.pct_change(fill_method=None)).sum(axis=1).std() * np.sqrt(252)
    scaled_vol = (scaled * closes.pct_change(fill_method=None)).sum(axis=1).std() * np.sqrt(252)
    assert abs(scaled_vol - 0.10) < abs(plain_vol - 0.10)


def test_volatility_target_does_not_look_ahead(panel):
    closes = pd.DataFrame({s: df["close"] for s, df in panel.items()})
    weights = pd.DataFrame(1.0 / len(panel), index=closes.index, columns=closes.columns)
    full = volatility_target(weights, closes, 0.10, 20)
    cut = volatility_target(weights.iloc[:-40], closes.iloc[:-40], 0.10, 20)
    pd.testing.assert_frame_equal(full.iloc[20:len(cut)], cut.iloc[20:], rtol=1e-9)


def test_trailing_stop_flattens_a_losing_long():
    index = pd.bdate_range("2024-01-01", periods=60)
    close = pd.Series(np.concatenate([np.full(30, 100.0), np.linspace(100.0, 60.0, 30)]), index=index)
    atr = pd.Series(1.0, index=index)
    weights = pd.Series(1.0, index=index)
    stopped = apply_trailing_stop(weights, close, close, close, atr, multiple=3.0)
    assert stopped.iloc[-1] == 0.0
    assert stopped.iloc[10] == 1.0


def test_buy_and_hold_holds_one_symbol(panel):
    result = buy_and_hold_result(panel, "SPY")
    assert result.positions["SPY"].iloc[-1] == pytest.approx(1.0)
    assert result.positions.drop(columns=["SPY"]).abs().to_numpy().sum() == 0.0


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def test_cagr_on_a_known_doubling():
    returns = pd.Series([0.0] * 252)
    returns.iloc[0] = 1.0  # double on day one, flat afterwards
    assert M.cagr(returns, 252) == pytest.approx(1.0, rel=1e-6)


def test_sharpe_is_zero_for_a_flat_series():
    assert np.isnan(M.sharpe_ratio(pd.Series([0.0] * 100), 252, risk_free=0.0))


def test_max_drawdown_matches_a_hand_computed_fall():
    returns = pd.Series([0.5, -0.5, 0.0])   # 1 -> 1.5 -> 0.75
    assert M.max_drawdown(returns) == pytest.approx(-0.5, rel=1e-9)


def test_drawdown_is_never_positive(panel):
    result = buy_and_hold_result(panel, "SPY")
    assert (result.drawdown.dropna() <= 1e-12).all()


def test_sortino_exceeds_sharpe_when_downside_is_small():
    rng = np.random.default_rng(1)
    returns = pd.Series(np.abs(rng.normal(0.001, 0.005, 500)))  # almost no losing bars
    assert M.sortino_ratio(returns) > M.sharpe_ratio(returns)


def test_profit_factor_of_a_series_with_no_losses_is_infinite():
    assert M.profit_factor(pd.Series([0.01, 0.02, 0.03])) == float("inf")


def test_value_at_risk_is_below_conditional_var():
    rng = np.random.default_rng(5)
    returns = pd.Series(rng.normal(0, 0.01, 2000))
    assert M.conditional_var(returns) < M.value_at_risk(returns)


def test_calendar_year_returns_compound_within_each_year():
    index = pd.bdate_range("2023-01-02", "2024-12-31")
    returns = pd.Series(0.001, index=index)
    yearly = M.calendar_year_returns(returns)
    assert set(yearly.index) == {2023, 2024}
    assert (yearly > 0).all()


def test_summarise_survives_an_empty_series():
    perf = M.summarise(pd.Series(dtype=float))
    assert perf.bars == 0
    assert np.isnan(perf.cagr)


def test_comparison_table_has_a_row_per_strategy(panel):
    results = {
        "hold": buy_and_hold_result(panel, "SPY").performance,
        "hold_qqq": buy_and_hold_result(panel, "QQQ").performance,
    }
    table = M.comparison_table(results)
    assert list(table.index) == ["hold", "hold_qqq"]
    assert "sharpe" in table.columns

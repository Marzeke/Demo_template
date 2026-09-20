"""Every registered strategy must behave itself, and none may look ahead."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import BacktestConfig, run_backtest
from src.strategies import HEADLINE, available, get_strategy, strategy_class
from src.strategies.base import ParamSpec, Strategy, register

DAILY = [k for k in available() if "1d" in strategy_class(k).intervals]


@pytest.mark.parametrize("key", DAILY)
def test_weights_are_well_formed(key, panel):
    weights = get_strategy(key).generate_weights(panel)
    assert list(weights.columns) == list(panel)
    assert weights.index.equals(next(iter(panel.values())).index)
    assert np.isfinite(weights.to_numpy()).all(), f"{key} produced NaN or infinite weights"


@pytest.mark.parametrize("key", DAILY)
def test_gross_exposure_stays_within_its_declared_cap(key, panel):
    strategy = get_strategy(key)
    weights = strategy.generate_weights(panel)
    cap = strategy.params.get("gross", 1.0)
    assert weights.abs().sum(axis=1).max() <= cap + 1e-9, f"{key} exceeded its gross cap"


@pytest.mark.parametrize("key", DAILY)
def test_strategy_does_not_look_ahead(key, panel):
    """Removing the last year must not change any earlier weight.

    A strategy that fails this is reading the future. The warm-up head of the
    series is skipped because a shorter history legitimately warms up later.
    """
    full = get_strategy(key).generate_weights(panel)
    short_panel = {s: df.iloc[:-250] for s, df in panel.items()}
    truncated = get_strategy(key).generate_weights(short_panel)
    overlap = truncated.index
    pd.testing.assert_frame_equal(
        full.loc[overlap].iloc[300:], truncated.iloc[300:], rtol=1e-8, check_freq=False
    )


@pytest.mark.parametrize("key", DAILY)
def test_backtest_runs_and_produces_finite_statistics(key, panel):
    strategy = get_strategy(key)
    result = run_backtest(panel, strategy.generate_weights(panel), BacktestConfig(), name=key)
    assert len(result.returns) == len(next(iter(panel.values())))
    assert np.isfinite(result.performance.total_return)
    assert result.equity.iloc[-1] > 0, f"{key} drove equity to zero or below"


@pytest.mark.parametrize("key", DAILY)
def test_chart_frames_align_with_the_price_index(key, panel):
    strategy = get_strategy(key)
    chart = strategy.chart("SPY", panel["SPY"])
    if not chart.price_overlays.empty:
        assert chart.price_overlays.index.equals(panel["SPY"].index)
    for title, frame in chart.panels.items():
        assert frame.index.equals(panel["SPY"].index), f"{key}: panel {title} is misaligned"


def test_headline_strategies_are_registered():
    for key in HEADLINE:
        assert key in available()


def test_unknown_strategy_key_is_rejected():
    with pytest.raises(ValueError, match="unknown strategy"):
        get_strategy("not_a_strategy")


def test_unknown_parameter_is_rejected():
    with pytest.raises(ValueError, match="unknown parameters"):
        get_strategy("mean_reversion", not_a_param=3)


def test_parameters_are_clamped_to_their_range():
    strategy = get_strategy("mean_reversion", rsi_window=9999)
    spec = {p.name: p for p in strategy.PARAMS}["rsi_window"]
    assert strategy.params["rsi_window"] == spec.maximum


def test_choice_parameter_rejects_an_unlisted_value():
    with pytest.raises(ValueError, match="not in"):
        get_strategy("trend_vol_target", signal="telepathy")


def test_bool_parameter_accepts_a_string():
    assert get_strategy("mean_reversion", regime_filter="false").params["regime_filter"] is False


def test_absolute_momentum_filter_forces_cash_in_a_falling_universe():
    """When nothing has positive momentum, dual momentum must hold nothing."""
    index = pd.bdate_range("2020-01-01", periods=400)
    falling = 100.0 * (0.998 ** np.arange(400))
    prices = {
        name: pd.DataFrame(
            {"open": falling, "high": falling, "low": falling, "close": falling, "volume": 1e6},
            index=index,
        )
        for name in ("A", "B", "C")
    }
    weights = get_strategy("momentum_rotation", absolute_filter=True).generate_weights(prices)
    assert weights.abs().to_numpy().sum() == 0.0


def test_without_the_filter_momentum_still_holds_the_best_loser():
    index = pd.bdate_range("2020-01-01", periods=400)
    prices = {}
    for name, decay in (("A", 0.998), ("B", 0.999)):
        series = 100.0 * (decay ** np.arange(400))
        prices[name] = pd.DataFrame(
            {"open": series, "high": series, "low": series, "close": series, "volume": 1e6},
            index=index,
        )
    weights = get_strategy(
        "momentum_rotation", absolute_filter=False, top_n=1
    ).generate_weights(prices)
    assert weights.abs().to_numpy().sum() > 0
    assert weights["B"].abs().sum() > weights["A"].abs().sum()  # B fell less


def test_mean_reversion_regime_filter_blocks_buys_below_the_average():
    index = pd.bdate_range("2020-01-01", periods=400)
    falling = 100.0 * (0.995 ** np.arange(400))
    prices = {"A": pd.DataFrame(
        {"open": falling, "high": falling, "low": falling, "close": falling, "volume": 1e6},
        index=index)}
    filtered = get_strategy("mean_reversion", regime_filter=True).generate_weights(prices)
    unfiltered = get_strategy("mean_reversion", regime_filter=False).generate_weights(prices)
    assert filtered.abs().to_numpy().sum() == 0.0
    assert unfiltered.abs().to_numpy().sum() > 0.0


def test_mean_reversion_respects_its_holding_limit():
    index = pd.bdate_range("2020-01-01", periods=300)
    rng = np.random.default_rng(11)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 300))), index=index)
    prices = {"A": pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1e6}, index=index)}
    weights = get_strategy(
        "mean_reversion", max_hold=3, regime_filter=False, exit_level=99.0
    ).generate_weights(prices)
    held = (weights["A"].abs() > 1e-9).astype(int)
    runs, current = [], 0
    for flag in held:
        current = current + 1 if flag else 0
        runs.append(current)
    assert max(runs) <= 3


def test_trend_following_shorts_only_when_allowed(panel):
    long_only = get_strategy("trend_vol_target", allow_short=False).generate_weights(panel)
    assert (long_only.to_numpy() >= -1e-12).all()
    both_ways = get_strategy("trend_vol_target", allow_short=True).generate_weights(panel)
    assert (both_ways.to_numpy() < -1e-9).any()


def test_portfolio_volatility_targeting_lands_near_its_target(panel):
    strategy = get_strategy("trend_vol_target", sizing="portfolio_vol",
                            target_volatility=0.10, gross=3.0, max_position=3.0)
    result = run_backtest(panel, strategy.generate_weights(panel), BacktestConfig(max_leverage=3.0))
    assert 0.04 < result.performance.annual_volatility < 0.20


def test_ensemble_shares_must_not_all_be_zero(panel):
    strategy = get_strategy("ensemble", momentum_weight=0.0, trend_weight=0.0, reversion_weight=0.0)
    with pytest.raises(ValueError, match="sum to zero"):
        strategy.generate_weights(panel)


def test_ensemble_sits_between_its_components(panel):
    """A blend cannot be more volatile than the most volatile thing in it."""
    blend = get_strategy("ensemble", target_volatility=0.0)
    parts = {name: run_backtest(panel, s.generate_weights(panel), name=name).performance
             for name, s in blend.components.items()}
    combined = run_backtest(panel, blend.generate_weights(panel), name="ensemble").performance
    worst = max(p.annual_volatility for p in parts.values())
    assert combined.annual_volatility <= worst + 1e-9


def test_opening_range_refuses_daily_bars(panel):
    with pytest.raises(ValueError, match="intraday"):
        get_strategy("opening_range_breakout").generate_weights(panel)


def test_opening_range_runs_on_intraday_bars(intraday_panel):
    weights = get_strategy("opening_range_breakout", min_range_atr=0.0).generate_weights(intraday_panel)
    assert weights.abs().to_numpy().sum() > 0


def test_opening_range_is_flat_at_the_end_of_every_session(intraday_panel):
    weights = get_strategy(
        "opening_range_breakout", min_range_atr=0.0, close_at_session_end=True
    ).generate_weights(intraday_panel)
    last_bars = weights.groupby(weights.index.normalize()).tail(1)
    assert last_bars.abs().to_numpy().sum() == 0.0


def test_registry_rejects_a_duplicate_key():
    class Duplicate(Strategy):
        key = "mean_reversion"
        PARAMS = (ParamSpec("x", "X", "int", 1),)

        def generate_weights(self, prices):
            return self._empty_weights(next(iter(prices.values())).index, prices)

    with pytest.raises(ValueError, match="already registered"):
        register(Duplicate)

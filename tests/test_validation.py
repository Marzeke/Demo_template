"""Sweeps, walk-forward, bootstrap, signals, reporting and the command line."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import BacktestConfig
from src.backtest.walkforward import (
    bootstrap_confidence, expand_grid, parameter_sweep, walk_forward,
)
from src.modeling.predict import compare_strategies, signal_table, summarise_book
from src.modeling.train import DEFAULT_GRIDS, fit_strategy, load_report, save_report
from src.strategies import available, get_strategy

GRID = {"lookback": [63, 126], "top_n": [1, 2]}


def test_expand_grid_covers_every_combination():
    assert len(expand_grid(GRID)) == 4
    assert expand_grid({}) == [{}]


def test_sweep_returns_a_row_per_combination(panel):
    frame = parameter_sweep("momentum_rotation", panel, GRID)
    assert len(frame) == 4
    assert {"lookback", "top_n", "sharpe", "cagr"} <= set(frame.columns)


def test_sweep_is_sorted_best_first(panel):
    frame = parameter_sweep("momentum_rotation", panel, GRID)
    assert frame["objective"].is_monotonic_decreasing


def test_sweep_rejects_an_unknown_objective(panel):
    with pytest.raises(ValueError, match="unknown objective"):
        parameter_sweep("momentum_rotation", panel, GRID, objective="vibes")


def test_walk_forward_is_strictly_out_of_sample(panel):
    """Every stitched bar must come from a segment after its training window."""
    result = walk_forward("momentum_rotation", panel, GRID, train_bars=400, test_bars=120)
    assert len(result.folds) >= 2
    index = next(iter(panel.values())).index
    for _, fold in result.folds.iterrows():
        assert fold["test_start"] > fold["train_end"]
    assert result.returns.index.min() >= index[400]


def test_walk_forward_segments_do_not_overlap(panel):
    result = walk_forward("momentum_rotation", panel, GRID, train_bars=400, test_bars=120)
    assert result.returns.index.is_monotonic_increasing
    assert not result.returns.index.duplicated().any()


def test_walk_forward_needs_enough_history(panel):
    tiny = {s: df.iloc[:50] for s, df in panel.items()}
    with pytest.raises(ValueError, match="need at least"):
        walk_forward("momentum_rotation", tiny, GRID, train_bars=400, test_bars=120)


def test_walk_forward_reports_degradation(panel):
    result = walk_forward("momentum_rotation", panel, GRID, train_bars=400, test_bars=120)
    assert np.isfinite(result.degradation())


def test_bootstrap_brackets_the_observed_value():
    rng = np.random.default_rng(4)
    returns = pd.Series(rng.normal(0.0004, 0.01, 1500))
    frame = bootstrap_confidence(returns, n_samples=200, block=21)
    assert set(frame.index) == {"cagr", "sharpe", "max_drawdown", "total_return"}
    assert (frame["lower"] <= frame["upper"]).all()
    assert frame.loc["sharpe", "lower"] < frame.loc["sharpe", "median"] < frame.loc["sharpe", "upper"]


def test_bootstrap_needs_a_workable_sample():
    with pytest.raises(ValueError, match="at least"):
        bootstrap_confidence(pd.Series([0.01] * 10), block=21)


def test_block_bootstrap_tracks_the_observed_drawdown_better_than_a_naive_one():
    """Sampling single bars destroys volatility clustering.

    The series below alternates long calm and long violent stretches. Resampling
    it one bar at a time shuffles those regimes together, so the resampled paths
    stop resembling the original and their drawdowns drift away from what was
    observed. Block sampling keeps the runs intact and stays closer.
    """
    rng = np.random.default_rng(9)
    n = 3000
    regime = (np.arange(n) // 250) % 2          # 250-bar calm / violent blocks
    vol = np.where(regime == 0, 0.002, 0.03)
    returns = pd.Series(rng.normal(0.0, 1.0, n) * vol)

    blocked = bootstrap_confidence(returns, n_samples=400, block=125)
    naive = bootstrap_confidence(returns, n_samples=400, block=1)
    observed = blocked.loc["max_drawdown", "observed"]
    assert abs(blocked.loc["max_drawdown", "median"] - observed) < \
        abs(naive.loc["max_drawdown", "median"] - observed)


def test_bootstrap_interval_contains_its_own_median():
    rng = np.random.default_rng(12)
    returns = pd.Series(rng.normal(0.0003, 0.008, 1200))
    frame = bootstrap_confidence(returns, n_samples=200, block=21)
    assert (frame["lower"] <= frame["median"]).all()
    assert (frame["median"] <= frame["upper"]).all()


def test_every_default_grid_names_real_parameters():
    for key, grid in DEFAULT_GRIDS.items():
        assert key in available(), f"{key} has a grid but is not registered"
        names = {spec.name for spec in get_strategy(key).PARAMS}
        assert set(grid) <= names, f"{key}: grid names {set(grid) - names} do not exist"


def test_fit_report_round_trips(panel, tmp_path):
    report, sweep = fit_strategy(
        "momentum_rotation", panel, GRID, train_bars=400, test_bars=120, bootstrap_samples=60
    )
    assert report.strategy == "momentum_rotation"
    assert len(sweep) == 4
    assert isinstance(report.trustworthy, bool)
    save_report(report, tmp_path)
    assert load_report("momentum_rotation", tmp_path).best_params == report.best_params


def test_load_report_returns_none_when_absent(tmp_path):
    assert load_report("momentum_rotation", tmp_path) is None


# --------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------

def test_signal_table_covers_every_symbol(panel):
    table = signal_table(get_strategy("momentum_rotation"), panel, capital=100_000)
    assert set(table.index) == set(panel)
    assert {"target_weight", "action", "notional", "units"} <= set(table.columns)


def test_signal_actions_follow_the_change_column(panel):
    table = signal_table(get_strategy("momentum_rotation"), panel)
    for _, row in table.iterrows():
        if row["change"] > 1e-6:
            assert row["action"] == "buy"
        elif row["change"] < -1e-6:
            assert row["action"] == "sell"
        else:
            assert row["action"] == "hold"


def test_signal_table_accounts_for_an_existing_book(panel):
    strategy = get_strategy("momentum_rotation")
    targets = signal_table(strategy, panel)["target_weight"].to_dict()
    table = signal_table(strategy, panel, current_weights=targets)
    assert (table["action"] == "hold").all()


def test_summarise_book_reports_exposure(panel):
    book = summarise_book(signal_table(get_strategy("momentum_rotation"), panel))
    assert book["gross_exposure"] >= abs(book["net_exposure"]) - 1e-9


def test_compare_strategies_counts_agreement(panel):
    frame = compare_strategies(["momentum_rotation", "trend_vol_target"], panel)
    assert "agreement" in frame.columns
    assert frame["agreement"].max() <= 2


# --------------------------------------------------------------------------
# Report and CLI
# --------------------------------------------------------------------------

def test_report_writes_a_self_contained_page(tmp_path):
    from src.report import build_report

    path = build_report(
        symbols=["SPY", "QQQ", "TLT"], strategy_keys=["momentum_rotation", "mean_reversion"],
        start="2020-01-01", end="2023-12-31", provider="synthetic", allow_synthetic=True,
        output=tmp_path / "report.html", embed_plotly=False,
    )
    html = path.read_text()
    assert "<html" in html
    assert "simulated" in html.lower(), "a report built on simulated bars must say so"


def test_report_flags_simulated_data_prominently(tmp_path):
    from src.report import build_report

    path = build_report(
        symbols=["SPY"], strategy_keys=["mean_reversion"],
        start="2020-01-01", end="2023-12-31", provider="synthetic", allow_synthetic=True,
        output=tmp_path / "r.html", embed_plotly=False,
    )
    assert "partly fiction" in path.read_text()


@pytest.mark.parametrize("argv", [
    ["strategies"],
    ["strategies", "-v"],
    ["markets"],
])
def test_cli_informational_commands_exit_cleanly(argv, capsys):
    from src.cli import main

    assert main(argv) == 0
    assert capsys.readouterr().out.strip()


def test_cli_backtest_runs_on_simulated_data(capsys):
    from src.cli import main

    code = main([
        "backtest", "--symbols", "SPY", "QQQ", "TLT", "--provider", "synthetic",
        "--allow-synthetic", "--start", "2020-01-01", "--end", "2023-12-31",
        "--strategy", "momentum_rotation", "--strategy", "mean_reversion", "--no-cache",
    ])
    assert code == 0
    out = capsys.readouterr()
    assert "sharpe" in out.out
    assert "SIMULATED" in out.err


def test_cli_signals_runs(capsys):
    from src.cli import main

    code = main([
        "signals", "--symbols", "SPY", "QQQ", "TLT", "--provider", "synthetic",
        "--allow-synthetic", "--start", "2020-01-01", "--end", "2023-12-31",
        "--strategy", "momentum_rotation", "--no-cache",
    ])
    assert code == 0
    assert "Cross-sectional momentum rotation" in capsys.readouterr().out


def test_fractional_instruments_report_fractional_units(panel):
    """A book smaller than one bitcoin is still a position, not zero."""
    from src.modeling.predict import _units

    assert _units(43_000.0, 81_000.0, "crypto") == pytest.approx(0.530864, abs=1e-6)
    assert _units(43_000.0, 81_000.0, "equity_index") == 0.0
    assert _units(10_000.0, 100.0, "equity_index") == 100.0
    assert _units(500.0, 0.0, "crypto") == 0.0

"""Fit strategy parameters, and record how much of the fit survives out of sample.

"Training" here is a parameter search, not a learned model. The point of this
module is less to find good parameters than to measure how much trust the search
result deserves, which is what :func:`fit_strategy` reports alongside it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src import config
from src.backtest.engine import BacktestConfig
from src.backtest.walkforward import bootstrap_confidence, parameter_sweep, walk_forward

#: Sensible search grids per strategy. Deliberately coarse: a fine grid over a
#: short sample finds noise and calls it signal.
DEFAULT_GRIDS: dict[str, dict[str, list]] = {
    "momentum_rotation": {
        "lookback": [63, 126, 189, 252],
        "top_n": [1, 2, 3, 4],
        "rebalance": ["W", "M", "Q"],
    },
    "dual_momentum": {
        "lookback": [63, 126, 252],
        "rebalance": ["M", "Q"],
    },
    "trend_vol_target": {
        "signal": ["donchian", "ma_cross", "supertrend"],
        "entry_window": [20, 50, 100],
        "exit_window": [10, 25, 50],
    },
    "mean_reversion": {
        "rsi_window": [2, 3, 5],
        "entry_level": [5.0, 10.0, 20.0],
        "exit_level": [50.0, 60.0, 70.0],
    },
    "ensemble": {
        "momentum_weight": [0.2, 0.4, 0.6],
        "trend_weight": [0.2, 0.3, 0.4],
    },
    "ema_crossover": {
        "fast": [10, 20, 50],
        "slow": [50, 100, 200],
    },
}


@dataclass
class FitReport:
    """What a parameter search found, and how far to trust it."""

    strategy: str
    symbols: list[str]
    best_params: dict
    in_sample_sharpe: float
    out_of_sample_sharpe: float
    degradation: float
    sharpe_ci_low: float
    sharpe_ci_high: float
    folds: int
    combinations: int
    fitted_at: str

    @property
    def trustworthy(self) -> bool:
        """A rough, deliberately strict reading of whether the fit held up.

        It asks for a positive out-of-sample Sharpe, modest degradation, and a
        confidence interval whose lower bound is not negative. Most parameter
        searches fail this, which is the useful part.
        """
        return (
            self.out_of_sample_sharpe > 0
            and self.degradation < 0.5
            and self.sharpe_ci_low > 0
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["trustworthy"] = self.trustworthy
        return data


def fit_strategy(
    strategy_key: str,
    prices: dict[str, pd.DataFrame],
    grid: dict[str, list] | None = None,
    cfg: BacktestConfig | None = None,
    objective: str = "sharpe",
    train_bars: int = 504,
    test_bars: int = 126,
    bootstrap_samples: int = 500,
) -> tuple[FitReport, pd.DataFrame]:
    """Search ``grid``, validate it walk-forward, and report both.

    Returns the report and the full sweep table, so the parameter surface can be
    inspected rather than reduced to one winning row.
    """
    grid = grid or DEFAULT_GRIDS.get(strategy_key, {})
    cfg = cfg or BacktestConfig()

    sweep = parameter_sweep(strategy_key, prices, grid, cfg, objective)
    if "objective" not in sweep.columns or sweep.empty:
        raise ValueError(f"no usable results for {strategy_key}; check the grid")
    best = {k: v for k, v in sweep.iloc[0].items() if k in grid}

    wf = walk_forward(strategy_key, prices, grid, train_bars, test_bars, cfg, objective)
    try:
        ci = bootstrap_confidence(wf.returns, n_samples=bootstrap_samples)
        low, high = float(ci.loc["sharpe", "lower"]), float(ci.loc["sharpe", "upper"])
    except ValueError:
        low = high = float("nan")

    report = FitReport(
        strategy=strategy_key,
        symbols=sorted(prices),
        best_params=best,
        in_sample_sharpe=float(sweep.iloc[0]["sharpe"]),
        out_of_sample_sharpe=float(wf.performance.sharpe),
        degradation=float(wf.degradation()),
        sharpe_ci_low=low,
        sharpe_ci_high=high,
        folds=len(wf.folds),
        combinations=len(sweep),
        fitted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return report, sweep


def save_report(report: FitReport, directory: Path | None = None) -> Path:
    """Write a fit report to ``models/`` as JSON."""
    directory = directory or config.MODELS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"fit_{report.strategy}.json"
    path.write_text(json.dumps(report.to_dict(), indent=2))
    return path


def load_report(strategy_key: str, directory: Path | None = None) -> FitReport | None:
    """Read back a saved fit report, or ``None`` if there is none."""
    directory = directory or config.MODELS_DIR
    path = directory / f"fit_{strategy_key}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    data.pop("trustworthy", None)
    return FitReport(**data)

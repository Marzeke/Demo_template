"""Out-of-sample validation: sweeps, walk-forward, and bootstrap intervals.

A single backtest over a single window is the weakest evidence a strategy can
produce, and it is the evidence most tools stop at. The tools here exist to make
the weakness visible:

* :func:`parameter_sweep` shows the whole parameter surface, so you can see
  whether a good result is a plateau or a spike. A spike is a fitting artefact.
* :func:`walk_forward` re-picks parameters on past data only and trades them
  forward, then stitches the untouched segments into one honest equity curve.
* :func:`bootstrap_confidence` resamples in blocks to put an interval around a
  headline number, so a Sharpe of 0.8 can be read as "0.3 to 1.3" rather than
  as a fact. Blocks, not single bars, so volatility clustering survives.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.backtest.engine import BacktestConfig, BacktestResult, run_backtest
from src.backtest.metrics import summarise
from src.strategies.base import get_strategy

#: Statistics a sweep can rank on. All are "higher is better".
OBJECTIVES = ("sharpe", "sortino", "calmar", "cagr", "total_return", "profit_factor")


def _score(result: BacktestResult, objective: str) -> float:
    if objective not in OBJECTIVES:
        raise ValueError(f"unknown objective {objective!r}; expected one of {OBJECTIVES}")
    value = getattr(result.performance, objective)
    return float(value) if np.isfinite(value) else float("-inf")


def expand_grid(grid: dict[str, list]) -> list[dict]:
    """Every combination of the parameter lists in ``grid``."""
    if not grid:
        return [{}]
    names = list(grid)
    return [dict(zip(names, values)) for values in itertools.product(*(grid[n] for n in names))]


def parameter_sweep(
    strategy_key: str,
    prices: dict[str, pd.DataFrame],
    grid: dict[str, list],
    cfg: BacktestConfig | None = None,
    objective: str = "sharpe",
    subset: slice | None = None,
) -> pd.DataFrame:
    """Backtest every combination in ``grid`` and return one row per combination.

    The result is sorted best-first on ``objective``, but read the spread rather
    than the top row: a parameter set that only works at one exact setting is
    telling you about the sample, not about the market.
    """
    cfg = cfg or BacktestConfig()
    window = {s: (df.iloc[subset] if subset else df) for s, df in prices.items()}

    rows = []
    for params in expand_grid(grid):
        try:
            strategy = get_strategy(strategy_key, **params)
            weights = strategy.generate_weights(window)
            result = run_backtest(window, weights, cfg, name=strategy_key)
        except (ValueError, KeyError) as exc:
            rows.append({**params, "error": str(exc)})
            continue
        stats = result.performance.to_dict()
        rows.append({**params, **stats, "objective": _score(result, objective)})

    frame = pd.DataFrame(rows)
    if "objective" in frame.columns:
        frame = frame.sort_values("objective", ascending=False)
    return frame.reset_index(drop=True)


@dataclass
class WalkForwardResult:
    """The stitched out-of-sample record, plus what happened in each fold."""

    returns: pd.Series
    folds: pd.DataFrame
    chosen: list[dict] = field(default_factory=list)
    in_sample: pd.Series | None = None

    @property
    def performance(self):
        return summarise(self.returns)

    def degradation(self) -> float:
        """In-sample Sharpe minus out-of-sample Sharpe.

        A large positive number is the signature of over-fitting: the parameters
        looked good on the data that chose them and not afterwards.
        """
        if self.in_sample is None or len(self.in_sample) == 0:
            return float("nan")
        return float(summarise(self.in_sample).sharpe - self.performance.sharpe)


def walk_forward(
    strategy_key: str,
    prices: dict[str, pd.DataFrame],
    grid: dict[str, list],
    train_bars: int = 504,
    test_bars: int = 126,
    cfg: BacktestConfig | None = None,
    objective: str = "sharpe",
    anchored: bool = False,
) -> WalkForwardResult:
    """Re-fit on a rolling training window, then trade the next segment untouched.

    ``anchored`` keeps the training window's start fixed and lets it grow, which
    is the right choice when you believe older data still applies.
    """
    cfg = cfg or BacktestConfig()
    index = next(iter(prices.values())).index
    total = len(index)
    if total < train_bars + test_bars:
        raise ValueError(
            f"need at least {train_bars + test_bars} bars for this split; got {total}"
        )

    oos_parts: list[pd.Series] = []
    is_parts: list[pd.Series] = []
    chosen: list[dict] = []
    rows = []

    start = 0
    while start + train_bars + test_bars <= total:
        train_slice = slice(0 if anchored else start, start + train_bars)
        test_slice = slice(start + train_bars, start + train_bars + test_bars)

        sweep = parameter_sweep(strategy_key, prices, grid, cfg, objective, subset=train_slice)
        valid = sweep[sweep.get("objective", pd.Series(dtype=float)).notna()] if len(sweep) else sweep
        if len(valid) == 0:
            start += test_bars
            continue
        best = {k: v for k, v in valid.iloc[0].items() if k in grid}

        # The test segment needs the training bars in front of it so indicators
        # are warm on its first bar. Only the test segment's returns are kept.
        warm = slice(max(0, test_slice.start - train_bars), test_slice.stop)
        window = {s: df.iloc[warm] for s, df in prices.items()}
        strategy = get_strategy(strategy_key, **best)
        result = run_backtest(window, strategy.generate_weights(window), cfg, name=strategy_key)

        test_index = index[test_slice]
        oos = result.returns.reindex(test_index).dropna()
        oos_parts.append(oos)
        chosen.append(best)

        train_window = {s: df.iloc[train_slice] for s, df in prices.items()}
        train_result = run_backtest(
            train_window, get_strategy(strategy_key, **best).generate_weights(train_window),
            cfg, name=strategy_key,
        )
        is_parts.append(train_result.returns)

        rows.append(
            {
                "train_start": index[train_slice.start].date(),
                "train_end": index[train_slice.stop - 1].date(),
                "test_start": test_index[0].date(),
                "test_end": test_index[-1].date(),
                **best,
                "in_sample_sharpe": train_result.performance.sharpe,
                "out_of_sample_sharpe": summarise(oos).sharpe,
                "out_of_sample_return": summarise(oos).total_return,
            }
        )
        start += test_bars

    if not oos_parts:
        raise ValueError("walk-forward produced no out-of-sample segments")

    stitched = pd.concat(oos_parts).sort_index()
    stitched = stitched[~stitched.index.duplicated(keep="first")]
    stitched.name = f"{strategy_key} (out of sample)"
    return WalkForwardResult(
        returns=stitched,
        folds=pd.DataFrame(rows),
        chosen=chosen,
        in_sample=pd.concat(is_parts) if is_parts else None,
    )


def bootstrap_confidence(
    returns: pd.Series,
    n_samples: int = 1000,
    block: int = 21,
    periods_per_year: int = 252,
    level: float = 0.90,
    seed: int = 7,
) -> pd.DataFrame:
    """Block-bootstrap interval around the headline statistics.

    Blocks rather than single bars, because returns cluster. Sampling one bar at
    a time shuffles calm and violent stretches together, so the resampled paths
    no longer resemble the series they came from and the drawdown estimates drift
    away from it. Block sampling keeps runs of similar volatility intact.

    The interval is a description of sampling variability in *this* history. It
    is not a confidence interval for future performance, and no resampling of a
    single sample can be.
    """
    r = returns.dropna().to_numpy()
    if len(r) < block * 3:
        raise ValueError(f"need at least {block * 3} returns to bootstrap; got {len(r)}")

    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(len(r) / block))
    starts_max = len(r) - block

    records = []
    for _ in range(n_samples):
        starts = rng.integers(0, starts_max + 1, size=n_blocks)
        sample = np.concatenate([r[s:s + block] for s in starts])[: len(r)]
        series = pd.Series(sample)
        perf = summarise(series, periods_per_year)
        records.append({"cagr": perf.cagr, "sharpe": perf.sharpe,
                        "max_drawdown": perf.max_drawdown, "total_return": perf.total_return})

    draws = pd.DataFrame(records)
    lower, upper = (1 - level) / 2, 1 - (1 - level) / 2
    observed = summarise(returns.dropna(), periods_per_year)
    return pd.DataFrame(
        {
            "observed": [observed.cagr, observed.sharpe, observed.max_drawdown, observed.total_return],
            "lower": draws.quantile(lower).to_numpy(),
            "median": draws.median().to_numpy(),
            "upper": draws.quantile(upper).to_numpy(),
        },
        index=["cagr", "sharpe", "max_drawdown", "total_return"],
    )

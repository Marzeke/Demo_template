"""Vectorised portfolio backtester.

The contract is deliberately narrow. A strategy produces a frame of **target
weights** - one column per symbol, one row per bar, where ``0.5`` means half of
equity long and ``-0.25`` means a quarter short. The engine turns those weights
into a net return stream, charging costs on every weight change.

Timing
------
A weight on row ``t`` is a decision made using information up to the close of
bar ``t``. The engine lags it by ``execution_lag`` bars before applying any
return, so the default of 1 means "decide at today's close, hold through
tomorrow". Nothing here models an intrabar fill; a stop is evaluated on closes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src import config
from src.backtest.metrics import Performance, equity_curve, summarise


@dataclass(frozen=True)
class BacktestConfig:
    """Everything the engine needs beyond prices and weights."""

    initial_capital: float = config.INITIAL_CAPITAL
    commission_bps: float = config.COMMISSION_BPS
    slippage_bps: float = config.SLIPPAGE_BPS
    cash_yield: float = config.CASH_YIELD
    max_leverage: float = config.MAX_LEVERAGE
    periods_per_year: int = 252
    execution_lag: int = 1
    #: Rebalance only when a symbol's target moves at least this much. Keeps
    #: turnover honest for strategies that jitter around a target.
    rebalance_threshold: float = 0.0
    risk_free_rate: float | None = None

    @property
    def cost_rate(self) -> float:
        """Cost charged per unit of traded notional, as a fraction."""
        return (self.commission_bps + self.slippage_bps) / 10_000.0


@dataclass
class BacktestResult:
    """What a backtest produced, from headline numbers down to per-bar detail."""

    name: str
    returns: pd.Series
    gross_returns: pd.Series
    equity: pd.Series
    positions: pd.DataFrame
    turnover: pd.Series
    costs: pd.Series
    performance: Performance
    asset_returns: pd.DataFrame = field(default_factory=pd.DataFrame)
    metadata: dict = field(default_factory=dict)

    @property
    def drawdown(self) -> pd.Series:
        peak = self.equity.cummax()
        return self.equity / peak.replace(0.0, np.nan) - 1.0

    @property
    def gross_exposure(self) -> pd.Series:
        return self.positions.abs().sum(axis=1)

    @property
    def net_exposure(self) -> pd.Series:
        return self.positions.sum(axis=1)

    def summary_row(self) -> pd.Series:
        row = self.performance.to_series()
        row.name = self.name
        return row


def _as_panel(prices) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Normalise prices into a close panel plus the per-symbol OHLCV frames."""
    if isinstance(prices, pd.DataFrame) and "close" in prices.columns:
        frames = {"asset": prices}
    elif isinstance(prices, dict):
        frames = dict(prices)
    else:
        raise TypeError("prices must be an OHLCV DataFrame or a dict of them")
    if not frames:
        raise ValueError("no price frames supplied")
    closes = pd.DataFrame({sym: df["close"] for sym, df in frames.items()})
    return closes.sort_index(), frames


def _apply_threshold(weights: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Hold the previous weight until the target moves by more than ``threshold``."""
    if threshold <= 0:
        return weights
    held = weights.to_numpy(copy=True)
    for i in range(1, len(held)):
        prev, target = held[i - 1], held[i]
        keep = np.abs(target - prev) < threshold
        held[i] = np.where(keep, prev, target)
    return pd.DataFrame(held, index=weights.index, columns=weights.columns)


def run_backtest(
    prices,
    weights: pd.DataFrame | pd.Series,
    cfg: BacktestConfig | None = None,
    name: str = "strategy",
    metadata: dict | None = None,
) -> BacktestResult:
    """Run ``weights`` against ``prices`` and return the full result.

    ``prices`` is either one OHLCV frame or a ``{symbol: frame}`` mapping.
    ``weights`` is a frame of target weights (or a series, for a single asset).
    """
    cfg = cfg or BacktestConfig()
    closes, _frames = _as_panel(prices)

    if isinstance(weights, pd.Series):
        weights = weights.to_frame(closes.columns[0] if len(closes.columns) == 1 else "asset")

    missing = [c for c in weights.columns if c not in closes.columns]
    if missing:
        raise ValueError(f"weights reference symbols with no prices: {missing}")

    # Align to the price calendar; an absent weight is no position.
    weights = weights.reindex(index=closes.index, columns=closes.columns).fillna(0.0)
    weights = _apply_threshold(weights, cfg.rebalance_threshold)

    # Cap gross exposure without changing the mix between symbols.
    gross = weights.abs().sum(axis=1)
    scale = np.minimum(1.0, cfg.max_leverage / gross.replace(0.0, np.nan))
    weights = weights.mul(scale.fillna(1.0), axis=0)

    asset_returns = closes.pct_change(fill_method=None)
    # A symbol with no quote on a bar contributes nothing rather than a NaN.
    asset_returns = asset_returns.where(closes.notna() & closes.shift(1).notna(), 0.0)

    positions = weights.shift(cfg.execution_lag).fillna(0.0)

    gross_returns = (positions * asset_returns).sum(axis=1)

    traded = (positions - positions.shift(1).fillna(0.0)).abs()
    turnover = traded.sum(axis=1)
    costs = turnover * cfg.cost_rate

    idle = (1.0 - positions.abs().sum(axis=1)).clip(lower=0.0)
    cash_return = idle * (cfg.cash_yield / cfg.periods_per_year)

    net_returns = gross_returns - costs + cash_return
    net_returns.name = name

    equity = equity_curve(net_returns, cfg.initial_capital)
    years = max(len(net_returns) / cfg.periods_per_year, 1e-9)

    perf = summarise(
        net_returns,
        periods_per_year=cfg.periods_per_year,
        exposure=float(positions.abs().sum(axis=1).mean()),
        annual_turnover=float(turnover.sum() / years),
        risk_free=cfg.risk_free_rate,
    )

    return BacktestResult(
        name=name,
        returns=net_returns,
        gross_returns=gross_returns,
        equity=equity,
        positions=positions,
        turnover=turnover,
        costs=costs,
        performance=perf,
        asset_returns=asset_returns,
        metadata=metadata or {},
    )


# --------------------------------------------------------------------------
# Risk overlays
# --------------------------------------------------------------------------

def volatility_target(
    weights: pd.DataFrame,
    closes: pd.DataFrame,
    target_vol: float = config.TARGET_VOLATILITY,
    window: int = 20,
    periods_per_year: int = 252,
    max_scale: float = 3.0,
) -> pd.DataFrame:
    """Scale ``weights`` so the portfolio's recent realised volatility meets a target.

    The scale factor uses only volatility measured up to the current bar, so it
    introduces no look-ahead. It is capped so a dead-calm stretch cannot lever
    the book to an absurd size.
    """
    asset_returns = closes.pct_change(fill_method=None).fillna(0.0)
    portfolio = (weights * asset_returns).sum(axis=1)
    realised = portfolio.rolling(window, min_periods=window).std(ddof=0) * np.sqrt(periods_per_year)
    scale = (target_vol / realised.replace(0.0, np.nan)).clip(upper=max_scale)
    return weights.mul(scale.fillna(0.0), axis=0)


def apply_trailing_stop(
    weights: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_series: pd.Series,
    multiple: float = 3.0,
) -> pd.Series:
    """Flatten a single-asset position when price closes through a trailing stop.

    The stop trails the best close since entry by ``multiple`` ATRs and never
    loosens while the position is held. Once hit, the position stays flat until
    the strategy's own signal flips, which stops the stop from re-entering on
    the same bar it exited.
    """
    w = weights.to_numpy(copy=True)
    c, a = close.to_numpy(), atr_series.to_numpy()
    out = np.zeros_like(w)
    stopped_side = 0.0
    anchor = np.nan

    for i in range(len(w)):
        target = w[i]
        if np.isnan(target) or target == 0.0:
            out[i], stopped_side, anchor = 0.0, 0.0, np.nan
            continue
        side = np.sign(target)
        if stopped_side == side:
            out[i] = 0.0          # still flat after a stop, awaiting a signal flip
            continue
        if out[i - 1] == 0.0 if i else True:
            anchor = c[i]         # fresh entry
        anchor = max(anchor, c[i]) if side > 0 else min(anchor, c[i])
        if np.isnan(a[i]):
            out[i] = target
            continue
        stop = anchor - side * multiple * a[i]
        if (side > 0 and c[i] < stop) or (side < 0 and c[i] > stop):
            out[i], stopped_side, anchor = 0.0, side, np.nan
        else:
            out[i] = target
    return pd.Series(out, index=weights.index, name=weights.name)


def buy_and_hold_result(
    prices, symbol: str | None = None, cfg: BacktestConfig | None = None,
    name: str = "Buy & hold",
) -> BacktestResult:
    """The benchmark every strategy has to beat: fully invested, never traded."""
    closes, _ = _as_panel(prices)
    target = symbol or closes.columns[0]
    weights = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    weights[target] = 1.0
    return run_backtest(prices, weights, cfg, name=name)

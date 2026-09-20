"""Performance and risk statistics for a strategy's return stream.

Every function takes a series of *periodic net returns* (fractions, one per bar)
and annualises using ``periods_per_year``. Nothing here assumes daily bars.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import config
from src.features import drawdown


def equity_curve(returns: pd.Series, initial: float = 1.0) -> pd.Series:
    """Compound ``returns`` into an equity curve starting at ``initial``."""
    return initial * (1.0 + returns.fillna(0.0)).cumprod()


def total_return(returns: pd.Series) -> float:
    """Cumulative return over the whole sample, as a fraction."""
    if len(returns) == 0:
        return float("nan")
    return float((1.0 + returns.fillna(0.0)).prod() - 1.0)


def cagr(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Compound annual growth rate."""
    n = len(returns.dropna())
    if n < 2:
        return float("nan")
    growth = float((1.0 + returns.fillna(0.0)).prod())
    if growth <= 0:
        return -1.0
    return growth ** (periods_per_year / n) - 1.0


def annual_volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Annualised standard deviation of returns."""
    if len(returns.dropna()) < 2:
        return float("nan")
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year))


def sharpe_ratio(returns: pd.Series, periods_per_year: int = 252,
                 risk_free: float | None = None) -> float:
    """Annualised Sharpe ratio, net of a flat risk-free rate."""
    rf = config.RISK_FREE_RATE if risk_free is None else risk_free
    excess = returns.dropna() - rf / periods_per_year
    if len(excess) < 2:
        return float("nan")
    sd = excess.std(ddof=1)
    if sd == 0 or np.isnan(sd):
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(periods_per_year))


def sortino_ratio(returns: pd.Series, periods_per_year: int = 252,
                  risk_free: float | None = None) -> float:
    """Sharpe's downside-only cousin: penalises only returns below the target."""
    rf = config.RISK_FREE_RATE if risk_free is None else risk_free
    excess = returns.dropna() - rf / periods_per_year
    if len(excess) < 2:
        return float("nan")
    downside = excess.clip(upper=0.0)
    dd = np.sqrt((downside ** 2).mean())
    if dd == 0 or np.isnan(dd):
        return float("nan")
    return float(excess.mean() / dd * np.sqrt(periods_per_year))


def max_drawdown(returns: pd.Series) -> float:
    """Worst peak-to-trough fall in the equity curve, as a negative fraction."""
    if len(returns) == 0:
        return float("nan")
    return float(drawdown(equity_curve(returns)).min())


def calmar_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    """CAGR divided by the depth of the worst drawdown."""
    mdd = max_drawdown(returns)
    if mdd is None or np.isnan(mdd) or mdd == 0:
        return float("nan")
    return float(cagr(returns, periods_per_year) / abs(mdd))


def ulcer_index(returns: pd.Series) -> float:
    """Root-mean-square drawdown: depth *and* duration of pain."""
    if len(returns) == 0:
        return float("nan")
    dd = drawdown(equity_curve(returns))
    return float(np.sqrt((dd.fillna(0.0) ** 2).mean()))


def longest_drawdown(returns: pd.Series) -> int:
    """Most bars spent below a previous equity peak."""
    if len(returns) == 0:
        return 0
    dd = drawdown(equity_curve(returns)).fillna(0.0)
    under = dd < 0
    longest = run = 0
    for flag in under:
        run = run + 1 if flag else 0
        longest = max(longest, run)
    return int(longest)


def hit_rate(returns: pd.Series) -> float:
    """Share of non-flat bars that made money."""
    active = returns[returns != 0].dropna()
    if len(active) == 0:
        return float("nan")
    return float((active > 0).mean())


def profit_factor(returns: pd.Series) -> float:
    """Gross gains divided by gross losses."""
    r = returns.dropna()
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else float("nan")
    return float(gains / losses)


def value_at_risk(returns: pd.Series, level: float = 0.95) -> float:
    """Historical VaR: the loss that ``level`` of bars stay better than."""
    r = returns.dropna()
    if len(r) == 0:
        return float("nan")
    return float(np.quantile(r, 1.0 - level))


def conditional_var(returns: pd.Series, level: float = 0.95) -> float:
    """Expected loss on the bars worse than the VaR threshold."""
    r = returns.dropna()
    if len(r) == 0:
        return float("nan")
    threshold = np.quantile(r, 1.0 - level)
    tail = r[r <= threshold]
    return float(tail.mean()) if len(tail) else float(threshold)


@dataclass(frozen=True)
class Performance:
    """The full statistic set for one return stream."""

    total_return: float
    cagr: float
    annual_volatility: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    ulcer_index: float
    longest_drawdown_bars: int
    hit_rate: float
    profit_factor: float
    var_95: float
    cvar_95: float
    skew: float
    kurtosis: float
    exposure: float
    annual_turnover: float
    bars: int

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    def to_series(self) -> pd.Series:
        return pd.Series(self.to_dict())


def summarise(
    returns: pd.Series,
    periods_per_year: int = 252,
    exposure: float = float("nan"),
    annual_turnover: float = float("nan"),
    risk_free: float | None = None,
) -> Performance:
    """Compute every statistic for one net return stream."""
    r = returns.dropna()
    return Performance(
        total_return=total_return(r),
        cagr=cagr(r, periods_per_year),
        annual_volatility=annual_volatility(r, periods_per_year),
        sharpe=sharpe_ratio(r, periods_per_year, risk_free),
        sortino=sortino_ratio(r, periods_per_year, risk_free),
        calmar=calmar_ratio(r, periods_per_year),
        max_drawdown=max_drawdown(r),
        ulcer_index=ulcer_index(r),
        longest_drawdown_bars=longest_drawdown(r),
        hit_rate=hit_rate(r),
        profit_factor=profit_factor(r),
        var_95=value_at_risk(r),
        cvar_95=conditional_var(r),
        skew=float(r.skew()) if len(r) > 2 else float("nan"),
        kurtosis=float(r.kurtosis()) if len(r) > 3 else float("nan"),
        exposure=exposure,
        annual_turnover=annual_turnover,
        bars=int(len(r)),
    )


def comparison_table(results: dict[str, Performance]) -> pd.DataFrame:
    """One row per strategy, one column per statistic."""
    return pd.DataFrame({name: perf.to_series() for name, perf in results.items()}).T


def rolling_sharpe(returns: pd.Series, window: int = 126,
                   periods_per_year: int = 252, risk_free: float | None = None) -> pd.Series:
    """Sharpe ratio computed on a rolling window."""
    rf = config.RISK_FREE_RATE if risk_free is None else risk_free
    excess = returns.fillna(0.0) - rf / periods_per_year
    mean = excess.rolling(window, min_periods=window).mean()
    sd = excess.rolling(window, min_periods=window).std(ddof=1).replace(0.0, np.nan)
    return mean / sd * np.sqrt(periods_per_year)


def monthly_returns(returns: pd.Series) -> pd.DataFrame:
    """Calendar-month returns laid out as years down, months across."""
    if len(returns) == 0:
        return pd.DataFrame()
    monthly = (1.0 + returns.fillna(0.0)).resample("ME").prod() - 1.0
    frame = monthly.to_frame("ret")
    frame["year"] = frame.index.year
    frame["month"] = frame.index.month
    return frame.pivot(index="year", columns="month", values="ret")


def calendar_year_returns(returns: pd.Series) -> pd.Series:
    """One compounded return per calendar year."""
    if len(returns) == 0:
        return pd.Series(dtype=float)
    yearly = (1.0 + returns.fillna(0.0)).resample("YE").prod() - 1.0
    yearly.index = yearly.index.year
    return yearly

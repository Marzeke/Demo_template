"""Benchmarks and deliberately simple rules.

These exist so that every headline strategy has something honest to be measured
against. A strategy that cannot beat equal weight, after costs, has not earned
its complexity.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features import ema, macd, realised_volatility, sma
from src.strategies.base import ParamSpec, Strategy, StrategyChart, register


@register
class BuyAndHold(Strategy):
    key = "buy_and_hold"
    label = "Buy and hold"
    category = "benchmark"
    description = "Hold the universe at fixed weights and never trade again."
    evidence = (
        "The benchmark, not a strategy. Over most windows it is very hard to "
        "beat after costs and tax, and any approach that does not clear it is "
        "paying for activity it does not need."
    )
    PARAMS = (
        ParamSpec("weighting", "Weighting", "choice", "equal", choices=("equal", "inverse_vol"),
                  help="Equal weight, or inverse volatility for a rough risk parity."),
        ParamSpec("vol_window", "Volatility window (bars)", "int", 60, 10, 252, 1),
        ParamSpec("rebalance", "Rebalance", "choice", "Q", choices=("D", "W", "M", "Q"),
                  help="Inverse-volatility weights drift, so they need resetting."),
        ParamSpec("gross", "Gross exposure", "float", 1.0, 0.1, 1.5, 0.05),
    )

    def generate_weights(self, prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = self._panel(prices)
        if self.p["weighting"] == "inverse_vol":
            vol = closes.apply(lambda s: realised_volatility(s, self.p["vol_window"]))
            raw = (1.0 / vol.replace(0.0, np.nan)).fillna(0.0)
            targets = self._normalise(raw, gross=self.p["gross"])
            return self._hold(targets, self._rebalance_mask(closes.index, self.p["rebalance"]))
        raw = pd.DataFrame(1.0, index=closes.index, columns=closes.columns).where(closes.notna(), 0.0)
        return self._normalise(raw, gross=self.p["gross"])


@register
class EMACrossover(Strategy):
    key = "ema_crossover"
    label = "EMA crossover"
    category = "baseline"
    description = "Long while a fast EMA is above a slow EMA, flat or short below."
    evidence = (
        "The most widely published trading rule there is, and a useful control "
        "precisely because it is so exposed to range-bound markets. Tested "
        "through the choppy stretches of 2024 and 2025 it whipsawed badly, with "
        "profit factors near one. Treat a good result from it as a warning that "
        "the sample was kind, not that the rule is strong."
    )
    PARAMS = (
        ParamSpec("fast", "Fast EMA (bars)", "int", 20, 2, 200, 1),
        ParamSpec("slow", "Slow EMA (bars)", "int", 100, 5, 400, 1),
        ParamSpec("allow_short", "Allow shorts", "bool", False),
        ParamSpec("gross", "Gross exposure", "float", 1.0, 0.1, 2.0, 0.1),
    )

    def _direction(self, close: pd.Series) -> pd.Series:
        fast, slow = ema(close, self.p["fast"]), ema(close, self.p["slow"])
        d = pd.Series(
            np.where(fast.isna() | slow.isna(), 0.0, np.where(fast > slow, 1.0, -1.0)),
            index=close.index,
        )
        return d if self.p["allow_short"] else d.clip(lower=0.0)

    def generate_weights(self, prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = self._panel(prices)
        raw = closes.apply(self._direction)
        return self._normalise(raw, gross=self.p["gross"])

    def chart(self, symbol: str, df: pd.DataFrame) -> StrategyChart:
        close = df["close"]
        overlays = pd.DataFrame(
            {
                f"EMA {self.p['fast']}": ema(close, self.p["fast"]),
                f"EMA {self.p['slow']}": ema(close, self.p["slow"]),
            }
        )
        return StrategyChart(
            price_overlays=overlays,
            panels={"Position": pd.DataFrame({"Direction": self._direction(close)})},
            levels={"Position": [0.0]},
        )


@register
class MACDTrend(Strategy):
    key = "macd_trend"
    label = "MACD histogram"
    category = "baseline"
    description = "Long while the MACD histogram is positive, optionally short below."
    evidence = (
        "A smoothed momentum rule, and the benchmark that enhanced-momentum "
        "research usually measures itself against. Sound as a comparison point; "
        "unremarkable on its own."
    )
    PARAMS = (
        ParamSpec("fast", "Fast EMA (bars)", "int", 12, 2, 100, 1),
        ParamSpec("slow", "Slow EMA (bars)", "int", 26, 5, 200, 1),
        ParamSpec("signal", "Signal EMA (bars)", "int", 9, 2, 50, 1),
        ParamSpec("allow_short", "Allow shorts", "bool", False),
        ParamSpec("trend_filter", "Require price above long average", "bool", False),
        ParamSpec("trend_window", "Long average (bars)", "int", 200, 20, 400, 1),
        ParamSpec("gross", "Gross exposure", "float", 1.0, 0.1, 2.0, 0.1),
    )

    def _direction(self, close: pd.Series) -> pd.Series:
        hist = macd(close, self.p["fast"], self.p["slow"], self.p["signal"])["histogram"]
        d = pd.Series(np.where(hist.isna(), 0.0, np.where(hist > 0, 1.0, -1.0)), index=close.index)
        if self.p["trend_filter"]:
            above = (close >= sma(close, self.p["trend_window"])).fillna(False)
            d = d.where(((d > 0) & above) | ((d < 0) & ~above), 0.0)
        return d if self.p["allow_short"] else d.clip(lower=0.0)

    def generate_weights(self, prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = self._panel(prices)
        return self._normalise(closes.apply(self._direction), gross=self.p["gross"])

    def chart(self, symbol: str, df: pd.DataFrame) -> StrategyChart:
        close = df["close"]
        frame = macd(close, self.p["fast"], self.p["slow"], self.p["signal"])
        overlays = pd.DataFrame(index=df.index)
        if self.p["trend_filter"]:
            overlays[f"SMA {self.p['trend_window']}"] = sma(close, self.p["trend_window"])
        return StrategyChart(
            price_overlays=overlays,
            panels={"MACD": frame[["macd", "signal", "histogram"]]},
            levels={"MACD": [0.0]},
        )

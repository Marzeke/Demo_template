"""Short-horizon mean reversion, gated by a long-horizon trend filter.

Buy weakness, but only in a market that is still in an uptrend. The filter is
the whole point: unfiltered dip-buying works beautifully until the one time the
dip keeps going, and then it gives back years of small wins. Requiring price to
sit above a long moving average refuses the trade in exactly the regime where
the tail risk lives.

This is the natural complement to trend following rather than a rival to it.
Trend systems make money when moves persist; this makes money when they do not.
Run together, the pair is calmer than either alone, which is the documented case
for blending them - see :class:`src.strategies.ensemble.Ensemble`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features import bollinger, rsi, sma, zscore
from src.strategies.base import ParamSpec, Strategy, StrategyChart, register


@register
class MeanReversion(Strategy):
    key = "mean_reversion"
    label = "Mean reversion, regime filtered"
    category = "mean_reversion"
    cross_sectional = False
    asset_classes = ("equity_index", "equity_single", "equity_sector")
    description = (
        "Buy a short-term oversold reading, but only while the market is above "
        "its long-term average. Exit on recovery or after a holding limit."
    )
    evidence = (
        "Short-horizon reversal is among the better documented anomalies in "
        "equity indices, and its high hit rate makes it feel safer than it is. "
        "The return profile is deliberately lopsided: many small wins against "
        "rare large losses, so a headline win rate tells you almost nothing. "
        "The long-term trend filter, and a hard holding limit, are what keep the "
        "left tail survivable. It works least well in commodities and currencies."
    )

    PARAMS = (
        ParamSpec("mode", "Entry signal", "choice", "rsi", choices=("rsi", "zscore", "bollinger"),
                  help="Which oversold measure triggers the entry."),
        ParamSpec("rsi_window", "RSI window (bars)", "int", 2, 2, 30, 1,
                  help="A very short window is the point; 2 is the classic setting."),
        ParamSpec("entry_level", "RSI entry below", "float", 10.0, 1.0, 50.0, 1.0),
        ParamSpec("exit_level", "RSI exit above", "float", 60.0, 20.0, 95.0, 1.0),
        ParamSpec("zscore_window", "Z-score window (bars)", "int", 20, 5, 120, 1),
        ParamSpec("entry_z", "Z-score entry below", "float", -2.0, -4.0, 0.0, 0.1),
        ParamSpec("exit_z", "Z-score exit above", "float", 0.0, -2.0, 3.0, 0.1),
        ParamSpec("regime_filter", "Long-term trend filter", "bool", True,
                  help="Only buy while price is above its long moving average."),
        ParamSpec("regime_window", "Long average (bars)", "int", 200, 20, 400, 1),
        ParamSpec("max_hold", "Max holding (bars)", "int", 10, 1, 120, 1,
                  help="Give up after this many bars whether or not the signal cleared."),
        ParamSpec("allow_short", "Allow shorts on strength", "bool", False,
                  help="Mirror the rule to sell overbought readings below the average."),
        ParamSpec("position_size", "Weight per position", "float", 1.0, 0.05, 1.0, 0.05),
        ParamSpec("allocation", "Capital allocation", "choice", "concentrate",
                  choices=("concentrate", "equal_universe"),
                  help="concentrate splits the book across whichever symbols are "
                       "signalling now; equal_universe reserves a fixed slice for "
                       "every symbol whether or not it fires."),
        ParamSpec("gross", "Max gross exposure", "float", 1.0, 0.1, 2.0, 0.1),
    )

    # -- entry and exit triggers ------------------------------------------

    def _triggers(self, df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        """``(long_entry, long_exit, short_entry, short_exit)`` boolean series."""
        close = df["close"]
        mode = self.p["mode"]

        if mode == "rsi":
            osc = rsi(close, self.p["rsi_window"])
            long_entry = osc < self.p["entry_level"]
            long_exit = osc > self.p["exit_level"]
            short_entry = osc > (100.0 - self.p["entry_level"])
            short_exit = osc < (100.0 - self.p["exit_level"])
        elif mode == "zscore":
            osc = zscore(close, self.p["zscore_window"])
            long_entry = osc < self.p["entry_z"]
            long_exit = osc > self.p["exit_z"]
            short_entry = osc > -self.p["entry_z"]
            short_exit = osc < -self.p["exit_z"]
        else:  # bollinger
            # With the default two standard deviations this is the same rule as
            # the z-score mode, by construction: a close below the lower band is
            # exactly a z-score below -2. The two differ once the band width or
            # the z thresholds are moved apart.
            bands = bollinger(close, self.p["zscore_window"])
            long_entry = close < bands["lower"]
            long_exit = close > bands["middle"]
            short_entry = close > bands["upper"]
            short_exit = close < bands["middle"]

        return (
            long_entry.fillna(False), long_exit.fillna(False),
            short_entry.fillna(False), short_exit.fillna(False),
        )

    def _position(self, df: pd.DataFrame) -> pd.Series:
        """Run the entry, exit and holding-limit state machine for one symbol."""
        long_entry, long_exit, short_entry, short_exit = self._triggers(df)

        if self.p["regime_filter"]:
            long_ma = sma(df["close"], self.p["regime_window"])
            above = (df["close"] >= long_ma).fillna(False)
            long_entry &= above
            short_entry &= ~above & long_ma.notna()
        if not self.p["allow_short"]:
            short_entry = pd.Series(False, index=df.index)

        le, lx = long_entry.to_numpy(), long_exit.to_numpy()
        se, sx = short_entry.to_numpy(), short_exit.to_numpy()
        state = np.zeros(len(df))
        held = 0

        for i in range(len(df)):
            prev = state[i - 1] if i else 0.0
            if prev > 0:
                held += 1
                state[i] = 0.0 if (lx[i] or held >= self.p["max_hold"]) else 1.0
            elif prev < 0:
                held += 1
                state[i] = 0.0 if (sx[i] or held >= self.p["max_hold"]) else -1.0
            else:
                state[i] = 0.0
            # A position that closed on this bar does not reopen on the same
            # bar. Exiting and re-entering at one price is a round trip that
            # pays costs for nothing, and it would let a holding limit be
            # renewed indefinitely without ever going flat.
            closed_here = prev != 0.0 and state[i] == 0.0
            if state[i] == 0.0:
                held = 0
                if not closed_here:
                    if le[i]:
                        state[i], held = 1.0, 1
                    elif se[i]:
                        state[i], held = -1.0, 1
        return pd.Series(state * self.p["position_size"], index=df.index)

    def generate_weights(self, prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = self._panel(prices)
        weights = pd.DataFrame(0.0, index=closes.index, columns=list(prices))
        for symbol, df in prices.items():
            aligned = df.reindex(closes.index).ffill()
            weights[symbol] = self._position(aligned).reindex(closes.index).fillna(0.0)

        if self.p["allocation"] == "concentrate":
            # Share the book across whatever is signalling right now, so a lone
            # signal is a real position rather than a rounding error.
            weights = self._normalise(weights, gross=self.p["gross"])
        else:
            weights = weights / max(len(prices), 1)

        gross = weights.abs().sum(axis=1)
        scale = np.minimum(1.0, self.p["gross"] / gross.replace(0.0, np.nan))
        return weights.mul(scale.fillna(1.0), axis=0)

    def chart(self, symbol: str, df: pd.DataFrame) -> StrategyChart:
        close = df["close"]
        overlays = pd.DataFrame(index=df.index)
        bands: list[tuple[str, str]] = []

        if self.p["regime_filter"]:
            overlays[f"SMA {self.p['regime_window']}"] = sma(close, self.p["regime_window"])
        if self.p["mode"] in {"bollinger", "zscore"}:
            b = bollinger(close, self.p["zscore_window"])
            overlays["Upper band"] = b["upper"]
            overlays["Lower band"] = b["lower"]
            overlays["Band centre"] = b["middle"]
            bands = [("Upper band", "Lower band")]

        if self.p["mode"] == "rsi":
            panel_name = f"RSI {self.p['rsi_window']}"
            panel = pd.DataFrame({panel_name: rsi(close, self.p["rsi_window"])})
            levels = [self.p["entry_level"], self.p["exit_level"]]
        else:
            panel_name = f"Z-score {self.p['zscore_window']}"
            panel = pd.DataFrame({panel_name: zscore(close, self.p["zscore_window"])})
            levels = [self.p["entry_z"], self.p["exit_z"]]

        return StrategyChart(
            price_overlays=overlays,
            panels={panel_name: panel, "Position": pd.DataFrame({"Direction": self._position(df)})},
            bands=bands,
            levels={panel_name: levels, "Position": [0.0]},
        )

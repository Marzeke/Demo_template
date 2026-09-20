"""Cross-sectional momentum rotation, with an absolute-momentum safety switch.

Rank every symbol in the universe by its trailing return, hold the strongest
few, and repeat on a fixed schedule. The lookback skips the most recent month
because the very last month tends to reverse - the classic "12 minus 1"
construction.

The absolute-momentum filter is what turns relative strength into *dual*
momentum: a symbol has to be beating cash on its own, not merely beating its
peers, before it earns an allocation. In a market where everything is falling,
the strategy holds nothing instead of holding the best loser.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features import realised_volatility, sma
from src.strategies.base import ParamSpec, Strategy, StrategyChart, register


@register
class MomentumRotation(Strategy):
    key = "momentum_rotation"
    label = "Cross-sectional momentum rotation"
    category = "momentum"
    cross_sectional = True
    asset_classes = ("equity_sector", "equity_index", "commodity", "crypto", "fixed_income")
    description = (
        "Hold the strongest few symbols in a universe on a fixed rebalance schedule, "
        "ranked on trailing return with the most recent month skipped."
    )
    evidence = (
        "The most durable of the three headline approaches, and the one with the "
        "longest independent replication record across asset classes. It pays for "
        "that with sharp, fast reversals when leadership rotates: the crowded "
        "leaders unwind together, and a monthly rebalance is always late to it. "
        "The absolute-momentum filter is what limits the damage in a broad "
        "drawdown; without it the strategy stays fully invested in the best loser."
    )

    PARAMS = (
        ParamSpec("lookback", "Lookback (bars)", "int", 252, 20, 1000, 1,
                  help="Formation window. 252 bars is roughly twelve months of daily data."),
        ParamSpec("skip", "Skip recent (bars)", "int", 21, 0, 120, 1,
                  help="Bars excluded at the near end, to sidestep short-term reversal."),
        ParamSpec("top_n", "Symbols held", "int", 3, 1, 30, 1,
                  help="How many of the highest-ranked symbols to hold."),
        ParamSpec("rebalance", "Rebalance", "choice", "M", choices=("D", "W", "M", "Q"),
                  help="How often ranks are recomputed and the book is reset."),
        ParamSpec("absolute_filter", "Absolute momentum filter", "bool", True,
                  help="Drop any holding whose own trailing return is negative."),
        ParamSpec("trend_filter", "Price above long average", "bool", False,
                  help="Additionally require price above its long moving average."),
        ParamSpec("trend_window", "Long average (bars)", "int", 200, 20, 400, 1),
        ParamSpec("weighting", "Weighting", "choice", "equal", choices=("equal", "inverse_vol", "rank"),
                  help="How capital is split across the chosen symbols."),
        ParamSpec("vol_window", "Volatility window (bars)", "int", 60, 10, 252, 1,
                  help="Window for inverse-volatility weighting."),
        ParamSpec("gross", "Gross exposure", "float", 1.0, 0.0, 2.0, 0.05,
                  help="Total invested fraction when the strategy is fully allocated."),
    )

    def _scores(self, closes: pd.DataFrame) -> pd.DataFrame:
        """Trailing return over the formation window, ending ``skip`` bars back."""
        skip, lookback = self.p["skip"], self.p["lookback"]
        near = closes.shift(skip)
        far = closes.shift(skip + lookback)
        return near / far - 1.0

    def generate_weights(self, prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = self._panel(prices)
        scores = self._scores(closes)

        eligible = scores.notna()
        if self.p["absolute_filter"]:
            eligible &= scores > 0
        if self.p["trend_filter"]:
            long_ma = closes.apply(lambda s: sma(s, self.p["trend_window"]))
            eligible &= closes >= long_ma

        masked = scores.where(eligible)
        ranks = masked.rank(axis=1, ascending=False, method="first")
        chosen = (ranks <= self.p["top_n"]) & eligible

        if self.p["weighting"] == "inverse_vol":
            vol = closes.apply(lambda s: realised_volatility(s, self.p["vol_window"]))
            raw = (1.0 / vol.replace(0.0, np.nan)).where(chosen, 0.0).fillna(0.0)
        elif self.p["weighting"] == "rank":
            # Highest rank gets the largest slice, tapering to the last holding.
            raw = (self.p["top_n"] + 1 - ranks).where(chosen, 0.0).fillna(0.0).clip(lower=0.0)
        else:
            raw = chosen.astype(float)

        targets = self._normalise(raw, gross=self.p["gross"])
        mask = self._rebalance_mask(closes.index, self.p["rebalance"])
        return self._hold(targets, mask)

    def chart(self, symbol: str, df: pd.DataFrame) -> StrategyChart:
        close = df["close"]
        overlays = pd.DataFrame({f"SMA {self.p['trend_window']}": sma(close, self.p["trend_window"])})
        score = close.shift(self.p["skip"]) / close.shift(self.p["skip"] + self.p["lookback"]) - 1.0
        return StrategyChart(
            price_overlays=overlays,
            panels={"Momentum score": pd.DataFrame({"Trailing return": score})},
            levels={"Momentum score": [0.0]},
        )


@register
class DualMomentum(MomentumRotation):
    """Antonacci-style dual momentum: one winner at a time, or cash."""

    key = "dual_momentum"
    label = "Dual momentum (single winner)"
    category = "momentum"
    description = (
        "Hold only the single strongest symbol, and only while its own trailing "
        "return is positive. Otherwise hold nothing."
    )
    evidence = (
        "A concentrated special case of cross-sectional momentum. Fewer holdings "
        "means less diversification and a lumpier path; the concentration is the "
        "point, and it is also the risk. Results are very sensitive to the "
        "rebalance date, which is a warning about how much of any backtest of it "
        "is luck."
    )

    PARAMS = tuple(
        ParamSpec("top_n", "Symbols held", "int", 1, 1, 5, 1,
                  help="How many of the highest-ranked symbols to hold.")
        if p.name == "top_n" else p
        for p in MomentumRotation.PARAMS
    )

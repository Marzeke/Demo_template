"""Opening range breakout, for intraday bars.

Mark the high and low of the first stretch of the session, then trade the first
break of that range, and go home flat. It needs intraday data; on daily bars the
rule has no meaning, so the strategy refuses to run on them rather than quietly
producing something that looks like a result.

A warning that belongs next to the rule, not in a footnote: the published
evidence on this one is genuinely contested. Favourable tests tend to use
leveraged instruments, short samples and no slippage, which is where most of
the reported return comes from. A 2026 falsification study that swept the
variants systematically found most of them unprofitable once costs were charged.
The volatility filter below is the part both camps agree on: without a minimum
range size relative to recent volatility, the rule trades every quiet morning
and loses to the spread.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.features import atr
from src.strategies.base import ParamSpec, Strategy, StrategyChart, register


@register
class OpeningRangeBreakout(Strategy):
    key = "opening_range_breakout"
    label = "Opening range breakout (intraday)"
    category = "breakout"
    cross_sectional = False
    asset_classes = ("equity_index", "equity_single")
    intervals = ("1m", "5m", "15m", "30m", "1h")
    description = (
        "Trade the first break of the session's opening range, filtered by range "
        "size relative to recent volatility, and close out before the bell."
    )
    evidence = (
        "Contested. Favourable published tests lean on leveraged products, short "
        "samples and no transaction costs; a systematic falsification study "
        "found most variants unprofitable once those are restored. It degrades "
        "sharply on quiet days, which is what the volatility filter is for. "
        "Included as an option to test rather than as a recommendation."
    )

    PARAMS = (
        ParamSpec("range_bars", "Opening range (bars)", "int", 2, 1, 24, 1,
                  help="How many bars from the open define the range."),
        ParamSpec("direction", "Direction", "choice", "both", choices=("both", "long", "short")),
        ParamSpec("min_range_atr", "Minimum range / ATR", "float", 1.5, 0.0, 6.0, 0.1,
                  help="Skip the session when the opening range is small for the "
                       "recent volatility. This is the filter that matters most. "
                       "The ratio compares the whole opening range against a single "
                       "bar's ATR, so it scales with the opening range length: on "
                       "30-minute bars with a two-bar range the typical reading is "
                       "around 1.7, and 1.5 skips roughly the quietest third of "
                       "sessions. Re-check the distribution after changing either "
                       "the bar size or the range length."),
        ParamSpec("atr_window", "ATR window (bars)", "int", 14, 2, 200, 1),
        ParamSpec("stop_at_range", "Stop at the far side of the range", "bool", True),
        ParamSpec("target_r", "Profit target (R multiples)", "float", 0.0, 0.0, 10.0, 0.5,
                  help="Zero means hold until the close of the session."),
        ParamSpec("close_at_session_end", "Flat at the close", "bool", True),
        ParamSpec("position_size", "Weight per position", "float", 1.0, 0.05, 1.0, 0.05),
    )

    def _session_position(self, df: pd.DataFrame) -> pd.Series:
        """Run the opening-range rule one session at a time for a single symbol."""
        rng = atr(df["high"], df["low"], df["close"], self.p["atr_window"])
        position = pd.Series(0.0, index=df.index)
        sessions = df.groupby(df.index.normalize(), sort=True)

        n_range = self.p["range_bars"]
        want_long = self.p["direction"] in {"both", "long"}
        want_short = self.p["direction"] in {"both", "short"}

        for _day, bars in sessions:
            if len(bars) <= n_range + 1:
                continue
            opening = bars.iloc[:n_range]
            hi, lo = float(opening["high"].max()), float(opening["low"].min())
            width = hi - lo
            if width <= 0:
                continue

            reference = rng.reindex(bars.index).iloc[n_range - 1]
            if self.p["min_range_atr"] > 0:
                if np.isnan(reference) or reference <= 0:
                    continue
                if width / reference < self.p["min_range_atr"]:
                    continue

            side, entry_price, stop = 0.0, np.nan, np.nan
            rest = bars.iloc[n_range:]
            values = np.zeros(len(rest))

            for i, (_ts, bar) in enumerate(rest.iterrows()):
                close = float(bar["close"])
                if side == 0.0:
                    if want_long and close > hi:
                        side, entry_price = 1.0, close
                        stop = lo if self.p["stop_at_range"] else close - width
                    elif want_short and close < lo:
                        side, entry_price = -1.0, close
                        stop = hi if self.p["stop_at_range"] else close + width
                else:
                    risk = abs(entry_price - stop)
                    hit_stop = (side > 0 and close <= stop) or (side < 0 and close >= stop)
                    hit_target = (
                        self.p["target_r"] > 0
                        and risk > 0
                        and (close - entry_price) * side >= self.p["target_r"] * risk
                    )
                    if hit_stop or hit_target:
                        side = 0.0
                values[i] = side

            if self.p["close_at_session_end"] and len(values):
                values[-1] = 0.0
            position.loc[rest.index] = values

        return position * self.p["position_size"]

    def generate_weights(self, prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = self._panel(prices)
        if closes.index.normalize().nunique() >= len(closes) * 0.9:
            raise ValueError(
                "opening_range_breakout needs intraday bars; this looks like daily "
                "data, where an opening range does not exist. Load 5m, 15m, 30m or "
                "1h bars instead."
            )
        weights = pd.DataFrame(0.0, index=closes.index, columns=list(prices))
        for symbol, df in prices.items():
            weights[symbol] = self._session_position(df.reindex(closes.index).ffill())
        return self._normalise(weights, gross=1.0)

    def chart(self, symbol: str, df: pd.DataFrame) -> StrategyChart:
        n = self.p["range_bars"]
        by_session = df.groupby(df.index.normalize(), sort=True)
        high = by_session["high"].transform(lambda s: s.iloc[:n].max())
        low = by_session["low"].transform(lambda s: s.iloc[:n].min())
        overlays = pd.DataFrame({"Opening range high": high, "Opening range low": low})
        return StrategyChart(
            price_overlays=overlays,
            bands=[("Opening range high", "Opening range low")],
            panels={"Position": pd.DataFrame({"Direction": self._session_position(df)})},
            levels={"Position": [0.0]},
        )

"""Time-series trend following with a volatility-targeted position size.

Each symbol is judged on its own: is it trending up, down, or neither? Position
size is then set so that every symbol contributes a similar amount of risk, and
so that the book as a whole aims at a chosen annual volatility. Sizing is where
most of this approach's risk-adjusted return comes from - the entry rule matters
less than people expect.

Three entry rules are offered because they fail differently:

``donchian``   break of an N-bar high, exit on a shorter-channel break. Slow to
               enter, slow to leave, survives noise.
``ma_cross``   fast moving average over slow. Smoothest, and the worst behaved
               in a range, where it whipsaws.
``supertrend`` ATR-ratcheted band. Reacts to volatility rather than to time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src import config
from src.backtest.engine import volatility_target
from src.features import atr, donchian, ema, realised_volatility, sma, supertrend
from src.strategies.base import ParamSpec, Strategy, StrategyChart, register


@register
class TrendFollowing(Strategy):
    key = "trend_vol_target"
    label = "Trend following, volatility targeted"
    category = "trend"
    cross_sectional = False
    asset_classes = ("equity_index", "commodity", "currency", "crypto", "fixed_income")
    description = (
        "Go with the direction of each market separately, sizing every position "
        "by its own volatility so risk is shared evenly across the book."
    )
    evidence = (
        "The workhorse of managed futures, and the approach with the widest "
        "cross-market evidence. Its weakness is not subtle: in a range-bound "
        "market it buys every false break and bleeds. Published tests through "
        "2024 and 2025 show exactly that, with long choppy stretches and profit "
        "factors around one. The volatility target is the part that most "
        "reliably improves the risk-adjusted result; the entry rule is the part "
        "most often over-fitted."
    )

    PARAMS = (
        ParamSpec("signal", "Entry rule", "choice", "donchian",
                  choices=("donchian", "ma_cross", "supertrend"),
                  help="Which trend definition to trade."),
        ParamSpec("entry_window", "Entry window (bars)", "int", 50, 5, 400, 1,
                  help="Breakout lookback, or the slow average for a crossover."),
        ParamSpec("exit_window", "Exit window (bars)", "int", 25, 3, 200, 1,
                  help="Shorter channel used to leave a position."),
        ParamSpec("fast_window", "Fast average (bars)", "int", 50, 3, 200, 1,
                  help="Fast moving average, used by the crossover rule."),
        ParamSpec("atr_window", "ATR window (bars)", "int", 14, 2, 100, 1),
        ParamSpec("atr_multiple", "Supertrend ATR multiple", "float", 3.0, 0.5, 10.0, 0.5),
        ParamSpec("allow_short", "Allow shorts", "bool", True,
                  help="Trade the downside as well as the upside."),
        ParamSpec("sizing", "Position sizing", "choice", "portfolio_vol",
                  choices=("portfolio_vol", "per_symbol_vol", "fixed"),
                  help="portfolio_vol targets the whole book's volatility; "
                       "per_symbol_vol gives each market the same risk budget; "
                       "fixed uses flat weights."),
        ParamSpec("target_volatility", "Target volatility (annual)", "float",
                  config.TARGET_VOLATILITY, 0.02, 0.60, 0.01,
                  help="Annual volatility the sizing aims at, read as a whole-book "
                       "figure under portfolio_vol sizing."),
        ParamSpec("max_scale", "Max volatility scale-up", "float", 3.0, 1.0, 10.0, 0.5,
                  help="Ceiling on the leverage a calm stretch may call for."),
        ParamSpec("vol_window", "Volatility window (bars)", "int", 20, 5, 252, 1),
        ParamSpec("max_position", "Max weight per symbol", "float", 1.0, 0.05, 3.0, 0.05),
        ParamSpec("gross", "Max gross exposure", "float", 1.0, 0.1, 3.0, 0.1),
        ParamSpec("trend_filter", "Require long-term trend agreement", "bool", False,
                  help="Only take longs above, and shorts below, a long moving average."),
        ParamSpec("trend_window", "Long average (bars)", "int", 200, 20, 400, 1),
    )

    # -- signal construction ----------------------------------------------

    def _direction(self, df: pd.DataFrame) -> pd.Series:
        """+1 long, -1 short, 0 flat, for one symbol."""
        close, high, low = df["close"], df["high"], df["low"]
        rule = self.p["signal"]

        if rule == "donchian":
            entry = donchian(high, low, self.p["entry_window"])
            exit_ = donchian(high, low, self.p["exit_window"])
            state = np.zeros(len(close))
            c = close.to_numpy()
            eu, el = entry["upper"].to_numpy(), entry["lower"].to_numpy()
            xu, xl = exit_["upper"].to_numpy(), exit_["lower"].to_numpy()
            for i in range(1, len(c)):
                prev = state[i - 1]
                if prev > 0:
                    state[i] = 0.0 if (not np.isnan(xl[i]) and c[i] < xl[i]) else 1.0
                elif prev < 0:
                    state[i] = 0.0 if (not np.isnan(xu[i]) and c[i] > xu[i]) else -1.0
                else:
                    state[i] = prev
                if not np.isnan(eu[i]) and c[i] > eu[i]:
                    state[i] = 1.0
                elif not np.isnan(el[i]) and c[i] < el[i]:
                    state[i] = -1.0
            direction = pd.Series(state, index=close.index)

        elif rule == "ma_cross":
            fast = ema(close, self.p["fast_window"])
            slow = sma(close, self.p["entry_window"])
            direction = pd.Series(
                np.where(fast.isna() | slow.isna(), 0.0, np.where(fast > slow, 1.0, -1.0)),
                index=close.index,
            )

        else:  # supertrend
            st = supertrend(high, low, close, self.p["atr_window"], self.p["atr_multiple"])
            direction = st["direction"].fillna(0.0)

        if self.p["trend_filter"]:
            long_ma = sma(close, self.p["trend_window"])
            allow_long = (close >= long_ma).fillna(False)
            allow_short = (close < long_ma).fillna(False)
            direction = direction.where(
                ((direction > 0) & allow_long) | ((direction < 0) & allow_short), 0.0
            )

        if not self.p["allow_short"]:
            direction = direction.clip(lower=0.0)
        return direction.fillna(0.0)

    def _sized(self, df: pd.DataFrame, direction: pd.Series) -> pd.Series:
        """Scale a direction into a raw per-symbol weight before book-level sizing."""
        mode = self.p["sizing"]
        if mode == "fixed":
            return direction * self.p["max_position"]
        vol = realised_volatility(df["close"], self.p["vol_window"])
        inverse_vol = (1.0 / vol.replace(0.0, np.nan)).fillna(0.0)
        if mode == "per_symbol_vol":
            # Each market gets the same annual risk budget outright.
            size = (self.p["target_volatility"] * inverse_vol).clip(upper=self.p["max_position"])
            return direction * size
        # portfolio_vol: shape only. The book is scaled to target afterwards.
        return direction * inverse_vol

    def generate_weights(self, prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = self._panel(prices)
        weights = pd.DataFrame(0.0, index=closes.index, columns=list(prices))
        for symbol, df in prices.items():
            aligned = df.reindex(closes.index)
            sized = self._sized(aligned, self._direction(aligned))
            weights[symbol] = sized.reindex(closes.index).fillna(0.0)

        if self.p["sizing"] == "portfolio_vol":
            # Equal risk contribution across whatever is currently held, then one
            # scale factor so the whole book aims at the stated volatility. The
            # scale uses only volatility measured up to the current bar.
            weights = self._normalise(weights, gross=1.0)
            weights = volatility_target(
                weights,
                closes,
                target_vol=self.p["target_volatility"],
                window=self.p["vol_window"],
                max_scale=self.p["max_scale"],
            )
            weights = weights.clip(lower=-self.p["max_position"], upper=self.p["max_position"])
        else:
            # Fixed and per-symbol sizing share the book across the universe.
            weights = weights / max(len(prices), 1)

        gross = weights.abs().sum(axis=1)
        scale = np.minimum(1.0, self.p["gross"] / gross.replace(0.0, np.nan))
        return weights.mul(scale.fillna(1.0), axis=0)

    def chart(self, symbol: str, df: pd.DataFrame) -> StrategyChart:
        close, high, low = df["close"], df["high"], df["low"]
        rule = self.p["signal"]
        overlays = pd.DataFrame(index=df.index)
        bands: list[tuple[str, str]] = []
        pairs: list[tuple[str, str]] = []

        if rule == "donchian":
            entry = donchian(high, low, self.p["entry_window"])
            exit_ = donchian(high, low, self.p["exit_window"])
            overlays["Entry high"] = entry["upper"]
            overlays["Entry low"] = entry["lower"]
            overlays["Exit high"] = exit_["upper"]
            overlays["Exit low"] = exit_["lower"]
            bands = [("Entry high", "Entry low")]
            pairs = [("Exit high", "Exit low")]
        elif rule == "ma_cross":
            overlays[f"EMA {self.p['fast_window']}"] = ema(close, self.p["fast_window"])
            overlays[f"SMA {self.p['entry_window']}"] = sma(close, self.p["entry_window"])
        else:
            overlays["Supertrend"] = supertrend(
                high, low, close, self.p["atr_window"], self.p["atr_multiple"]
            )["supertrend"]

        if self.p["trend_filter"]:
            overlays[f"SMA {self.p['trend_window']}"] = sma(close, self.p["trend_window"])

        panels = {
            "Position": pd.DataFrame({"Direction": self._direction(df)}),
            # Realised volatility and ATR live on different scales, so they get
            # their own panels. Two scales on one axis is the fastest way to make
            # a chart lie.
            "Realised volatility (annual)": pd.DataFrame(
                {"Realised": realised_volatility(close, self.p["vol_window"])}
            ),
            "ATR as share of price": pd.DataFrame(
                {"ATR": atr(high, low, close, self.p["atr_window"]) / close}
            ),
        }
        return StrategyChart(
            price_overlays=overlays, panels=panels, bands=bands, pairs=pairs,
            levels={
                "Position": [0.0],
                "Realised volatility (annual)": [self.p["target_volatility"]],
            },
        )


@register
class DonchianBreakout(TrendFollowing):
    """The plain breakout, with no volatility sizing. A baseline to beat."""

    key = "donchian_breakout"
    label = "Donchian breakout (unsized)"
    category = "baseline"
    description = "Buy an N-bar high, sell an N-bar low, full size, no risk scaling."
    evidence = (
        "Included as a control, not a recommendation. Comparing it with the "
        "volatility-targeted version is the cleanest way to see how much of the "
        "result comes from sizing rather than from the entry rule."
    )
    PARAMS = tuple(
        ParamSpec("sizing", "Position sizing", "choice", "fixed",
                  choices=("portfolio_vol", "per_symbol_vol", "fixed"),
                  help="Fixed by default, which is what makes this a control.")
        if p.name == "sizing" else p
        for p in TrendFollowing.PARAMS
    )

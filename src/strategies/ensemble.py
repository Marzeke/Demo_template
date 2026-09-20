"""A blend of the headline strategies, run as one book.

Trend following and mean reversion are close to opposites: one needs moves to
persist, the other needs them to snap back. Momentum rotation is slower than
both and earns its return from a different place again. Because their good
periods do not line up, blending them tends to raise the risk-adjusted return
mostly by lowering volatility rather than by lifting return. That is the
documented effect, and it is also the least glamorous kind of edge, which is
part of why it survives.

The blend is a weighted sum of each component's target weights, so a symbol two
components both like simply gets a larger allocation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.backtest.engine import volatility_target
from src.strategies.base import ParamSpec, Strategy, StrategyChart, register
from src.strategies.mean_reversion import MeanReversion
from src.strategies.momentum_rotation import MomentumRotation
from src.strategies.trend_following import TrendFollowing


@register
class Ensemble(Strategy):
    key = "ensemble"
    label = "Blended ensemble"
    category = "ensemble"
    cross_sectional = True
    asset_classes = ("equity_index", "equity_sector", "commodity", "crypto", "fixed_income")
    description = (
        "Run momentum rotation, trend following and mean reversion together and "
        "hold the weighted sum of what they each want."
    )
    evidence = (
        "Blending weakly related return streams is the most reliable improvement "
        "available here, and the gain shows up as lower volatility rather than "
        "higher return. It is not free: the blend trades more than any single "
        "component, so costs matter more, and in a period where every component "
        "struggles it simply loses on all three at once. Diversification across "
        "strategies is not a hedge."
    )

    PARAMS = (
        ParamSpec("momentum_weight", "Momentum rotation share", "float", 0.4, 0.0, 1.0, 0.05),
        ParamSpec("trend_weight", "Trend following share", "float", 0.3, 0.0, 1.0, 0.05),
        ParamSpec("reversion_weight", "Mean reversion share", "float", 0.3, 0.0, 1.0, 0.05),
        ParamSpec("target_volatility", "Target volatility (annual)", "float", 0.12, 0.0, 0.5, 0.01,
                  help="Applied to the blended book. Zero leaves the blend unscaled."),
        ParamSpec("vol_window", "Volatility window (bars)", "int", 20, 5, 252, 1),
        ParamSpec("max_scale", "Max volatility scale-up", "float", 2.0, 1.0, 10.0, 0.5),
        ParamSpec("gross", "Max gross exposure", "float", 1.0, 0.1, 3.0, 0.1),
    )

    def __init__(self, components: dict[str, Strategy] | None = None, **params):
        super().__init__(**params)
        self.components = components or {
            "momentum": MomentumRotation(),
            "trend": TrendFollowing(),
            "reversion": MeanReversion(),
        }

    def _blend_weights(self) -> dict[str, float]:
        """Component shares, normalised to sum to one."""
        raw = {
            "momentum": self.p["momentum_weight"],
            "trend": self.p["trend_weight"],
            "reversion": self.p["reversion_weight"],
        }
        raw = {k: v for k, v in raw.items() if k in self.components}
        for key in self.components:
            raw.setdefault(key, 1.0)
        total = sum(raw.values())
        if total <= 0:
            raise ValueError("ensemble component shares sum to zero")
        return {k: v / total for k, v in raw.items()}

    def component_weights(self, prices: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """Each component's target weights, before blending. Useful for attribution."""
        return {name: strat.generate_weights(prices) for name, strat in self.components.items()}

    def generate_weights(self, prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = self._panel(prices)
        shares = self._blend_weights()

        blended = pd.DataFrame(0.0, index=closes.index, columns=list(prices))
        for name, frame in self.component_weights(prices).items():
            aligned = frame.reindex(index=closes.index, columns=blended.columns).fillna(0.0)
            blended = blended + aligned * shares.get(name, 0.0)

        if self.p["target_volatility"] > 0:
            blended = volatility_target(
                blended, closes,
                target_vol=self.p["target_volatility"],
                window=self.p["vol_window"],
                max_scale=self.p["max_scale"],
            )

        gross = blended.abs().sum(axis=1)
        scale = np.minimum(1.0, self.p["gross"] / gross.replace(0.0, np.nan))
        return blended.mul(scale.fillna(1.0), axis=0)

    def chart(self, symbol: str, df: pd.DataFrame) -> StrategyChart:
        """Show each component's view of this symbol, stacked."""
        overlays = pd.DataFrame(index=df.index)
        panels: dict[str, pd.DataFrame] = {}
        for name, strat in self.components.items():
            sub = strat.chart(symbol, df)
            for col in sub.price_overlays.columns:
                overlays[f"{name}: {col}"] = sub.price_overlays[col]
            for title, frame in sub.panels.items():
                panels[f"{name} - {title}"] = frame
        return StrategyChart(price_overlays=overlays, panels=panels)

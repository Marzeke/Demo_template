"""Strategy library.

Importing this package registers every strategy, so
:func:`src.strategies.base.available` returns the full catalogue.
"""

from src.strategies.base import (  # noqa: F401
    ParamSpec,
    Strategy,
    StrategyChart,
    available,
    catalogue,
    get_strategy,
    register,
    strategy_class,
)
from src.strategies import baselines  # noqa: F401
from src.strategies import ensemble  # noqa: F401
from src.strategies import mean_reversion  # noqa: F401
from src.strategies import momentum_rotation  # noqa: F401
from src.strategies import opening_range  # noqa: F401
from src.strategies import trend_following  # noqa: F401

#: The three approaches the app leads with, in the order they are presented.
HEADLINE = ("momentum_rotation", "trend_vol_target", "mean_reversion")

__all__ = [
    "ParamSpec", "Strategy", "StrategyChart", "available", "catalogue",
    "get_strategy", "register", "strategy_class", "HEADLINE",
]

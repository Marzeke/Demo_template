"""The strategy contract, its parameter metadata, and the registry.

A strategy's only job is to turn prices into **target weights**. It never sees
capital, costs or fills - :mod:`src.backtest.engine` owns those. That split is
what lets the same strategy run on one chart, on a sector rotation, or inside a
walk-forward sweep without changing a line.

Each strategy also declares:

* ``PARAMS``   - typed parameter metadata, so the user interface can build its
  own controls and the command line can validate input without hard-coding
  anything per strategy.
* ``chart``    - the indicator frames a chart should draw, so a strategy's
  reasoning is visible on the price panel rather than hidden in its returns.
* ``EVIDENCE`` - a short, honest note on what is actually known about the
  approach, including where it fails.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ParamSpec:
    """One tunable parameter, described well enough to build a control from."""

    name: str
    label: str
    kind: str  # "int" | "float" | "bool" | "choice"
    default: object
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    choices: tuple[str, ...] = ()
    help: str = ""

    def coerce(self, value):
        """Cast and clamp ``value`` into this parameter's domain."""
        if self.kind == "int":
            value = int(round(float(value)))
        elif self.kind == "float":
            value = float(value)
        elif self.kind == "bool":
            if isinstance(value, str):
                value = value.strip().lower() in {"1", "true", "yes", "on"}
            value = bool(value)
        elif self.kind == "choice":
            value = str(value)
            if self.choices and value not in self.choices:
                raise ValueError(f"{self.name}: {value!r} not in {self.choices}")
        if self.kind in {"int", "float"}:
            if self.minimum is not None:
                value = max(value, type(value)(self.minimum))
            if self.maximum is not None:
                value = min(value, type(value)(self.maximum))
        return value


@dataclass
class StrategyChart:
    """What a chart should draw to show a strategy's reasoning."""

    #: Series drawn on the price panel, in price units.
    price_overlays: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: Extra stacked panels: ``{panel title: frame of series}``.
    panels: dict[str, pd.DataFrame] = field(default_factory=dict)
    #: Column pairs on the price panel to shade between, e.g. band edges.
    bands: list[tuple[str, str]] = field(default_factory=list)
    #: Column pairs that describe one object and so should share a colour,
    #: without being shaded. The two edges of a second channel, for instance.
    pairs: list[tuple[str, str]] = field(default_factory=list)
    #: Horizontal reference lines, ``{panel title: [levels]}``.
    levels: dict[str, list[float]] = field(default_factory=dict)


class Strategy(ABC):
    """Turn prices into target weights."""

    key: str = "base"
    label: str = "Base strategy"
    category: str = "other"
    description: str = ""
    #: An honest note on the evidence, including the conditions where it fails.
    evidence: str = ""
    #: Asset classes the approach is normally used on. Advisory, not enforced.
    asset_classes: tuple[str, ...] = ()
    #: True when the strategy ranks symbols against each other and so needs the
    #: whole panel. False when it decides each symbol on its own.
    cross_sectional: bool = False
    #: Bar intervals the strategy makes sense on.
    intervals: tuple[str, ...] = ("1d", "1wk")
    PARAMS: tuple[ParamSpec, ...] = ()

    def __init__(self, **params):
        specs = {p.name: p for p in self.PARAMS}
        unknown = set(params) - set(specs)
        if unknown:
            raise ValueError(f"{self.key}: unknown parameters {sorted(unknown)}")
        resolved = {name: spec.default for name, spec in specs.items()}
        for name, value in params.items():
            resolved[name] = specs[name].coerce(value)
        self.params = resolved

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.params.items())
        return f"{type(self).__name__}({args})"

    @property
    def p(self) -> dict:
        """Shorthand for the resolved parameters."""
        return self.params

    @abstractmethod
    def generate_weights(self, prices: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Target weights, one column per symbol, one row per bar."""

    def chart(self, symbol: str, df: pd.DataFrame) -> StrategyChart:
        """Indicator frames a chart should draw for ``symbol``. Optional."""
        return StrategyChart()

    # -- helpers shared by concrete strategies -----------------------------

    @staticmethod
    def _panel(prices: dict[str, pd.DataFrame], column: str = "close") -> pd.DataFrame:
        """One column from every symbol, aligned on a shared index."""
        if not prices:
            raise ValueError("no price frames supplied")
        return pd.DataFrame({s: df[column] for s, df in prices.items()}).sort_index()

    @staticmethod
    def _empty_weights(index: pd.Index, symbols) -> pd.DataFrame:
        return pd.DataFrame(0.0, index=index, columns=list(symbols))

    @staticmethod
    def _normalise(weights: pd.DataFrame, gross: float = 1.0) -> pd.DataFrame:
        """Scale each row so gross exposure equals ``gross`` when anything is held."""
        total = weights.abs().sum(axis=1)
        scale = (gross / total.replace(0.0, np.nan)).fillna(0.0)
        return weights.mul(scale, axis=0)

    @staticmethod
    def _rebalance_mask(index: pd.DatetimeIndex, freq: str) -> pd.Series:
        """True on the first bar of each period, where a decision is allowed.

        ``freq`` is ``D`` (every bar), ``W``, ``M`` or ``Q``.

        The first bar of a period, not the last. Marking the last bar would mean
        asking whether the *next* bar starts a new month, which is future
        information: you cannot know at today's close that tomorrow is a holiday.
        Anchoring on the first bar of a period needs only the current timestamp,
        and it makes the signal identical whether the series ends today or ran
        to the end of the year.
        """
        if freq == "D":
            return pd.Series(True, index=index)
        rule = {"W": "W", "M": "M", "Q": "Q"}.get(freq)
        if rule is None:
            raise ValueError(f"unknown rebalance frequency {freq!r}")
        period = index.to_period(rule)
        first = np.empty(len(period), dtype=bool)
        if len(period):
            first[0] = True
            first[1:] = period[1:] != period[:-1]
        return pd.Series(first, index=index)

    @staticmethod
    def _hold(decisions: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
        """Carry a decision forward until the next bar where ``mask`` is True."""
        held = decisions.where(mask, other=np.nan)
        return held.ffill().fillna(0.0)


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

_REGISTRY: dict[str, type[Strategy]] = {}


def register(cls: type[Strategy]) -> type[Strategy]:
    """Class decorator that adds a strategy to the registry."""
    if cls.key in _REGISTRY:
        raise ValueError(f"strategy key {cls.key!r} is already registered")
    _REGISTRY[cls.key] = cls
    return cls


def get_strategy(key: str, **params) -> Strategy:
    """Instantiate a registered strategy by key."""
    try:
        cls = _REGISTRY[key]
    except KeyError:
        raise ValueError(f"unknown strategy {key!r}; expected one of {available()}") from None
    return cls(**params)


def strategy_class(key: str) -> type[Strategy]:
    """The registered class for ``key``, without instantiating it."""
    try:
        return _REGISTRY[key]
    except KeyError:
        raise ValueError(f"unknown strategy {key!r}; expected one of {available()}") from None


def available() -> list[str]:
    """Every registered strategy key."""
    return list(_REGISTRY)


def catalogue() -> pd.DataFrame:
    """A readable table of every strategy and what it claims to do."""
    rows = []
    for key, cls in _REGISTRY.items():
        rows.append(
            {
                "key": key,
                "label": cls.label,
                "category": cls.category,
                "cross_sectional": cls.cross_sectional,
                "asset_classes": ", ".join(cls.asset_classes) or "any",
                "description": cls.description.strip().split("\n")[0],
            }
        )
    return pd.DataFrame(rows).set_index("key")

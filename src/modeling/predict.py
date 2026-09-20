"""What a strategy wants to do right now.

A backtest answers "would this have worked". This answers "what is the position
today", which is the question anyone actually running a strategy asks. It reads
the last row of the weight frame and turns it into instructions against a
current book.
"""

from __future__ import annotations

import pandas as pd

from src.features import realised_volatility, rsi, trend_regime
from src.services.universe import get_instrument
from src.strategies.base import Strategy, get_strategy


def current_targets(strategy: Strategy, prices: dict[str, pd.DataFrame]) -> pd.Series:
    """The strategy's target weight per symbol on the most recent bar."""
    weights = strategy.generate_weights(prices)
    if weights.empty:
        return pd.Series(dtype=float)
    latest = weights.iloc[-1]
    latest.name = weights.index[-1]
    return latest


def signal_table(
    strategy: Strategy,
    prices: dict[str, pd.DataFrame],
    current_weights: dict[str, float] | None = None,
    capital: float | None = None,
) -> pd.DataFrame:
    """One row per symbol: where the strategy wants to be, and what that means.

    ``current_weights`` is your book today. The ``change`` column is what has to
    trade to reach the target; with ``capital`` it is also expressed in notional
    and in whole units at the latest close.
    """
    targets = current_targets(strategy, prices)
    if targets.empty:
        return pd.DataFrame()

    current = current_weights or {}
    rows = []
    for symbol in targets.index:
        df = prices[symbol]
        close = float(df["close"].iloc[-1])
        instrument = get_instrument(symbol)
        target = float(targets[symbol])
        held = float(current.get(symbol, 0.0))
        change = target - held

        row = {
            "symbol": symbol,
            "name": instrument.name,
            "asset_class": instrument.asset_class,
            "market": instrument.market,
            "close": close,
            "target_weight": target,
            "current_weight": held,
            "change": change,
            "action": "buy" if change > 1e-6 else ("sell" if change < -1e-6 else "hold"),
            "trend": _label_trend(df),
            "rsi_14": float(rsi(df["close"], 14).iloc[-1]),
            "realised_vol": float(realised_volatility(df["close"], 20).iloc[-1]),
            "as_of": df.index[-1],
        }
        if capital:
            row["notional"] = change * capital
            row["units"] = _units(row["notional"], close, instrument.asset_class)
        rows.append(row)

    frame = pd.DataFrame(rows).set_index("symbol")
    return frame.sort_values("target_weight", key=abs, ascending=False)


#: Asset classes that trade in fractions rather than whole units. Rounding a
#: crypto or currency position to a whole unit would report zero for any book
#: smaller than one bitcoin.
FRACTIONAL = {"crypto", "currency"}


def _units(notional: float, close: float, asset_class: str) -> float:
    """Units to trade, whole for share-like instruments and fractional otherwise."""
    if close <= 0:
        return 0.0
    raw = notional / close
    if asset_class in FRACTIONAL:
        return round(raw, 6)
    # Shares trade whole, and rounding toward zero never over-commits capital.
    return float(int(raw))


def _label_trend(df: pd.DataFrame, window: int = 200) -> str:
    """A plain-language read of the long-term trend, or where it is unknown."""
    if len(df) < window:
        return "unknown"
    regime = trend_regime(df["close"], window).iloc[-1]
    if pd.isna(regime):
        return "unknown"
    return "above long average" if regime > 0 else "below long average"


def compare_strategies(
    keys: list[str],
    prices: dict[str, pd.DataFrame],
    params: dict[str, dict] | None = None,
) -> pd.DataFrame:
    """Today's target weights from several strategies, side by side.

    Where several strategies want the same symbol, that agreement is the useful
    signal - and where they disagree, so is that.
    """
    params = params or {}
    columns = {}
    for key in keys:
        strategy = get_strategy(key, **params.get(key, {}))
        try:
            columns[strategy.label] = current_targets(strategy, prices)
        except ValueError as exc:
            columns[strategy.label] = pd.Series({"error": str(exc)})
    frame = pd.DataFrame(columns).fillna(0.0)
    frame["agreement"] = (frame.abs() > 1e-6).sum(axis=1)
    return frame.sort_values("agreement", ascending=False)


def summarise_book(signals: pd.DataFrame) -> dict:
    """Headline numbers for a signal table: exposure, count, and what to trade."""
    if signals.empty:
        return {"positions": 0, "gross_exposure": 0.0, "net_exposure": 0.0, "trades": 0}
    return {
        "positions": int((signals["target_weight"].abs() > 1e-6).sum()),
        "gross_exposure": float(signals["target_weight"].abs().sum()),
        "net_exposure": float(signals["target_weight"].sum()),
        "trades": int((signals["action"] != "hold").sum()),
        "as_of": signals["as_of"].max(),
    }

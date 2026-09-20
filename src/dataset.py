"""Loading, aligning and caching price data.

This is the single door into market data for the rest of the app. It resolves a
provider, caches what it fetches, and - the part that quietly matters most -
puts every symbol on a shared calendar before a strategy ever sees it.

Why alignment matters
---------------------
Crypto trades every day, foreign exchange five and a half days, US equities
fewer than that, and exchange holidays differ by country. Stack them on a union
index and every rolling window straddles gaps, so volatility and correlation
estimates come back as ``NaN`` and positions silently go to zero. Aligning first
is not housekeeping; it is the difference between a working backtest and an
empty one.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from src import config
from src.services.providers import (
    CSVProvider,
    ProviderError,
    fetch_with_fallback,
    get_provider,
)
from src.services.universe import get_instrument, universe_symbols

#: How to reconcile symbols that trade on different calendars.
ALIGNMENT_MODES = ("intersect", "union_ffill", "none")


def _cache_path(symbol: str, interval: str) -> Path:
    return CSVProvider().path_for(symbol, interval)


def _cache_is_fresh(path: Path, ttl_hours: float) -> bool:
    if not path.exists():
        return False
    if ttl_hours <= 0:
        return True
    return (time.time() - path.stat().st_mtime) < ttl_hours * 3600


def load_symbol(
    symbol: str,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    interval: str = config.DEFAULT_INTERVAL,
    provider: str = config.DEFAULT_PROVIDER,
    use_cache: bool = True,
    refresh: bool = False,
    allow_synthetic: bool = False,
) -> tuple[pd.DataFrame, str]:
    """Load one symbol's bars. Returns ``(frame, source_name)``.

    ``provider="auto"`` walks :data:`src.config.PROVIDER_CHAIN` and takes the
    first source that answers, so a missing network degrades instead of failing.
    Simulated bars are never substituted unless ``allow_synthetic`` is set, and
    the source name is returned so the caller can say where the data came from.
    """
    start = start or config.DEFAULT_START
    cache = _cache_path(symbol, interval)

    # The cache only short-circuits the automatic chain. Naming a provider is a
    # request for that provider's data, and quietly answering from cache would
    # make the source label wrong - which is the one thing this function must
    # never get wrong.
    if provider == "auto" and use_cache and not refresh and _cache_is_fresh(
        cache, config.CACHE_TTL_HOURS
    ):
        try:
            return CSVProvider().fetch(get_instrument(symbol), start, end, interval), "cache"
        except ProviderError:
            pass  # a stale or corrupt cache is not a reason to stop

    if provider == "auto":
        chain = config.PROVIDER_CHAIN
        if allow_synthetic:
            chain = tuple(chain) + (config.SYNTHETIC_PROVIDER,)
        df, source = fetch_with_fallback(symbol, start, end, interval, chain=chain)
    else:
        impl = get_provider(provider)
        df, source = impl.fetch(get_instrument(symbol), start, end, interval), provider

    if use_cache and source not in {"cache", "synthetic"}:
        CSVProvider().write(symbol, interval, df)
    return df, source


def align_frames(
    frames: dict[str, pd.DataFrame], mode: str = "intersect", min_bars: int = 30
) -> dict[str, pd.DataFrame]:
    """Put every frame on one calendar.

    ``intersect``    keep only timestamps every symbol quotes. Safest for
                     cross-asset work, and the default.
    ``union_ffill``  keep every timestamp and carry the last close forward. Use
                     when you want a symbol's full history preserved and accept
                     that its non-trading days show as zero return.
    ``none``         leave the frames alone.

    Symbols with fewer than ``min_bars`` rows are dropped, with their names
    returned to the caller through the log rather than failing the load.
    """
    if mode not in ALIGNMENT_MODES:
        raise ValueError(f"unknown alignment {mode!r}; expected one of {ALIGNMENT_MODES}")
    usable = {s: df for s, df in frames.items() if len(df) >= min_bars}
    if not usable or mode == "none":
        return usable

    if mode == "intersect":
        index = None
        for df in usable.values():
            index = df.index if index is None else index.intersection(df.index)
        if index is None or len(index) == 0:
            raise ValueError(
                "no timestamps are shared by every symbol; try align='union_ffill' "
                "or load markets with compatible calendars separately"
            )
        return {s: df.loc[index].copy() for s, df in usable.items()}

    index = None
    for df in usable.values():
        index = df.index if index is None else index.union(df.index)
    out = {}
    for s, df in usable.items():
        # Forward-fill price, but never invent volume on a day that did not trade.
        reindexed = df.reindex(index)
        reindexed[["open", "high", "low", "close"]] = reindexed[
            ["open", "high", "low", "close"]
        ].ffill()
        out[s] = reindexed.dropna(subset=["close"])
    shared = None
    for df in out.values():
        shared = df.index if shared is None else shared.intersection(df.index)
    return {s: df.loc[shared].copy() for s, df in out.items()}


def load_prices(
    symbols: list[str] | str,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    interval: str = config.DEFAULT_INTERVAL,
    provider: str = config.DEFAULT_PROVIDER,
    align: str = "intersect",
    use_cache: bool = True,
    refresh: bool = False,
    skip_failures: bool = True,
    allow_synthetic: bool = False,
) -> dict[str, pd.DataFrame]:
    """Load several symbols and return them on a shared calendar.

    With ``skip_failures`` a symbol that no provider can serve is left out
    rather than taking the whole load down. If nothing loads, that is an error.

    Each returned frame carries its provider in ``df.attrs["source"]``. Read it
    with :func:`source_report` and show it: a backtest whose data came partly
    from a simulator is not a backtest, and the only defence against presenting
    one as real is knowing where every bar came from."""
    if isinstance(symbols, str):
        symbols = [symbols]
    symbols = list(dict.fromkeys(s.upper().strip() for s in symbols))

    frames: dict[str, pd.DataFrame] = {}
    sources: dict[str, str] = {}
    failures: dict[str, str] = {}
    for symbol in symbols:
        try:
            frames[symbol], sources[symbol] = load_symbol(
                symbol, start, end, interval, provider, use_cache, refresh, allow_synthetic
            )
        except (ProviderError, ValueError) as exc:
            if not skip_failures:
                raise
            failures[symbol] = str(exc)

    if not frames:
        detail = "; ".join(f"{s}: {e}" for s, e in failures.items())
        raise ProviderError(f"no symbols could be loaded. {detail}")

    aligned = align_frames(frames, align)
    for symbol, df in aligned.items():
        df.attrs["symbol"] = symbol
        df.attrs["source"] = sources.get(symbol, "unknown")
        df.attrs["instrument"] = get_instrument(symbol)
        df.attrs["failures"] = dict(failures)
    return aligned


def load_universe(
    name: str = config.DEFAULT_UNIVERSE,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    interval: str = config.DEFAULT_INTERVAL,
    **kwargs,
) -> dict[str, pd.DataFrame]:
    """Load every symbol in a named universe."""
    return load_prices(universe_symbols(name), start, end, interval, **kwargs)


def close_panel(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Closing prices as one frame, symbols across the columns."""
    return pd.DataFrame({s: df["close"] for s, df in frames.items()}).sort_index()


def returns_panel(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Simple returns per symbol, aligned."""
    return close_panel(frames).pct_change(fill_method=None)


def source_report(frames: dict[str, pd.DataFrame]) -> pd.Series:
    """Which provider served each symbol."""
    return pd.Series({s: df.attrs.get("source", "unknown") for s, df in frames.items()})


def synthetic_symbols(frames: dict[str, pd.DataFrame]) -> list[str]:
    """Symbols whose bars are simulated rather than observed.

    Anything in this list makes every statistic computed from it fiction. Show
    it wherever results are shown.
    """
    return sorted(s for s, df in frames.items() if df.attrs.get("source") == "synthetic")


def coverage_report(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """What actually loaded: source, rows, date span, and any gaps."""
    rows = []
    for symbol, df in frames.items():
        inst = get_instrument(symbol)
        rows.append(
            {
                "symbol": symbol,
                "name": inst.name,
                "asset_class": inst.asset_class,
                "market": inst.market,
                "source": df.attrs.get("source", "unknown"),
                "bars": len(df),
                "start": df.index[0].date() if len(df) else None,
                "end": df.index[-1].date() if len(df) else None,
                "missing_close": int(df["close"].isna().sum()),
            }
        )
    return pd.DataFrame(rows).set_index("symbol").sort_index()

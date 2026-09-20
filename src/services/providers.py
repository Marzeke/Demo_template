"""Price data providers.

Every provider returns the same thing: a :class:`pandas.DataFrame` indexed by a
timezone-naive ``DatetimeIndex`` with the columns ``open, high, low, close,
volume``, sorted ascending and free of duplicate timestamps. The rest of the app
never learns which provider produced a frame.

Providers in this module
------------------------
``csv``        Local files under ``data/raw`` - the cache, and the way to bring
               your own history from any vendor.
``ibkr``       JSON snapshots exported from the Interactive Brokers connector.
``yfinance``   Yahoo Finance over the network.
``stooq``      Stooq CSV endpoint over the network. No API key.
``synthetic``  Deterministic regime-switching simulation. Needs no network, so
               the app and its tests always run.
"""

from __future__ import annotations

import hashlib
import io
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.services.universe import Instrument, get_instrument

OHLCV = ["open", "high", "low", "close", "volume"]

#: Intervals whose bars describe a whole session, so the time of day carries
#: no information. Their timestamps are floored to midnight, which is what
#: lets a US equity bar stamped 13:30Z line up with a crypto bar stamped 00:00Z.
SESSION_INTERVALS = ("1d", "1wk", "1mo")


class ProviderError(RuntimeError):
    """Raised when a provider cannot return usable data for a symbol."""


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def normalise(df: pd.DataFrame, symbol: str, interval: str = "1d") -> pd.DataFrame:
    """Coerce a provider frame into the canonical OHLCV shape.

    For daily and coarser bars the timestamp is floored to midnight, because a
    session bar's time of day is an artefact of the venue rather than data. This
    is what allows markets on different clocks to be aligned later.

    Raises :class:`ProviderError` when required columns are missing or no row
    survives cleaning, so a silently empty frame can never reach a strategy.
    """
    if df is None or len(df) == 0:
        raise ProviderError(f"no rows returned for {symbol}")

    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        # yfinance returns (field, ticker) columns for multi-symbol downloads.
        out.columns = [str(c[0]) for c in out.columns]
    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    out = out.rename(columns={"adj_close": "adj_close", "vol": "volume", "date": "timestamp"})

    if "timestamp" in out.columns:
        out = out.set_index("timestamp")

    missing = [c for c in ("open", "high", "low", "close") if c not in out.columns]
    if missing:
        raise ProviderError(f"{symbol}: provider frame is missing {missing}")

    if "volume" not in out.columns:
        out["volume"] = np.nan

    out.index = pd.to_datetime(out.index, utc=True, errors="coerce").tz_localize(None)
    out = out[~out.index.isna()]
    if interval in SESSION_INTERVALS:
        out.index = out.index.normalize()
    out = out[OHLCV].apply(pd.to_numeric, errors="coerce")
    out = out.dropna(subset=["open", "high", "low", "close"])
    out = out[~out.index.duplicated(keep="last")].sort_index()

    # A bar whose high is below its low, or whose close sits outside the range,
    # is corrupt. Repair the envelope rather than dropping the bar. Both bounds
    # are taken from the original four values: writing the high back first and
    # then reading it again would lose the original low.
    envelope = out[["open", "high", "low", "close"]]
    out["high"] = envelope.max(axis=1)
    out["low"] = envelope.min(axis=1)

    if len(out) == 0:
        raise ProviderError(f"{symbol}: no usable rows after cleaning")
    out.index.name = "timestamp"
    return out


def slice_window(df: pd.DataFrame, start: str | datetime | None, end: str | datetime | None) -> pd.DataFrame:
    """Restrict a frame to ``[start, end]`` inclusive, tolerating ``None``."""
    if start is not None:
        df = df[df.index >= pd.Timestamp(start)]
    if end is not None:
        df = df[df.index <= pd.Timestamp(end)]
    return df


# --------------------------------------------------------------------------
# Provider interface
# --------------------------------------------------------------------------

class PriceProvider(ABC):
    """Fetch OHLCV bars for one instrument."""

    name: str = "base"
    #: Intervals this provider can serve.
    intervals: tuple[str, ...] = ("1d",)

    def available(self) -> bool:
        """Whether this provider can be used in the current environment."""
        return True

    def supports(self, interval: str) -> bool:
        return interval in self.intervals

    @abstractmethod
    def fetch(
        self,
        instrument: Instrument,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Return canonical OHLCV bars, or raise :class:`ProviderError`."""


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------

class CSVProvider(PriceProvider):
    """Read bars from ``data/raw/<interval>/<SYMBOL>.csv``.

    This doubles as the on-disk cache written by :mod:`src.dataset`, and as the
    way to load history exported from any vendor the app does not speak to.
    """

    name = "csv"
    intervals = ("1d", "1wk", "1mo", "1h", "30m", "15m", "5m", "1m")

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else config.RAW_DATA_DIR

    def path_for(self, symbol: str, interval: str) -> Path:
        return self.root / interval / f"{symbol.upper()}.csv"

    def available(self) -> bool:
        return self.root.exists()

    def fetch(self, instrument, start=None, end=None, interval="1d") -> pd.DataFrame:
        path = self.path_for(instrument.symbol, interval)
        if not path.exists():
            raise ProviderError(f"no cached file at {path}")
        df = pd.read_csv(path, index_col=0)
        return slice_window(normalise(df, instrument.symbol, interval), start, end)

    def write(self, symbol: str, interval: str, df: pd.DataFrame) -> Path:
        """Persist ``df`` for ``symbol`` and return the file path."""
        path = self.path_for(symbol, interval)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path)
        return path


# --------------------------------------------------------------------------
# Interactive Brokers snapshots
# --------------------------------------------------------------------------

class IBKRSnapshotProvider(PriceProvider):
    """Read JSON exported from the Interactive Brokers price-history connector.

    The connector returns parallel arrays (``time``, ``open``, ``high``, ``low``,
    ``close``, ``volume``). Drop those payloads into ``data/external/ibkr`` as
    ``<SYMBOL>_<interval>.json`` and they become a first-class source.
    """

    name = "ibkr"
    intervals = ("1d", "1wk", "1mo", "1h", "30m", "15m", "5m", "1m")

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else config.IBKR_SNAPSHOT_DIR

    def available(self) -> bool:
        return self.root.exists() and any(self.root.glob("*.json"))

    def path_for(self, symbol: str, interval: str) -> Path:
        return self.root / f"{symbol.upper()}_{interval}.json"

    def fetch(self, instrument, start=None, end=None, interval="1d") -> pd.DataFrame:
        path = self.path_for(instrument.symbol, interval)
        if not path.exists():
            raise ProviderError(f"no IBKR snapshot at {path}")
        payload = json.loads(path.read_text())
        return slice_window(normalise(self.parse(payload), instrument.symbol, interval), start, end)

    @staticmethod
    def parse(payload: dict) -> pd.DataFrame:
        """Turn a connector payload's parallel arrays into a frame."""
        required = ("time", "open", "high", "low", "close")
        missing = [k for k in required if k not in payload]
        if missing:
            raise ProviderError(f"IBKR payload missing {missing}")
        lengths = {len(payload[k]) for k in required}
        if len(lengths) != 1:
            raise ProviderError("IBKR payload arrays have mismatched lengths")
        frame = pd.DataFrame(
            {
                "timestamp": payload["time"],
                "open": payload["open"],
                "high": payload["high"],
                "low": payload["low"],
                "close": payload["close"],
                "volume": payload.get("volume", [np.nan] * len(payload["time"])),
            }
        )
        return frame.set_index("timestamp")


# --------------------------------------------------------------------------
# Yahoo Finance
# --------------------------------------------------------------------------

class YFinanceProvider(PriceProvider):
    """Download bars from Yahoo Finance. Split- and dividend-adjusted."""

    name = "yfinance"
    intervals = ("1d", "1wk", "1mo", "1h", "30m", "15m", "5m", "1m")

    def available(self) -> bool:
        try:
            import yfinance  # noqa: F401
        except ImportError:
            return False
        return True

    def fetch(self, instrument, start=None, end=None, interval="1d") -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ProviderError("yfinance is not installed") from exc

        ticker = instrument.provider_symbol("yfinance")
        try:
            df = yf.download(
                ticker,
                start=start,
                end=end,
                interval=interval,
                auto_adjust=True,
                progress=False,
                threads=False,
            )
        except Exception as exc:  # network, rate limit, parse - all are "no data"
            raise ProviderError(f"yfinance failed for {ticker}: {exc}") from exc
        return slice_window(normalise(df, instrument.symbol, interval), start, end)


# --------------------------------------------------------------------------
# Stooq
# --------------------------------------------------------------------------

class StooqProvider(PriceProvider):
    """Download daily bars from Stooq's CSV endpoint. No API key required."""

    name = "stooq"
    intervals = ("1d", "1wk", "1mo")
    _STEP = {"1d": "d", "1wk": "w", "1mo": "m"}
    URL = "https://stooq.com/q/d/l/"

    def available(self) -> bool:
        try:
            import requests  # noqa: F401
        except ImportError:
            return False
        return True

    def fetch(self, instrument, start=None, end=None, interval="1d") -> pd.DataFrame:
        import requests

        if interval not in self._STEP:
            raise ProviderError(f"stooq does not serve {interval} bars")
        ticker = instrument.provider_symbol("stooq")
        try:
            resp = requests.get(
                self.URL, params={"s": ticker, "i": self._STEP[interval]}, timeout=30
            )
            resp.raise_for_status()
        except Exception as exc:
            raise ProviderError(f"stooq failed for {ticker}: {exc}") from exc
        text = resp.text.strip()
        if not text or text.lower().startswith("<") or "no data" in text.lower():
            raise ProviderError(f"stooq returned no data for {ticker}")
        df = pd.read_csv(io.StringIO(text))
        return slice_window(normalise(df, instrument.symbol, interval), start, end)


# --------------------------------------------------------------------------
# Synthetic
# --------------------------------------------------------------------------

class SyntheticProvider(PriceProvider):
    """Deterministic regime-switching price simulation.

    Bars are generated from a two-state Markov chain - a trending state and a
    choppy mean-reverting state - so that trend and mean-reversion strategies
    each get conditions they are built for. The seed is derived from the symbol,
    so the same ticker always produces the same history.

    This exists so the app, the demo and the test suite run with no network. It
    is a fixture, not a forecast, and results on it say nothing about a real
    market.
    """

    name = "synthetic"
    intervals = ("1d", "1wk", "1mo", "1h", "30m", "15m", "5m", "1m")

    #: Bars per calendar year, by interval, used to build the index.
    _FREQ = {"1d": "B", "1wk": "W-FRI", "1mo": "ME", "1h": "h", "30m": "30min",
             "15m": "15min", "5m": "5min", "1m": "1min"}

    def __init__(self, seed_salt: str = "charting") -> None:
        self.seed_salt = seed_salt

    def _seed(self, symbol: str) -> int:
        digest = hashlib.sha256(f"{self.seed_salt}:{symbol.upper()}".encode()).hexdigest()
        return int(digest[:8], 16)

    def fetch(self, instrument, start=None, end=None, interval="1d") -> pd.DataFrame:
        start_ts = pd.Timestamp(start) if start else pd.Timestamp(config.DEFAULT_START)
        end_ts = pd.Timestamp(end) if end else pd.Timestamp.today().normalize()
        if end_ts <= start_ts:
            raise ProviderError(f"{instrument.symbol}: end must be after start")

        freq = self._FREQ.get(interval, "B")
        index = pd.date_range(start_ts, end_ts, freq=freq)
        if len(index) < 3:
            raise ProviderError(f"{instrument.symbol}: window too short to simulate")

        ppy = config.PERIODS_PER_YEAR.get(interval, 252)
        rng = np.random.default_rng(self._seed(instrument.symbol))
        n = len(index)

        # Two-state regime chain: 0 = trending, 1 = choppy.
        stay = np.array([0.985, 0.975])
        regime = np.zeros(n, dtype=int)
        for t in range(1, n):
            regime[t] = regime[t - 1] if rng.random() < stay[regime[t - 1]] else 1 - regime[t - 1]

        base_vol = instrument.synthetic_vol / np.sqrt(ppy)
        drift = instrument.synthetic_drift / ppy

        # Trend state: persistent drift with a slowly flipping sign.
        trend_sign = np.sign(rng.standard_normal(1)[0]) or 1.0
        trend = np.zeros(n)
        for t in range(1, n):
            if regime[t] == 0:
                if rng.random() < 0.004:
                    trend_sign = -trend_sign
                trend[t] = trend_sign * base_vol * 0.55
            else:
                trend[t] = 0.0

        # Volatility clusters via a slow GARCH-like envelope.
        vol = np.empty(n)
        vol[0] = base_vol
        shocks = rng.standard_normal(n)
        for t in range(1, n):
            target = base_vol * (0.85 if regime[t] == 0 else 1.35)
            vol[t] = 0.94 * vol[t - 1] + 0.06 * target + 0.02 * abs(shocks[t - 1]) * base_vol

        rets = np.empty(n)
        rets[0] = 0.0
        for t in range(1, n):
            noise = shocks[t] * vol[t]
            # Choppy state pulls the last move back; trending state does not.
            pull = -0.22 * rets[t - 1] if regime[t] == 1 else 0.0
            rets[t] = drift + trend[t] + pull + noise

        close = 100.0 * np.exp(np.cumsum(rets))
        open_ = np.empty(n)
        open_[0] = close[0] * (1 - 0.15 * vol[0])
        open_[1:] = close[:-1] * np.exp(rng.standard_normal(n - 1) * vol[1:] * 0.25)
        spread = np.abs(rng.standard_normal(n)) * vol * 0.9 * close
        high = np.maximum(open_, close) + spread * 0.6
        low = np.minimum(open_, close) - spread * 0.6
        volume = np.round(
            1e6 * np.exp(rng.standard_normal(n) * 0.35) * (1 + 6 * np.abs(rets))
        )

        df = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=index,
        )
        df.index.name = "timestamp"
        return normalise(df, instrument.symbol, interval)


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

_REGISTRY: dict[str, type[PriceProvider]] = {
    "csv": CSVProvider,
    "ibkr": IBKRSnapshotProvider,
    "yfinance": YFinanceProvider,
    "stooq": StooqProvider,
    "synthetic": SyntheticProvider,
}


def provider_names() -> list[str]:
    """Every registered provider name."""
    return list(_REGISTRY)


def get_provider(name: str) -> PriceProvider:
    """Instantiate a provider by name."""
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise ValueError(f"unknown provider {name!r}; expected one of {provider_names()}") from None


def fetch_with_fallback(
    symbol: str,
    start=None,
    end=None,
    interval: str = "1d",
    chain: tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, str]:
    """Try each provider in ``chain`` and return the first frame that loads.

    Returns ``(frame, provider_name)``. Raises :class:`ProviderError` listing
    every attempt if none of them worked.
    """
    instrument = get_instrument(symbol)
    chain = chain or config.PROVIDER_CHAIN
    failures: list[str] = []
    for name in chain:
        try:
            provider = get_provider(name)
        except ValueError as exc:
            failures.append(str(exc))
            continue
        if not provider.available() or not provider.supports(interval):
            failures.append(f"{name}: unavailable or cannot serve {interval}")
            continue
        try:
            return provider.fetch(instrument, start, end, interval), name
        except ProviderError as exc:
            failures.append(f"{name}: {exc}")
        except Exception as exc:  # a provider must never take the app down
            failures.append(f"{name}: unexpected {type(exc).__name__}: {exc}")
    raise ProviderError(f"could not load {symbol} ({interval}). Tried: " + " | ".join(failures))

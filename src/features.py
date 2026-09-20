"""Technical indicators and derived features.

Every function takes and returns pandas objects, is vectorised, and never looks
ahead: the value at bar ``t`` uses only information available at the close of
bar ``t``. Warm-up periods come back as ``NaN`` rather than being back-filled,
so a strategy can see where it does not yet have a reading.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Moving averages
# --------------------------------------------------------------------------

def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average with a standard ``2/(span+1)`` decay."""
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def wilder_ma(series: pd.Series, window: int) -> pd.Series:
    """Wilder's smoothing, the average behind RSI, ATR and ADX."""
    return series.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()


# --------------------------------------------------------------------------
# Momentum and oscillators
# --------------------------------------------------------------------------

def roc(series: pd.Series, window: int) -> pd.Series:
    """Rate of change over ``window`` bars, as a fraction."""
    return series.pct_change(window)


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index, 0-100."""
    delta = series.diff()
    gain = wilder_ma(delta.clip(lower=0.0), window)
    loss = wilder_ma((-delta).clip(lower=0.0), window)
    rs = gain / loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    # A window with no losses is maximal strength, not undefined.
    return out.where(loss.ne(0.0) | gain.isna(), 100.0)


def macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    """MACD line, its signal line and the histogram between them."""
    line = ema(series, fast) - ema(series, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "histogram": line - sig})


def stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14, smooth: int = 3
) -> pd.DataFrame:
    """Stochastic oscillator %K and %D."""
    lowest = low.rolling(window, min_periods=window).min()
    highest = high.rolling(window, min_periods=window).max()
    span = (highest - lowest).replace(0.0, np.nan)
    k = 100.0 * (close - lowest) / span
    return pd.DataFrame({"k": k, "d": k.rolling(smooth, min_periods=smooth).mean()})


def zscore(series: pd.Series, window: int = 20) -> pd.Series:
    """Rolling z-score: how many standard deviations from the rolling mean."""
    mean = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std(ddof=0).replace(0.0, np.nan)
    return (series - mean) / std


# --------------------------------------------------------------------------
# Volatility and range
# --------------------------------------------------------------------------

def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """True range: the greater of today's range and either gap from yesterday."""
    prev_close = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average True Range."""
    return wilder_ma(true_range(high, low, close), window)


def realised_volatility(
    close: pd.Series, window: int = 20, periods_per_year: int = 252
) -> pd.Series:
    """Annualised standard deviation of log returns over a rolling window."""
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window, min_periods=window).std(ddof=0) * np.sqrt(periods_per_year)


def bollinger(series: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Bollinger bands, plus bandwidth and %B position within the band."""
    mid = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std(ddof=0)
    upper, lower = mid + num_std * std, mid - num_std * std
    width = (upper - lower).replace(0.0, np.nan)
    return pd.DataFrame(
        {
            "middle": mid,
            "upper": upper,
            "lower": lower,
            "bandwidth": (upper - lower) / mid.replace(0.0, np.nan),
            "percent_b": (series - lower) / width,
        }
    )


def keltner(
    high: pd.Series, low: pd.Series, close: pd.Series, window: int = 20, mult: float = 2.0
) -> pd.DataFrame:
    """Keltner channel: an EMA centre with ATR-scaled edges."""
    mid = ema(close, window)
    rng = atr(high, low, close, window)
    return pd.DataFrame({"middle": mid, "upper": mid + mult * rng, "lower": mid - mult * rng})


def donchian(high: pd.Series, low: pd.Series, window: int = 20) -> pd.DataFrame:
    """Donchian channel of the prior ``window`` bars.

    The channel is shifted by one bar so that a close *at* today's high does not
    count as a breakout of a channel that today's bar itself created.
    """
    upper = high.rolling(window, min_periods=window).max().shift(1)
    lower = low.rolling(window, min_periods=window).min().shift(1)
    return pd.DataFrame({"upper": upper, "lower": lower, "middle": (upper + lower) / 2.0})


# --------------------------------------------------------------------------
# Trend strength and direction
# --------------------------------------------------------------------------

def adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.DataFrame:
    """Average Directional Index with the +DI and -DI directional lines."""
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)

    rng = wilder_ma(true_range(high, low, close), window).replace(0.0, np.nan)
    plus_di = 100.0 * wilder_ma(plus_dm, window) / rng
    minus_di = 100.0 * wilder_ma(minus_dm, window) / rng
    denom = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / denom
    return pd.DataFrame({"adx": wilder_ma(dx, window), "plus_di": plus_di, "minus_di": minus_di})


def supertrend(
    high: pd.Series, low: pd.Series, close: pd.Series, window: int = 10, mult: float = 3.0
) -> pd.DataFrame:
    """Supertrend line and its direction (+1 up, -1 down).

    The band ratchets: it only ever tightens toward price while the trend holds,
    and resets when price closes through it.
    """
    rng = atr(high, low, close, window)
    hl2 = (high + low) / 2.0
    upper_basic = hl2 + mult * rng
    lower_basic = hl2 - mult * rng

    upper = upper_basic.to_numpy(copy=True)
    lower = lower_basic.to_numpy(copy=True)
    c = close.to_numpy()
    direction = np.ones(len(close))

    for i in range(1, len(close)):
        if np.isnan(upper_basic.iloc[i]):
            direction[i] = direction[i - 1]
            continue
        if not np.isnan(upper[i - 1]) and (upper_basic.iloc[i] > upper[i - 1] and c[i - 1] <= upper[i - 1]):
            upper[i] = upper[i - 1]
        if not np.isnan(lower[i - 1]) and (lower_basic.iloc[i] < lower[i - 1] and c[i - 1] >= lower[i - 1]):
            lower[i] = lower[i - 1]
        if c[i] > upper[i - 1]:
            direction[i] = 1.0
        elif c[i] < lower[i - 1]:
            direction[i] = -1.0
        else:
            direction[i] = direction[i - 1]

    line = np.where(direction > 0, lower, upper)
    out = pd.DataFrame({"supertrend": line, "direction": direction}, index=close.index)
    return out.where(rng.notna())


def ichimoku(
    high: pd.Series, low: pd.Series, close: pd.Series,
    conversion: int = 9, base: int = 26, span_b: int = 52,
) -> pd.DataFrame:
    """Ichimoku conversion, base and the two cloud spans."""
    def mid(n: int) -> pd.Series:
        return (high.rolling(n, min_periods=n).max() + low.rolling(n, min_periods=n).min()) / 2.0

    conv, bas = mid(conversion), mid(base)
    return pd.DataFrame(
        {
            "conversion": conv,
            "base": bas,
            "span_a": ((conv + bas) / 2.0).shift(base),
            "span_b": mid(span_b).shift(base),
            "lagging": close.shift(-base),
        }
    )


# --------------------------------------------------------------------------
# Volume
# --------------------------------------------------------------------------

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume.fillna(0.0)).cumsum()


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
         window: int | None = None) -> pd.Series:
    """Volume-weighted average price, cumulative or over a rolling window."""
    typical = (high + low + close) / 3.0
    vol = volume.fillna(0.0)
    if window is None:
        cum_vol = vol.cumsum().replace(0.0, np.nan)
        return (typical * vol).cumsum() / cum_vol
    num = (typical * vol).rolling(window, min_periods=window).sum()
    den = vol.rolling(window, min_periods=window).sum().replace(0.0, np.nan)
    return num / den


def volume_ratio(volume: pd.Series, window: int = 20) -> pd.Series:
    """Volume relative to its own rolling average. 1.0 means typical."""
    avg = volume.rolling(window, min_periods=window).mean().replace(0.0, np.nan)
    return volume / avg


# --------------------------------------------------------------------------
# Drawdown and regime
# --------------------------------------------------------------------------

def drawdown(equity: pd.Series) -> pd.Series:
    """Fractional drawdown from the running peak. Zero or negative."""
    peak = equity.cummax()
    return equity / peak.replace(0.0, np.nan) - 1.0


def trend_regime(close: pd.Series, window: int = 200) -> pd.Series:
    """+1 when price is above its long moving average, -1 below, NaN in warm-up."""
    long_ma = sma(close, window)
    return pd.Series(
        np.where(close.isna() | long_ma.isna(), np.nan, np.where(close >= long_ma, 1.0, -1.0)),
        index=close.index,
    )


def volatility_regime(close: pd.Series, window: int = 20, lookback: int = 252) -> pd.Series:
    """Percentile rank of current realised volatility within its own history.

    0.0 is the calmest reading in ``lookback`` bars, 1.0 the most violent.
    """
    vol = realised_volatility(close, window)
    return vol.rolling(lookback, min_periods=max(window, lookback // 4)).rank(pct=True)


# --------------------------------------------------------------------------
# Bulk helper
# --------------------------------------------------------------------------

def add_indicators(df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    """Return ``df`` with a standard indicator set appended.

    ``config`` overrides window lengths, e.g. ``{"rsi": 2, "sma_fast": 20}``.
    """
    cfg = {
        "sma_fast": 50, "sma_slow": 200, "ema_fast": 12, "ema_slow": 26,
        "rsi": 14, "atr": 14, "bb": 20, "donchian": 20, "adx": 14, "vol": 20,
    }
    cfg.update(config or {})

    out = df.copy()
    close, high, low = out["close"], out["high"], out["low"]

    out[f"sma_{cfg['sma_fast']}"] = sma(close, cfg["sma_fast"])
    out[f"sma_{cfg['sma_slow']}"] = sma(close, cfg["sma_slow"])
    out[f"ema_{cfg['ema_fast']}"] = ema(close, cfg["ema_fast"])
    out[f"ema_{cfg['ema_slow']}"] = ema(close, cfg["ema_slow"])
    out[f"rsi_{cfg['rsi']}"] = rsi(close, cfg["rsi"])
    out[f"atr_{cfg['atr']}"] = atr(high, low, close, cfg["atr"])
    out["realised_vol"] = realised_volatility(close, cfg["vol"])
    out["trend_regime"] = trend_regime(close, cfg["sma_slow"])

    for name, frame in (
        ("bb", bollinger(close, cfg["bb"])),
        ("dc", donchian(high, low, cfg["donchian"])),
        ("adx", adx(high, low, close, cfg["adx"])),
        ("macd", macd(close, cfg["ema_fast"], cfg["ema_slow"])),
    ):
        for col in frame.columns:
            out[f"{name}_{col}"] = frame[col]

    if "volume" in out.columns:
        out["obv"] = obv(close, out["volume"])
        out["volume_ratio"] = volume_ratio(out["volume"], cfg["vol"])
    return out

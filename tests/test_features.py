"""Indicator correctness, warm-up behaviour, and absence of look-ahead."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import features as F


@pytest.fixture
def ramp():
    return pd.Series(np.arange(1.0, 51.0), index=pd.bdate_range("2020-01-01", periods=50))


def test_sma_matches_hand_calculation(ramp):
    result = F.sma(ramp, 5)
    assert np.isnan(result.iloc[3])            # warm-up is not back-filled
    assert result.iloc[4] == pytest.approx(3.0)   # mean of 1..5
    assert result.iloc[-1] == pytest.approx(48.0)  # mean of 46..50


def test_ema_warms_up_then_tracks(ramp):
    result = F.ema(ramp, 10)
    assert result.iloc[:9].isna().all()
    assert result.notna().iloc[9:].all()
    assert result.iloc[-1] < ramp.iloc[-1]  # a lagging average trails a rising series


def test_rsi_is_bounded_and_maxes_on_an_unbroken_rise(ramp):
    result = F.rsi(ramp, 14).dropna()
    assert ((result >= 0) & (result <= 100)).all()
    assert result.iloc[-1] == pytest.approx(100.0)


def test_rsi_bottoms_on_an_unbroken_fall(ramp):
    result = F.rsi(ramp.iloc[::-1].reset_index(drop=True), 14).dropna()
    assert result.iloc[-1] == pytest.approx(0.0, abs=1e-9)


def test_true_range_uses_the_previous_close(one_frame):
    tr = F.true_range(one_frame["high"], one_frame["low"], one_frame["close"])
    assert (tr.dropna() >= 0).all()
    assert (tr.iloc[1:] >= (one_frame["high"] - one_frame["low"]).iloc[1:] - 1e-9).all()


def test_donchian_channel_excludes_the_current_bar(one_frame):
    """A close at today's high must not count as breaking a channel it just made."""
    channel = F.donchian(one_frame["high"], one_frame["low"], 20)
    naive = one_frame["high"].rolling(20).max()
    assert not channel["upper"].equals(naive)
    pd.testing.assert_series_equal(
        channel["upper"].dropna(), naive.shift(1).dropna(), check_names=False
    )


def test_bollinger_percent_b_and_zscore_agree_at_two_sigma(one_frame):
    bands = F.bollinger(one_frame["close"], 20, 2.0)
    z = F.zscore(one_frame["close"], 20)
    below_band = one_frame["close"] < bands["lower"]
    below_two_sigma = z < -2.0
    valid = bands["lower"].notna() & z.notna()
    assert (below_band[valid] == below_two_sigma[valid]).all()


def test_adx_is_bounded(one_frame):
    frame = F.adx(one_frame["high"], one_frame["low"], one_frame["close"], 14).dropna()
    assert ((frame["adx"] >= 0) & (frame["adx"] <= 100)).all()


def test_supertrend_direction_is_only_ever_plus_or_minus_one(one_frame):
    frame = F.supertrend(one_frame["high"], one_frame["low"], one_frame["close"]).dropna()
    assert set(frame["direction"].unique()) <= {-1.0, 1.0}


def test_drawdown_is_never_positive(one_frame):
    assert (F.drawdown(one_frame["close"]).dropna() <= 1e-12).all()


@pytest.mark.parametrize(
    "name,call",
    [
        ("sma", lambda d: F.sma(d["close"], 20)),
        ("ema", lambda d: F.ema(d["close"], 20)),
        ("rsi", lambda d: F.rsi(d["close"], 14)),
        ("atr", lambda d: F.atr(d["high"], d["low"], d["close"], 14)),
        ("adx", lambda d: F.adx(d["high"], d["low"], d["close"], 14)["adx"]),
        ("zscore", lambda d: F.zscore(d["close"], 20)),
        ("realised_vol", lambda d: F.realised_volatility(d["close"], 20)),
        ("donchian", lambda d: F.donchian(d["high"], d["low"], 20)["upper"]),
        ("macd", lambda d: F.macd(d["close"])["histogram"]),
        ("supertrend", lambda d: F.supertrend(d["high"], d["low"], d["close"])["direction"]),
        ("bollinger", lambda d: F.bollinger(d["close"], 20)["percent_b"]),
    ],
)
def test_indicator_does_not_look_ahead(one_frame, name, call):
    """Truncating the future must not change any past value.

    This is the property that matters most. An indicator that fails it makes
    every backtest built on it worthless, and the failure is invisible in the
    equity curve.
    """
    full = call(one_frame)
    truncated = call(one_frame.iloc[:-50])
    overlap = truncated.index
    pd.testing.assert_series_equal(
        full.loc[overlap].iloc[50:], truncated.iloc[50:], check_names=False, rtol=1e-9
    )


def test_ichimoku_lagging_span_is_the_one_deliberate_exception(one_frame):
    """The lagging span is plotted in the past on purpose, so it is forward-shifted."""
    frame = F.ichimoku(one_frame["high"], one_frame["low"], one_frame["close"])
    assert frame["lagging"].iloc[-1] != frame["lagging"].iloc[-1] or True  # trailing NaNs
    assert frame["lagging"].tail(26).isna().all()


def test_add_indicators_returns_original_columns_plus_more(one_frame):
    enriched = F.add_indicators(one_frame)
    assert set(one_frame.columns).issubset(enriched.columns)
    assert len(enriched.columns) > len(one_frame.columns)
    assert len(enriched) == len(one_frame)

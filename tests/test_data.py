"""Providers, normalisation, alignment and provenance."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src import config
from src.dataset import align_frames, coverage_report, load_prices, synthetic_symbols
from src.services.providers import (
    CSVProvider, IBKRSnapshotProvider, ProviderError, SyntheticProvider,
    fetch_with_fallback, normalise,
)
from src.services.universe import UNIVERSES, get_instrument, universe_symbols


def test_normalise_rejects_a_frame_with_no_price_columns():
    with pytest.raises(ProviderError, match="missing"):
        normalise(pd.DataFrame({"foo": [1, 2, 3]}), "TEST")


def test_normalise_rejects_an_empty_frame():
    with pytest.raises(ProviderError):
        normalise(pd.DataFrame(), "TEST")


def test_normalise_repairs_a_bar_whose_envelope_is_inverted():
    frame = pd.DataFrame(
        {"open": [10.0], "high": [5.0], "low": [12.0], "close": [11.0], "volume": [100]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    out = normalise(frame, "TEST")
    assert out["high"].iloc[0] == 12.0
    assert out["low"].iloc[0] == 5.0


def test_normalise_floors_session_bars_to_midnight():
    """US equity and crypto daily bars carry different clock times; they must align."""
    equity = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1]},
        index=pd.to_datetime(["2024-01-02T13:30:00Z"]),
    )
    crypto = equity.copy()
    crypto.index = pd.to_datetime(["2024-01-02T00:00:00Z"])
    assert normalise(equity, "A", "1d").index[0] == normalise(crypto, "B", "1d").index[0]


def test_normalise_keeps_the_clock_on_intraday_bars():
    frame = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1]},
        index=pd.to_datetime(["2024-01-02T14:30:00Z"]),
    )
    assert normalise(frame, "A", "30m").index[0].hour == 14


def test_normalise_drops_duplicate_timestamps():
    index = pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-03"])
    frame = pd.DataFrame(
        {"open": [1.0, 2.0, 3.0], "high": [1.0, 2.0, 3.0],
         "low": [1.0, 2.0, 3.0], "close": [1.0, 2.0, 3.0], "volume": [1, 2, 3]},
        index=index,
    )
    out = normalise(frame, "TEST")
    assert len(out) == 2
    assert out["close"].iloc[0] == 2.0  # the last quote for a timestamp wins


def test_synthetic_provider_is_deterministic():
    inst = get_instrument("SPY")
    first = SyntheticProvider().fetch(inst, "2020-01-01", "2021-01-01")
    second = SyntheticProvider().fetch(inst, "2020-01-01", "2021-01-01")
    pd.testing.assert_frame_equal(first, second)


def test_synthetic_provider_differs_between_symbols():
    a = SyntheticProvider().fetch(get_instrument("SPY"), "2020-01-01", "2021-01-01")
    b = SyntheticProvider().fetch(get_instrument("QQQ"), "2020-01-01", "2021-01-01")
    assert not np.allclose(a["close"].to_numpy(), b["close"].to_numpy())


def test_synthetic_bars_are_internally_consistent():
    frame = SyntheticProvider().fetch(get_instrument("BTCUSD"), "2020-01-01", "2021-01-01")
    assert (frame["high"] >= frame[["open", "close"]].max(axis=1) - 1e-9).all()
    assert (frame["low"] <= frame[["open", "close"]].min(axis=1) + 1e-9).all()
    assert (frame["close"] > 0).all()


def test_ibkr_parse_rejects_mismatched_arrays():
    with pytest.raises(ProviderError, match="mismatched"):
        IBKRSnapshotProvider.parse(
            {"time": ["2024-01-02", "2024-01-03"], "open": [1.0], "high": [1.0],
             "low": [1.0], "close": [1.0]}
        )


def test_ibkr_parse_accepts_a_payload_with_no_volume(tmp_path):
    """Currency bars carry no volume; that must not be an error."""
    payload = {
        "time": ["2024-01-02T00:00:00Z", "2024-01-03T00:00:00Z"],
        "open": [1.10, 1.11], "high": [1.12, 1.13],
        "low": [1.09, 1.10], "close": [1.11, 1.12],
    }
    path = tmp_path / "EURUSD_1d.json"
    path.write_text(json.dumps(payload))
    frame = IBKRSnapshotProvider(tmp_path).fetch(get_instrument("EURUSD"), interval="1d")
    assert len(frame) == 2
    assert frame["volume"].isna().all()


def test_csv_round_trip(tmp_path):
    provider = CSVProvider(tmp_path)
    original = SyntheticProvider().fetch(get_instrument("SPY"), "2022-01-01", "2022-06-01")
    provider.write("SPY", "1d", original)
    restored = provider.fetch(get_instrument("SPY"), interval="1d")
    pd.testing.assert_frame_equal(original, restored)


def test_fallback_reports_every_attempt_when_nothing_works():
    with pytest.raises(ProviderError, match="Tried:"):
        fetch_with_fallback("NOT_A_REAL_TICKER_XYZ", chain=("csv", "ibkr"))


def test_fallback_reaches_the_simulator_when_it_is_in_the_chain():
    frame, source = fetch_with_fallback("SPY", "2022-01-01", "2022-06-01", chain=("synthetic",))
    assert source == "synthetic"
    assert len(frame) > 50


def test_synthetic_is_not_in_the_default_chain():
    """A failed download must never be papered over with simulated bars."""
    assert "synthetic" not in config.PROVIDER_CHAIN


def test_intersect_alignment_gives_every_symbol_the_same_index(panel):
    indexes = [df.index for df in panel.values()]
    for other in indexes[1:]:
        assert other.equals(indexes[0])


def test_intersect_alignment_drops_unshared_timestamps():
    index_a = pd.bdate_range("2024-01-01", periods=10)
    index_b = pd.date_range("2024-01-01", periods=10, freq="D")
    frames = {}
    for name, index in (("A", index_a), ("B", index_b)):
        frames[name] = pd.DataFrame(
            {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=index
        )
    aligned = align_frames(frames, "intersect", min_bars=1)
    assert len(aligned["A"]) == len(aligned["B"]) <= 10


def test_alignment_raises_when_no_timestamp_is_shared():
    frames = {}
    for name, start in (("A", "2024-01-01"), ("B", "2025-01-01")):
        index = pd.bdate_range(start, periods=40)
        frames[name] = pd.DataFrame(
            {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=index
        )
    with pytest.raises(ValueError, match="no timestamps are shared"):
        align_frames(frames, "intersect", min_bars=1)


def test_alignment_rejects_an_unknown_mode(panel):
    with pytest.raises(ValueError, match="unknown alignment"):
        align_frames(panel, "sideways")


def test_load_prices_labels_simulated_data():
    frames = load_prices(["SPY"], "2022-01-01", "2022-12-31",
                         provider="synthetic", use_cache=False)
    assert synthetic_symbols(frames) == ["SPY"]
    assert coverage_report(frames).loc["SPY", "source"] == "synthetic"


def test_load_prices_skips_a_symbol_no_provider_can_serve():
    frames = load_prices(
        ["SPY", "NOT_A_REAL_TICKER_XYZ"], "2022-01-01", "2022-12-31",
        provider="synthetic", use_cache=False,
    )
    assert "SPY" in frames


def test_load_prices_raises_when_nothing_loads():
    with pytest.raises(ProviderError, match="no symbols could be loaded"):
        load_prices(["NOPE_A", "NOPE_B"], provider="csv", use_cache=False)


def test_every_universe_names_catalogued_symbols():
    for name in UNIVERSES:
        for symbol in universe_symbols(name):
            assert get_instrument(symbol).name, f"{name}: {symbol} has no catalogue entry"


def test_unknown_symbol_gets_a_usable_stub():
    inst = get_instrument("zzzz")
    assert inst.symbol == "ZZZZ"
    assert inst.provider_symbol("yfinance") == "ZZZZ"

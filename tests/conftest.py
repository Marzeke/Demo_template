"""Shared fixtures.

Tests run against the deterministic synthetic provider, so they need no network
and give the same answer every time. Where real bars happen to be cached in the
repository they are used instead, which makes the suite a smoke test of the real
data path as well.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dataset import align_frames  # noqa: E402
from src.services.providers import SyntheticProvider  # noqa: E402
from src.services.universe import get_instrument  # noqa: E402

SYMBOLS = ["SPY", "QQQ", "TLT", "GLD", "EEM", "XLK"]
START, END = "2018-01-01", "2024-12-31"


def _simulate(symbol: str, interval: str = "1d"):
    return SyntheticProvider().fetch(get_instrument(symbol), START, END, interval)


@pytest.fixture(scope="session")
def one_frame():
    """A single symbol's daily bars."""
    return _simulate("SPY")


@pytest.fixture(scope="session")
def panel():
    """Several symbols on a shared calendar."""
    return align_frames({s: _simulate(s) for s in SYMBOLS}, "intersect")


@pytest.fixture(scope="session")
def intraday_panel():
    """Intraday bars, for the strategies that need a session."""
    frames = {
        s: SyntheticProvider().fetch(get_instrument(s), "2024-01-01", "2024-04-01", "1h")
        for s in ("SPY", "QQQ")
    }
    return align_frames(frames, "intersect")

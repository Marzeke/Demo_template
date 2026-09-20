"""Project paths, defaults and environment configuration."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

PROJ_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJ_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
INTERIM_DATA_DIR = DATA_DIR / "interim"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EXTERNAL_DATA_DIR = DATA_DIR / "external"
IBKR_SNAPSHOT_DIR = EXTERNAL_DATA_DIR / "ibkr"

MODELS_DIR = PROJ_ROOT / "models"
REPORTS_DIR = PROJ_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

for _d in (RAW_DATA_DIR, INTERIM_DATA_DIR, PROCESSED_DATA_DIR, IBKR_SNAPSHOT_DIR, FIGURES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Data defaults
# --------------------------------------------------------------------------

#: Order the loader falls back through when ``provider="auto"``.
#:
#: ``synthetic`` is deliberately NOT in this chain. Simulated bars that quietly
#: stand in for a symbol whose download failed will produce a backtest result
#: that looks real and is not, and a trend strategy in particular scores
#: absurdly well on simulated data. Synthetic data is opt-in, through
#: ``allow_synthetic=True`` or ``provider="synthetic"``, and is always labelled.
PROVIDER_CHAIN: tuple[str, ...] = tuple(
    p.strip()
    for p in os.getenv("PROVIDER_CHAIN", "csv,ibkr,yfinance,stooq").split(",")
    if p.strip()
)

#: Appended to the chain only when synthetic data is explicitly allowed.
SYNTHETIC_PROVIDER = "synthetic"

DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "auto")
DEFAULT_INTERVAL = os.getenv("DEFAULT_INTERVAL", "1d")
DEFAULT_START = os.getenv("DEFAULT_START", "2015-01-01")
DEFAULT_UNIVERSE = os.getenv("DEFAULT_UNIVERSE", "us_sectors")
CACHE_TTL_HOURS = float(os.getenv("CACHE_TTL_HOURS", "12"))

#: Bars per year, by interval. Used to annualise return and risk.
PERIODS_PER_YEAR = {
    "1d": 252,
    "1wk": 52,
    "1mo": 12,
    "1h": 252 * 7,
    "30m": 252 * 13,
    "15m": 252 * 26,
    "5m": 252 * 78,
    "1m": 252 * 390,
}

# --------------------------------------------------------------------------
# Backtest defaults
# --------------------------------------------------------------------------

INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "100000"))
#: Round-turn commission in basis points of traded notional.
COMMISSION_BPS = float(os.getenv("COMMISSION_BPS", "2.0"))
#: Slippage in basis points applied to every traded unit of notional.
SLIPPAGE_BPS = float(os.getenv("SLIPPAGE_BPS", "3.0"))
#: Cash earns this annual rate when the strategy is flat.
CASH_YIELD = float(os.getenv("CASH_YIELD", "0.0"))
#: Annual volatility a volatility-targeted strategy aims at.
TARGET_VOLATILITY = float(os.getenv("TARGET_VOLATILITY", "0.15"))
#: Hard cap on gross exposure, applied after any volatility scaling.
MAX_LEVERAGE = float(os.getenv("MAX_LEVERAGE", "1.5"))
#: Risk-free rate used for Sharpe and Sortino.
RISK_FREE_RATE = float(os.getenv("RISK_FREE_RATE", "0.02"))

THEME_MODE = os.getenv("THEME_MODE", "light")
CANDLE_SCHEME = os.getenv("CANDLE_SCHEME", "classic")

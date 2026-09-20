"""Catalogue of instruments and ready-made universes across markets.

One :class:`Instrument` carries the symbol spellings every provider needs, so the
rest of the app talks in canonical symbols and never in provider dialects.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: Broad asset-class buckets used for filtering and for the correlation view.
ASSET_CLASSES = (
    "equity_index",
    "equity_sector",
    "equity_single",
    "fixed_income",
    "commodity",
    "currency",
    "crypto",
    "volatility",
)


@dataclass(frozen=True)
class Instrument:
    """A tradeable thing, with the identifiers each data provider expects."""

    symbol: str
    name: str
    asset_class: str
    market: str
    currency: str = "USD"
    yahoo: str | None = None
    stooq: str | None = None
    ibkr_conid: int | None = None
    ibkr_sectype: str = "STK"
    ibkr_exchange: str | None = None
    #: Typical annualised volatility. Only used to seed the synthetic provider.
    synthetic_vol: float = 0.18
    synthetic_drift: float = 0.06

    def provider_symbol(self, provider: str) -> str:
        """Return the ticker spelling ``provider`` expects for this instrument."""
        if provider == "yfinance":
            return self.yahoo or self.symbol
        if provider == "stooq":
            return self.stooq or f"{self.symbol.lower()}.us"
        return self.symbol


def _inst(symbol, name, asset_class, market, **kw) -> Instrument:
    return Instrument(symbol=symbol, name=name, asset_class=asset_class, market=market, **kw)


# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------

_CATALOGUE: list[Instrument] = [
    # --- US broad equity ----------------------------------------------------
    _inst("SPY", "S&P 500 ETF", "equity_index", "US", yahoo="SPY", ibkr_conid=756733,
          ibkr_exchange="ARCA", synthetic_vol=0.16, synthetic_drift=0.09),
    _inst("QQQ", "Nasdaq 100 ETF", "equity_index", "US", yahoo="QQQ", ibkr_conid=320227571,
          ibkr_exchange="NASDAQ", synthetic_vol=0.22, synthetic_drift=0.13),
    _inst("IWM", "Russell 2000 ETF", "equity_index", "US", yahoo="IWM",
          synthetic_vol=0.22, synthetic_drift=0.06),
    _inst("DIA", "Dow Jones 30 ETF", "equity_index", "US", yahoo="DIA",
          synthetic_vol=0.15, synthetic_drift=0.07),
    _inst("MDY", "S&P Midcap 400 ETF", "equity_index", "US", yahoo="MDY",
          synthetic_vol=0.19, synthetic_drift=0.07),
    _inst("RSP", "S&P 500 Equal Weight ETF", "equity_index", "US", yahoo="RSP",
          synthetic_vol=0.17, synthetic_drift=0.07),

    # --- US sectors (the rotation universe) ---------------------------------
    _inst("XLK", "Technology", "equity_sector", "US", yahoo="XLK", synthetic_vol=0.24, synthetic_drift=0.15),
    _inst("XLF", "Financials", "equity_sector", "US", yahoo="XLF", synthetic_vol=0.21, synthetic_drift=0.08),
    _inst("XLV", "Health Care", "equity_sector", "US", yahoo="XLV", synthetic_vol=0.16, synthetic_drift=0.05),
    _inst("XLE", "Energy", "equity_sector", "US", yahoo="XLE", synthetic_vol=0.30, synthetic_drift=0.06),
    _inst("XLI", "Industrials", "equity_sector", "US", yahoo="XLI", synthetic_vol=0.19, synthetic_drift=0.08),
    _inst("XLY", "Consumer Discretionary", "equity_sector", "US", yahoo="XLY", synthetic_vol=0.22, synthetic_drift=0.09),
    _inst("XLP", "Consumer Staples", "equity_sector", "US", yahoo="XLP", synthetic_vol=0.13, synthetic_drift=0.05),
    _inst("XLU", "Utilities", "equity_sector", "US", yahoo="XLU", synthetic_vol=0.16, synthetic_drift=0.06),
    _inst("XLB", "Materials", "equity_sector", "US", yahoo="XLB", synthetic_vol=0.20, synthetic_drift=0.06),
    _inst("XLRE", "Real Estate", "equity_sector", "US", yahoo="XLRE", synthetic_vol=0.20, synthetic_drift=0.03),
    _inst("XLC", "Communication Services", "equity_sector", "US", yahoo="XLC", synthetic_vol=0.22, synthetic_drift=0.11),

    # --- US single names ----------------------------------------------------
    _inst("AAPL", "Apple", "equity_single", "US", yahoo="AAPL", synthetic_vol=0.28, synthetic_drift=0.15),
    _inst("MSFT", "Microsoft", "equity_single", "US", yahoo="MSFT", synthetic_vol=0.26, synthetic_drift=0.16),
    _inst("NVDA", "NVIDIA", "equity_single", "US", yahoo="NVDA", synthetic_vol=0.50, synthetic_drift=0.35),
    _inst("AMZN", "Amazon", "equity_single", "US", yahoo="AMZN", synthetic_vol=0.32, synthetic_drift=0.14),
    _inst("GOOGL", "Alphabet", "equity_single", "US", yahoo="GOOGL", synthetic_vol=0.29, synthetic_drift=0.13),
    _inst("META", "Meta Platforms", "equity_single", "US", yahoo="META", synthetic_vol=0.38, synthetic_drift=0.15),
    _inst("TSLA", "Tesla", "equity_single", "US", yahoo="TSLA", synthetic_vol=0.55, synthetic_drift=0.18),
    _inst("JPM", "JPMorgan Chase", "equity_single", "US", yahoo="JPM", synthetic_vol=0.24, synthetic_drift=0.10),

    # --- International equity ----------------------------------------------
    _inst("EFA", "Developed ex-US", "equity_index", "Global", yahoo="EFA", synthetic_vol=0.17, synthetic_drift=0.05),
    _inst("EEM", "Emerging Markets", "equity_index", "Global", yahoo="EEM", synthetic_vol=0.21, synthetic_drift=0.03),
    _inst("EWJ", "Japan", "equity_index", "Japan", yahoo="EWJ", synthetic_vol=0.17, synthetic_drift=0.05),
    _inst("EWA", "Australia", "equity_index", "Australia", yahoo="EWA", synthetic_vol=0.19, synthetic_drift=0.05),
    _inst("FXI", "China Large Cap", "equity_index", "China", yahoo="FXI", synthetic_vol=0.27, synthetic_drift=0.01),
    _inst("EWU", "United Kingdom", "equity_index", "UK", yahoo="EWU", synthetic_vol=0.18, synthetic_drift=0.04),
    _inst("EWG", "Germany", "equity_index", "Germany", yahoo="EWG", synthetic_vol=0.21, synthetic_drift=0.05),
    _inst("INDA", "India", "equity_index", "India", yahoo="INDA", synthetic_vol=0.19, synthetic_drift=0.08),

    # --- Fixed income -------------------------------------------------------
    _inst("TLT", "US Treasury 20+yr", "fixed_income", "US", yahoo="TLT", synthetic_vol=0.16, synthetic_drift=0.00),
    _inst("IEF", "US Treasury 7-10yr", "fixed_income", "US", yahoo="IEF", synthetic_vol=0.07, synthetic_drift=0.01),
    _inst("SHY", "US Treasury 1-3yr", "fixed_income", "US", yahoo="SHY", synthetic_vol=0.02, synthetic_drift=0.02),
    _inst("LQD", "Investment Grade Credit", "fixed_income", "US", yahoo="LQD", synthetic_vol=0.08, synthetic_drift=0.02),
    _inst("HYG", "High Yield Credit", "fixed_income", "US", yahoo="HYG", synthetic_vol=0.09, synthetic_drift=0.04),
    _inst("BNDX", "Global Bonds ex-US", "fixed_income", "Global", yahoo="BNDX", synthetic_vol=0.05, synthetic_drift=0.01),

    # --- Commodities --------------------------------------------------------
    _inst("GLD", "Gold", "commodity", "Global", yahoo="GLD", synthetic_vol=0.15, synthetic_drift=0.08),
    _inst("SLV", "Silver", "commodity", "Global", yahoo="SLV", synthetic_vol=0.28, synthetic_drift=0.06),
    _inst("USO", "Crude Oil", "commodity", "Global", yahoo="USO", synthetic_vol=0.35, synthetic_drift=0.01),
    _inst("DBC", "Broad Commodities", "commodity", "Global", yahoo="DBC", synthetic_vol=0.17, synthetic_drift=0.03),
    _inst("DBA", "Agriculture", "commodity", "Global", yahoo="DBA", synthetic_vol=0.15, synthetic_drift=0.02),
    _inst("COPX", "Copper Miners", "commodity", "Global", yahoo="COPX", synthetic_vol=0.34, synthetic_drift=0.06),

    # --- Currencies ---------------------------------------------------------
    _inst("EURUSD", "Euro / US Dollar", "currency", "FX", yahoo="EURUSD=X", ibkr_sectype="CASH",
          synthetic_vol=0.08, synthetic_drift=0.00),
    _inst("GBPUSD", "Sterling / US Dollar", "currency", "FX", yahoo="GBPUSD=X", ibkr_sectype="CASH",
          synthetic_vol=0.09, synthetic_drift=0.00),
    _inst("USDJPY", "US Dollar / Yen", "currency", "FX", yahoo="USDJPY=X", ibkr_sectype="CASH",
          synthetic_vol=0.10, synthetic_drift=0.01),
    _inst("AUDUSD", "Aussie / US Dollar", "currency", "FX", yahoo="AUDUSD=X", ibkr_sectype="CASH",
          synthetic_vol=0.10, synthetic_drift=0.00),
    _inst("USDCAD", "US Dollar / Canadian Dollar", "currency", "FX", yahoo="USDCAD=X", ibkr_sectype="CASH",
          synthetic_vol=0.07, synthetic_drift=0.00),
    _inst("DXY", "US Dollar Index ETF", "currency", "FX", yahoo="UUP", synthetic_vol=0.08, synthetic_drift=0.01),

    # --- Crypto -------------------------------------------------------------
    _inst("BTCUSD", "Bitcoin", "crypto", "Crypto", yahoo="BTC-USD", ibkr_sectype="CRYPTO",
          synthetic_vol=0.60, synthetic_drift=0.35),
    _inst("ETHUSD", "Ethereum", "crypto", "Crypto", yahoo="ETH-USD", ibkr_sectype="CRYPTO",
          synthetic_vol=0.72, synthetic_drift=0.25),
    _inst("SOLUSD", "Solana", "crypto", "Crypto", yahoo="SOL-USD", ibkr_sectype="CRYPTO",
          synthetic_vol=0.95, synthetic_drift=0.30),

    # --- Volatility ---------------------------------------------------------
    _inst("VIXY", "Short-Term VIX Futures", "volatility", "US", yahoo="VIXY",
          synthetic_vol=0.70, synthetic_drift=-0.35),
]

CATALOGUE: dict[str, Instrument] = {i.symbol: i for i in _CATALOGUE}


# --------------------------------------------------------------------------
# Named universes
# --------------------------------------------------------------------------

UNIVERSES: dict[str, dict] = {
    "us_core": {
        "label": "US core indices",
        "description": "Large, mid and small cap US equity benchmarks.",
        "symbols": ["SPY", "QQQ", "IWM", "DIA", "MDY", "RSP"],
    },
    "us_sectors": {
        "label": "US equity sectors",
        "description": "The eleven S&P sector ETFs. The classic rotation universe.",
        "symbols": ["XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"],
    },
    "megacap_tech": {
        "label": "Mega-cap technology",
        "description": "The largest US technology and platform names.",
        "symbols": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"],
    },
    "global_equity": {
        "label": "Global equity regions",
        "description": "Regional equity exposure outside a single home market.",
        "symbols": ["SPY", "EFA", "EEM", "EWJ", "EWA", "EWU", "EWG", "FXI", "INDA"],
    },
    "cross_asset": {
        "label": "Cross-asset macro",
        "description": "Equities, bonds, commodities, currency and crypto in one sleeve.",
        "symbols": ["SPY", "EFA", "EEM", "TLT", "IEF", "LQD", "HYG", "GLD", "DBC", "USO", "BTCUSD", "DXY"],
    },
    "fx_majors": {
        "label": "FX majors",
        "description": "The most liquid currency pairs.",
        "symbols": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"],
    },
    "commodities": {
        "label": "Commodities",
        "description": "Metals, energy and agriculture.",
        "symbols": ["GLD", "SLV", "USO", "DBC", "DBA", "COPX"],
    },
    "crypto": {
        "label": "Crypto majors",
        "description": "The largest digital assets. Highest volatility in the catalogue.",
        "symbols": ["BTCUSD", "ETHUSD", "SOLUSD"],
    },
    "fixed_income": {
        "label": "Fixed income",
        "description": "Duration and credit exposure across the curve.",
        "symbols": ["TLT", "IEF", "SHY", "LQD", "HYG", "BNDX"],
    },
    "asia_pacific": {
        "label": "Asia Pacific",
        "description": "Regional equity markets across Asia and Australia.",
        "symbols": ["EWJ", "EWA", "FXI", "INDA", "EEM"],
    },
}


def get_instrument(symbol: str) -> Instrument:
    """Return the catalogued :class:`Instrument`, or a sensible stub if unknown.

    Unknown symbols are not an error: the app must accept a ticker the catalogue
    has never seen and hand it straight to the provider.
    """
    key = symbol.upper().strip()
    if key in CATALOGUE:
        return CATALOGUE[key]
    return Instrument(symbol=key, name=key, asset_class="equity_single", market="Unknown", yahoo=key)


def universe_symbols(name: str) -> list[str]:
    """Symbols in the named universe."""
    try:
        return list(UNIVERSES[name]["symbols"])
    except KeyError:
        raise ValueError(f"unknown universe {name!r}; expected one of {sorted(UNIVERSES)}") from None


def universe_instruments(name: str) -> list[Instrument]:
    """Instruments in the named universe."""
    return [get_instrument(s) for s in universe_symbols(name)]


def all_symbols() -> list[str]:
    """Every catalogued symbol, sorted."""
    return sorted(CATALOGUE)


def symbols_by_asset_class(asset_class: str) -> list[str]:
    """Catalogued symbols in one asset class."""
    return sorted(s for s, i in CATALOGUE.items() if i.asset_class == asset_class)


def with_conid(symbol: str, conid: int, sectype: str = "STK", exchange: str | None = None) -> Instrument:
    """Return a copy of the instrument carrying an Interactive Brokers contract id."""
    inst = get_instrument(symbol)
    return replace(inst, ibkr_conid=conid, ibkr_sectype=sectype, ibkr_exchange=exchange)

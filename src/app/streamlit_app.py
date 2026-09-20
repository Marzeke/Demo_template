"""Interactive charting and strategy analysis.

    python -m src.cli app          # or: streamlit run src/app/streamlit_app.py

Parameter controls are generated from each strategy's ``PARAMS`` metadata, so
adding a strategy adds its controls with no work here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src import config, plots  # noqa: E402
from src.backtest.engine import (  # noqa: E402
    BacktestConfig, buy_and_hold_result, run_backtest,
)
from src.backtest.metrics import comparison_table  # noqa: E402
from src.backtest.walkforward import (  # noqa: E402
    bootstrap_confidence, parameter_sweep, walk_forward,
)
from src.dataset import (  # noqa: E402
    coverage_report, load_prices, returns_panel, synthetic_symbols,
)
from src.modeling.predict import compare_strategies, signal_table, summarise_book  # noqa: E402
from src.modeling.train import DEFAULT_GRIDS  # noqa: E402
from src.services.universe import UNIVERSES, all_symbols, get_instrument  # noqa: E402
from src.strategies import HEADLINE, available, get_strategy, strategy_class  # noqa: E402
from src.theme import BRAND_BLUE, BRAND_MIDDLE_BLUE  # noqa: E402

st.set_page_config(page_title="Charting analysis", page_icon="~", layout="wide")

st.markdown(
    f"""
    <style>
      .block-container {{ padding-top: 2.2rem; max-width: 1500px; }}
      h1, h2, h3 {{ color: {BRAND_BLUE}; }}
      div[data-testid="stMetricValue"] {{ color: {BRAND_BLUE}; font-size: 1.6rem; }}
      div[data-testid="stSidebarUserContent"] h2 {{ font-size: 1.05rem; }}
      .stTabs [data-baseweb="tab-list"] {{ gap: 2px; }}
      .stTabs [aria-selected="true"] {{ border-bottom: 3px solid {BRAND_MIDDLE_BLUE}; }}
    </style>
    """,
    unsafe_allow_html=True,
)

PERCENT_STATS = {"cagr", "annual_volatility", "max_drawdown", "hit_rate", "exposure", "total_return"}
HEADLINE_STATS = ["cagr", "annual_volatility", "sharpe", "sortino", "calmar",
                  "max_drawdown", "hit_rate", "exposure", "annual_turnover"]


@st.cache_data(show_spinner="Loading prices...", ttl=3600)
def cached_prices(symbols, start, end, interval, provider, align, allow_synthetic):
    return load_prices(list(symbols), start, end, interval, provider,
                       align=align, allow_synthetic=allow_synthetic)


def parameter_controls(key: str, columns, prefix: str = "") -> dict:
    """Build a control for every parameter a strategy declares.

    The controls come from the strategy's own ``PARAMS`` metadata, so a new
    strategy gets its interface for free and nothing here needs editing.
    """
    cls = strategy_class(key)
    values = {}
    for index, spec in enumerate(cls.PARAMS):
        holder = columns[index % len(columns)]
        widget_key = f"{prefix}{key}:{spec.name}"
        if spec.kind == "bool":
            values[spec.name] = holder.checkbox(
                spec.label, value=bool(spec.default), help=spec.help, key=widget_key)
        elif spec.kind == "choice":
            options = list(spec.choices)
            values[spec.name] = holder.selectbox(
                spec.label, options, index=options.index(spec.default),
                help=spec.help, key=widget_key)
        elif spec.kind == "int":
            values[spec.name] = holder.number_input(
                spec.label, min_value=int(spec.minimum), max_value=int(spec.maximum),
                value=int(spec.default), step=int(spec.step or 1),
                help=spec.help, key=widget_key)
        else:
            values[spec.name] = holder.number_input(
                spec.label, min_value=float(spec.minimum), max_value=float(spec.maximum),
                value=float(spec.default), step=float(spec.step or 0.05),
                help=spec.help, key=widget_key)
    return values


def format_stats(table: pd.DataFrame) -> pd.DataFrame:
    out = table.copy()
    for column in out.columns:
        out[column] = (out[column] * 100).round(1) if column in PERCENT_STATS else out[column].round(2)
    return out


def stat_style(table: pd.DataFrame):
    """Percent columns get a suffix; nothing is encoded by colour alone."""
    formats = {c: ("{:.1f}%" if c in PERCENT_STATS else "{:.2f}") for c in table.columns}
    return table.style.format(formats)


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------

st.sidebar.markdown("## Market")
universe_name = st.sidebar.selectbox(
    "Universe", sorted(UNIVERSES), index=sorted(UNIVERSES).index(config.DEFAULT_UNIVERSE),
    format_func=lambda n: UNIVERSES[n]["label"],
)
st.sidebar.caption(UNIVERSES[universe_name]["description"])

default_symbols = UNIVERSES[universe_name]["symbols"]
symbols = st.sidebar.multiselect(
    "Symbols", options=sorted(set(all_symbols()) | set(default_symbols)),
    default=default_symbols,
    format_func=lambda s: f"{s} - {get_instrument(s).name}",
)
extra = st.sidebar.text_input("Add tickers", placeholder="e.g. NVDA, ^FTSE, BTC-USD",
                              help="Comma separated. Passed to the provider as typed.")
if extra:
    symbols = list(dict.fromkeys(symbols + [s.strip().upper() for s in extra.split(",") if s.strip()]))

st.sidebar.markdown("## Window")
col_a, col_b = st.sidebar.columns(2)
start = col_a.date_input("From", value=pd.Timestamp(config.DEFAULT_START)).isoformat()
end_value = col_b.date_input("To", value=pd.Timestamp.today())
end = pd.Timestamp(end_value).isoformat()
interval = st.sidebar.selectbox("Bar size", ["1d", "1wk", "1mo", "1h", "30m", "15m", "5m"], index=0)

st.sidebar.markdown("## Data")
provider = st.sidebar.selectbox("Provider", ["auto", "csv", "ibkr", "yfinance", "stooq", "synthetic"])
align = st.sidebar.selectbox(
    "Calendar alignment", ["intersect", "union_ffill", "none"],
    help="Markets keep different hours. 'intersect' keeps only the bars every symbol quotes.",
)
allow_synthetic = st.sidebar.checkbox(
    "Allow simulated data", value=False,
    help="Lets the simulator stand in for symbols no provider can serve. Results then "
         "describe a random number generator rather than a market.",
)

st.sidebar.markdown("## Costs")
commission = st.sidebar.number_input("Commission (bps)", 0.0, 50.0, config.COMMISSION_BPS, 0.5)
slippage = st.sidebar.number_input("Slippage (bps)", 0.0, 50.0, config.SLIPPAGE_BPS, 0.5)
threshold = st.sidebar.number_input(
    "Rebalance threshold", 0.0, 0.5, 0.0, 0.005,
    help="Ignore target changes smaller than this. Cuts turnover on strategies that "
         "adjust size every bar.",
)

st.sidebar.markdown("## Display")
theme_mode = st.sidebar.radio("Theme", ["light", "dark"], horizontal=True)
candle_scheme = st.sidebar.radio("Candles", ["classic", "brand"], horizontal=True)

if not symbols:
    st.warning("Pick at least one symbol in the sidebar.")
    st.stop()

try:
    prices = cached_prices(tuple(symbols), start, end, interval, provider, align, allow_synthetic)
except Exception as exc:  # a failed load must explain itself, not traceback
    st.error(f"Could not load prices: {exc}")
    st.stop()

cfg = BacktestConfig(
    commission_bps=commission, slippage_bps=slippage,
    periods_per_year=config.PERIODS_PER_YEAR.get(interval, 252),
    rebalance_threshold=threshold,
)

simulated = synthetic_symbols(prices)
missing = sorted(set(symbols) - set(prices))

st.title("Charting analysis")
first = next(iter(prices.values()))
st.caption(
    f"{len(prices)} instruments &middot; {first.index[0].date()} to {first.index[-1].date()} "
    f"&middot; {len(first)} bars at {interval}"
)
if simulated:
    st.error(
        f"**{', '.join(simulated)} are simulated bars, not real market data.** Every "
        "number derived from them is fiction, and trend rules score absurdly well on "
        "simulated series. Turn off 'Allow simulated data' or supply real history."
    )
if missing:
    st.warning(f"No data for {', '.join(missing)}. Excluded from everything below.")

tab_chart, tab_backtest, tab_validate, tab_signals, tab_data = st.tabs(
    ["Chart", "Backtest", "Validation", "Signals today", "Data"]
)

# --------------------------------------------------------------------------
# Chart
# --------------------------------------------------------------------------

with tab_chart:
    left, right = st.columns([3, 1])
    symbol = left.selectbox("Symbol", sorted(prices),
                            format_func=lambda s: f"{s} - {get_instrument(s).name}")
    strategy_key = right.selectbox("Strategy", available(), index=available().index("trend_vol_target"),
                                   format_func=lambda k: strategy_class(k).label)

    with st.expander("Strategy parameters", expanded=False):
        cls = strategy_class(strategy_key)
        st.caption(cls.description.strip())
        st.info(f"**What is known about this:** {cls.evidence.strip()}")
        params = parameter_controls(strategy_key, st.columns(3), prefix="chart:")

    show_volume = st.checkbox("Show volume", value=True)
    bars = st.slider("Bars shown", 60, max(120, len(first)), min(400, len(first)), 10)

    try:
        strategy = get_strategy(strategy_key, **params)
        weights = strategy.generate_weights(prices)
        chart = strategy.chart(symbol, prices[symbol])
        window = prices[symbol].tail(bars)
        figure = plots.price_chart(
            window, symbol, chart, weights[symbol].tail(bars),
            mode=theme_mode, candle_scheme=candle_scheme, show_volume=show_volume,
            title=f"{symbol} - {get_instrument(symbol).name}",
        )
        st.plotly_chart(figure, width="stretch")
    except ValueError as exc:
        st.error(str(exc))

# --------------------------------------------------------------------------
# Backtest
# --------------------------------------------------------------------------

with tab_backtest:
    chosen = st.multiselect("Strategies", available(), default=list(HEADLINE) + ["ensemble"],
                            format_func=lambda k: strategy_class(k).label)
    include_benchmark = st.checkbox("Include buy and hold", value=True)

    results, errors = {}, []
    for key in chosen:
        strategy = get_strategy(key)
        try:
            results[strategy.label] = run_backtest(
                prices, strategy.generate_weights(prices), cfg, name=strategy.label)
        except ValueError as exc:
            errors.append(f"{strategy.label}: {exc}")
    if include_benchmark:
        results["Buy and hold"] = buy_and_hold_result(prices, cfg=cfg, name="Buy and hold")
    for message in errors:
        st.warning(message)

    if not results:
        st.info("Choose at least one strategy.")
    else:
        stats = comparison_table({k: r.performance for k, r in results.items()})
        best = stats["sharpe"].idxmax()
        perf = results[best].performance
        cards = st.columns(5)
        cards[0].metric("Best Sharpe", best)
        cards[1].metric("CAGR", f"{perf.cagr * 100:.1f}%")
        cards[2].metric("Volatility", f"{perf.annual_volatility * 100:.1f}%")
        cards[3].metric("Max drawdown", f"{perf.max_drawdown * 100:.1f}%")
        cards[4].metric("Sharpe", f"{perf.sharpe:.2f}")

        st.dataframe(stat_style(stats[HEADLINE_STATS]), width="stretch")
        st.caption(
            "Backtested on this sample only, with costs charged on every trade and fills "
            "on the following bar. Not a forecast. Use the Validation tab before believing "
            "any row above."
        )

        log_scale = st.checkbox("Log scale", value=False)
        st.plotly_chart(plots.equity_chart(results, mode=theme_mode, log_scale=log_scale),
                        width="stretch")
        one, two = st.columns(2)
        one.plotly_chart(plots.drawdown_chart(results, mode=theme_mode), width="stretch")
        two.plotly_chart(plots.annual_returns_chart(results, mode=theme_mode), width="stretch")
        three, four = st.columns(2)
        three.plotly_chart(
            plots.rolling_sharpe_chart(results, periods_per_year=cfg.periods_per_year, mode=theme_mode),
            width="stretch")
        four.plotly_chart(plots.return_distribution(results, mode=theme_mode), width="stretch")

        focus = st.selectbox("Detail for", list(results))
        five, six = st.columns(2)
        five.plotly_chart(plots.monthly_heatmap(results[focus].returns, mode=theme_mode),
                          width="stretch")
        six.plotly_chart(plots.allocation_chart(results[focus].positions, mode=theme_mode),
                         width="stretch")

# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

with tab_validate:
    st.markdown(
        "A single backtest is the weakest evidence a strategy can produce. These three "
        "views are what separate a rule that works from one that was fitted to this sample."
    )
    key = st.selectbox("Strategy to validate", [k for k in available() if k in DEFAULT_GRIDS],
                       format_func=lambda k: strategy_class(k).label)
    grid = DEFAULT_GRIDS[key]
    st.caption(f"Search grid: {grid}")

    sweep_tab, wf_tab = st.tabs(["Parameter surface", "Walk forward"])

    with sweep_tab:
        if st.button("Run sweep", key="sweep"):
            with st.spinner("Sweeping..."):
                frame = parameter_sweep(key, prices, grid, cfg)
            columns = [c for c in frame.columns if c in grid] + \
                      ["cagr", "sharpe", "max_drawdown", "annual_turnover"]
            st.dataframe(format_stats(frame[columns].set_index(list(grid))), width="stretch")
            st.caption(
                "Read the spread, not the top row. A setting that only works at one exact "
                "value is telling you about this sample, not about the market."
            )

    with wf_tab:
        cols = st.columns(3)
        train_bars = cols[0].number_input("Train bars", 120, 2000, 504, 21)
        test_bars = cols[1].number_input("Test bars", 21, 500, 126, 21)
        anchored = cols[2].checkbox("Anchored window", value=False)
        if st.button("Run walk forward", key="wf"):
            try:
                with st.spinner("Re-fitting on each window..."):
                    result = walk_forward(key, prices, grid, int(train_bars), int(test_bars),
                                          cfg, anchored=anchored)
            except ValueError as exc:
                st.error(str(exc))
            else:
                perf = result.performance
                cards = st.columns(4)
                cards[0].metric("Out-of-sample CAGR", f"{perf.cagr * 100:.1f}%")
                cards[1].metric("Out-of-sample Sharpe", f"{perf.sharpe:.2f}")
                cards[2].metric("Max drawdown", f"{perf.max_drawdown * 100:.1f}%")
                cards[3].metric("Sharpe degradation", f"{result.degradation():.2f}",
                                help="In-sample minus out-of-sample. Large and positive "
                                     "means the search fitted noise.")
                st.dataframe(result.folds.round(3), width="stretch")
                try:
                    ci = bootstrap_confidence(result.returns, n_samples=400)
                    st.markdown("**Block bootstrap, 90% interval**")
                    st.dataframe(ci.round(3), width="stretch")
                    st.caption(
                        "Resampled in blocks so volatility clustering survives. If the "
                        "lower bound on Sharpe is below zero, this sample cannot "
                        "distinguish the strategy from luck."
                    )
                except ValueError as exc:
                    st.info(f"Bootstrap skipped: {exc}")

# --------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------

with tab_signals:
    capital = st.number_input("Capital", 1000.0, 1e9, config.INITIAL_CAPITAL, 1000.0)
    picks = st.multiselect("Strategies", available(), default=list(HEADLINE),
                           format_func=lambda k: strategy_class(k).label)
    for key in picks:
        strategy = get_strategy(key)
        st.markdown(f"### {strategy.label}")
        try:
            table = signal_table(strategy, prices, capital=capital)
        except ValueError as exc:
            st.warning(str(exc))
            continue
        live = table[table["target_weight"].abs() > 1e-6]
        if live.empty:
            st.info("No positions. The strategy wants to be flat.")
        else:
            st.dataframe(
                live[["name", "close", "target_weight", "action", "trend", "rsi_14",
                      "notional", "units"]].round(3),
                width="stretch",
            )
        book = summarise_book(table)
        cols = st.columns(4)
        cols[0].metric("Positions", book["positions"])
        cols[1].metric("Gross exposure", f"{book['gross_exposure'] * 100:.0f}%")
        cols[2].metric("Net exposure", f"{book['net_exposure'] * 100:.0f}%")
        cols[3].metric("Trades to place", book["trades"])

    if len(picks) > 1:
        st.markdown("### Where the strategies agree")
        st.dataframe(compare_strategies(picks, prices).round(3), width="stretch")
        st.caption("Agreement counts how many of the chosen strategies want a symbol today.")

# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

with tab_data:
    st.markdown("### What loaded, and from where")
    st.dataframe(coverage_report(prices), width="stretch")
    st.caption(
        "The source column is the point of this table. A backtest built partly on "
        "simulated bars is not a backtest."
    )
    st.markdown("### Correlation across the universe")
    st.plotly_chart(plots.correlation_heatmap(returns_panel(prices), mode=theme_mode),
                    width="stretch")
    st.caption("Highly correlated holdings mean the book is one bet wearing several names.")

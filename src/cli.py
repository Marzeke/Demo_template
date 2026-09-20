"""Command line interface.

    python -m src.cli strategies
    python -m src.cli markets
    python -m src.cli backtest --universe us_sectors --strategy momentum_rotation --strategy ensemble
    python -m src.cli sweep --universe us_sectors --strategy momentum_rotation
    python -m src.cli walkforward --universe us_sectors --strategy momentum_rotation
    python -m src.cli signals --universe cross_asset --strategy ensemble
    python -m src.cli report --universe cross_asset --open
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from src import config
from src.backtest.engine import BacktestConfig, buy_and_hold_result, run_backtest
from src.backtest.metrics import comparison_table
from src.backtest.walkforward import bootstrap_confidence, parameter_sweep, walk_forward
from src.dataset import coverage_report, load_prices, synthetic_symbols
from src.modeling.predict import signal_table, summarise_book
from src.modeling.train import DEFAULT_GRIDS
from src.services.universe import UNIVERSES, universe_symbols
from src.strategies import HEADLINE, available, catalogue, get_strategy

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)

HEADLINE_STATS = [
    "cagr", "annual_volatility", "sharpe", "sortino", "calmar",
    "max_drawdown", "hit_rate", "exposure", "annual_turnover",
]


def _parse_params(items: list[str] | None) -> dict:
    """Turn ``name=value`` strings into a parameter dict."""
    out = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"--param expects name=value, got {item!r}")
        name, value = item.split("=", 1)
        out[name.strip()] = value.strip()
    return out


def _resolve_symbols(args) -> list[str]:
    if args.symbols:
        return [s.strip().upper() for s in args.symbols]
    return universe_symbols(args.universe)


def _warn_synthetic(prices: dict) -> None:
    """Say so, loudly, when any of the loaded bars are simulated."""
    simulated = synthetic_symbols(prices)
    if simulated:
        print(
            f"WARNING: {', '.join(simulated)} are SIMULATED bars, not real market data. "
            "Every statistic derived from them is fiction.",
            file=sys.stderr,
        )


def _load(args) -> dict:
    prices = load_prices(
        _resolve_symbols(args),
        start=args.start,
        end=args.end,
        interval=args.interval,
        provider=args.provider,
        align=args.align,
        use_cache=not args.no_cache,
        refresh=args.refresh,
        allow_synthetic=args.allow_synthetic,
    )
    _warn_synthetic(prices)
    requested = set(_resolve_symbols(args))
    missing = sorted(requested - set(prices))
    if missing:
        print(f"note: no data for {', '.join(missing)}; excluded from this run.", file=sys.stderr)
    return prices


def _config(args) -> BacktestConfig:
    return BacktestConfig(
        commission_bps=args.commission_bps,
        slippage_bps=args.slippage_bps,
        periods_per_year=config.PERIODS_PER_YEAR.get(args.interval, 252),
        rebalance_threshold=args.rebalance_threshold,
    )


def _percent(frame: pd.DataFrame) -> pd.DataFrame:
    """Render the rate columns as percentages, for reading rather than maths."""
    out = frame.copy()
    for col in ("cagr", "annual_volatility", "max_drawdown", "hit_rate", "total_return", "exposure"):
        if col in out.columns:
            out[col] = (out[col] * 100).round(2)
    return out.round(3)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_strategies(args) -> int:
    table = catalogue()
    print(table[["label", "category", "cross_sectional", "asset_classes"]].to_string())
    if args.verbose:
        for key in table.index:
            strategy = get_strategy(key)
            print(f"\n=== {key}: {strategy.label} ===")
            print(f"  {strategy.description.strip()}")
            print(f"  Evidence: {strategy.evidence.strip()}")
            for spec in strategy.PARAMS:
                rng = ""
                if spec.kind in {"int", "float"} and spec.minimum is not None:
                    rng = f" [{spec.minimum} .. {spec.maximum}]"
                elif spec.choices:
                    rng = f" {list(spec.choices)}"
                print(f"    {spec.name:22s} = {spec.default!r:<14}{rng}  {spec.help}")
    return 0


def cmd_markets(args) -> int:
    rows = [
        {"universe": name, "label": meta["label"], "symbols": len(meta["symbols"]),
         "members": ", ".join(meta["symbols"])}
        for name, meta in UNIVERSES.items()
    ]
    print(pd.DataFrame(rows).set_index("universe").to_string())
    return 0


def cmd_data(args) -> int:
    prices = _load(args)
    print(coverage_report(prices).to_string())
    return 0


def cmd_backtest(args) -> int:
    prices = _load(args)
    cfg = _config(args)
    keys = args.strategy or list(HEADLINE)
    params = _parse_params(args.param)

    results = {}
    for key in keys:
        strategy = get_strategy(key, **params)
        try:
            weights = strategy.generate_weights(prices)
        except ValueError as exc:
            print(f"skipping {key}: {exc}", file=sys.stderr)
            continue
        results[strategy.label] = run_backtest(prices, weights, cfg, name=strategy.label)

    if args.benchmark:
        results["Buy and hold"] = buy_and_hold_result(prices, cfg=cfg, name="Buy and hold")
    if not results:
        print("nothing ran", file=sys.stderr)
        return 1

    table = comparison_table({k: r.performance for k, r in results.items()})
    print(_percent(table[HEADLINE_STATS]).to_string())

    if args.save_charts:
        from src import plots
        paths = [
            plots.save(plots.equity_chart(results, mode=args.theme), "equity.html"),
            plots.save(plots.drawdown_chart(results, mode=args.theme), "drawdown.html"),
            plots.save(plots.annual_returns_chart(results, mode=args.theme), "annual_returns.html"),
        ]
        print("\nsaved:", *paths, sep="\n  ")
    return 0


def cmd_sweep(args) -> int:
    prices = _load(args)
    key = (args.strategy or ["momentum_rotation"])[0]
    grid = DEFAULT_GRIDS.get(key)
    if not grid:
        print(f"no default grid for {key}; add one to src/modeling/train.py", file=sys.stderr)
        return 1
    frame = parameter_sweep(key, prices, grid, _config(args), args.objective)
    columns = [c for c in frame.columns if c in grid] + ["cagr", "sharpe", "max_drawdown", "annual_turnover"]
    print(_percent(frame[columns]).head(args.top).to_string(index=False))
    print(f"\n{len(frame)} combinations. Read the spread, not the top row: a result "
          f"that only appears at one setting is a fitting artefact.")
    return 0


def cmd_walkforward(args) -> int:
    prices = _load(args)
    key = (args.strategy or ["momentum_rotation"])[0]
    grid = DEFAULT_GRIDS.get(key)
    if not grid:
        print(f"no default grid for {key}", file=sys.stderr)
        return 1
    result = walk_forward(key, prices, grid, args.train_bars, args.test_bars,
                          _config(args), args.objective, anchored=args.anchored)
    print(result.folds.round(3).to_string(index=False))
    perf = result.performance
    print(f"\nOut of sample: CAGR {perf.cagr * 100:.2f}%  Sharpe {perf.sharpe:.2f}  "
          f"max drawdown {perf.max_drawdown * 100:.1f}%")
    print(f"Degradation from in-sample Sharpe: {result.degradation():.2f} "
          f"(large and positive means the search fitted noise)")
    try:
        print("\n" + bootstrap_confidence(result.returns, n_samples=args.bootstrap).round(3).to_string())
    except ValueError as exc:
        print(f"\nbootstrap skipped: {exc}")
    return 0


def cmd_signals(args) -> int:
    prices = _load(args)
    params = _parse_params(args.param)
    for key in (args.strategy or list(HEADLINE)):
        strategy = get_strategy(key, **params)
        try:
            table = signal_table(strategy, prices, capital=args.capital)
        except ValueError as exc:
            print(f"skipping {key}: {exc}", file=sys.stderr)
            continue
        print(f"\n=== {strategy.label} ===")
        columns = ["name", "close", "target_weight", "action", "trend", "rsi_14"]
        if args.capital:
            columns += ["notional", "units"]
        live = table if args.all else table[table["target_weight"].abs() > 1e-6]
        print(live[columns].round(3).to_string() if len(live) else "  no positions")
        book = summarise_book(table)
        print(
            f"  positions {book['positions']}  "
            f"gross {book['gross_exposure'] * 100:.0f}%  "
            f"net {book['net_exposure'] * 100:.0f}%  "
            f"trades {book['trades']}  "
            f"as of {pd.Timestamp(book['as_of']).date()}"
        )
    return 0


def cmd_report(args) -> int:
    from src.report import build_report
    path = build_report(
        symbols=_resolve_symbols(args),
        strategy_keys=args.strategy or list(HEADLINE),
        start=args.start, end=args.end, interval=args.interval,
        provider=args.provider, align=args.align, cfg=_config(args),
        theme=args.theme, title=args.title, allow_synthetic=args.allow_synthetic,
    )
    print(f"report written to {path}")
    return 0


def cmd_app(args) -> int:
    import subprocess
    target = config.PROJ_ROOT / "src" / "app" / "streamlit_app.py"
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(target)])


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="src.cli", description="Stock charting and strategy analysis."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_data_args(p):
        p.add_argument("--universe", default=config.DEFAULT_UNIVERSE, choices=sorted(UNIVERSES),
                       help="A named market universe.")
        p.add_argument("--symbols", nargs="+", help="Explicit symbols, overriding --universe.")
        p.add_argument("--start", default=config.DEFAULT_START)
        p.add_argument("--end", default=None)
        p.add_argument("--interval", default=config.DEFAULT_INTERVAL,
                       choices=sorted(config.PERIODS_PER_YEAR))
        p.add_argument("--provider", default=config.DEFAULT_PROVIDER,
                       help="auto, csv, ibkr, yfinance, stooq or synthetic.")
        p.add_argument("--align", default="intersect", choices=("intersect", "union_ffill", "none"))
        p.add_argument("--no-cache", action="store_true")
        p.add_argument("--refresh", action="store_true", help="Ignore the cache and refetch.")
        p.add_argument("--allow-synthetic", action="store_true",
                       help="Let the simulator stand in for symbols no provider can serve. "
                            "Results then describe a random number generator, not a market.")

    def add_backtest_args(p):
        p.add_argument("--strategy", action="append", choices=available())
        p.add_argument("--param", action="append", help="name=value, repeatable.")
        p.add_argument("--commission-bps", type=float, default=config.COMMISSION_BPS)
        p.add_argument("--slippage-bps", type=float, default=config.SLIPPAGE_BPS)
        p.add_argument("--rebalance-threshold", type=float, default=0.0,
                       help="Ignore target changes smaller than this, to cut churn.")

    p = sub.add_parser("strategies", help="List the strategy catalogue.")
    p.add_argument("--verbose", "-v", action="store_true", help="Include parameters and evidence.")
    p.set_defaults(func=cmd_strategies)

    p = sub.add_parser("markets", help="List the market universes.")
    p.set_defaults(func=cmd_markets)

    p = sub.add_parser("data", help="Show what data loads for a universe.")
    add_data_args(p)
    p.set_defaults(func=cmd_data)

    p = sub.add_parser("backtest", help="Compare strategies over a window.")
    add_data_args(p); add_backtest_args(p)
    p.add_argument("--benchmark", action="store_true", default=True)
    p.add_argument("--no-benchmark", dest="benchmark", action="store_false")
    p.add_argument("--save-charts", action="store_true")
    p.add_argument("--theme", default=config.THEME_MODE, choices=("light", "dark"))
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("sweep", help="Search a strategy's parameter grid.")
    add_data_args(p); add_backtest_args(p)
    p.add_argument("--objective", default="sharpe")
    p.add_argument("--top", type=int, default=15)
    p.set_defaults(func=cmd_sweep)

    p = sub.add_parser("walkforward", help="Validate a strategy out of sample.")
    add_data_args(p); add_backtest_args(p)
    p.add_argument("--objective", default="sharpe")
    p.add_argument("--train-bars", type=int, default=504)
    p.add_argument("--test-bars", type=int, default=126)
    p.add_argument("--anchored", action="store_true")
    p.add_argument("--bootstrap", type=int, default=500)
    p.set_defaults(func=cmd_walkforward)

    p = sub.add_parser("signals", help="Show what each strategy wants to hold today.")
    add_data_args(p); add_backtest_args(p)
    p.add_argument("--capital", type=float, default=config.INITIAL_CAPITAL)
    p.add_argument("--all", action="store_true", help="Include symbols with no position.")
    p.set_defaults(func=cmd_signals)

    p = sub.add_parser("report", help="Build a standalone HTML report.")
    add_data_args(p); add_backtest_args(p)
    p.add_argument("--theme", default=config.THEME_MODE, choices=("light", "dark"))
    p.add_argument("--title", default="Strategy analysis")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("app", help="Launch the interactive app.")
    p.set_defaults(func=cmd_app)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

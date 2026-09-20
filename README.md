# Charting analysis

A charting and strategy analysis app for a variety of markets: US and
international equities, sectors, single names, bonds, commodities, currencies
and crypto. It draws the chart, runs the rule, charges the costs, and then tries
hard to talk you out of believing the result.

![strategies](https://img.shields.io/badge/strategies-10-002664)
![markets](https://img.shields.io/badge/universes-10-0A34A1)
![tests](https://img.shields.io/badge/tests-160%20passing-4B87E0)

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env

python -m src.cli markets                  # what you can look at
python -m src.cli strategies -v            # what you can run, and its caveats
python -m src.cli backtest --universe us_sectors
python -m src.cli walkforward --universe us_sectors --strategy momentum_rotation
python -m src.cli signals --universe cross_asset --strategy ensemble
python -m src.cli report --universe cross_asset
python -m src.cli app                      # the interactive app
```

The repository ships five years of real daily bars for 21 instruments and one
quarter of 30-minute bars, so every command above works before you connect any
data source.

## The three headline strategies

Chosen on breadth of independent evidence, cross-market applicability and
whether they can be validated honestly, then re-measured here on real bars with
costs charged. The reasoning, the failure modes and the sources are in
[docs/STRATEGIES.md](docs/STRATEGIES.md).

| | Approach | Out-of-sample Sharpe | Sharpe 90% interval |
|---|---|---|---|
| 1 | Cross-sectional momentum rotation | 0.82 | 0.14 to 1.92 |
| 2 | Trend following, volatility targeted | -1.02 | -2.23 to -0.17 |
| 3 | Mean reversion, regime filtered | 0.36 | -0.30 to 1.27 |

Walk-forward on eleven US sector ETFs, five folds, September 2021 to September
2026. Only the first has an interval that stays above zero. Trend following lost
money on every universe tested over this window, which is consistent with
published results for 2024 and 2025 and is reported rather than hidden. On the
same universe, equal-weight buy and hold beat all three.

Also included: a blended ensemble, dual momentum, an intraday opening range
breakout, and four baselines to measure against.

## What else is in the box

**Markets.** Ten ready-made universes and a catalogue of 55 instruments across
eight asset classes, plus any ticker you type. Markets on different calendars
are aligned before a strategy sees them, which is not optional: a union index
puts a gap in every rolling window and silently zeroes the book.

**Data.** Five providers behind one interface. Local CSV, Interactive Brokers
snapshots, Yahoo Finance, Stooq, and a deterministic simulator. The chain falls
back until something answers, with a hard rule: it never reaches the simulator
unless you ask. Every frame records where it came from, and anything simulated
is called out in red wherever results appear.

**Indicators.** Moving averages, RSI, MACD, stochastic, Bollinger, Keltner,
Donchian, ATR, ADX, Supertrend, Ichimoku, OBV, VWAP, realised volatility,
z-scores, drawdown, and trend and volatility regime labels. Every one has a test
proving that removing future bars does not change any past value.

**Backtesting.** Vectorised, multi-asset, long and short, with commission and
slippage on every unit of traded notional, an execution lag, a leverage cap, a
rebalance threshold and cash yield while flat. Twenty statistics including
Sortino, Calmar, Ulcer index, conditional value at risk and turnover.

**Validation, which is the point.** Parameter surfaces, so you can see whether a
good result is a plateau or a spike. Walk-forward, which re-picks parameters on
past data only and trades the next segment untouched, and reports how much of
the fit survived. Block bootstraps, which put an interval around a headline
number so a Sharpe of 0.8 reads as "0.14 to 1.92" instead of as a fact.

**Charts.** Candles with strategy overlays, shaded channels, trade markers and
stacked indicator panels. Equity curves, drawdowns, rolling Sharpe, monthly
heat maps, calendar-year bars, allocation over time, return distributions and
correlation. One scale per panel, never two. Colour assigned by identity in a
fixed order and validated for colour-vision deficiency in both light and dark.

**Outputs.** An interactive app, a command line, and a self-contained HTML
report with the plotting library embedded, so its charts render on a machine
with no network.

## Connecting your own data

Out of the box the app reads the bundled snapshots. To go live:

```bash
python -m src.cli backtest --universe us_core --provider yfinance --refresh
```

Yahoo Finance and Stooq need only a network connection. For Interactive Brokers,
export price history as JSON to `data/external/ibkr/<SYMBOL>_<interval>.json`.
For anything else, drop a CSV with a date index and OHLCV columns into
`data/raw/<interval>/<SYMBOL>.csv` and it is picked up automatically.

Defaults live in `.env`: provider chain, date range, costs, volatility target,
theme.

## Reading a result honestly

Every number this app produces is a backtest: what the rules would have done on
one sample, with costs charged and fills on the following bar. It is not a
forecast, and it does not model market impact, borrowing cost, tax, or whether a
real fill existed at that price.

The figures worth weighing are the walk-forward and bootstrap ones, because they
are the only ones measured on data that did not choose the parameters. Where a
bootstrap interval crosses zero, the honest reading is that the sample is too
short to tell whether the strategy works. That will be true more often than not.

Nothing here is financial advice.

## Project layout

See [docs/PLAN.md](docs/PLAN.md) for the architecture, the contracts between
layers, and the decisions behind them.

```
src/
  config.py            paths, defaults, environment overrides
  theme.py             brand palette and Plotly template
  features.py          indicator library
  dataset.py           loading, caching, calendar alignment, provenance
  plots.py             chart builders
  report.py            standalone HTML report
  cli.py               command line
  services/            instrument catalogue, data providers
  strategies/          strategy contract, registry, the strategies
  backtest/            engine, metrics, walk-forward, bootstrap
  modeling/            parameter fitting, today's signals
  app/                 interactive app
data/
  external/ibkr/       bundled real bars, 21 instruments
  raw/                 provider cache
tests/                 160 tests, including look-ahead checks
docs/                  plan and strategy research
```

## Tests

```bash
python -m pytest tests/ -q
```

The suite runs against the deterministic simulator, so it needs no network. The
tests that matter most are the look-ahead checks: for every indicator and every
strategy, removing the last year of data must not change a single earlier value.
Three genuine bugs were found that way during development, including a rebalance
schedule that was reading tomorrow's date.

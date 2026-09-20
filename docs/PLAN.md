# App plan

## What it is for

A charting and analysis tool for someone who wants to look at a chart, ask
whether a rule would have worked, and get an answer they can defend. Not a
trading system, not a signal service. The design goal throughout is that a
result you cannot trust should look untrustworthy on screen.

## Shape of the thing

```
                 ┌──────────────┐   ┌───────────────┐   ┌──────────┐
   providers ──▶ │   dataset    │──▶│  strategies   │──▶│ backtest │──┐
 csv/ibkr/yf/    │ cache, align │   │ → weights     │   │ → returns│  │
 stooq/synth     └──────────────┘   └───────────────┘   └──────────┘  │
                        │                   │                         ▼
                        │                   │              ┌────────────────────┐
                        │                   └─────────────▶│ walk-forward,      │
                        │                                  │ sweeps, bootstrap  │
                        │                                  └────────────────────┘
                        ▼                                            │
                 ┌──────────────┐                                    ▼
                 │  features    │──────────────▶ plots ──▶ app · CLI · HTML report
                 │ indicators   │
                 └──────────────┘
```

Each stage has one job and hands on a plain pandas object. A strategy never sees
capital or costs; the engine never sees an indicator; a chart never computes a
signal. That separation is what lets the same strategy run on one chart, on a
twelve-market rotation, and inside a walk-forward sweep without changing a line.

## The contract between the layers

**Providers → dataset.** A provider returns a frame indexed by a naive
`DatetimeIndex` with `open, high, low, close, volume`, ascending, no duplicates.
Nothing downstream knows which provider produced it.

**Dataset → strategy.** A dict of `{symbol: frame}`, all on one calendar. The
alignment step is not housekeeping. Crypto trades daily, foreign exchange five
and a half days, equities fewer, and holidays differ by country. Stack them on a
union index and every rolling window straddles gaps, volatility comes back as
`NaN`, and positions silently go to zero. This bug was real, was found during
development, and the fix is to align before a strategy ever sees the data.

**Strategy → engine.** A frame of target weights, one column per symbol, where
`0.5` means half of equity long. A weight on row `t` is a decision made with
information up to the close of bar `t`. The engine lags it before applying any
return.

**Engine → everything else.** A `BacktestResult` carrying returns, equity,
positions, turnover, costs and a full statistic set.

## Decisions worth recording

**Weights, not orders.** Target weights compose. Two strategies can be blended
by adding their weight frames, which is what makes the ensemble three lines
rather than a rewrite. An order-based interface would not.

**Parameters carry their own metadata.** Each strategy declares typed
`ParamSpec` entries with ranges and help text. The interface builds its controls
from that, the command line validates against it, and the sweep grids reference
it. A new strategy gets its whole interface for free.

**Synthetic data is opt-in and always labelled.** An earlier version let the
simulator quietly stand in for symbols whose download failed. It produced a
trend-following Sharpe of 4.7 that looked entirely plausible in a table. The
provider chain no longer reaches the simulator unless asked, every frame records
its source, and anything simulated is called out in red wherever results appear.

**Validation is a first-class surface, not a utility.** A single backtest over a
single window is the weakest evidence a strategy can produce, and it is where
most tools stop. Walk-forward, parameter surfaces and block bootstraps have
their own tab, and the numbers they produce are less flattering than the
headline backtest by design.

**Costs are on by default.** Two basis points of commission and three of
slippage, charged on every unit of traded notional. Turnover is a headline
statistic, not a footnote, because an 80-times-a-year strategy is a different
proposition from a 4-times-a-year one.

## What is deliberately not modelled

Intrabar fills, market impact, borrowing cost and availability for shorts, tax,
dividends beyond what adjusted prices carry, and survivorship in the instrument
catalogue. Each of these would flatter or penalise a result, and pretending to
model them badly is worse than naming them.

## Layout

| Path | What lives there |
|---|---|
| `src/config.py` | Paths, defaults, environment overrides |
| `src/theme.py` | Brand palette, validated categorical slots, Plotly template |
| `src/services/universe.py` | Instrument catalogue and named market universes |
| `src/services/providers.py` | The five data providers and the fallback chain |
| `src/dataset.py` | Loading, caching, calendar alignment, provenance |
| `src/features.py` | Indicator library |
| `src/strategies/` | Strategy contract, registry, and the strategies |
| `src/backtest/` | Engine, metrics, walk-forward and bootstrap |
| `src/modeling/` | Parameter fitting, and today's signals |
| `src/plots.py` | Chart builders |
| `src/report.py` | Standalone HTML report |
| `src/app/` | Interactive app |
| `src/cli.py` | Command line |
| `tests/` | 161 tests, including look-ahead checks on every indicator and strategy |

## Build order, and what each step cost

1. Theme and palette, validated for colour-vision deficiency in both modes.
2. Instrument catalogue across eight asset classes and ten named universes.
3. Providers and the fallback chain.
4. Indicator library, with a look-ahead test per indicator.
5. Backtest engine and metrics, with arithmetic checked against hand-computed cases.
6. The three headline strategies, plus an ensemble, four baselines and an
   intraday breakout.
7. Calendar alignment, after the cross-asset panel silently returned zero weights.
8. Charts, then rendered and looked at, which is how the squashed candle window,
   the title-legend collision, the two-scale volatility panel and the
   hundreds-of-spurious-markers bug were all found.
9. Walk-forward, sweeps and bootstrap.
10. Command line, app and report.
11. Test suite, which found the rebalance mask reading tomorrow's date, the
    same-bar re-entry that defeated the holding limit, and the envelope repair
    that clobbered the low.

## What would come next

- Position-level trade records, so per-trade expectancy and holding periods can
  be reported rather than inferred from bar returns.
- An intraday data path that is more than a snapshot, so the breakout strategy
  can be judged on a sample worth judging.
- Live broker integration for the signals tab, so targets can be compared
  against a real book rather than a typed one.
- Multiple-testing correction on the sweep, because searching fifty parameter
  sets and reporting the best one is exactly how a spurious result is
  manufactured.

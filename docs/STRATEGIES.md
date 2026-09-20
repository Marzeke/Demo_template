# The three strategies, and why these three

## How they were chosen

There is no authoritative league table of trading strategies for 2024 to 2026,
and anyone presenting one is selling something. Published results disagree
sharply, almost always because of what was measured: which market, which window,
whether costs were charged, and whether the parameters were chosen before or
after seeing the data.

So the three below were not picked by ranking returns. They were picked on three
criteria that survive that problem:

1. **Breadth of independent evidence.** The approach has been tested by people
   with no stake in each other's results, across more than one market and more
   than one decade.
2. **It works on more than one asset class.** A rule that only works on US
   large-cap equities in the 2010s is a description of the 2010s.
3. **It can be stated in a few lines and measured honestly.** Anything needing a
   dozen tuned constants cannot be validated on five years of daily data.

Every claim below is then re-measured inside this app, on real bars, with costs
charged. Where the measurement disagrees with the literature, the measurement is
reported.

---

## 1. Cross-sectional momentum rotation

**The rule.** Rank a universe by trailing return, skipping the most recent
month, hold the strongest few, rebalance monthly. Drop anything whose own
trailing return is negative and hold cash instead.

**Why it is here.** Relative-strength momentum has the longest independent
replication record of anything in this list, and it holds up across equities,
sectors, bonds, commodities and currencies. The recent-month skip is not a
tweak; short-horizon reversal is a separate, well-documented effect that eats
into a naive twelve-month signal. The absolute-momentum filter is what turns
relative strength into *dual* momentum: without it, in a market where everything
is falling, the strategy dutifully holds the best loser.

**Where it fails.** Leadership rotations. The crowded winners unwind together
and a monthly rebalance is always late to it. Momentum has produced both the
highest long-run risk-adjusted returns among the classic factors and its most
spectacular crashes, and those are the same property viewed from two sides.

**Measured here** (11 US sector ETFs, Sept 2021 to Sept 2026, 2bp commission,
3bp slippage):

| | Value |
|---|---|
| CAGR | 8.8% |
| Volatility | 14.2% |
| Sharpe | 0.52 |
| Max drawdown | -17.4% |
| Turnover per year | 4.6x |

Walk-forward, re-fitting parameters on 504 bars and trading the next 126
untouched, five folds:

| | Value |
|---|---|
| Out-of-sample CAGR | 15.6% |
| Out-of-sample Sharpe | 0.82 |
| Sharpe degradation from in-sample | 0.13 |
| Sharpe, 90% block-bootstrap interval | 0.14 to 1.92 |

This is the only one of the three whose out-of-sample interval stays above zero,
and the only one whose parameters barely degraded when taken out of sample. That
is the strongest result in this repository, and it is still an interval that
reaches from "barely worth the trouble" to "very good".

---

## 2. Trend following with volatility targeting

**The rule.** Judge each market on its own: break of an N-bar high means long,
break of an N-bar low means short, exit on a shorter channel. Size every
position by its own recent volatility, then scale the whole book so it aims at a
chosen annual volatility.

**Why it is here.** It is the workhorse of managed futures and the approach with
the widest cross-market evidence of anything here. The important and
under-appreciated part is the sizing, not the entry: most of the risk-adjusted
improvement comes from volatility targeting, and the entry rule is the part most
often over-fitted. The app therefore ships three entry rules and a control with
no sizing at all, so the two effects can be separated.

**Where it fails.** Range-bound markets, where it buys every false break and
bleeds. This is not a hypothetical. Published tests through 2024 and 2025
describe exactly that: extended choppy stretches, whipsaws, and profit factors
collapsing to around one.

**Measured here.** It lost money on every universe tested, over this window:

| Universe | CAGR | Sharpe | Max drawdown |
|---|---|---|---|
| US sectors (11) | -7.3% | -0.83 | -35.3% |
| Cross-asset (7) | -3.9% | -0.46 | -24.9% |
| US indices (3) | -3.3% | -0.31 | -20.9% |

Walk-forward on the sector universe gives an out-of-sample Sharpe of -1.02, with
a Sharpe degradation of 1.50 from in-sample: the search found parameters that
looked good on the training window and did the opposite afterwards. The 90%
bootstrap interval, -2.23 to -0.17, does not reach zero.

That is a real result and it is reported as one. Two things are worth saying
next to it. Five years is a short sample for an approach whose edge arrives in
occasional large trends, and this particular window contained few of them on
these instruments. And trend following is normally run on futures across dozens
of markets, not on a handful of equity ETFs, which is close to the least
favourable setting for it. Neither of those makes the number go away.

---

## 3. Mean reversion, regime filtered

**The rule.** Buy a short-term oversold reading, but only while price is above
its long-term moving average. Exit on recovery, or after a holding limit
whichever comes first.

**Why it is here.** It is the natural complement to trend following rather than
a rival: trend systems make money when moves persist, this makes money when they
do not. Short-horizon reversal in equity indices is among the better documented
anomalies, and the two together are calmer than either alone. The filter is what
makes it survivable. Unfiltered dip-buying works beautifully right up until the
dip keeps going, and then it returns years of small wins in a fortnight.

**Where it fails.** The return shape is deliberately lopsided: many small wins
against rare large losses. A high win rate tells you almost nothing about it.
It is also weak outside equities, and it trades a great deal.

**Measured here** (11 US sector ETFs, same window and costs):

| | Value |
|---|---|
| CAGR | 8.1% |
| Volatility | 12.4% |
| Sharpe | 0.53 |
| Max drawdown | -15.8% |
| Average exposure | 44% |
| Turnover per year | 81.5x |

Note the exposure and the turnover together. It earns a similar return to
momentum rotation while invested less than half the time, which is the appeal,
and it pays for that with eighty round trips a year, which is the catch. At the
default 5 basis points all-in, that is roughly 0.8% of annual drag before any
market impact. Walk-forward gives an out-of-sample Sharpe of 0.36 with a 90%
interval of -0.30 to 1.27: this sample cannot distinguish it from luck.

---

## Also included

**Blended ensemble.** All three above, weighted and run as one book. Blending
weakly related return streams is the most reliable improvement available here,
and the gain arrives as lower volatility rather than higher return. On the
cross-asset universe it produced the lowest drawdown of anything tested (-10.9%)
and the best Calmar ratio (1.09). It is not a hedge: in a period where all three
components struggle it loses on all three at once, which is what happened on the
sector universe.

**Dual momentum.** Cross-sectional momentum concentrated into a single holding.
The concentration is the point and also the risk, and results are very sensitive
to which day of the month it rebalances, which is a warning about how much of
any backtest of it is luck.

**Opening range breakout, intraday.** Included because it is widely discussed,
and flagged because the evidence is genuinely contested. Favourable published
tests lean on leveraged instruments, short samples and no transaction costs; a
systematic falsification study sweeping the variants found most of them
unprofitable once those are restored. On 30-minute bars of two US index ETFs over
one quarter it lost money at every filter setting tested. A quarter is not a
sample, and that is exactly the point.

**Baselines: buy and hold, EMA crossover, MACD, Donchian without sizing.** These
exist so the headline strategies have something honest to be measured against.
They are not filler. On the sector universe, equal-weight buy and hold returned
19.8% a year at a Sharpe of 0.75 and beat every active strategy in this
repository on both. A strategy that cannot clear its benchmark after costs has
not earned its complexity, and saying so is the job of a tool like this.

---

## What the numbers above are not

Every figure on this page is a backtest over one five-year window on one set of
instruments. It is what the rules would have done, with costs charged and fills
on the following bar. It is not a forecast. It does not model market impact,
borrowing costs, tax, or whether a real fill was available at that price.

The walk-forward and bootstrap figures are the ones to weigh, because they are
the only ones measured on data that did not choose the parameters. Where a
bootstrap interval crosses zero, the honest reading is that five years is not
enough data to tell whether the strategy works.

---

## Sources

- [Man Group: Trend Following and Drawdowns, Is This Time Different?](https://www.man.com/insights/is-this-time-different)
- [Follow the Leader: Enhancing Systematic Trend-Following Using Network Momentum (arXiv)](https://arxiv.org/html/2501.07135v1)
- [Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures: A Systematic Falsification Study (arXiv)](https://arxiv.org/pdf/2605.04004)
- [Quantpedia: Sector Momentum Rotational System](https://quantpedia.com/strategies/sector-momentum-rotational-system)
- [Quantpedia: Momentum Asset Allocation Strategy](https://quantpedia.com/strategies/asset-class-momentum-rotational-system)
- [QuantifiedStrategies: Momentum Trading Strategies, Backtests and Rules](https://www.quantifiedstrategies.com/momentum-trading-strategies/)
- [Comparing Trend Following and Mean Reversion Strategy Performance](https://stratzy.in/blog/untitled-10/)
- [This Blog is Systematic: Very slow mean reversion, and trading at different speeds](https://qoppac.blogspot.com/2025/03/very-slow-mean-reversion-and-some.html)
- [Mean Reversion Strategy 2026: Backtests, Win Rates and Risks](https://lunefi.com/blog/mean-reversion-trading-strategy-2026-backtests-win-rates-risks-hybrid-tips)
- [Concretum Group research papers on opening range breakout](https://concretumgroup.com/papers/)
- [Momentum Trading Bot Strategies: Data-Backed Methods](https://theledgermind.com/momentum-trading-bot-strategies/)

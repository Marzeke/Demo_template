"""Build a standalone HTML report: charts, statistics and the honest caveats.

The report is one self-contained file. It is meant to be the thing you send to
someone else, so it carries the assumptions and the limitations next to the
numbers rather than in a separate note that gets lost.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src import config, plots
from src.backtest.engine import BacktestConfig, buy_and_hold_result, run_backtest
from src.backtest.metrics import comparison_table
from src.dataset import coverage_report, load_prices, returns_panel, synthetic_symbols
from src.strategies import get_strategy
from src.theme import get_surface

_STAT_LABELS = {
    "cagr": "CAGR",
    "annual_volatility": "Volatility",
    "sharpe": "Sharpe",
    "sortino": "Sortino",
    "calmar": "Calmar",
    "max_drawdown": "Max drawdown",
    "hit_rate": "Winning bars",
    "exposure": "Average exposure",
    "annual_turnover": "Turnover per year",
    "total_return": "Total return",
}
_PERCENT_STATS = {"cagr", "annual_volatility", "max_drawdown", "hit_rate", "exposure", "total_return"}


def _format_table(table: pd.DataFrame) -> pd.DataFrame:
    """Round and label a statistics table for display."""
    out = pd.DataFrame(index=table.index)
    for column, label in _STAT_LABELS.items():
        if column not in table.columns:
            continue
        values = table[column]
        out[label] = (values * 100).map("{:.1f}%".format) if column in _PERCENT_STATS \
            else values.map("{:.2f}".format)
    return out


def _table_html(table: pd.DataFrame, surface) -> str:
    return table.to_html(classes="stats", border=0, escape=False)


def _stylesheet(surface) -> str:
    return f"""
    :root {{
      --background: {surface.background};
      --panel: {surface.panel};
      --text: {surface.text_primary};
      --muted: {surface.text_secondary};
      --line: {surface.grid};
      --brand: #002664;
      --accent: #4B87E0;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; background: var(--background); color: var(--text);
      font-family: Inter, "Segoe UI", Helvetica, Arial, sans-serif;
      font-size: 15px; line-height: 1.55;
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 32px 16px 72px; }}
    header {{ border-bottom: 3px solid var(--brand); padding-bottom: 18px; margin-bottom: 28px; }}
    h1 {{ font-size: 28px; margin: 0 0 6px; color: var(--brand); letter-spacing: -0.01em; }}
    h2 {{ font-size: 19px; margin: 40px 0 10px; color: var(--brand); }}
    h3 {{ font-size: 15px; margin: 24px 0 8px; color: var(--text); }}
    p, li {{ color: var(--text); max-width: 76ch; }}
    .sub {{ color: var(--muted); font-size: 14px; margin: 0; }}
    .cards {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 18px 0 8px; }}
    .card {{
      background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
      padding: 14px 18px; min-width: 150px; flex: 1 1 150px;
    }}
    .card .label {{ font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }}
    .card .value {{ font-size: 24px; font-weight: 600; color: var(--brand); margin-top: 2px; }}
    table.stats {{ border-collapse: collapse; width: 100%; font-size: 14px; margin: 10px 0 4px; }}
    table.stats th, table.stats td {{
      border-bottom: 1px solid var(--line); padding: 9px 12px; text-align: right;
    }}
    table.stats th {{ color: var(--muted); font-weight: 600; font-size: 12px;
      text-transform: uppercase; letter-spacing: .05em; }}
    table.stats tbody th, table.stats td:first-child {{ text-align: left; }}
    table.stats tbody tr:hover {{ background: var(--panel); }}
    .note {{
      background: var(--panel); border-left: 3px solid var(--accent);
      padding: 14px 18px; border-radius: 0 8px 8px 0; margin: 16px 0;
    }}
    .note strong {{ color: var(--brand); }}
    .caveat {{ border-left-color: #fab219; }}
    .alarm {{ border-left-color: #d03b3b; }}
    .alarm strong {{ color: #d03b3b; }}
    .chart {{ margin: 8px 0 26px; }}
    footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--line);
      color: var(--muted); font-size: 13px; }}
    @media (max-width: 720px) {{ .wrap {{ padding: 20px 16px 48px; }} h1 {{ font-size: 23px; }} }}
    """


def build_report(
    symbols: list[str],
    strategy_keys: list[str],
    start: str | None = None,
    end: str | None = None,
    interval: str = "1d",
    provider: str = "auto",
    align: str = "intersect",
    cfg: BacktestConfig | None = None,
    theme: str = config.THEME_MODE,
    title: str = "Strategy analysis",
    params: dict[str, dict] | None = None,
    output: Path | None = None,
    allow_synthetic: bool = False,
    embed_plotly: bool = True,
) -> Path:
    """Run the strategies, draw the charts, and write one self-contained page.

    ``embed_plotly`` inlines the plotting library so the file renders with no
    network at all. It costs a few megabytes and is worth it: a report whose
    charts are blank on the recipient's machine is not a report.
    """
    cfg = cfg or BacktestConfig(periods_per_year=config.PERIODS_PER_YEAR.get(interval, 252))
    surface = get_surface(theme)
    params = params or {}

    prices = load_prices(symbols, start, end, interval, provider, align=align,
                         allow_synthetic=allow_synthetic)
    coverage = coverage_report(prices)
    simulated = synthetic_symbols(prices)
    dropped = sorted(set(s.upper() for s in symbols) - set(prices))

    results, evidence = {}, {}
    for key in strategy_keys:
        strategy = get_strategy(key, **params.get(key, {}))
        try:
            weights = strategy.generate_weights(prices)
        except ValueError:
            continue
        results[strategy.label] = run_backtest(prices, weights, cfg, name=strategy.label)
        evidence[strategy.label] = strategy.evidence.strip()
    results["Buy and hold"] = buy_and_hold_result(prices, cfg=cfg, name="Buy and hold")

    stats = comparison_table({k: r.performance for k, r in results.items()})
    best_name = stats["sharpe"].idxmax()
    best = results[best_name]

    figures = [
        ("Growth of 100", plots.equity_chart(results, mode=theme)),
        ("Drawdown", plots.drawdown_chart(results, mode=theme)),
        ("Return by calendar year", plots.annual_returns_chart(results, mode=theme)),
        ("Rolling Sharpe", plots.rolling_sharpe_chart(
            results, periods_per_year=cfg.periods_per_year, mode=theme)),
        (f"Monthly returns: {best_name}", plots.monthly_heatmap(best.returns, mode=theme)),
        (f"Allocation: {best_name}", plots.allocation_chart(best.positions, mode=theme)),
        ("Correlation across the universe", plots.correlation_heatmap(returns_panel(prices), mode=theme)),
    ]

    chart_html = []
    for index, (heading, fig) in enumerate(figures):
        # The page supplies its own heading, so drop the figure's own title
        # rather than printing the same words twice.
        fig.update_layout(title_text=None, margin={"t": 48})
        if index == 0:
            include_js = True if embed_plotly else "cdn"
        else:
            include_js = False
        body = fig.to_html(
            include_plotlyjs=include_js,
            full_html=False,
            config={"displayModeBar": False, "responsive": True},
        )
        chart_html.append(f'<section class="chart"><h3>{heading}</h3>{body}</section>')

    perf = best.performance
    cards = [
        ("Best Sharpe", best_name),
        ("CAGR", f"{perf.cagr * 100:.1f}%"),
        ("Volatility", f"{perf.annual_volatility * 100:.1f}%"),
        ("Max drawdown", f"{perf.max_drawdown * 100:.1f}%"),
        ("Sharpe", f"{perf.sharpe:.2f}"),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="label">{label}</div><div class="value">{value}</div></div>'
        for label, value in cards
    )

    evidence_html = "".join(
        f"<h3>{name}</h3><p>{text}</p>" for name, text in evidence.items() if text
    )

    warnings = []
    if simulated:
        warnings.append(
            '<div class="note alarm"><strong>These results are partly fiction.</strong> '
            f'Bars for {", ".join(simulated)} are simulated, not observed. Any statistic '
            'computed from them describes a random number generator. Trend-following '
            'rules in particular score absurdly well on simulated series. Remove these '
            'symbols or supply real history before reading anything below.</div>'
        )
    if dropped:
        warnings.append(
            '<div class="note caveat"><strong>Symbols left out.</strong> '
            f'{", ".join(dropped)} could not be loaded from any provider and were '
            'excluded, so the universe below is smaller than the one requested.</div>'
        )
    warnings_html = "".join(warnings)

    first = next(iter(prices.values()))
    span = f"{first.index[0].date()} to {first.index[-1].date()} ({len(first)} bars, {interval})"
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{_stylesheet(surface)}</style></head>
<body><div class="wrap">
<header>
  <h1>{title}</h1>
  <p class="sub">{len(prices)} instruments &middot; {span} &middot; generated {generated}</p>
</header>

<div class="cards">{cards_html}</div>

{warnings_html}

<div class="note caveat">
  <strong>Read this before the numbers.</strong> Every figure below is a
  backtest. It is what the rules would have done on this sample, with
  {cfg.commission_bps:.0f} basis points of commission and {cfg.slippage_bps:.0f} of
  slippage charged on every trade, filled at the following bar's close. It is not
  a forecast, it does not model market impact, borrowing cost, tax or the
  liquidity of a real fill, and a single sample of this length cannot separate
  skill from luck. Treat the walk-forward and bootstrap tools in the app as the
  actual evidence, and this page as a description.
</div>

<h2>Results</h2>
{_table_html(_format_table(stats), surface)}

<h2>Charts</h2>
{''.join(chart_html)}

<h2>What is known about these approaches</h2>
{evidence_html}

<h2>Data</h2>
{_table_html(coverage, surface)}

<footer>
  Generated by the charting analysis app. Backtested results are hypothetical and
  carry no guarantee of future performance. Nothing here is financial advice.
</footer>
</div></body></html>"""

    output = output or (config.REPORTS_DIR / "strategy_report.html")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return output

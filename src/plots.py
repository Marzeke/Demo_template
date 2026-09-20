"""Chart builders, all on the brand theme.

Rules these figures follow, because they are what make a chart readable rather
than merely colourful:

* **One y-axis per panel.** Two measures on different scales get two panels,
  never two axes on one plot.
* **Colour by identity, in a fixed order.** A strategy keeps its colour when
  another is filtered out. Past six series the rest fold into "Other" rather
  than inventing hues nobody can tell apart.
* **A legend whenever there are two or more series**, plus direct labels at the
  right edge when there are few enough to place.
* **Status colours are reserved** for gain and loss, and never double as a
  series colour.
* **Recessive grid and axes**, thin marks, and a crosshair hover on every
  time-series panel.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src import config
from src.theme import Surface, candle_colours, get_surface, plotly_template

_HOVER = {"hovermode": "x unified"}


def _apply_theme(fig: go.Figure, surface: Surface, title: str | None, height: int) -> go.Figure:
    layout = plotly_template(surface.mode)["layout"]
    fig.update_layout(**layout, height=height, **_HOVER)
    if title:
        # Give the title its own line above the legend rather than letting the
        # two overlap at the top-left corner.
        fig.update_layout(
            title={"text": title, "y": 0.985, "yanchor": "top"},
            legend={"y": 1.015, "yanchor": "bottom"},
            margin={"l": 56, "r": 24, "t": 92, "b": 44},
        )
    fig.update_xaxes(showgrid=False, showspikes=True, spikemode="across",
                     spikethickness=1, spikecolor=surface.axis, spikedash="dot")
    fig.update_yaxes(gridcolor=surface.grid, zeroline=False)
    return fig


def fold_other(frame: pd.DataFrame, keep: int = 6, by: str = "mean_abs") -> pd.DataFrame:
    """Keep the ``keep`` most important columns and sum the rest into "Other".

    Past a handful of series a categorical palette stops being readable, so the
    tail is aggregated rather than given invented colours.
    """
    if frame.shape[1] <= keep:
        return frame
    score = frame.abs().mean() if by == "mean_abs" else frame.abs().max()
    top = list(score.sort_values(ascending=False).index[:keep])
    rest = [c for c in frame.columns if c not in top]
    out = frame[top].copy()
    out["Other"] = frame[rest].sum(axis=1)
    return out


def _clip_chart(chart, index: pd.Index):
    """Reindex a strategy's overlays and panels onto the visible bars."""
    from src.strategies.base import StrategyChart

    return StrategyChart(
        price_overlays=chart.price_overlays.reindex(index)
        if not chart.price_overlays.empty else chart.price_overlays,
        panels={title: frame.reindex(index) for title, frame in chart.panels.items()},
        bands=list(chart.bands),
        pairs=list(getattr(chart, "pairs", [])),
        levels=dict(chart.levels),
    )


def _series_colours(names, surface: Surface, pairs=()) -> dict[str, str]:
    """Map names to categorical slots in fixed order, with "Other" set aside.

    ``pairs`` names columns that belong to the same object - the two edges of one
    channel, say. Both members take the same colour, because they are one thing,
    and giving them different hues implies a contrast that is not there.
    """
    partner = {}
    for first, second in pairs:
        partner[second] = first

    colours, slot = {}, 0
    for name in names:
        if str(name).lower() == "other":
            colours[name] = surface.other
            continue
        mate = partner.get(name)
        if mate is not None and mate in colours:
            colours[name] = colours[mate]
            continue
        colours[name] = surface.series_colour(slot)
        slot += 1
    return colours


def _direct_labels(fig: go.Figure, frame: pd.DataFrame, colours: dict[str, str],
                   surface: Surface, fmt: str = "{:.0f}") -> None:
    """Label the right-hand end of each line, when there are few enough to place.

    Only for single-panel figures. Annotations are placed on the default axes,
    so passing subplot coordinates here would fail on a plain figure.
    """
    if frame.shape[1] > 4:
        return
    for name in frame.columns:
        series = frame[name].dropna()
        if series.empty:
            continue
        fig.add_annotation(
            x=series.index[-1], y=float(series.iloc[-1]),
            text=f"  {name} {fmt.format(series.iloc[-1])}",
            showarrow=False, xanchor="left", font={"size": 11, "color": colours[name]},
        )


# --------------------------------------------------------------------------
# Price chart
# --------------------------------------------------------------------------

def price_chart(
    df: pd.DataFrame,
    symbol: str,
    chart=None,
    positions: pd.Series | None = None,
    mode: str = config.THEME_MODE,
    candle_scheme: str = config.CANDLE_SCHEME,
    show_volume: bool = True,
    title: str | None = None,
    height: int | None = None,
) -> go.Figure:
    """Candles for one symbol, with a strategy's overlays and its own panels.

    ``chart`` is a :class:`src.strategies.base.StrategyChart`; when supplied its
    price overlays are drawn over the candles and each of its panels becomes a
    stacked row beneath them, so the strategy's reasoning is visible rather than
    implied.
    """
    surface = get_surface(mode)
    up, down = candle_colours(mode, candle_scheme)

    # A strategy computes its indicators on the full history so warm-up periods
    # are correct, but the chart may show only a window of it. Clip everything to
    # the candles on screen, or the price panel gets squashed into a corner by
    # overlays that run far past it.
    if chart is not None:
        chart = _clip_chart(chart, df.index)

    panels = dict(chart.panels) if chart is not None else {}
    rows = 1 + (1 if show_volume else 0) + len(panels)
    heights = [0.52] + ([0.12] if show_volume else [])
    remaining = 1.0 - sum(heights)
    heights += [remaining / len(panels)] * len(panels) if panels else []
    if not panels and not show_volume:
        heights = [1.0]
    elif not panels:
        heights = [0.78, 0.22]

    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=heights,
        subplot_titles=[""] + (["Volume"] if show_volume else []) + list(panels),
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
            name=symbol,
            increasing={"line": {"color": up, "width": 1}, "fillcolor": up},
            decreasing={"line": {"color": down, "width": 1}, "fillcolor": down},
            showlegend=False,
        ),
        row=1, col=1,
    )

    # Price overlays, and any shaded band between a named pair of them.
    if chart is not None and not chart.price_overlays.empty:
        overlays = chart.price_overlays
        colours = _series_colours(
            overlays.columns, surface,
            pairs=list(chart.bands) + list(getattr(chart, "pairs", [])),
        )
        band_members = {c for pair in chart.bands for c in pair}
        for lower_name, upper_name in chart.bands:
            if lower_name in overlays and upper_name in overlays:
                fig.add_trace(
                    go.Scatter(x=overlays.index, y=overlays[lower_name], line={"width": 0},
                               showlegend=False, hoverinfo="skip", name=lower_name),
                    row=1, col=1,
                )
                fig.add_trace(
                    go.Scatter(x=overlays.index, y=overlays[upper_name], line={"width": 0},
                               fill="tonexty", fillcolor=surface.band, showlegend=False,
                               hoverinfo="skip", name=upper_name),
                    row=1, col=1,
                )
        for name in overlays.columns:
            fig.add_trace(
                go.Scatter(
                    x=overlays.index, y=overlays[name], name=str(name),
                    line={"color": colours[name], "width": 2,
                          "dash": "dot" if name in band_members else "solid"},
                    mode="lines",
                ),
                row=1, col=1,
            )

    # Entry and exit markers mark changes of *direction*, not changes of size.
    # A volatility-targeted strategy adjusts its weight on nearly every bar, so
    # marking weight changes would bury the chart in triangles that mean nothing.
    if positions is not None and positions.abs().sum() > 0:
        side = np.sign(positions.fillna(0.0))
        previous = side.shift(1).fillna(0.0)
        opened_long = side[(side > 0) & (previous <= 0)].index
        opened_short = side[(side < 0) & (previous >= 0)].index
        closed = side[(side == 0) & (previous != 0)].index
        for stamps, colour, marker, label in (
            (opened_long, surface.up, "triangle-up", "Open long"),
            (opened_short, surface.down, "triangle-down", "Open short"),
            (closed, surface.flat, "x", "Close"),
        ):
            stamps = [s for s in stamps if s in df.index]
            if not stamps:
                continue
            fig.add_trace(
                go.Scatter(
                    x=stamps, y=df.loc[stamps, "close"], mode="markers", name=label,
                    marker={"symbol": marker, "size": 10, "color": colour,
                            "line": {"width": 2, "color": surface.background}},
                    hovertemplate="%{x|%Y-%m-%d}: " + label + "<extra></extra>",
                ),
                row=1, col=1,
            )

    current_row = 2
    if show_volume:
        vol_colour = np.where(df["close"] >= df["open"], up, down)
        fig.add_trace(
            go.Bar(x=df.index, y=df["volume"], name="Volume", marker={"color": vol_colour},
                   opacity=0.55, showlegend=False),
            row=current_row, col=1,
        )
        current_row += 1

    for panel_title, frame in panels.items():
        colours = _series_colours(frame.columns, surface)
        for name in frame.columns:
            series = frame[name]
            is_histogram = "hist" in str(name).lower()
            if is_histogram:
                bar_colour = np.where(series >= 0, surface.up, surface.down)
                fig.add_trace(
                    go.Bar(x=series.index, y=series, name=str(name),
                           marker={"color": bar_colour}, opacity=0.6, showlegend=False),
                    row=current_row, col=1,
                )
            else:
                # A position or direction series is piecewise constant, so draw
                # it as steps rather than sloping between states it never held.
                stepped = str(name).lower() in {"direction", "position", "weight"}
                fig.add_trace(
                    go.Scatter(
                        x=series.index, y=series, name=str(name),
                        line={"color": colours[name], "width": 2,
                              "shape": "hv" if stepped else "linear"},
                        mode="lines", showlegend=False,
                    ),
                    row=current_row, col=1,
                )
        for level in (chart.levels.get(panel_title, []) if chart else []):
            fig.add_hline(y=level, line={"color": surface.axis, "width": 1, "dash": "dot"},
                          row=current_row, col=1)
        current_row += 1

    fig.update_layout(xaxis_rangeslider_visible=False, barmode="overlay")
    height = height or (360 + 150 * (rows - 1))
    _apply_theme(fig, surface, title or f"{symbol} price and signals", height)
    for annotation in fig.layout.annotations:
        annotation.font.size = 12
        annotation.font.color = surface.text_secondary
    return fig


# --------------------------------------------------------------------------
# Performance charts
# --------------------------------------------------------------------------

def equity_chart(results: dict, mode: str = config.THEME_MODE, log_scale: bool = False,
                 rebase: float = 100.0, title: str = "Growth of 100", height: int = 420) -> go.Figure:
    """Rebased equity curves, one line per strategy."""
    surface = get_surface(mode)
    frame = pd.DataFrame({name: res.equity for name, res in results.items()}).dropna(how="all")
    if frame.empty:
        return _apply_theme(go.Figure(), surface, title, height)
    frame = frame.divide(frame.bfill().iloc[0]).multiply(rebase)
    frame = fold_other(frame, keep=6, by="max_abs")
    colours = _series_colours(frame.columns, surface)

    fig = go.Figure()
    for name in frame.columns:
        fig.add_trace(
            go.Scatter(x=frame.index, y=frame[name], name=str(name), mode="lines",
                       line={"color": colours[name], "width": 2},
                       hovertemplate="%{y:.1f}<extra>" + str(name) + "</extra>")
        )
    fig.add_hline(y=rebase, line={"color": surface.axis, "width": 1, "dash": "dot"})
    fig.update_yaxes(type="log" if log_scale else "linear", title_text="Index")
    _apply_theme(fig, surface, title, height)
    _direct_labels(fig, frame, colours, surface, fmt="{:.0f}")
    fig.update_layout(showlegend=frame.shape[1] > 1, margin={"r": 140})
    return fig


def drawdown_chart(results: dict, mode: str = config.THEME_MODE,
                   title: str = "Drawdown from peak", height: int = 300) -> go.Figure:
    """Underwater curves. Depth and, just as important, how long they last."""
    surface = get_surface(mode)
    frame = pd.DataFrame({name: res.drawdown for name, res in results.items()}).dropna(how="all")
    if frame.empty:
        return _apply_theme(go.Figure(), surface, title, height)
    frame = fold_other(frame, keep=6)
    colours = _series_colours(frame.columns, surface)

    fig = go.Figure()
    single = frame.shape[1] == 1
    for name in frame.columns:
        fig.add_trace(
            go.Scatter(
                x=frame.index, y=frame[name] * 100.0, name=str(name), mode="lines",
                line={"color": colours[name], "width": 2},
                fill="tozeroy" if single else None,
                fillcolor=surface.band if single else None,
                hovertemplate="%{y:.1f}%<extra>" + str(name) + "</extra>",
            )
        )
    fig.update_yaxes(title_text="Percent", ticksuffix="%")
    _apply_theme(fig, surface, title, height)
    fig.update_layout(showlegend=not single)
    return fig


def rolling_sharpe_chart(results: dict, window: int = 126, periods_per_year: int = 252,
                         mode: str = config.THEME_MODE, height: int = 300) -> go.Figure:
    """Sharpe on a rolling window: whether an edge held up, or came from one year."""
    from src.backtest.metrics import rolling_sharpe

    surface = get_surface(mode)
    frame = pd.DataFrame(
        {name: rolling_sharpe(res.returns, window, periods_per_year) for name, res in results.items()}
    ).dropna(how="all")
    if frame.empty:
        return _apply_theme(go.Figure(), surface, "Rolling Sharpe", height)
    frame = fold_other(frame, keep=6)
    colours = _series_colours(frame.columns, surface)

    fig = go.Figure()
    for name in frame.columns:
        fig.add_trace(
            go.Scatter(x=frame.index, y=frame[name], name=str(name), mode="lines",
                       line={"color": colours[name], "width": 2},
                       hovertemplate="%{y:.2f}<extra>" + str(name) + "</extra>")
        )
    fig.add_hline(y=0.0, line={"color": surface.axis, "width": 1, "dash": "dot"})
    fig.update_yaxes(title_text="Sharpe ratio")
    _apply_theme(fig, surface, f"Rolling Sharpe over {window} bars", height)
    fig.update_layout(showlegend=frame.shape[1] > 1)
    return fig


def allocation_chart(positions: pd.DataFrame, mode: str = config.THEME_MODE,
                     title: str = "Allocation over time", height: int = 320) -> go.Figure:
    """Where the book actually was, bar by bar."""
    surface = get_surface(mode)
    frame = fold_other(positions.fillna(0.0), keep=6)
    colours = _series_colours(frame.columns, surface)

    fig = go.Figure()
    for name in frame.columns:
        fig.add_trace(
            go.Scatter(
                x=frame.index, y=frame[name] * 100.0, name=str(name), mode="lines",
                line={"color": colours[name], "width": 0.5}, stackgroup="one",
                hovertemplate="%{y:.1f}%<extra>" + str(name) + "</extra>",
            )
        )
    fig.update_yaxes(title_text="Weight", ticksuffix="%")
    _apply_theme(fig, surface, title, height)
    return fig


# --------------------------------------------------------------------------
# Matrix views
# --------------------------------------------------------------------------

def _diverging_scale(surface: Surface) -> list:
    """Two poles with a neutral midpoint. Never a hue in the middle."""
    from src.theme import DIVERGING_NEGATIVE, DIVERGING_POSITIVE
    return [[0.0, DIVERGING_NEGATIVE], [0.5, surface.diverging_mid], [1.0, DIVERGING_POSITIVE]]


def monthly_heatmap(returns: pd.Series, mode: str = config.THEME_MODE,
                    title: str = "Monthly returns", height: int = 320) -> go.Figure:
    """Calendar months down the years. Values are labelled, not colour alone."""
    from src.backtest.metrics import monthly_returns

    surface = get_surface(mode)
    table = monthly_returns(returns)
    if table.empty:
        return _apply_theme(go.Figure(), surface, title, height)

    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    table = table.reindex(columns=range(1, 13))
    values = table.to_numpy() * 100.0
    limit = float(np.nanmax(np.abs(values))) if np.isfinite(values).any() else 1.0

    fig = go.Figure(
        go.Heatmap(
            z=values, x=names, y=[str(y) for y in table.index],
            colorscale=_diverging_scale(surface), zmid=0.0, zmin=-limit, zmax=limit,
            text=np.where(np.isnan(values), "", np.round(values, 1).astype(str)),
            texttemplate="%{text}", textfont={"size": 10},
            hovertemplate="%{y} %{x}: %{z:.2f}%<extra></extra>",
            xgap=2, ygap=2,
            colorbar={"title": "%", "thickness": 10, "outlinewidth": 0},
        )
    )
    fig.update_yaxes(autorange="reversed")
    return _apply_theme(fig, surface, title, height)


def correlation_heatmap(returns: pd.DataFrame, mode: str = config.THEME_MODE,
                        title: str = "Return correlation", height: int = 460) -> go.Figure:
    """How much of the book is really one bet."""
    surface = get_surface(mode)
    corr = returns.corr()
    if corr.empty:
        return _apply_theme(go.Figure(), surface, title, height)
    fig = go.Figure(
        go.Heatmap(
            z=corr.to_numpy(), x=list(corr.columns), y=list(corr.index),
            colorscale=_diverging_scale(surface), zmid=0.0, zmin=-1.0, zmax=1.0,
            text=np.round(corr.to_numpy(), 2).astype(str), texttemplate="%{text}",
            textfont={"size": 10},
            hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>",
            xgap=2, ygap=2,
            colorbar={"title": "r", "thickness": 10, "outlinewidth": 0},
        )
    )
    fig.update_yaxes(autorange="reversed")
    return _apply_theme(fig, surface, title, height)


def return_distribution(results: dict, mode: str = config.THEME_MODE,
                        title: str = "Distribution of bar returns", height: int = 320) -> go.Figure:
    """The shape of the returns, where the tail risk is actually visible."""
    surface = get_surface(mode)
    frame = pd.DataFrame({name: res.returns for name, res in results.items()}).dropna(how="all")
    if frame.empty:
        return _apply_theme(go.Figure(), surface, title, height)
    frame = fold_other(frame, keep=6)
    colours = _series_colours(frame.columns, surface)

    fig = go.Figure()
    for name in frame.columns:
        fig.add_trace(
            go.Histogram(x=frame[name] * 100.0, name=str(name), opacity=0.55,
                         marker={"color": colours[name]}, nbinsx=80)
        )
    fig.update_layout(barmode="overlay")
    fig.update_xaxes(title_text="Return per bar", ticksuffix="%")
    fig.update_yaxes(title_text="Bars")
    _apply_theme(fig, surface, title, height)
    fig.update_layout(showlegend=frame.shape[1] > 1)
    return fig


def annual_returns_chart(results: dict, mode: str = config.THEME_MODE,
                         title: str = "Return by calendar year", height: int = 340) -> go.Figure:
    """Grouped bars by year. Gaps between bars, and a labelled zero line."""
    from src.backtest.metrics import calendar_year_returns

    surface = get_surface(mode)
    frame = pd.DataFrame(
        {name: calendar_year_returns(res.returns) for name, res in results.items()}
    ).dropna(how="all")
    if frame.empty:
        return _apply_theme(go.Figure(), surface, title, height)
    frame = fold_other(frame, keep=6, by="max_abs")
    colours = _series_colours(frame.columns, surface)

    fig = go.Figure()
    for name in frame.columns:
        fig.add_trace(
            go.Bar(x=[str(i) for i in frame.index], y=frame[name] * 100.0, name=str(name),
                   marker={"color": colours[name], "line": {"width": 2, "color": surface.background}},
                   hovertemplate="%{x}: %{y:.1f}%<extra>" + str(name) + "</extra>")
        )
    fig.add_hline(y=0.0, line={"color": surface.axis, "width": 1})
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
    fig.update_yaxes(title_text="Return", ticksuffix="%")
    _apply_theme(fig, surface, title, height)
    fig.update_layout(showlegend=frame.shape[1] > 1)
    return fig


def save(fig: go.Figure, filename: str, directory=None) -> str:
    """Write a figure to ``reports/figures`` as a self-contained HTML file."""
    directory = directory or config.FIGURES_DIR
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(path), include_plotlyjs="cdn", full_html=True)
    return str(path)

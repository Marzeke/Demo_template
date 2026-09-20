"""Brand theme for every chart and surface in the app.

Colour is assigned by the *job* it does, not by taste:

* **Brand**      - identity: navigation, headings, chrome.
* **Categorical**- series identity (one strategy = one hue, fixed order, never cycled).
* **Sequential** - magnitude on a single brand hue, light to dark.
* **Diverging**  - polarity around a neutral midpoint (returns above/below zero).
* **Status**     - state (profit, loss, caution). Reserved; never reused as a series.

The categorical slots were checked with the ``validate_palette`` six-check
validator in both light and dark mode: lightness band, chroma floor, adjacent-pair
colour-vision-deficiency separation, normal-vision floor and contrast vs surface.
Slot 1 is the brand Middle Blue; the remaining hues are stepped away from it so
that adjacent series stay separable for protan, deutan and tritan viewers.

The brand blues alone fail as a *categorical* palette - they are one hue family,
and the deep navy and light blue sit outside the lightness band. They are
therefore used for brand chrome and for the sequential ramp, which is what a
single-hue family is for.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Brand palette
# --------------------------------------------------------------------------

BRAND_BLUE = "#002664"
BRAND_WHITE = "#FFFFFF"
BRAND_BLACK = "#000000"
BRAND_DARK_BLUE = "#0A34A1"
BRAND_MIDDLE_BLUE = "#4B87E0"
BRAND_LIGHT_BLUE = "#BCDBEC"

# --------------------------------------------------------------------------
# Categorical series slots - fixed order, never cycled
# --------------------------------------------------------------------------

CATEGORICAL_LIGHT = (
    BRAND_MIDDLE_BLUE,  # 1 blue   (brand)
    "#eb6834",          # 2 orange
    "#1baf7a",          # 3 aqua
    "#eda100",          # 4 yellow
    "#e87ba4",          # 5 magenta
    "#4a3aa7",          # 6 violet
)

CATEGORICAL_DARK = (
    BRAND_MIDDLE_BLUE,  # 1 blue   (brand)
    "#d95926",          # 2 orange
    "#199e70",          # 3 aqua
    "#c98500",          # 4 yellow
    "#d55181",          # 5 magenta
    "#9085e9",          # 6 violet
)

#: Past slot 6 a chart does not invent a hue - it folds the rest into "Other",
#: facets into small multiples, or drops series. See :func:`series_colour`.
MAX_SERIES = len(CATEGORICAL_LIGHT)
OTHER_LIGHT = "#8a8985"
OTHER_DARK = "#9d9c96"

# Sequential: one brand hue, light to dark.
SEQUENTIAL = (BRAND_LIGHT_BLUE, BRAND_MIDDLE_BLUE, BRAND_DARK_BLUE, BRAND_BLUE)

# Diverging: warm/cool poles with a neutral (not a hue) midpoint.
DIVERGING_NEGATIVE = "#d03b3b"
DIVERGING_POSITIVE = BRAND_BLUE
DIVERGING_MID_LIGHT = "#f0efec"
DIVERGING_MID_DARK = "#383835"

# Status - reserved, always paired with a label or icon, never colour alone.
STATUS_GOOD = "#0ca30c"
STATUS_WARNING = "#fab219"
STATUS_SERIOUS = "#ec835a"
STATUS_CRITICAL = "#d03b3b"


@dataclass(frozen=True)
class Surface:
    """Everything a chart needs to sit correctly on one background."""

    mode: str
    background: str
    panel: str
    text_primary: str
    text_secondary: str
    text_muted: str
    grid: str
    axis: str
    categorical: tuple[str, ...]
    other: str
    diverging_mid: str
    up: str
    down: str
    flat: str
    band: str = field(default="")

    def series_colour(self, index: int) -> str:
        """Colour for categorical slot ``index`` (0-based), fixed, never cycled."""
        if index < 0:
            raise ValueError("series index must be >= 0")
        if index >= len(self.categorical):
            return self.other
        return self.categorical[index]


LIGHT = Surface(
    mode="light",
    background=BRAND_WHITE,
    panel="#f6f8fb",
    text_primary="#101418",
    text_secondary="#4a5260",
    text_muted="#767e8c",
    grid="#e6ebf2",
    axis="#c3cbd8",
    categorical=CATEGORICAL_LIGHT,
    other=OTHER_LIGHT,
    diverging_mid=DIVERGING_MID_LIGHT,
    up=STATUS_GOOD,
    down=STATUS_CRITICAL,
    flat="#8a8985",
    band="rgba(75,135,224,0.14)",
)

DARK = Surface(
    mode="dark",
    background="#11161d",
    panel="#171e27",
    text_primary="#FFFFFF",
    text_secondary="#b8c2d0",
    text_muted="#8a94a3",
    grid="#222c38",
    axis="#3a4656",
    categorical=CATEGORICAL_DARK,
    other=OTHER_DARK,
    diverging_mid=DIVERGING_MID_DARK,
    up=STATUS_GOOD,
    down=STATUS_CRITICAL,
    flat="#9d9c96",
    band="rgba(75,135,224,0.20)",
)

SURFACES = {"light": LIGHT, "dark": DARK}

#: Candle colour schemes. ``classic`` uses the reserved status colours, which is
#: what traders read instinctively. ``brand`` keeps the chart inside the brand
#: blues for report screenshots that must stay on-palette.
CANDLE_SCHEMES = {
    "classic": {"light": (STATUS_GOOD, STATUS_CRITICAL), "dark": (STATUS_GOOD, STATUS_CRITICAL)},
    "brand": {"light": (BRAND_MIDDLE_BLUE, BRAND_BLUE), "dark": (BRAND_MIDDLE_BLUE, BRAND_LIGHT_BLUE)},
}


def get_surface(mode: str = "light") -> Surface:
    """Return the :class:`Surface` for ``mode`` (``light`` or ``dark``)."""
    try:
        return SURFACES[mode]
    except KeyError:
        raise ValueError(f"unknown theme mode {mode!r}; expected one of {sorted(SURFACES)}") from None


def candle_colours(mode: str = "light", scheme: str = "classic") -> tuple[str, str]:
    """Return ``(up, down)`` candle colours for ``mode`` under ``scheme``."""
    try:
        return CANDLE_SCHEMES[scheme][mode]
    except KeyError:
        raise ValueError(f"unknown candle scheme {scheme!r}/{mode!r}") from None


def plotly_template(mode: str = "light") -> dict:
    """A Plotly template dict carrying the brand surface for ``mode``."""
    s = get_surface(mode)
    return {
        "layout": {
            "colorway": list(s.categorical),
            "paper_bgcolor": s.background,
            "plot_bgcolor": s.background,
            "font": {
                "family": "Inter, 'Segoe UI', Helvetica, Arial, sans-serif",
                "size": 13,
                "color": s.text_primary,
            },
            "title": {"font": {"size": 17, "color": s.text_primary}, "x": 0.0, "xanchor": "left"},
            "xaxis": {
                "gridcolor": s.grid,
                "linecolor": s.axis,
                "zerolinecolor": s.grid,
                "tickfont": {"color": s.text_secondary, "size": 11},
                "title": {"font": {"color": s.text_secondary, "size": 12}},
            },
            "yaxis": {
                "gridcolor": s.grid,
                "linecolor": s.axis,
                "zerolinecolor": s.grid,
                "tickfont": {"color": s.text_secondary, "size": 11},
                "title": {"font": {"color": s.text_secondary, "size": 12}},
            },
            "legend": {
                "font": {"color": s.text_secondary, "size": 11},
                "bgcolor": "rgba(0,0,0,0)",
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.02,
                "xanchor": "left",
                "x": 0.0,
            },
            "hoverlabel": {"font": {"size": 12}, "namelength": -1},
            "margin": {"l": 56, "r": 24, "t": 56, "b": 44},
        }
    }

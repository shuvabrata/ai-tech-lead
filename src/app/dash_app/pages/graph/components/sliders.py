"""Slider components for the graph visualization page.

Provides reusable factory functions for Dash slider components used
across the graph page layout.
"""

from dash import dcc, html
from app.dash_app.styles import (
    COLOR_GRAY_DARK,
    FONT_WEIGHT_SEMIBOLD,
)


def create_time_slider_pair(suffix: str, label: str) -> html.Div:
    """Create a paired time-range filter section with coarse and fine sliders.

    Returns a muted-background ``<div>`` containing the property label, a
    coarse ``dcc.RangeSlider``, a fine ``dcc.RangeSlider`` (initialised to
    the same range), and a value label at the bottom.

    Parameters
    ----------
    suffix : str
        ID suffix for the slider and label components (e.g. ``"created"``
        produces ``id="time-slider-created"``, ``id="time-slider-created-fine"``,
        and ``id="time-slider-created-label"``).
    label : str
        Human-readable label text (e.g. ``"Created At"``).

    Returns
    -------
    html.Div
        A ``<div>`` with muted background containing all elements.
    """
    return html.Div([
        html.Label(label, style={
            "fontSize": "11px",
            "fontWeight": FONT_WEIGHT_SEMIBOLD,
            "color": COLOR_GRAY_DARK,
            "marginBottom": "4px",
            "display": "block",
        }),
        dcc.RangeSlider(
            id=f"time-slider-{suffix}",
            min=0, max=1, step=1,
            value=[0, 1],
            marks=None,
            tooltip={"placement": "bottom", "always_visible": False, "transform": "epochDayToDate"},
            allow_direct_input=False,
        ),
        dcc.RangeSlider(
            id=f"time-slider-{suffix}-fine",
            min=0, max=1, step=1,
            value=[0, 1],
            marks=None,
            tooltip={"placement": "bottom", "always_visible": False, "transform": "epochDayToDate"},
            allow_direct_input=False,
        ),
        html.Small(
            id=f"time-slider-{suffix}-label",
            className="d-block mt-1",
            style={"fontSize": "10px", "color": "var(--color-text-secondary)"},
        ),
    ], style={
        "backgroundColor": "var(--color-background-pale)",
        "border": "1px solid var(--color-border-gray)",
        "borderRadius": "4px",
        "padding": "8px",
    }, className="mb-2")

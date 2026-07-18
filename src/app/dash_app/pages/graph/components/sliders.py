"""Slider components for the graph visualization page.

Provides reusable factory functions for Dash slider components used
across the graph page layout.
"""

from dash import dcc, html
from app.dash_app.styles import (
    COLOR_GRAY_DARK,
    COLOR_TEXT_SECONDARY,
    FONT_WEIGHT_SEMIBOLD,
)


def create_time_slider(suffix: str, label: str) -> html.Div:
    """Create a time-range slider with label and value display.

    Parameters
    ----------
    suffix : str
        ID suffix for the slider and label components (e.g. ``"created"``
        produces ``id="time-slider-created"`` and ``id="time-slider-created-label"``).
    label : str
        Human-readable label text (e.g. ``"Created At"``).

    Returns
    -------
    html.Div
        A ``<div>`` containing the label, RangeSlider, and small label display.
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
        html.Small(
            id=f"time-slider-{suffix}-label",
            className="d-block mt-1",
            style={"fontSize": "10px", "color": "var(--color-text-secondary)"},
        ),
    ], className="mb-2")

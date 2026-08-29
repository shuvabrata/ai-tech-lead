"""Callbacks for the Graph Styling settings page.

Phase 4.3 — per-row live preview + reset. Each node-type row carries an inline
CSS glyph that reflects the row's current fill/border/border-width/shape/width/
height in real time (aspect-ratio preserved, with a numeric ``WxH`` label) and
a reset button that clears the row back to "inherit base".
"""

from __future__ import annotations

from typing import Any

from dash import MATCH, Input, Output, callback, html

from app.dash_app.pages.graph.utils.ui_components import get_shape_css
from app.dash_app.styles import (
    COLOR_GRAY_MEDIUM,
    FONT_SANS,
    FONT_SIZE_XTINY,
)

# Reference node dimensions (px) used as fallbacks when width/height are unset
# (matches the default node width/height in the base theme tokens: 60x50).
_REF_WIDTH = 60.0
_REF_HEIGHT = 50.0

# Preview box (px) that the glyph is normalized into. The shape is scaled so
# its larger dimension fits this box, preserving the width:height aspect ratio.
_BOX_WIDTH = 48.0
_BOX_HEIGHT = 30.0
_MIN_GLYPH = 6.0

# Default fill/border when a field is unset (matches base "default" node).
_DEFAULT_FILL = "#B8B8B8"
_DEFAULT_BORDER = "#9E9E9E"


def _num(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def build_glyph_style(
    fill: Any,
    border: Any,
    border_width: Any,
    shape: Any,
    width: Any,
    height: Any,
) -> dict[str, Any]:
    """Compute the inline glyph style from a row's current field values.

    Scales the node width/height into the preview box while **preserving the
    aspect ratio** (the larger dimension fills the box), applies fill/border,
    and layers the shape's clip-path/border-radius/transform via
    :func:`get_shape_css`.
    """
    shape_css = get_shape_css(shape or "ellipse")

    w = max(_num(width, _REF_WIDTH), 1.0)
    h = max(_num(height, _REF_HEIGHT), 1.0)
    scale = min(_BOX_WIDTH / w, _BOX_HEIGHT / h)
    glyph_w = max(_MIN_GLYPH, w * scale)
    glyph_h = max(_MIN_GLYPH, h * scale)

    style: dict[str, Any] = {
        "width": f"{glyph_w:.0f}px",
        "height": f"{glyph_h:.0f}px",
        "backgroundColor": fill or _DEFAULT_FILL,
        "border": f"{_num(border_width, 0):.0f}px solid {border or _DEFAULT_BORDER}",
        "flexShrink": 0,
    }
    for key in ("clipPath", "borderRadius", "transform"):
        if key in shape_css:
            style[key] = shape_css[key]
    return style


def _size_label(width: Any, height: Any) -> str:
    """Numeric ``WxH`` label for the preview glyph."""
    w = _num(width, _REF_WIDTH)
    h = _num(height, _REF_HEIGHT)
    return f"{w:.0f}\u00d7{h:.0f}"


@callback(
    Output(
        {"type": "gs-node-glyph", "base_theme": MATCH, "node_type": MATCH},
        "children",
    ),
    Input(
        {"type": "gs-node-field", "base_theme": MATCH, "node_type": MATCH, "field": "color"},
        "value",
    ),
    Input(
        {"type": "gs-node-field", "base_theme": MATCH, "node_type": MATCH, "field": "border"},
        "value",
    ),
    Input(
        {"type": "gs-node-field", "base_theme": MATCH, "node_type": MATCH, "field": "border_width"},
        "value",
    ),
    Input(
        {"type": "gs-node-field", "base_theme": MATCH, "node_type": MATCH, "field": "shape"},
        "value",
    ),
    Input(
        {"type": "gs-node-field", "base_theme": MATCH, "node_type": MATCH, "field": "width"},
        "value",
    ),
    Input(
        {"type": "gs-node-field", "base_theme": MATCH, "node_type": MATCH, "field": "height"},
        "value",
    ),
)
def update_node_glyph(
    fill: Any,
    border: Any,
    border_width: Any,
    shape: Any,
    width: Any,
    height: Any,
) -> list[Any]:
    """Update a row's inline preview glyph from its six field values."""
    style = build_glyph_style(fill, border, border_width, shape, width, height)
    shape_div = html.Div(style=style)
    label = html.Div(
        _size_label(width, height),
        style={
            "fontFamily": FONT_SANS,
            "fontSize": FONT_SIZE_XTINY,
            "color": COLOR_GRAY_MEDIUM,
            "lineHeight": "1",
        },
    )
    return [shape_div, label]


@callback(
    Output(
        {"type": "gs-node-field", "base_theme": MATCH, "node_type": MATCH, "field": "color"},
        "value",
    ),
    Output(
        {"type": "gs-node-field", "base_theme": MATCH, "node_type": MATCH, "field": "border"},
        "value",
    ),
    Output(
        {"type": "gs-node-field", "base_theme": MATCH, "node_type": MATCH, "field": "border_width"},
        "value",
    ),
    Output(
        {"type": "gs-node-field", "base_theme": MATCH, "node_type": MATCH, "field": "shape"},
        "value",
    ),
    Output(
        {"type": "gs-node-field", "base_theme": MATCH, "node_type": MATCH, "field": "width"},
        "value",
    ),
    Output(
        {"type": "gs-node-field", "base_theme": MATCH, "node_type": MATCH, "field": "height"},
        "value",
    ),
    Input(
        {"type": "gs-node-reset", "base_theme": MATCH, "node_type": MATCH},
        "n_clicks",
    ),
    prevent_initial_call=True,
)
def reset_node_row(_n_clicks: int) -> tuple:
    """Clear a row's six fields back to \"inherit base\" (unset)."""
    return None, None, None, None, None, None


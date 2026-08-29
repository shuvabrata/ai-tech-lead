"""Callbacks for the Graph Styling settings page.

Phase 4.3 — per-row live preview. Each node-type row carries an inline CSS
glyph that reflects the row's current fill/border/border-width/shape/width/
height in real time. The glyph reuses the legend's shape mapping so it matches
the graph's node shapes without spinning up a Cytoscape engine per row.
"""

from __future__ import annotations

from typing import Any

from dash import MATCH, Input, Output, callback, html

from app.dash_app.pages.graph.utils.ui_components import get_shape_css

# Reference node dimensions (px) used to scale the preview glyph into the
# fixed-size preview box. Matches the default node width/height in the base
# theme tokens (60px x 50px).
_REF_WIDTH = 60.0
_REF_HEIGHT = 50.0
_MAX_GLYPH = 28.0
_MIN_GLYPH = 10.0

# Default fill/border when a field is unset (matches base "default" node).
_DEFAULT_FILL = "#B8B8B8"
_DEFAULT_BORDER = "#9E9E9E"


def build_glyph_style(
    fill: Any,
    border: Any,
    border_width: Any,
    shape: Any,
    width: Any,
    height: Any,
) -> dict[str, Any]:
    """Compute the inline glyph style from a row's current field values.

    Scales the node width/height into the fixed preview box, applies the
    fill/border, and layers the shape's clip-path/border-radius/transform via
    :func:`get_shape_css`.
    """
    shape_css = get_shape_css(shape or "ellipse")

    def _num(value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    w = _num(width, _REF_WIDTH)
    h = _num(height, _REF_HEIGHT)
    scale = _MAX_GLYPH / _REF_WIDTH
    glyph_w = max(_MIN_GLYPH, min(_MAX_GLYPH, w * scale))
    glyph_h = max(_MIN_GLYPH, min(_MAX_GLYPH, h * scale))

    style: dict[str, Any] = {
        "width": f"{glyph_w:.0f}px",
        "height": f"{glyph_h:.0f}px",
        "backgroundColor": fill or _DEFAULT_FILL,
        "border": f"{_num(border_width, 0):.0f}px solid {border or _DEFAULT_BORDER}",
    }
    for key in ("clipPath", "borderRadius", "transform"):
        if key in shape_css:
            style[key] = shape_css[key]
    return style


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
    return [html.Div(style=style)]


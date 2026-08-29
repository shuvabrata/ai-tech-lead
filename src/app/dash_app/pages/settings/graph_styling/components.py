"""Reusable component builders for the Graph Styling editor.

Builds the base-mode sections, node-type cards, Edges card, and Global card
that together form the editor layout (Plan 017, Phase 4.2). IDs use
pattern-matching dicts so later phases (live preview, actions) can bind
callbacks to individual fields.
"""

from __future__ import annotations

from typing import Any

import dash_bootstrap_components as dbc
from dash import dcc, html

from app.common.graph_theme import ALLOWED_SHAPES, NODE_TYPES
from app.dash_app.styles import (
    COLOR_BACKGROUND_LIGHT,
    COLOR_BORDER,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_GRAY_MEDIUM,
    FONT_SANS,
    FONT_SIZE_SMALL,
    FONT_SIZE_XSMALL,
    FONT_SIZE_XTINY,
    FONT_WEIGHT_MEDIUM,
    FONT_WEIGHT_SEMIBOLD,
    SPACING_XXSMALL,
    SPACING_XSMALL,
    SPACING_SMALL,
)

# Common Cytoscape target-arrow shapes offered in the Edges card.
ARROW_SHAPES: tuple[str, ...] = (
    "triangle",
    "tee",
    "vee",
    "triangle-tee",
    "triangle-backcurve",
    "chevron",
    "circle",
    "diamond",
    "square",
    "none",
)

BASE_THEMES: tuple[str, ...] = ("executive-dark", "executive-light")

# Per-field metadata for a node-type card: (field_key, label, input kind).
# ``kind`` drives which widget is rendered by :func:`_build_field_input`.
_NODE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("color", "Fill", "color"),
    ("border", "Border", "color"),
    ("border_width", "Border W", "number"),
    ("shape", "Shape", "shape"),
    ("width", "Width", "number"),
    ("height", "Height", "number"),
)

# Grid template shared by the node-type header row and each node-type row:
# a fixed name column, one column per configurable field, a preview glyph,
# then a reset button.
_NODE_GRID_TEMPLATE = "140px repeat(6, minmax(0, 1fr)) 56px 36px"

# Column labels for the node-type header row (aligned with _NODE_FIELDS).
_NODE_HEADER_LABELS: tuple[str, ...] = (
    "Node Type",
    "Fill",
    "Border",
    "Border W",
    "Shape",
    "Width",
    "Height",
    "Preview",
    "",
)


# ── Field-level helpers ────────────────────────────────────────────────


def _field_label(text: str) -> html.Div:
    """Small uppercase field label."""
    return html.Div(
        text,
        style={
            "fontFamily": FONT_SANS,
            "fontSize": FONT_SIZE_XTINY,
            "fontWeight": FONT_WEIGHT_MEDIUM,
            "color": COLOR_GRAY_MEDIUM,
            "textTransform": "uppercase",
            "letterSpacing": "0.5px",
            "marginBottom": SPACING_XXSMALL,
        },
    )


def _color_input(input_id: dict[str, Any]) -> dcc.Input:
    """Native colour picker input."""
    return dcc.Input(
        id=input_id,
        type="color",
        style={
            "width": "100%",
            "height": "34px",
            "padding": "0",
            "border": f"1px solid {COLOR_BORDER}",
            "borderRadius": "2px",
            "cursor": "pointer",
            "backgroundColor": COLOR_BACKGROUND_LIGHT,
        },
    )


def _number_input(input_id: dict[str, Any]) -> dbc.Input:
    """Small numeric input."""
    return dbc.Input(
        id=input_id,
        type="number",
        min=1,
        step=1,
        style={
            "fontFamily": FONT_SANS,
            "fontSize": FONT_SIZE_SMALL,
            "padding": SPACING_XXSMALL,
            "border": f"1px solid {COLOR_BORDER}",
            "borderRadius": "2px",
            "width": "100%",
        },
    )


def _shape_input(input_id: dict[str, Any]) -> dcc.Dropdown:
    """Shape dropdown populated with the full Cytoscape shape set.

    Clearable so an empty value means "inherit the base shape".
    """
    return dcc.Dropdown(
        id=input_id,
        options=[{"label": shape, "value": shape} for shape in ALLOWED_SHAPES],
        clearable=True,
        placeholder="Inherit",
        style={"fontFamily": FONT_SANS, "fontSize": FONT_SIZE_XSMALL},
    )


def _build_field_input(
    field: str, kind: str, base_theme: str, node_type: str
) -> Any:
    """Build the input widget for a single node-type field."""
    input_id = {
        "type": "gs-node-field",
        "base_theme": base_theme,
        "node_type": node_type,
        "field": field,
    }
    if kind == "color":
        return _color_input(input_id)
    if kind == "shape":
        return _shape_input(input_id)
    return _number_input(input_id)


# ── Card builders ──────────────────────────────────────────────────────


def _card_wrapper(children: list[Any], card_id: dict[str, Any]) -> html.Div:
    """Shared card chrome (bordered box with title)."""
    return html.Div(
        children,
        id=card_id,
        style={
            "padding": SPACING_SMALL,
            "backgroundColor": COLOR_BACKGROUND_LIGHT,
            "border": f"1px solid {COLOR_BORDER}",
            "borderRadius": "2px",
            "marginBottom": SPACING_SMALL,
        },
    )


def _card_title(text: str) -> html.Div:
    return html.Div(
        text,
        style={
            "fontFamily": FONT_SANS,
            "fontSize": FONT_SIZE_SMALL,
            "fontWeight": FONT_WEIGHT_SEMIBOLD,
            "color": COLOR_CHARCOAL_MEDIUM,
            "textTransform": "uppercase",
            "letterSpacing": "0.5px",
            "marginBottom": SPACING_XSMALL,
        },
    )


def build_node_type_row(base_theme: str, node_type: str) -> html.Div:
    """Build a single editor row for one node type.

    Renders the node type name, six inline inputs (fill, border, border-width,
    shape, width, height), an inline live-preview glyph, and a reset button
    that clears the row back to "inherit base".
    """
    name = html.Div(
        node_type,
        style={
            "fontFamily": FONT_SANS,
            "fontSize": FONT_SIZE_SMALL,
            "fontWeight": FONT_WEIGHT_MEDIUM,
            "color": COLOR_CHARCOAL_MEDIUM,
        },
    )

    inputs = [
        _build_field_input(field, kind, base_theme, node_type)
        for field, _label, kind in _NODE_FIELDS
    ]

    glyph = build_node_glyph(base_theme, node_type)
    reset = build_node_reset(base_theme, node_type)

    return html.Div(
        [name, *inputs, glyph, reset],
        id={
            "type": "gs-node-row",
            "base_theme": base_theme,
            "node_type": node_type,
        },
        style={
            "display": "grid",
            "gridTemplateColumns": _NODE_GRID_TEMPLATE,
            "gap": SPACING_XSMALL,
            "alignItems": "center",
            "padding": f"{SPACING_XXSMALL} 0",
            "borderBottom": f"1px solid {COLOR_BORDER}",
        },
    )


def _node_header_row() -> html.Div:
    """Column header row aligned with the node-type rows."""
    return html.Div(
        [_field_label(label) for label in _NODE_HEADER_LABELS],
        style={
            "display": "grid",
            "gridTemplateColumns": _NODE_GRID_TEMPLATE,
            "gap": SPACING_XSMALL,
            "alignItems": "end",
            "marginBottom": SPACING_XXSMALL,
        },
    )


def build_edges_card(base_theme: str) -> html.Div:
    """Build the Edges card (applies to all edges)."""
    fields: list[html.Div] = []

    color_id = {"type": "gs-edge-field", "base_theme": base_theme, "field": "line_color"}
    fields.append(html.Div([_field_label("Line Color"), _color_input(color_id)]))

    width_id = {"type": "gs-edge-field", "base_theme": base_theme, "field": "width"}
    fields.append(html.Div([_field_label("Width"), _number_input(width_id)]))

    arrow_id = {"type": "gs-edge-field", "base_theme": base_theme, "field": "arrow_shape"}
    fields.append(
        html.Div(
            [
                _field_label("Arrow Shape"),
                dcc.Dropdown(
                    id=arrow_id,
                    options=[
                        {"label": shape, "value": shape} for shape in ARROW_SHAPES
                    ],
                    clearable=False,
                    style={"fontFamily": FONT_SANS, "fontSize": FONT_SIZE_XSMALL},
                ),
            ]
        )
    )

    label_color_id = {
        "type": "gs-edge-field",
        "base_theme": base_theme,
        "field": "label_color",
    }
    fields.append(
        html.Div([_field_label("Label Color"), _color_input(label_color_id)])
    )

    return _card_wrapper(
        [_card_title("Edges"), html.Div(fields)],
        {"type": "gs-edges-card", "base_theme": base_theme},
    )


def build_global_card(base_theme: str) -> html.Div:
    """Build the Global card (cross-cutting label/selection styling)."""
    fields: list[html.Div] = []

    label_color_id = {
        "type": "gs-global-field",
        "base_theme": base_theme,
        "field": "node_label_color",
    }
    fields.append(
        html.Div([_field_label("Node Label Color"), _color_input(label_color_id)])
    )

    selection_id = {
        "type": "gs-global-field",
        "base_theme": base_theme,
        "field": "selection_color",
    }
    fields.append(
        html.Div([_field_label("Selection Color"), _color_input(selection_id)])
    )

    edge_bg_id = {
        "type": "gs-global-field",
        "base_theme": base_theme,
        "field": "edge_label_background",
    }
    fields.append(
        html.Div([_field_label("Edge Label Background"), _color_input(edge_bg_id)])
    )

    return _card_wrapper(
        [_card_title("Global"), html.Div(fields)],
        {"type": "gs-global-card", "base_theme": base_theme},
    )


def _base_theme_label(base_theme: str) -> str:
    """Human-readable tab label for a base theme (e.g. 'Light' / 'Dark')."""
    return base_theme.split("-")[-1].title()


def build_base_mode_section(base_theme: str) -> html.Div:
    """Build a full base-mode section (node rows + Edges + Global)."""
    node_types = [nt for nt in NODE_TYPES if nt != "default"]

    node_rows = html.Div(
        [_node_header_row()]
        + [build_node_type_row(base_theme, nt) for nt in node_types],
        style={
            "border": f"1px solid {COLOR_BORDER}",
            "borderRadius": "2px",
            "padding": SPACING_XSMALL,
            "backgroundColor": COLOR_BACKGROUND_LIGHT,
            "marginBottom": SPACING_SMALL,
        },
    )

    # Edges + Global cards side by side.
    edge_global_row = dbc.Row(
        [
            dbc.Col(build_edges_card(base_theme), md=6, xs=12),
            dbc.Col(build_global_card(base_theme), md=6, xs=12),
        ],
        className="g-3",
    )

    return html.Div(
        [node_rows, edge_global_row],
        id={"type": "gs-base-section", "base_theme": base_theme},
    )


def build_base_mode_tabs() -> dbc.Tabs:
    """Build the tabbed base-mode editor (Dark / Light).

    The first tab (Dark) is active on load so its rows are visible without
    requiring an explicit tab selection.
    """
    return dbc.Tabs(
        [
            dbc.Tab(
                build_base_mode_section(base_theme),
                label=_base_theme_label(base_theme),
                tab_id=base_theme,
            )
            for base_theme in BASE_THEMES
        ],
        id="gs-base-mode-tabs",
        active_tab=BASE_THEMES[0],
        style={"marginBottom": SPACING_SMALL},
    )


# ── Inline per-row live preview glyph ──────────────────────────────────


def build_node_glyph(base_theme: str, node_type: str) -> html.Div:
    """Build the inline live-preview glyph for a single node-type row.

    A lightweight CSS glyph (no Cytoscape engine) that reflects the row's
    current fill/border/border-width/shape/width/height via a callback, plus a
    numeric ``WxH`` label. The shape is rendered with the same ``clip-path``
    mapping used by the node legend.
    """
    return html.Div(
        id={
            "type": "gs-node-glyph",
            "base_theme": base_theme,
            "node_type": node_type,
        },
        style={
            "width": "56px",
            "minHeight": "44px",
            "display": "flex",
            "flexDirection": "row",
            "alignItems": "center",
            "justifyContent": "flex-start",
            "gap": SPACING_XXSMALL,
        },
    )


def build_node_reset(base_theme: str, node_type: str) -> html.Button:
    """Build the row-level reset button (clears the row back to "inherit")."""
    return html.Button(
        html.I(className="fa-solid fa-rotate-left"),
        id={
            "type": "gs-node-reset",
            "base_theme": base_theme,
            "node_type": node_type,
        },
        title=f"Reset {node_type}",
        n_clicks=0,
        style={
            "background": "none",
            "border": "none",
            "color": COLOR_GRAY_MEDIUM,
            "cursor": "pointer",
            "padding": SPACING_XXSMALL,
            "fontSize": FONT_SIZE_SMALL,
        },
    )

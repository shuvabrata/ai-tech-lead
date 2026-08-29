"""Callbacks for the Graph Styling settings page.

Phase 4.3 — per-row live preview + reset. Each node-type row carries an inline
CSS glyph that reflects the row's current fill/border/border-width/shape/width/
height in real time (aspect-ratio preserved, with a numeric ``WxH`` label) and
a reset button that clears the row back to "inherit base".

Phase 4.4 — theme management. A per-tab theme selector loads a theme's
overrides into the editor; New / Duplicate / Save / Set-as-default / Delete
actions drive the ``/api/v1/graph-themes/`` REST API.
"""

from __future__ import annotations

import os
from typing import Any

import dash_bootstrap_components as dbc
import requests
from dash import (
    ALL,
    MATCH,
    Input,
    Output,
    State,
    callback,
    callback_context,
    html,
    no_update,
)
from dash.exceptions import PreventUpdate

from app.common.graph_theme import effective_semantic_theme
from app.dash_app.pages.graph.utils.ui_components import get_shape_css
from app.dash_app.pages.settings.graph_styling.components import build_editor_body
from app.dash_app.styles import (
    COLOR_GRAY_MEDIUM,
    FONT_SANS,
    FONT_SIZE_XTINY,
    get_theme_tokens,
)

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
THEMES_API = f"{API_BASE}/api/v1/graph-themes/"

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
            "whiteSpace": "nowrap",
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
    State({"type": "gs-loaded-values", "base_theme": MATCH}, "data"),
    prevent_initial_call=True,
)
def reset_node_row(
    _n_clicks: int, loaded_values: dict[str, Any] | None
) -> tuple:
    """Restore a row's six fields to their loaded (effective) values.

    Reads the effective node values cached in ``gs-loaded-values`` when the
    theme was selected and returns the original values for this node type,
    undoing any unsaved edits to the row.
    """
    node_type = callback_context.triggered_id["node_type"]
    row = (loaded_values or {}).get(node_type) or {}

    return (
        row.get("color"),
        row.get("border"),
        row.get("border_width"),
        row.get("shape"),
        row.get("width"),
        row.get("height"),
    )


# ── Edge preview ───────────────────────────────────────────────────────


def build_edge_preview_stylesheet(
    line_color: Any,
    width: Any,
    arrow_shape: Any,
    label_color: Any,
) -> list[dict[str, Any]]:
    """Build a Cytoscape stylesheet for the two-node edge preview.

    Styles the edge (line colour/width, target-arrow shape, label colour) and
    gives the two endpoint nodes a neutral appearance so the edge reads
    clearly, matching how edges render in the real graph.
    """
    color = line_color or "#C0C0C0"
    label = label_color or "#2d3748"
    stroke_w = int(_num(width, 2))
    arrow = arrow_shape or "triangle"

    return [
        {
            "selector": "node",
            "style": {
                "background-color": "#B8B8B8",
                "border-color": "#9E9E9E",
                "border-width": "1px",
                "width": "16px",
                "height": "16px",
                "label": "data(label)",
                "font-size": "9px",
                "color": "#666666",
                "text-valign": "bottom",
                "text-margin-y": "4px",
            },
        },
        {
            "selector": "edge",
            "style": {
                "width": stroke_w,
                "line-color": color,
                "target-arrow-color": color,
                "target-arrow-shape": arrow,
                "source-arrow-shape": "none",
                "mid-source-arrow-shape": "none",
                "mid-target-arrow-shape": "none",
                "arrow-scale": 1.0,
                "curve-style": "bezier",
                "label": "data(label)",
                "font-size": "9px",
                "color": label,
                "text-rotation": "autorotate",
                "text-background-color": "#ffffff",
                "text-background-opacity": 0.8,
            },
        },
    ]


@callback(
    Output({"type": "gs-edge-cytoscape", "base_theme": MATCH}, "stylesheet"),
    Input(
        {"type": "gs-edge-field", "base_theme": MATCH, "field": "line_color"}, "value"
    ),
    Input(
        {"type": "gs-edge-field", "base_theme": MATCH, "field": "width"}, "value"
    ),
    Input(
        {"type": "gs-edge-field", "base_theme": MATCH, "field": "arrow_shape"}, "value"
    ),
    Input(
        {"type": "gs-edge-field", "base_theme": MATCH, "field": "label_color"}, "value"
    ),
)
def update_edge_glyph(
    line_color: Any,
    width: Any,
    arrow_shape: Any,
    label_color: Any,
) -> list[dict[str, Any]]:
    """Update the edge preview stylesheet from the four edge field values."""
    return build_edge_preview_stylesheet(line_color, width, arrow_shape, label_color)


# ── Phase 4.4 — theme management ───────────────────────────────────────


def _list_themes(base_theme: str) -> list[dict[str, Any]]:
    """Fetch all themes for a base mode from the API."""
    resp = requests.get(THEMES_API, timeout=10)
    resp.raise_for_status()
    themes = resp.json()
    return [t for t in themes if t.get("base_theme") == base_theme]


def _theme_options(themes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build selector options with the default theme first, then by name."""
    ordered = sorted(
        themes,
        key=lambda t: (0 if t.get("is_default") else 1, t.get("name", "").lower()),
    )
    return [{"label": _theme_label(t), "value": t["id"]} for t in ordered]


def _theme_label(theme: dict[str, Any]) -> str:
    """Dropdown label for a theme (marks builtin and default)."""
    label = theme.get("name", "Unnamed")
    if theme.get("is_default"):
        label += " \u2605"
    if theme.get("source") == "builtin":
        label += " (builtin)"
    return label


def _feedback_alert(content: str, color: str) -> list[Any]:
    """Build a feedback alert region for the page."""
    return [
        dbc.Alert(
            content,
            color=color,
            dismissable=True,
            style={"fontFamily": FONT_SANS, "fontSize": FONT_SIZE_XTINY},
        )
    ]


@callback(
    Output({"type": "gs-theme-select", "base_theme": MATCH}, "options"),
    Output({"type": "gs-theme-store", "base_theme": MATCH}, "data"),
    Input("url", "pathname"),
    State({"type": "gs-theme-select", "base_theme": MATCH}, "id"),
)
def load_themes(pathname: str, select_id: dict[str, str]) -> tuple:
    """Load themes for a base mode when the page is visited.

    Fires on navigation and on first render of the matched select components.
    The ``pathname`` guard ensures it only loads for the Graph Styling page.
    """
    base_theme = select_id["base_theme"]
    if pathname not in ("/app/settings/graph-styling", "/app/settings/graph-styling/"):
        raise PreventUpdate

    try:
        themes = _list_themes(base_theme)
    except requests.RequestException:
        return [], {}

    options = [{"label": "Select a theme\u2026", "value": ""}] + _theme_options(themes)
    by_id = {str(t["id"]): t for t in themes}
    return options, by_id


@callback(
    Output({"type": "gs-editor-body", "base_theme": MATCH}, "children"),
    Output({"type": "gs-theme-name-input", "base_theme": MATCH}, "value"),
    Output({"type": "gs-theme-name", "base_theme": MATCH}, "children"),
    Output({"type": "gs-loaded-values", "base_theme": MATCH}, "data"),
    Input({"type": "gs-theme-select", "base_theme": MATCH}, "value"),
    State({"type": "gs-theme-store", "base_theme": MATCH}, "data"),
    prevent_initial_call=True,
)
def select_theme(
    theme_id: Any, store: dict[str, Any]
) -> tuple[Any, str | None, str, dict[str, Any]]:
    """Render the editor body for the selected theme.

    Populates every field with its **effective** (concrete) value, so a theme
    with sparse/no overrides still shows the base values it actually renders.
    The effective node values are also cached in ``gs-loaded-values`` so the
    per-row reset button can restore a row to its loaded values.
    """
    base_theme = callback_context.triggered_id["base_theme"]
    if theme_id is None or not store:
        raise PreventUpdate

    theme = store.get(str(theme_id))
    if theme is None:
        raise PreventUpdate

    overrides = theme.get("overrides") or {}
    effective = effective_semantic_theme(get_theme_tokens(base_theme), overrides)
    body = build_editor_body(base_theme, effective)
    name = theme.get("name", "")
    name_label = (
        f"Editing: {name}"
        + (" (builtin \u2014 duplicate to edit)" if theme.get("source") == "builtin" else "")
        + (" \u2605 default" if theme.get("is_default") else "")
    )
    loaded_values = effective.get("nodes") or {}
    return body, name, name_label, loaded_values


# Collect a theme's current field values into an overrides document.
_NODE_FIELD_MAP = {
    "color": "color",
    "border": "border",
    "border_width": "border_width",
    "shape": "shape",
    "width": "width",
    "height": "height",
}


def _collect_overrides(
    node_values: list[Any],
    node_ids: list[dict[str, str]],
    edge_values: list[Any],
    edge_ids: list[dict[str, str]],
    global_values: list[Any],
    global_ids: list[dict[str, str]],
) -> dict[str, Any]:
    """Assemble an override document from the editor's current field values.

    Empty/None values are omitted (delta semantics — inherit the base).
    """
    nodes: dict[str, dict[str, Any]] = {}
    for value, input_id in zip(node_values, node_ids):
        if not isinstance(input_id, dict):
            continue
        if value in (None, "", []):
            continue
        node_type = input_id["node_type"]
        field = input_id["field"]
        nodes.setdefault(node_type, {})[_NODE_FIELD_MAP[field]] = value

    edges: dict[str, Any] = {}
    for value, input_id in zip(edge_values, edge_ids):
        if not isinstance(input_id, dict):
            continue
        if value in (None, "", []):
            continue
        edges[input_id["field"]] = value

    global_: dict[str, Any] = {}
    for value, input_id in zip(global_values, global_ids):
        if not isinstance(input_id, dict):
            continue
        if value in (None, "", []):
            continue
        global_[input_id["field"]] = value

    return {"nodes": nodes, "edges": edges, "global": global_}


def _refresh_after_action(base_theme: str) -> tuple[Any, Any, Any, Any]:
    """Re-fetch themes and rebuild the selector options/store after a mutation."""
    themes = _list_themes(base_theme)
    options = _theme_options(themes)
    by_id = {str(t["id"]): t for t in themes}
    return options, by_id, no_update, no_update


@callback(
    Output({"type": "gs-theme-select", "base_theme": MATCH}, "options", allow_duplicate=True),
    Output({"type": "gs-theme-store", "base_theme": MATCH}, "data", allow_duplicate=True),
    Output("gs-page-feedback", "children"),
    Output({"type": "gs-theme-select", "base_theme": MATCH}, "value"),
    Input({"type": "gs-theme-new", "base_theme": MATCH}, "n_clicks"),
    State({"type": "gs-theme-name-input", "base_theme": MATCH}, "value"),
    prevent_initial_call=True,
)
def new_theme(n_clicks: int | None, name: str | None) -> tuple:
    """Create a new empty user theme."""
    base_theme = callback_context.triggered_id["base_theme"]
    if not n_clicks:
        raise PreventUpdate
    if not name:
        return no_update, no_update, _feedback_alert("Enter a theme name first.", "warning"), no_update

    try:
        resp = requests.post(
            THEMES_API,
            json={"name": name, "base_theme": base_theme, "overrides": {}},
            timeout=10,
        )
        if resp.status_code in (409, 422):
            detail = resp.json().get("detail", "Invalid request")
            return no_update, no_update, _feedback_alert(f"Create failed: {detail}", "danger"), no_update
        resp.raise_for_status()
        created = resp.json()
    except requests.RequestException as exc:
        return no_update, no_update, _feedback_alert(f"Create failed: {exc}", "danger"), no_update

    options, by_id, _, _ = _refresh_after_action(base_theme)
    return options, by_id, _feedback_alert(f"Created \u201c{created['name']}\u201d.", "success"), created["id"]


@callback(
    Output({"type": "gs-theme-select", "base_theme": MATCH}, "options", allow_duplicate=True),
    Output({"type": "gs-theme-store", "base_theme": MATCH}, "data", allow_duplicate=True),
    Output("gs-page-feedback", "children", allow_duplicate=True),
    Output({"type": "gs-theme-select", "base_theme": MATCH}, "value", allow_duplicate=True),
    Input({"type": "gs-theme-duplicate", "base_theme": MATCH}, "n_clicks"),
    State({"type": "gs-theme-select", "base_theme": MATCH}, "value"),
    prevent_initial_call=True,
)
def duplicate_theme(n_clicks: int | None, theme_id: Any) -> tuple:
    """Clone the selected theme (copy-on-write)."""
    base_theme = callback_context.triggered_id["base_theme"]
    if not n_clicks or theme_id is None:
        raise PreventUpdate

    try:
        resp = requests.post(f"{THEMES_API}{theme_id}/clone", timeout=10)
        if resp.status_code == 409:
            return no_update, no_update, _feedback_alert("Clone failed: name conflict.", "danger"), no_update
        resp.raise_for_status()
        cloned = resp.json()
    except requests.RequestException as exc:
        return no_update, no_update, _feedback_alert(f"Clone failed: {exc}", "danger"), no_update

    options, by_id, _, _ = _refresh_after_action(base_theme)
    return options, by_id, _feedback_alert(f"Duplicated to \u201c{cloned['name']}\u201d.", "success"), cloned["id"]


@callback(
    Output("gs-page-feedback", "children", allow_duplicate=True),
    Output({"type": "gs-theme-store", "base_theme": MATCH}, "data", allow_duplicate=True),
    Input({"type": "gs-theme-save", "base_theme": MATCH}, "n_clicks"),
    State({"type": "gs-theme-select", "base_theme": MATCH}, "value"),
    State({"type": "gs-theme-name-input", "base_theme": MATCH}, "value"),
    State({"type": "gs-node-field", "base_theme": MATCH, "node_type": ALL, "field": ALL}, "value"),
    State({"type": "gs-node-field", "base_theme": MATCH, "node_type": ALL, "field": ALL}, "id"),
    State({"type": "gs-edge-field", "base_theme": MATCH, "field": ALL}, "value"),
    State({"type": "gs-edge-field", "base_theme": MATCH, "field": ALL}, "id"),
    State({"type": "gs-global-field", "base_theme": MATCH, "field": ALL}, "value"),
    State({"type": "gs-global-field", "base_theme": MATCH, "field": ALL}, "id"),
    prevent_initial_call=True,
)
def save_theme(
    n_clicks: int | None,
    theme_id: Any,
    name: str | None,
    node_values: list[Any],
    node_ids: list[dict[str, str]],
    edge_values: list[Any],
    edge_ids: list[dict[str, str]],
    global_values: list[Any],
    global_ids: list[dict[str, str]],
) -> tuple:
    """Save the current editor values via a full-document PATCH."""
    if not n_clicks or theme_id is None:
        raise PreventUpdate

    overrides = _collect_overrides(
        node_values, node_ids, edge_values, edge_ids, global_values, global_ids
    )
    payload: dict[str, Any] = {"overrides": overrides}
    if name:
        payload["name"] = name

    try:
        resp = requests.patch(f"{THEMES_API}{theme_id}", json=payload, timeout=10)
        if resp.status_code == 409:
            detail = resp.json().get("detail", "Builtin themes are immutable.")
            return _feedback_alert(f"Save failed: {detail}", "danger"), no_update
        if resp.status_code == 422:
            return _feedback_alert("Save failed: invalid values.", "danger"), no_update
        resp.raise_for_status()
        updated = resp.json()
    except requests.RequestException as exc:
        return _feedback_alert(f"Save failed: {exc}", "danger"), no_update

    return _feedback_alert(f"Saved \u201c{updated['name']}\u201d.", "success"), no_update


@callback(
    Output("gs-set-default-confirm", "displayed"),
    Output("gs-set-default-pending", "data"),
    Input({"type": "gs-theme-set-default", "base_theme": ALL}, "n_clicks"),
    State({"type": "gs-theme-select", "base_theme": ALL}, "value"),
    State({"type": "gs-theme-set-default", "base_theme": ALL}, "id"),
    prevent_initial_call=True,
)
def confirm_set_default(
    n_clicks_list: list[int | None],
    selected_values: list[Any],
    button_ids: list[dict[str, str]],
) -> tuple[bool, Any]:
    """Show the set-default confirmation dialog and record the pending theme."""
    if not any(n for n in n_clicks_list):
        raise PreventUpdate

    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        raise PreventUpdate
    base_theme = triggered.get("base_theme")

    # Find the selected theme id for the clicked tab's selector.
    selected = None
    for value, bid in zip(selected_values, button_ids):
        if isinstance(bid, dict) and bid.get("base_theme") == base_theme:
            selected = value
            break

    if selected is None:
        raise PreventUpdate

    return True, {"theme_id": selected}


@callback(
    Output("gs-page-feedback", "children", allow_duplicate=True),
    Output({"type": "gs-theme-select", "base_theme": ALL}, "options", allow_duplicate=True),
    Output({"type": "gs-theme-store", "base_theme": ALL}, "data", allow_duplicate=True),
    Input("gs-set-default-confirm", "submit_n_clicks"),
    State("gs-set-default-pending", "data"),
    prevent_initial_call=True,
)
def execute_set_default(
    submit_n_clicks: int | None,
    pending: dict[str, Any] | None,
) -> tuple:
    """Set the pending theme as default for its base mode."""
    if not submit_n_clicks or not pending:
        raise PreventUpdate

    theme_id = pending.get("theme_id")
    if theme_id is None:
        raise PreventUpdate

    try:
        resp = requests.post(
            f"{THEMES_API}{theme_id}/set-default",
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return (
            _feedback_alert(f"Set default failed: {exc}", "danger"),
            [no_update, no_update],
            [no_update, no_update],
        )

    # Re-fetch themes for both base modes.
    all_options: list = []
    all_data: list = []
    for bt in ("executive-dark", "executive-light"):
        themes = _list_themes(bt)
        all_options.append(_theme_options(themes))
        all_data.append({str(t["id"]): t for t in themes})

    return _feedback_alert("Default theme updated.", "success"), all_options, all_data


@callback(
    Output("gs-delete-confirm", "displayed"),
    Output("gs-delete-pending", "data"),
    Input({"type": "gs-theme-delete", "base_theme": ALL}, "n_clicks"),
    State({"type": "gs-theme-select", "base_theme": ALL}, "value"),
    State({"type": "gs-theme-delete", "base_theme": ALL}, "id"),
    prevent_initial_call=True,
)
def confirm_delete(
    n_clicks_list: list[int | None],
    selected_values: list[Any],
    button_ids: list[dict[str, str]],
) -> tuple[bool, Any]:
    """Show the delete confirmation dialog and record the pending theme."""
    if not any(n for n in n_clicks_list):
        raise PreventUpdate

    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict):
        raise PreventUpdate
    base_theme = triggered.get("base_theme")

    selected = None
    for value, bid in zip(selected_values, button_ids):
        if isinstance(bid, dict) and bid.get("base_theme") == base_theme:
            selected = value
            break

    if selected is None:
        raise PreventUpdate

    return True, {"theme_id": selected}


@callback(
    Output("gs-page-feedback", "children", allow_duplicate=True),
    Output({"type": "gs-theme-select", "base_theme": ALL}, "options", allow_duplicate=True),
    Output({"type": "gs-theme-store", "base_theme": ALL}, "data", allow_duplicate=True),
    Input("gs-delete-confirm", "submit_n_clicks"),
    State("gs-delete-pending", "data"),
    prevent_initial_call=True,
)
def execute_delete(
    submit_n_clicks: int | None,
    pending: dict[str, Any] | None,
) -> tuple:
    """Delete the pending theme."""
    if not submit_n_clicks or not pending:
        raise PreventUpdate

    theme_id = pending.get("theme_id")
    if theme_id is None:
        raise PreventUpdate

    try:
        resp = requests.delete(f"{THEMES_API}{theme_id}", timeout=10)
        if resp.status_code == 409:
            detail = resp.json().get("detail", "Builtin themes cannot be deleted.")
            return (
                _feedback_alert(f"Delete failed: {detail}", "danger"),
                [no_update, no_update],
                [no_update, no_update],
            )
        resp.raise_for_status()
    except requests.RequestException as exc:
        return (
            _feedback_alert(f"Delete failed: {exc}", "danger"),
            [no_update, no_update],
            [no_update, no_update],
        )

    all_options: list = []
    all_data: list = []
    for bt in ("executive-dark", "executive-light"):
        themes = _list_themes(bt)
        all_options.append(_theme_options(themes))
        all_data.append({str(t["id"]): t for t in themes})

    return _feedback_alert("Theme deleted.", "success"), all_options, all_data


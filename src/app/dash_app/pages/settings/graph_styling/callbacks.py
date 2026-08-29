"""Callbacks for the Graph Styling settings page.

Phase 4.3 — single-node live preview. A single Cytoscape node reflects the
currently edited node type's shape/color/size in real time. The preview is
driven by the node-field inputs via ``overrides_to_cytoscape_rules()``.
"""

from __future__ import annotations

from typing import Any

from dash import ALL, Input, Output, State, callback, callback_context
from dash.exceptions import PreventUpdate

from app.common.graph_theme import merge_theme_overrides, overrides_to_cytoscape_rules
from app.dash_app.styles import get_theme_tokens

# Semantic field keys emitted by the node-field inputs (see components.py
# ``_NODE_FIELDS``). These map 1:1 onto ``NodeOverride`` model fields.
_NODE_FIELD_KEYS = ("color", "border", "border_width", "shape", "width", "height")


def build_preview_stylesheet(
    base_theme: str, node_type: str, node_overrides: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build a Cytoscape stylesheet for the single-node preview.

    Merges ``node_overrides`` (semantic keys) over the base tokens for
    ``base_theme`` and translates the result via
    :func:`overrides_to_cytoscape_rules`. Falls back to the base tokens on any
    validation error so the preview always renders.

    Args:
        base_theme: Base mode (``executive-light`` / ``executive-dark``).
        node_type: The node type being previewed (e.g. ``Person``).
        node_overrides: Semantic override dict for that node type (subset of
            ``color``/``border``/``border_width``/``shape``/``width``/``height``).

    Returns:
        A list of Cytoscape rule dicts.
    """
    base_tokens = get_theme_tokens(base_theme)
    try:
        merged = merge_theme_overrides(
            base_tokens, {"nodes": {node_type: node_overrides}}
        )
    except (ValueError, TypeError):
        merged = merge_theme_overrides(base_tokens, {})
    return overrides_to_cytoscape_rules(merged)


@callback(
    Output("gs-preview-node-type", "data"),
    Output("gs-preview-cytoscape", "elements"),
    Output("gs-preview-cytoscape", "stylesheet"),
    Input({"type": "gs-node-field", "base_theme": ALL, "node_type": ALL, "field": ALL}, "value"),
    State({"type": "gs-node-field", "base_theme": ALL, "node_type": ALL, "field": ALL}, "id"),
    prevent_initial_call=True,
)
def update_preview(values: list[Any], ids: list[dict[str, str]]) -> tuple:
    """Update the single-node preview when any node field changes.

    Determines the most-recently edited node type, gathers the current values
    of all six fields for that node type (from the matching inputs), and
    rebuilds the preview node's ``nodeType`` and stylesheet.
    """
    triggered = callback_context.triggered_id
    if not isinstance(triggered, dict) or triggered.get("type") != "gs-node-field":
        raise PreventUpdate

    node_type = triggered["node_type"]
    base_theme = triggered["base_theme"]

    # Gather current values for the edited node type / base mode.
    node_overrides: dict[str, Any] = {}
    for value, input_id in zip(values, ids):
        if not isinstance(input_id, dict):
            continue
        if input_id.get("base_theme") != base_theme:
            continue
        if input_id.get("node_type") != node_type:
            continue
        field = input_id.get("field")
        if field in _NODE_FIELD_KEYS and value not in (None, ""):
            node_overrides[field] = value

    stylesheet = build_preview_stylesheet(base_theme, node_type, node_overrides)
    elements = [
        {"data": {"id": "preview-node", "label": node_type, "nodeType": node_type}},
    ]
    return node_type, elements, stylesheet


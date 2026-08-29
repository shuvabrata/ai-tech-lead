"""Collaboration Network display callbacks — properties panel + stylesheet."""

import requests

from dash import Input, Output, callback, html

from app.dash_app.components.common import build_element_properties_content, register_edge_hover_dimming_callback
from app.dash_app.pages.graph.styles import build_cytoscape_stylesheet
from app.dash_app.styles import FONT_SIZE_XSMALL
from app.runtime_settings import runtime_settings
from common.logger import logger

from app.dash_app.pages.graph.utils import get_graph_api_base_url

register_edge_hover_dimming_callback("collab-cytoscape")

TIMEOUT_SECONDS = runtime_settings.get_int("HTTP_REQUEST_TIMEOUT")


def _fetch_effective_theme(base_theme: str) -> dict | None:
    """Fetch the server-merged effective theme for a base mode.

    Returns the merged tokens on 200, or ``None`` on any error so callers fall
    back to the base tokens (hardcoded palette).
    """
    try:
        api_base = get_graph_api_base_url()
        resp = requests.get(
            f"{api_base}/api/v1/graph-themes/effective",
            params={"base_theme": base_theme},
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            return resp.json()
        logger.warning(
            "Collab effective theme fetch returned %s for base_theme=%s",
            resp.status_code,
            base_theme,
        )
    except requests.RequestException as exc:
        logger.warning(
            "Collab effective theme fetch failed for base_theme=%s: %s",
            base_theme,
            exc,
        )
    return None


@callback(
    Output("collab-cytoscape", "stylesheet"),
    Input("theme-store", "data"),
)
def update_collab_stylesheet(theme_name):
    """Update the collab graph palette when the app theme changes.

    Fetches the server-merged effective theme (base tokens ⊕ default-theme
    overrides) for the active base mode, mirroring the Graph page.
    """
    active_theme = theme_name or "executive-light"
    effective = _fetch_effective_theme(active_theme)
    return build_cytoscape_stylesheet(active_theme, effective=effective)


_PLACEHOLDER = html.P(
    "Select a node or edge to see its properties.",
    className="text-muted text-center",
    style={"fontSize": FONT_SIZE_XSMALL, "padding": "16px 0"},
)


@callback(
    Output("collab-details-panel", "children"),
    [Input("collab-cytoscape", "selectedNodeData"),
     Input("collab-cytoscape", "selectedEdgeData")],
)
def display_collab_properties(selected_nodes, selected_edges):
    """Show properties for a selected node or edge.

    Expand Node is disabled (expand_node_enabled=False) because the
    collab page does not support on-demand neighbor loading.
    """
    if selected_nodes and len(selected_nodes) > 0:
        return build_element_properties_content(selected_nodes[0], expand_node_enabled=False)
    if selected_edges and len(selected_edges) > 0:
        return build_element_properties_content(selected_edges[0], expand_node_enabled=False)
    return _PLACEHOLDER

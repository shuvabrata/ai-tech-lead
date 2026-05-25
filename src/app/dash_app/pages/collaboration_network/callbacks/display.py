"""Collaboration Network display callbacks — properties panel."""

from dash import Input, Output, callback, html

from app.dash_app.components.common import build_element_properties_content
from app.dash_app.styles import FONT_SIZE_XSMALL


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

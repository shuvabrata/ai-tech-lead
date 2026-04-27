"""Callbacks for switching the generic graph page into analytics mode."""

from urllib.parse import parse_qs

from dash import Input, Output, callback

from app.dash_app.styles import GRAPH_QUERY_SECTION_CONTAINER_STYLE


@callback(
    Output("graph-query-section", "style"),
    [Input("url", "pathname"), Input("url", "search")],
)
def toggle_query_panel_for_analytics_mode(pathname: str | None, search: str | None):
    """Hide the Cypher query console when the graph page is in analytics mode."""
    if pathname != "/app/graph":
        return GRAPH_QUERY_SECTION_CONTAINER_STYLE

    params = parse_qs((search or "").lstrip("?"))
    if params.get("mode"):
        return {**GRAPH_QUERY_SECTION_CONTAINER_STYLE, "display": "none"}

    return GRAPH_QUERY_SECTION_CONTAINER_STYLE

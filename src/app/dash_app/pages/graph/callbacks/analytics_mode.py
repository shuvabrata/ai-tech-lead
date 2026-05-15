"""Callbacks for switching the generic graph page into analytics mode."""

from urllib.parse import parse_qs

from dash import Input, Output, callback


@callback(
    Output("graph-query-section", "style"),
    Output("graph-catalog-section", "style"),
    [Input("url", "pathname"), Input("url", "search")],
)
def toggle_query_panel_for_analytics_mode(pathname: str | None, search: str | None):
    """Hide the Cypher query console when the graph page is in analytics mode."""
    if pathname != "/app/graph":
        return {}, {}

    params = parse_qs((search or "").lstrip("?"))
    if params.get("mode"):
        return {"display": "none"}, {"display": "none"}

    return {}, {}

"""Right Panel Workbench Tab Callbacks

Handles tab switching, UI sync, and URL deep-link integration for the
three-tab workbench panel (Filters / Console / Catalog).
"""

from __future__ import annotations

from urllib.parse import parse_qs, unquote

from dash import Input, Output, State, callback, ctx, no_update
from dash.exceptions import MissingCallbackContextException, PreventUpdate


_TAB_BUTTON_IDS = {
    "right-tab-filters-btn": "filters",
    "right-tab-console-btn": "console",
    "right-tab-catalog-btn": "catalog",
}

_ACTIVE_CLASS = "graph-right-panel-tab-icon active"
_INACTIVE_CLASS = "graph-right-panel-tab-icon"


@callback(
    Output("right-panel-active-tab", "data"),
    Input("right-tab-filters-btn", "n_clicks"),
    Input("right-tab-console-btn", "n_clicks"),
    Input("right-tab-catalog-btn", "n_clicks"),
    State("right-panel-active-tab", "data"),
    prevent_initial_call=True,
)
def toggle_right_panel_tab(
    _filters_clicks: int | None,
    _console_clicks: int | None,
    _catalog_clicks: int | None,
    active_tab: str | None,
) -> str | None:
    """Open a tab on click; click the same tab again to close it (accordion behaviour)."""
    try:
        triggered_id = ctx.triggered_id
    except MissingCallbackContextException:
        raise PreventUpdate from None

    clicked_tab = _TAB_BUTTON_IDS.get(triggered_id)
    if clicked_tab is None:
        raise PreventUpdate

    # Toggle: clicking the active tab collapses all panels
    if active_tab == clicked_tab:
        return None

    return clicked_tab


@callback(
    Output("right-tab-filters-collapse", "is_open"),
    Output("right-tab-console-collapse", "is_open"),
    Output("right-tab-catalog-collapse", "is_open"),
    Output("right-tab-filters-btn", "className"),
    Output("right-tab-console-btn", "className"),
    Output("right-tab-catalog-btn", "className"),
    Input("right-panel-active-tab", "data"),
    prevent_initial_call=False,
)
def sync_right_panel_ui(active_tab: str | None):
    """Mirror the active-tab store to collapse open/close states and button styles."""
    filters_open = active_tab == "filters"
    console_open = active_tab == "console"
    catalog_open = active_tab == "catalog"

    filters_class = _ACTIVE_CLASS if filters_open else _INACTIVE_CLASS
    console_class = _ACTIVE_CLASS if console_open else _INACTIVE_CLASS
    catalog_class = _ACTIVE_CLASS if catalog_open else _INACTIVE_CLASS

    return (
        filters_open,
        console_open,
        catalog_open,
        filters_class,
        console_class,
        catalog_class,
    )


@callback(
    Output("right-panel-active-tab", "data", allow_duplicate=True),
    Output("graph-query-input", "value", allow_duplicate=True),
    Output("cypher-autoexec-store", "data", allow_duplicate=True),
    Input("url", "search"),
    prevent_initial_call="initial_duplicate",
)
def handle_url_deep_link_tab(search: str | None):
    """Open the correct tab based on URL query parameters on page load.

    - ``?cypher=<encoded>`` → open Console tab, pre-fill input, trigger auto-exec
    - ``?catalog=<id>``     → open Catalog tab (query selection handled elsewhere)
    - anything else         → no change
    """
    params = parse_qs((search or "").lstrip("?"))

    raw_cypher = params.get("cypher", [None])[0]
    if raw_cypher:
        cypher = unquote(raw_cypher)
        return "console", cypher, cypher

    if params.get("catalog", [None])[0]:
        return "catalog", no_update, no_update

    raise PreventUpdate

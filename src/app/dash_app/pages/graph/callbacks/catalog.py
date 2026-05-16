"""Catalog workbench callbacks for the Graph page."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash_bootstrap_components as dbc
import requests
from dash import ALL, Input, Output, State, callback, ctx, html, no_update
from dash.exceptions import MissingCallbackContextException

from common.logger import logger
from app.dash_app.components.common import create_alert
from app.dash_app.styles import (
    COLOR_BACKGROUND_WHITE,
    COLOR_CHARCOAL,
    COLOR_BORDER,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_TEXT_SECONDARY,
)
from app.settings import settings

from ..utils import create_error_alert, get_graph_api_base_url


TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT
ALL_NAMESPACES = "__all__"
ALL_VIEWS = "__all__"


def build_namespace_options(catalog_queries: list[dict]) -> list[dict]:
    """Build namespace filter options from loaded catalog queries."""
    options = [{"label": "All namespaces", "value": ALL_NAMESPACES}]
    seen: set[str] = set()
    for query in catalog_queries:
        namespace = query.get("namespace") or {}
        directory = namespace.get("directory")
        name = namespace.get("name")
        if not directory or directory in seen:
            continue
        seen.add(directory)
        options.append({"label": name or directory, "value": directory})
    return options


def filter_catalog_queries(
    catalog_queries: list[dict],
    namespace_filter: str | None,
    search_text: str | None,
    view_filter: str | None,
) -> list[dict]:
    """Filter catalog metadata client-side for the workbench."""
    filtered = catalog_queries

    if namespace_filter and namespace_filter != ALL_NAMESPACES:
        filtered = [
            query
            for query in filtered
            if (query.get("namespace") or {}).get("directory") == namespace_filter
        ]

    if view_filter and view_filter != ALL_VIEWS:
        filtered = [
            query
            for query in filtered
            if view_filter in (query.get("available_views") or [])
        ]

    if search_text and search_text.strip():
        needle = search_text.strip().lower()
        filtered = [
            query
            for query in filtered
            if _query_matches(query, needle)
        ]

    return filtered


def parse_catalog_deep_link(search: str | None) -> tuple[str | None, str | None]:
    """Extract catalog id and requested view from a URL query string."""
    params = parse_qs((search or "").lstrip("?"))
    catalog_id = params.get("catalog", [None])[0]
    requested_view = params.get("view", [None])[0]
    if requested_view not in {"graph", "tabular"}:
        requested_view = None
    return catalog_id, requested_view


def find_catalog_query(catalog_queries: list[dict], catalog_id: str | None) -> dict | None:
    """Find a catalog query by id."""
    if not catalog_id:
        return None
    for query in catalog_queries:
        if query.get("id") == catalog_id:
            return query
    return None


def determine_catalog_view(
    catalog_query: dict,
    requested_view: str | None,
    current_view: str | None,
) -> str | None:
    """Choose the active catalog view for a selected query."""
    available_views = catalog_query.get("available_views") or []
    if current_view in available_views:
        return current_view
    if requested_view in available_views:
        return requested_view
    default_view = catalog_query.get("default_view")
    if default_view in available_views:
        return default_view
    if "graph" in available_views:
        return "graph"
    if available_views:
        return available_views[0]
    return None


def required_parameters_missing(catalog_query: dict, parameter_values: dict | None) -> list[str]:
    """Return names of required catalog parameters that are missing."""
    parameter_values = parameter_values or {}
    missing: list[str] = []
    for parameter in catalog_query.get("parameters") or []:
        if not parameter.get("required"):
            continue
        value = parameter_values.get(parameter.get("name"))
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(parameter["name"])
    return missing


def _query_matches(query: dict, needle: str) -> bool:
    namespace = query.get("namespace") or {}
    haystack = " ".join(
        [
            query.get("id", ""),
            query.get("name", ""),
            query.get("description", ""),
            query.get("summary", ""),
            namespace.get("name", ""),
            namespace.get("directory", ""),
            " ".join(query.get("tags") or []),
            query.get("owner", ""),
            query.get("status", ""),
        ]
    ).lower()
    return needle in haystack


def _status_badge_color(status: str | None) -> str:
    if status == "active":
        return "success"
    if status == "draft":
        return "warning"
    if status == "deprecated":
        return "secondary"
    return "secondary"


def _build_status_badge(status: str | None):
    if not status:
        return None
    return dbc.Badge(
        status.title(),
        color=_status_badge_color(status),
        className="ms-2",
    )


def _parameter_label(parameter: dict) -> str:
    return parameter.get("label") or parameter.get("name") or "Parameter"


def _parameter_placeholder(parameter: dict) -> str:
    return parameter.get("placeholder") or parameter.get("env_var") or parameter.get("name") or ""


def _build_parameter_help_text(parameter: dict):
    help_parts: list = []
    description = parameter.get("description")
    env_var = parameter.get("env_var")
    parameter_type = parameter.get("type")

    if description:
        help_parts.append(html.Span(description))
    if parameter_type:
        if help_parts:
            help_parts.append(html.Br())
        help_parts.append(html.Span(f"Type: {parameter_type}"))
    if env_var:
        if help_parts:
            help_parts.append(html.Br())
        help_parts.append(html.Span(f"Env hint: {env_var}"))

    if not help_parts:
        return None

    return html.Div(
        help_parts,
        style={"fontSize": "11px", "color": COLOR_TEXT_SECONDARY, "marginTop": "4px"},
    )


@callback(
    Output("catalog-panel-collapse", "is_open"),
    Output("catalog-collapse-icon", "className"),
    Input("toggle-catalog-collapse-btn", "n_clicks"),
    Input("url", "search"),
    State("catalog-panel-collapse", "is_open"),
    prevent_initial_call=False,
)
def toggle_catalog_collapse(
    n_clicks: int | None, search: str | None, is_open: bool
) -> tuple[bool, str]:
    """Toggle the Query Catalog collapse panel and auto-open for deep links."""
    try:
        triggered_id = ctx.triggered_id
    except MissingCallbackContextException:
        triggered_id = None

    # On initial load or URL change, check if there's a catalog deep link
    if triggered_id == "url" or triggered_id is None:
        catalog_id, _ = parse_catalog_deep_link(search)
        if catalog_id:
            return True, "fas fa-chevron-down me-2"

    # On button click, toggle the state
    if triggered_id == "toggle-catalog-collapse-btn" and n_clicks:
        new_is_open = not is_open
        icon_class = "fas fa-chevron-down me-2" if new_is_open else "fas fa-chevron-right me-2"
        return new_is_open, icon_class

    # Fallback to current state
    return is_open, "fas fa-chevron-down me-2" if is_open else "fas fa-chevron-right me-2"


@callback(
    Output("query-catalog-store", "data"),
    Output("query-catalog-load-status", "children"),
    Input("url", "pathname"),
)
def load_query_catalog(pathname: str | None):
    """Fetch catalog metadata when the Graph page is opened."""
    if pathname != "/app/graph":
        return no_update, no_update

    api_base = get_graph_api_base_url()
    try:
        response = requests.get(
            f"{api_base}/api/v1/queries/catalog",
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items", [])
        logger.info("[GRAPH-CATALOG] loaded count=%d", len(items))
        return items, html.Div(
            f"Loaded {len(items)} shipped queries.",
            className="mb-2 graph-catalog-status-banner",
            style={
                "fontSize": "11px",
                "fontWeight": 500,
                "backgroundColor": COLOR_BACKGROUND_WHITE,
                "border": f"1px solid {COLOR_BORDER}",
                "color": COLOR_CHARCOAL_MEDIUM,
                "borderRadius": "4px",
                "padding": "8px 12px",
            },
        )
    except requests.exceptions.RequestException as exc:
        logger.error("[GRAPH-CATALOG] load_failed %s", exc)
        error_display = create_error_alert(
            "",
            alert_type="warning",
            heading="Catalog unavailable",
            hint="The query catalog API could not be reached. The query console still works.",
            doc_link=None,
        )
        return [], error_display


@callback(
    Output("catalog-namespace-filter", "options"),
    Input("query-catalog-store", "data"),
)
def populate_namespace_filter(catalog_queries: list[dict] | None):
    """Populate namespace options from loaded catalog metadata."""
    return build_namespace_options(catalog_queries or [])


@callback(
    Output("selected-catalog-query-store", "data"),
    Input({"type": "catalog-query-select", "catalog_id": ALL}, "n_clicks"),
    Input("url", "search"),
    Input("query-catalog-store", "data"),
    State("selected-catalog-query-store", "data"),
    prevent_initial_call="initial_duplicate",
)
def sync_selected_catalog_query(
    _clicks,
    search: str | None,
    catalog_queries: list[dict] | None,
    current_selection: dict | None,
):
    """Select a query from button clicks or URL deep links."""
    catalog_queries = catalog_queries or []
    if not catalog_queries:
        return None

    triggered_id = ctx.triggered_id

    if isinstance(triggered_id, dict):
        return {"id": triggered_id.get("catalog_id")}

    deep_link_id, deep_link_view = parse_catalog_deep_link(search)
    if deep_link_id and find_catalog_query(catalog_queries, deep_link_id):
        return {"id": deep_link_id, "preferred_view": deep_link_view}

    if current_selection and find_catalog_query(catalog_queries, current_selection.get("id")):
        return no_update

    return {"id": catalog_queries[0].get("id")}


@callback(
    Output("catalog-query-list", "children"),
    Input("query-catalog-store", "data"),
    Input("catalog-namespace-filter", "value"),
    Input("catalog-search-input", "value"),
    Input("catalog-view-filter", "value"),
    Input("selected-catalog-query-store", "data"),
)
def render_catalog_query_list(
    catalog_queries: list[dict] | None,
    namespace_filter: str | None,
    search_text: str | None,
    view_filter: str | None,
    selected_query: dict | None,
):
    """Render the filtered query list."""
    catalog_queries = catalog_queries or []
    filtered = filter_catalog_queries(
        catalog_queries,
        namespace_filter,
        search_text,
        view_filter,
    )

    if not catalog_queries:
        return html.Div(
            "No catalog metadata loaded yet.",
            style={"fontSize": "12px", "color": COLOR_TEXT_SECONDARY},
        )

    if not filtered:
        return html.Div(
            "No queries match the current filters.",
            style={"fontSize": "12px", "color": COLOR_TEXT_SECONDARY},
        )

    items = []
    selected_id = (selected_query or {}).get("id")
    for query in filtered:
        namespace = query.get("namespace") or {}
        subtitle = namespace.get("name", "")
        status_badge = _build_status_badge(query.get("status"))
        items.append(
            dbc.ListGroupItem(
                [
                    html.Div(
                        [
                            html.Span(query.get("name", "Untitled")),
                            status_badge,
                        ],
                        style={"fontWeight": 600, "fontSize": "12px"},
                    ),
                    html.Div(subtitle, style={"fontSize": "11px", "color": COLOR_TEXT_SECONDARY}),
                ],
                id={"type": "catalog-query-select", "catalog_id": query.get("id")},
                action=True,
                active=query.get("id") == selected_id,
                n_clicks=0,
                class_name="graph-catalog-list-item",
            )
        )

    return html.Div([
        html.Div(
            f"{len(filtered)} query{'ies' if len(filtered) != 1 else 'y'}",
            style={"fontSize": "11px", "color": COLOR_TEXT_SECONDARY, "marginBottom": "8px"},
        ),
        dbc.ListGroup(items, flush=True, class_name="graph-catalog-list-group"),
    ])


@callback(
    Output("catalog-query-detail", "children"),
    Output("catalog-query-view-toggle", "options"),
    Output("catalog-query-view-toggle", "value"),
    Output("catalog-parameter-inputs", "children"),
    Output("catalog-run-btn", "disabled"),
    Output("catalog-load-console-btn", "disabled"),
    Input("selected-catalog-query-store", "data"),
    Input("query-catalog-store", "data"),
    Input("catalog-parameters-store", "data"),
    State("catalog-query-view-toggle", "value"),
)
def render_catalog_query_detail(
    selected_query: dict | None,
    catalog_queries: list[dict] | None,
    parameter_values: dict | None,
    current_view: str | None,
):
    """Render selected query details, view toggle, and parameter inputs."""
    catalog_queries = catalog_queries or []
    parameter_values = parameter_values or {}
    query = find_catalog_query(catalog_queries, (selected_query or {}).get("id"))

    if not query:
        return (
            html.Div(
                "Select a catalog query to inspect it here.",
                style={"fontSize": "12px", "color": COLOR_TEXT_SECONDARY},
            ),
            [],
            None,
            [],
            True,
            True,
        )

    selected_view = determine_catalog_view(
        query,
        (selected_query or {}).get("preferred_view"),
        current_view,
    )
    missing_required = required_parameters_missing(query, parameter_values)

    tags = query.get("tags") or []
    status_badge = _build_status_badge(query.get("status"))
    detail_children = [
        html.Div(
            [
                html.Span(query.get("name", "Untitled")),
                status_badge,
            ],
            style={"fontSize": "16px", "fontWeight": 600, "color": COLOR_CHARCOAL},
        ),
        html.Div(
            query.get("description", ""),
            style={"fontSize": "12px", "color": COLOR_TEXT_SECONDARY, "marginTop": "6px"},
        ),
    ]

    summary = query.get("summary")
    if summary:
        detail_children.append(
            html.Div(
                summary,
                style={"fontSize": "12px", "color": COLOR_CHARCOAL_MEDIUM, "marginTop": "6px"},
            )
        )

    if tags:
        detail_children.append(
            html.Div(
                [dbc.Badge(tag, color="light", text_color="dark", className="me-1") for tag in tags],
                className="mt-2",
            )
        )

    owner = query.get("owner")
    if owner:
        detail_children.append(
            html.Div(
                f"Owner: {owner}",
                style={"fontSize": "11px", "color": COLOR_TEXT_SECONDARY, "marginTop": "10px"},
            )
        )

    detail_children.append(
        html.Div(
            query.get("id", ""),
            style={"fontSize": "11px", "color": COLOR_TEXT_SECONDARY, "marginTop": "10px"},
        )
    )

    view_options = [
        {"label": view.title(), "value": view}
        for view in (query.get("available_views") or [])
    ]

    parameter_children = []
    for parameter in query.get("parameters") or []:
        parameter_name = parameter.get("name")
        required = parameter.get("required", False)
        parameter_help = _build_parameter_help_text(parameter)
        parameter_children.append(
            html.Div([
                html.Label(
                    f"{_parameter_label(parameter)}{' *' if required else ''}",
                    style={"fontSize": "12px", "fontWeight": 600, "marginBottom": "4px"},
                ),
                dbc.Input(
                    id={"type": "catalog-parameter-input", "name": parameter_name},
                    value=parameter_values.get(parameter_name, ""),
                    type="text",
                    size="sm",
                    placeholder=_parameter_placeholder(parameter),
                ),
                parameter_help,
            ], className="mb-3")
        )

    if missing_required:
        parameter_children.append(
            create_alert(
                "Fill required parameters before running this query.",
                color="warning",
                class_name="mb-0",
                dismissable=False,
                style={"fontSize": "11px"},
            )
        )

    return (
        detail_children,
        view_options,
        selected_view,
        parameter_children,
        bool(missing_required) or not bool(selected_view),
        False,
    )


@callback(
    Output("catalog-parameters-store", "data"),
    Input({"type": "catalog-parameter-input", "name": ALL}, "value"),
    State({"type": "catalog-parameter-input", "name": ALL}, "id"),
)
def sync_catalog_parameter_values(values: list[str], ids: list[dict]):
    """Persist parameter form state in a store."""
    if not ids:
        return {}
    return {
        component_id.get("name"): value
        for component_id, value in zip(ids, values)
        if component_id.get("name")
    }


@callback(
    Output("graph-query-input", "value"),
    Input("catalog-load-console-btn", "n_clicks"),
    Input("selected-catalog-query-store", "data"),
    Input("url", "search"),
    State("selected-catalog-query-store", "data"),
    State("query-catalog-store", "data"),
    State("catalog-query-view-toggle", "value"),
    prevent_initial_call=True,
)
def load_catalog_query_into_console(
    _n_clicks: int,
    _selected_query_input: dict | None,
    search: str | None,
    selected_query: dict | None,
    catalog_queries: list[dict] | None,
    selected_view: str | None,
):
    """Populate the query console with the selected catalog query text."""
    try:
        triggered_id = ctx.triggered_id
    except MissingCallbackContextException:
        triggered_id = None

    query = find_catalog_query(catalog_queries or [], (selected_query or {}).get("id"))
    if not query or not selected_view:
        return no_update

    if triggered_id == "catalog-load-console-btn":
        return (query.get("queries") or {}).get(selected_view, no_update)

    deep_link_id, _ = parse_catalog_deep_link(search)
    if deep_link_id and deep_link_id == query.get("id"):
        return (query.get("queries") or {}).get(selected_view, no_update)

    return no_update

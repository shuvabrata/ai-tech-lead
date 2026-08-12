"""Catalog workbench callbacks for the Graph page."""

from __future__ import annotations

from urllib.parse import parse_qs

import dash_bootstrap_components as dbc
import requests
from dash import ALL, MATCH, Input, Output, State, callback, clientside_callback, ctx, dcc, html, no_update
from dash.exceptions import MissingCallbackContextException, PreventUpdate

from common.logger import logger
from app.dash_app.components.common import create_alert
from app.dash_app.styles import (
    COLOR_BACKGROUND_WHITE,
    COLOR_CHARCOAL,
    COLOR_BORDER,
    COLOR_CHARCOAL_MEDIUM,
    COLOR_TEXT_SECONDARY,
    COLOR_GRAY_MEDIUM,
)
from app.runtime_settings import runtime_settings

from ..utils import create_error_alert, get_graph_api_base_url


TIMEOUT_SECONDS = runtime_settings.get_int("HTTP_REQUEST_TIMEOUT")
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
    # Product preference: default to Graph whenever it is available.
    if "graph" in available_views:
        return "graph"
    default_view = catalog_query.get("default_view")
    if default_view in available_views:
        return default_view
    if available_views:
        return available_views[0]
    return None


def _extract_param_value(value):
    """Normalize a catalog parameter value to its raw runtime form.

    Person parameters are stored as ``{"wba": "...", "display": "..."}``
    while scalar parameters remain plain strings.  This helper unwraps
    dicts so that downstream consumers only see the ``wba`` string.
    """
    if isinstance(value, dict):
        return value.get("wba")
    return value


def required_parameters_missing(catalog_query: dict, parameter_values: dict | None) -> list[str]:
    """Return names of required catalog parameters that are missing."""
    parameter_values = parameter_values or {}
    missing: list[str] = []
    for parameter in catalog_query.get("parameters") or []:
        if not parameter.get("required"):
            continue
        value = _extract_param_value(parameter_values.get(parameter.get("name")))
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


def _build_person_picker(parameter: dict, current_value: str | dict | None) -> html.Div:
    """Build a custom combobox for parameters with type='person_id'.

    Uses a plain ``dbc.Input`` so the user types directly without any popup
    widget.  Suggestions appear in an absolutely-positioned panel below the
    input.  After a person is selected a chip replaces the search area,
    showing the canonical ``wba_id`` and a clear button.

    When ``current_value`` is a dict ``{"wba": "...", "display": "..."}``
    (i.e. a previously-picked person whose value was preserved in the
    parameter store), the chip is pre-rendered and the hidden
    ``catalog-person-value`` store is seeded so that the clear button
    correctly removes the entry from ``catalog-parameters-store``.
    """
    parameter_name = parameter.get("name")
    required = parameter.get("required", False)
    label_base = _parameter_label(parameter)

    # Determine whether we have a stored person selection
    stored_wba: str | None = None
    stored_display: str | None = None
    if isinstance(current_value, dict):
        stored_wba = current_value.get("wba")
        stored_display = current_value.get("display") or stored_wba or "Unknown"

    label_children: list = [label_base]
    if required:
        label_children.append(
            html.Span(" *", style={"color": "#dc3545", "fontWeight": 700})
        )

    # --- Chip (rendered when a stored value exists) ---
    chip_children: list = []
    if stored_wba:
        chip_children = [
            html.Div(
                [
                    html.Span(stored_display, className="catalog-person-chip-name"),
                    html.Span(stored_wba, className="catalog-person-chip-id"),
                ],
                className="catalog-person-chip-info",
            ),
            html.Button(
                "\u00d7",
                id={"type": "catalog-person-chip-clear", "name": parameter_name},
                n_clicks=0,
                className="catalog-person-chip-clear",
                title="Clear selection",
            ),
        ]

    return html.Div(
        [
            html.Label(
                label_children,
                style={"fontSize": "12px", "fontWeight": 600, "marginBottom": "4px"},
            ),
            # --- Chip (visible once a person is selected) ---
            html.Div(
                id={"type": "catalog-person-chip", "name": parameter_name},
                children=chip_children,
                style={"display": "flex" if stored_wba else "none"},
                className="catalog-person-chip-area",
            ),
            # --- Search area (visible while searching) ---
            html.Div(
                [
                    html.Div(
                        [
                            dbc.Input(
                                id={"type": "catalog-person-input", "name": parameter_name},
                                placeholder="Search by name or email (min 3 chars)",
                                type="text",
                                value="",
                                autocomplete="off",
                                size="sm",
                                style={"fontSize": "12px"},
                                debounce=False,
                            ),
                            html.Div(
                                id={"type": "catalog-person-suggestions", "name": parameter_name},
                                children=[],
                                style={"display": "none"},
                                className="catalog-person-suggestions",
                            ),
                        ],
                        className="catalog-person-combobox",
                    ),
                ],
                id={"type": "catalog-person-search-area", "name": parameter_name},
                style={"display": "none" if stored_wba else "block"},
            ),
            # --- Hidden stores (self-contained within the picker) ---
            dcc.Store(
                id={"type": "catalog-person-debounce", "name": parameter_name},
                storage_type="memory",
                data=None,
            ),
            dcc.Store(
                id={"type": "catalog-person-value", "name": parameter_name},
                storage_type="memory",
                data=current_value if isinstance(current_value, dict) else None,
            ),
        ],
        className="mb-3",
    )


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
        return items, None
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
    Input("selected-catalog-query-store", "data"),
)
def render_catalog_query_list(
    catalog_queries: list[dict] | None,
    namespace_filter: str | None,
    search_text: str | None,
    selected_query: dict | None,
):
    """Render the filtered query list."""
    catalog_queries = catalog_queries or []
    filtered = filter_catalog_queries(
        catalog_queries,
        namespace_filter,
        search_text,
        None,
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
    Input("selected-catalog-query-store", "data"),
    Input("query-catalog-store", "data"),
    Input("theme-store", "data"),
    State("catalog-parameters-store", "data"),  # State only — reading store must NOT trigger re-render
    State("catalog-query-view-toggle", "value"),
)
def render_catalog_query_detail(
    selected_query: dict | None,
    catalog_queries: list[dict] | None,
    theme_name: str | None,
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
    ]

    summary_text = query.get("summary") or "No summary available."
    description_text = query.get("description")

    summary_children = [html.Span(summary_text)]
    
    if description_text:
        icon_id = "query-detail-info-icon"
        summary_children.extend([
            html.I(
                className="fas fa-info-circle",
                id=icon_id,
                style={"cursor": "help", "marginLeft": "8px", "color": COLOR_GRAY_MEDIUM},
            ),
            dbc.Popover(
                dbc.PopoverBody(dcc.Markdown(description_text)),
                target=icon_id,
                trigger="hover",
                placement="auto",
                style={"maxWidth": "800px"},
                class_name=f"theme-{'executive-dark' if (theme_name or 'executive-light') == 'executive-light' else 'executive-light'}",
            )
        ])

    detail_children.append(
        html.Div(
            summary_children,
            style={"fontSize": "12px", "color": COLOR_CHARCOAL_MEDIUM, "marginTop": "6px", "display": "flex", "alignItems": "center"},
        )
    )

    if tags:
        detail_children.append(
            html.Div(
                [dbc.Badge(tag, color="light", text_color="dark", className="me-1") for tag in tags],
                className="mt-2",
            )
        )



    parameter_children = []
    available_views = query.get("available_views") or []
    ordered_views = sorted(
        available_views,
        key=lambda view: (0 if view == "graph" else 1 if view == "tabular" else 2, view),
    )
    view_options = [
        {"label": view.title(), "value": view}
        for view in ordered_views
    ]
    for parameter in query.get("parameters") or []:
        parameter_name = parameter.get("name")
        parameter_type = parameter.get("type")
        required = parameter.get("required", False)

        if parameter_type == "person_id":
            # Use the interactive autocomplete picker instead of a plain text input
            parameter_children.append(
                _build_person_picker(parameter, parameter_values.get(parameter_name))
            )
        else:
            parameter_help = _build_parameter_help_text(parameter)
            label_base = _parameter_label(parameter)
            label_children: list = [label_base]
            if required:
                label_children.append(
                    html.Span(" *", style={"color": "#dc3545", "fontWeight": 700})
                )
            parameter_children.append(
                html.Div([
                    html.Label(
                        label_children,
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

    return (
        detail_children,
        view_options,
        selected_view,
        parameter_children,
    )


@callback(
    Output("catalog-run-btn", "disabled"),
    Output("catalog-load-console-btn", "disabled"),
    Input("catalog-parameters-store", "data"),
    Input("selected-catalog-query-store", "data"),
    State("query-catalog-store", "data"),
    State("catalog-query-view-toggle", "value"),
    prevent_initial_call=False,
)
def update_run_button_state(
    parameter_values: dict | None,
    selected_query: dict | None,
    catalog_queries: list[dict] | None,
    current_view: str | None,
) -> tuple[bool, bool]:
    """Drive the Run / Load-to-console button disabled state.

    Separated from ``render_catalog_query_detail`` so that typing into a
    person picker (which updates the parameters store) only re-evaluates
    disabled state without re-rendering and unmounting the input fields.
    """
    catalog_queries = catalog_queries or []
    parameter_values = parameter_values or {}
    query = find_catalog_query(catalog_queries, (selected_query or {}).get("id"))
    if not query:
        return True, True
    missing_required = required_parameters_missing(query, parameter_values)
    run_disabled = bool(missing_required) or not bool(current_view)
    return run_disabled, False


@callback(
    Output("catalog-parameters-store", "data"),
    Input({"type": "catalog-parameter-input", "name": ALL}, "value"),
    State({"type": "catalog-parameter-input", "name": ALL}, "id"),
    State("catalog-parameters-store", "data"),
)
def sync_catalog_parameter_values(
    values: list[str],
    ids: list[dict],
    current_params: dict | None,
) -> dict:
    """Persist non-person parameter form state in the store.

    Merges into the existing store so that person picker wba_ids
    (written by ``sync_person_parameter_values``) are not overwritten.
    """
    params = dict(current_params or {})
    if not ids:
        return params
    for component_id, value in zip(ids, values):
        name = component_id.get("name")
        if name:
            params[name] = value or ""
    return params


@callback(
    Output("graph-query-input", "value"),
    Output("right-panel-active-tab", "data", allow_duplicate=True),
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
    catalog_view: str | None,
):
    """Populate the query console with the selected catalog query text."""
    try:
        triggered_id = ctx.triggered_id
    except MissingCallbackContextException:
        triggered_id = None

    query = find_catalog_query(catalog_queries or [], (selected_query or {}).get("id"))
    if not query:
        return no_update, no_update

    selected_view = determine_catalog_view(query, None, catalog_view)
    if not selected_view:
        return no_update, no_update

    if triggered_id == "catalog-load-console-btn":
        cypher = (query.get("queries") or {}).get(selected_view, no_update)
        return cypher, "console"

    deep_link_id, _ = parse_catalog_deep_link(search)
    if deep_link_id and deep_link_id == query.get("id"):
        return (query.get("queries") or {}).get(selected_view, no_update), no_update

    return no_update, no_update


# ===========================================================================
# Person Autocomplete Callbacks
# ===========================================================================

# ---------------------------------------------------------------------------
# 1. Clientside relay — forwards the input's live value into the debounce
#    store without a Python round-trip.  Dash's own diffing prevents
#    downstream callbacks from firing when the value hasn't changed.
# ---------------------------------------------------------------------------
clientside_callback(
    """
    function(values) {
        return values.map(function(v) { return (v && v.length > 0) ? v : null; });
    }
    """,
    Output({"type": "catalog-person-debounce", "name": ALL}, "data"),
    Input({"type": "catalog-person-input", "name": ALL}, "value"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# 2. Server callback — fetches suggestions and renders them as plain Buttons
#    inside the suggestions panel.  The input component itself is NOT updated
#    here, so it retains keyboard focus between keystrokes.
# ---------------------------------------------------------------------------
@callback(
    Output({"type": "catalog-person-suggestions", "name": ALL}, "children"),
    Output({"type": "catalog-person-suggestions", "name": ALL}, "style"),
    Input({"type": "catalog-person-debounce", "name": ALL}, "data"),
    State({"type": "catalog-person-debounce", "name": ALL}, "id"),
    prevent_initial_call=True,
)
def sync_person_suggestions(
    debounced_queries: list[str | None],
    debounce_ids: list[dict],
) -> tuple[list, list]:
    """Fetch person suggestions and render them into each picker's suggestions panel.

    Only the suggestions panel (a sibling of the input) is updated, so the
    input itself is never re-mounted and retains keyboard focus.
    """
    api_base = get_graph_api_base_url()
    _hidden = {"display": "none"}
    _visible: dict = {
        "display": "block",
        "position": "absolute",
        "top": "100%",
        "left": "0",
        "right": "0",
        "zIndex": "1050",
    }

    all_children: list = []
    all_styles: list = []

    for query_text, debounce_id in zip(debounced_queries, debounce_ids):
        parameter_name = debounce_id.get("name") if isinstance(debounce_id, dict) else None

        if not query_text or len(query_text.strip()) < 3:
            all_children.append([])
            all_styles.append(_hidden)
            continue

        try:
            response = requests.get(
                f"{api_base}/api/v1/search/persons",
                params={"q": query_text.strip(), "page_size": 10},
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as exc:
            logger.warning("[PersonSearch] API call failed: %s", exc)
            all_children.append([
                html.Small(
                    "Search failed — check your connection",
                    className="catalog-person-no-results",
                )
            ])
            all_styles.append(_visible)
            continue

        suggestions = data.get("results", [])
        if not suggestions:
            all_children.append([
                html.Small(
                    "No people found — try a different name or email",
                    className="catalog-person-no-results",
                )
            ])
            all_styles.append(_visible)
            continue

        items = []
        for i, person in enumerate(suggestions):
            name = person.get("name") or person.get("wba_id", "Unknown")
            email = person.get("email")
            source = person.get("source", "")
            login = person.get("login", "")
            wba_id = person.get("wba_id", "")
            secondary = email or (f"@{login}" if login else "")

            items.append(
                html.Button(
                    html.Div([
                        html.Div(name, className="catalog-suggestion-name"),
                        html.Div(
                            f"{secondary}  [{source}]" if secondary else f"[{source}]",
                            className="catalog-suggestion-detail",
                        ),
                    ]),
                    id={
                        "type": "catalog-person-pick",
                        "name": parameter_name,
                        "idx": i,
                        "wba": wba_id,
                        "display": name,
                    },
                    n_clicks=0,
                    className="catalog-suggestion-item",
                )
            )

        all_children.append(items)
        all_styles.append(_visible)

    return all_children, all_styles


# ---------------------------------------------------------------------------
# 3. Handle suggestion selection — show chip, hide search area, store value.
#    Uses MATCH so each named picker handles its own suggestions independently.
# ---------------------------------------------------------------------------
@callback(
    Output({"type": "catalog-person-chip", "name": MATCH}, "children"),
    Output({"type": "catalog-person-chip", "name": MATCH}, "style"),
    Output({"type": "catalog-person-search-area", "name": MATCH}, "style"),
    Output({"type": "catalog-person-suggestions", "name": MATCH}, "style"),
    Output({"type": "catalog-person-value", "name": MATCH}, "data"),
    Input({"type": "catalog-person-pick", "name": MATCH, "idx": ALL, "wba": ALL, "display": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_person_pick(all_clicks: list[int]) -> tuple:
    """Commit a suggestion selection for one person picker.

    Renders a chip showing the person's name + canonical wba_id, hides the
    search area and suggestions, and stores the wba_id for query execution.
    """
    triggered = ctx.triggered_id
    if not triggered or not any(c for c in (all_clicks or []) if c):
        raise PreventUpdate

    display: str = triggered.get("display", "Unknown")
    wba: str = triggered.get("wba", "")
    param_name: str = triggered.get("name", "")

    chip_children = [
        html.Div(
            [
                html.Span(display, className="catalog-person-chip-name"),
                html.Span(wba, className="catalog-person-chip-id"),
            ],
            className="catalog-person-chip-info",
        ),
        html.Button(
            "\u00d7",
            id={"type": "catalog-person-chip-clear", "name": param_name},
            n_clicks=0,
            className="catalog-person-chip-clear",
            title="Clear selection",
        ),
    ]

    return (
        chip_children,
        {"display": "flex"},   # chip visible
        {"display": "none"},   # search area hidden
        {"display": "none"},   # suggestions panel hidden
        {"wba": wba, "display": display},  # stored as dict for round-trip preservation
    )


# ---------------------------------------------------------------------------
# 4. Handle chip clear — restore search area and wipe the stored value.
# ---------------------------------------------------------------------------
@callback(
    Output({"type": "catalog-person-chip", "name": MATCH}, "style"),
    Output({"type": "catalog-person-search-area", "name": MATCH}, "style"),
    Output({"type": "catalog-person-input", "name": MATCH}, "value"),
    Output({"type": "catalog-person-value", "name": MATCH}, "data"),
    Input({"type": "catalog-person-chip-clear", "name": MATCH}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_person_chip_clear(n_clicks: int | None) -> tuple:
    """Clear the person selection and restore the search input."""
    if not n_clicks:
        raise PreventUpdate
    return (
        {"display": "none"},   # hide chip
        {"display": "block"},   # show search area
        "",                    # clear input text
        None,                  # clear value store
    )


# ---------------------------------------------------------------------------
# 5. Sync selected person value → catalog-parameters-store
# ---------------------------------------------------------------------------
@callback(
    Output("catalog-parameters-store", "data", allow_duplicate=True),
    Input({"type": "catalog-person-value", "name": ALL}, "data"),
    State({"type": "catalog-person-value", "name": ALL}, "id"),
    State("catalog-parameters-store", "data"),
    prevent_initial_call=True,
)
def sync_person_parameter_values(
    values: list[str | None],
    ids: list[dict],
    current_params: dict | None,
) -> dict:
    """Merge person picker selections into the shared catalog parameters store.

    Fires whenever any ``catalog-person-value`` store changes (pick or clear).
    Merges into the existing store so the ``required_parameters_missing`` and
    run-query logic work without modification.
    """
    params = dict(current_params or {})
    for component_id, value in zip(ids, values):
        name = component_id.get("name")
        if not name:
            continue
        if value:
            params[name] = value
        else:
            params.pop(name, None)
    return params

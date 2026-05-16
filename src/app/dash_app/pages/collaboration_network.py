"""Collaboration Network page.

A dedicated page for the Louvain community collaboration network visualization.
Accessed from Analytics → Open Visualization.

Having this as its own page (rather than the graph page with ?mode=...) means:
- No allow_duplicate callbacks or prevent_initial_call='initial_duplicate' hacks.
- No filter pipeline that can overwrite cytoscape elements.
- No layout-selector race condition.
- Clean, single-owner callbacks for every component on this page.
"""

from urllib.parse import parse_qs
from typing import Any

import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from dash import Input, Output, State, callback, clientside_callback, dcc, html
from dash.exceptions import PreventUpdate

from app.analytics.collaboration.config import CollaborationNetworkConfig
from app.api.graph.v1.service import get_collaboration_network
from common.logger import logger
from app.dash_app.components.common import create_alert
from app.dash_app.pages.graph.styles import CYTOSCAPE_STYLESHEET
from app.dash_app.styles import (
    COLOR_GRAY_DARK,
    COLOR_GRAY_LIGHTER,
    FONT_SIZE_SMALL,
    FONT_WEIGHT_SEMIBOLD,
)


_COLLABORATION_LAYOUT = {"name": "preset", "fit": False, "animate": False, "padding": 30}
"""Preset layout with fit:False.

fit:False is intentional: on first render the browser may not have finished laying
out the container, so letting Cytoscape auto-fit produces an invalid zoom.
The clientside render callback calls cy.resize() + cy.fit() explicitly once the
DOM is stable.
"""

_LABEL_STYLE = {
    "fontSize": "11px",
    "fontWeight": FONT_WEIGHT_SEMIBOLD,
    "color": COLOR_GRAY_DARK,
    "marginBottom": "8px",
    "display": "block",
}


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def _create_filter_panel() -> html.Div:
    """Return the collapsible filter sidebar for the collaboration network."""
    return html.Div([
        dbc.Button(
            [html.I(id="collab-filter-collapse-icon", className="fas fa-chevron-right me-2"), "Filters"],
            id="collab-filter-toggle-btn",
            className="w-100 text-start graph-filter-toggle-btn",
            style={
                "fontSize": "13px",
                "fontWeight": "600",
                "color": COLOR_GRAY_DARK,
                "border": "none",
                "borderBottom": f"1px solid {COLOR_GRAY_LIGHTER}",
                "borderRadius": "0",
                "backgroundColor": "transparent",
                "padding": "8px 0px",
                "marginBottom": "16px",
            },
        ),
        dbc.Collapse(
            id="collab-filter-panel-collapse",
            is_open=False,
            children=[
                dbc.Card([
                    dbc.CardBody([
                        # Summary row + Clear All
                        html.Div([
                            html.Div([
                                html.Small("Refining loaded graph", className="graph-filter-mode-label d-block"),
                                html.Small(
                                    id="collab-filter-results-summary",
                                    children="Load a graph to refine it locally.",
                                    className="graph-filter-summary d-block",
                                ),
                            ]),
                            dbc.Button(
                                "Clear All",
                                id="collab-clear-filters-btn",
                                color="link",
                                size="sm",
                                className="ms-auto",
                                style={"fontSize": "11px", "padding": "0", "textDecoration": "none"},
                            ),
                        ], className="d-flex justify-content-between align-items-start mb-3"),

                        # Active filter chips
                        html.Div(
                            id="collab-filter-active-chips",
                            className="graph-filter-chip-list mb-3",
                            children=[html.Span("No active filters", className="graph-filter-empty-state")],
                        ),

                        # Display mode
                        html.Div([
                            html.Label("Display Filtered Items:", style=_LABEL_STYLE),
                            dbc.RadioItems(
                                id="collab-filter-display-mode",
                                options=[
                                    {"label": "Hide", "value": "hide"},
                                    {"label": "Dim",  "value": "dim"},
                                ],
                                value="hide",
                                inline=True,
                                className="graph-filter-radio",
                                style={"fontSize": "12px"},
                            ),
                        ], className="mb-3"),

                        # Community filter
                        html.Div([
                            html.Label("Communities:", style=_LABEL_STYLE),
                            dbc.Checklist(
                                id="collab-community-filter",
                                options=[],
                                value=[],
                                inline=False,
                                className="graph-filter-checklist",
                                style={"fontSize": "12px"},
                            ),
                        ], className="mb-3"),

                        # Weight threshold
                        html.Div([
                            html.Label("Weight Threshold:", style=_LABEL_STYLE),
                            dcc.Slider(
                                id="collab-weight-threshold-slider",
                                min=0,
                                max=100,
                                step=1,
                                value=0,
                                marks={0: "0", 25: "25", 50: "50", 75: "75", 100: "100"},
                                tooltip={"placement": "bottom", "always_visible": False},
                            ),
                            html.Small(
                                id="collab-weight-threshold-label",
                                children="Show edges with weight \u2265 0",
                                className="d-block mt-1",
                                style={"fontSize": "10px", "color": "var(--color-text-secondary)"},
                            ),
                        ], className="mb-3"),

                        # Top-N toggle
                        html.Div([
                            html.Label("Edge Limit:", style=_LABEL_STYLE),
                            dbc.RadioItems(
                                id="collab-top-n-toggle",
                                options=[
                                    {"label": "Show All",      "value": "all"},
                                    {"label": "Top 50 Edges",  "value": "top50"},
                                    {"label": "Top 100 Edges", "value": "top100"},
                                ],
                                value="all",
                                inline=False,
                                className="graph-filter-radio",
                                style={"fontSize": "12px"},
                            ),
                        ]),
                    ], className="graph-filter-card-body", style={"padding": "0 0 24px 0"}),
                ], className="graph-filter-card", style={"border": "none", "backgroundColor": "transparent"}),
            ],
        ),
    ], className="mb-3")


def get_layout() -> html.Div:
    """Return the collaboration network page layout."""
    return html.Div(
        [
            # Stores
            dcc.Store(id="collab-elements-store", data=[]),
            dcc.Store(id="collab-community-available-store", data=[]),

            # Top bar: back link + live stats banner
            html.Div(
                [
                    dbc.Button(
                        [html.I(className="fas fa-arrow-left me-2"), "Analytics"],
                        href="/app/analytics",
                        color="link",
                        size="sm",
                        style={"padding": "0", "fontSize": "13px", "textDecoration": "none"},
                    ),
                    html.Div(id="collab-banner", children=[], style={"display": "none", "flex": "1"}),
                ],
                className="d-flex align-items-center gap-3 mb-2",
                style={"padding": "8px 0"},
            ),

            # Main 2-column row: canvas (left) + filter panel (right)
            dbc.Row([
                dbc.Col([
                    cyto.Cytoscape(
                        id="collab-cytoscape",
                        elements=[],
                        layout=_COLLABORATION_LAYOUT,
                        style={
                            "width": "100%",
                            "height": "calc(100vh - 160px)",
                            "border": f"1px solid {COLOR_GRAY_LIGHTER}",
                            "borderRadius": "2px",
                        },
                        stylesheet=CYTOSCAPE_STYLESHEET,
                        userZoomingEnabled=True,
                        userPanningEnabled=True,
                        wheelSensitivity=1.0,
                        minZoom=0.1,
                        maxZoom=3,
                    ),
                    html.Div(
                        id="collab-empty-state",
                        children="No collaboration data found for the selected parameters.",
                        style={
                            "display": "none",
                            "textAlign": "center",
                            "padding": "80px 16px",
                            "color": "var(--color-text-secondary)",
                            "fontSize": FONT_SIZE_SMALL,
                        },
                    ),
                ], width=9, style={"paddingRight": "16px"}),

                dbc.Col([
                    _create_filter_panel(),
                ], width=3, style={"borderLeft": f"1px solid {COLOR_GRAY_LIGHTER}", "paddingLeft": "16px"}),
            ], className="g-0"),

            # Hidden Output target for the clientside render callback.
            html.Div(id="collab-render-trigger", style={"display": "none"}),
        ],
        id="collab-page",
        className="mt-2",
        style={"padding": "0 8px"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error_banner(message: str) -> dbc.Alert:
    return create_alert(message, color="danger", class_name="mb-0")


def _split_elements(elements: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split a Cytoscape element list into (nodes, edges)."""
    nodes = [
        e for e in elements
        if isinstance(e, dict) and e.get("data", {}).get("source") is None and e.get("data", {}).get("id")
    ]
    edges = [
        e for e in elements
        if isinstance(e, dict) and e.get("data", {}).get("source")
    ]
    return nodes, edges


def _get_communities(elements: list[dict]) -> list[int]:
    """Return sorted list of unique community IDs present in elements."""
    seen: set[int] = set()
    for el in elements:
        community = el.get("data", {}).get("community")
        if community is not None:
            seen.add(int(community))
    return sorted(seen)


def _append_class(element: dict, class_name: str) -> dict:
    existing = element.get("classes", "") or ""
    classes = f"{existing} {class_name}".strip()
    return {**element, "classes": classes}


def _compute_collab_filtered(
    elements: list[dict],
    selected_communities: list[Any],
    weight_threshold: int,
    top_n_mode: str,
    display_mode: str,
) -> list[dict]:
    """Apply community, weight, and top-N filters to collaboration elements.

    Returns a list ready to assign to collab-cytoscape.elements.
    selected_communities: list of community IDs to SHOW; empty = show all.
    """
    if not elements:
        return []

    nodes, edges = _split_elements(elements)
    selected_set = {int(c) for c in selected_communities} if selected_communities else None

    # --- community filter ---
    if selected_set is not None:
        visible_node_ids = {
            n["data"]["id"]
            for n in nodes
            if int(n["data"].get("community", -1)) in selected_set
        }
    else:
        visible_node_ids = {n["data"]["id"] for n in nodes}

    # --- weight + community edge filter ---
    candidate_edges = [
        e for e in edges
        if e["data"].get("weight", 0) >= weight_threshold
        and e["data"].get("source") in visible_node_ids
        and e["data"].get("target") in visible_node_ids
    ]

    # --- top-N filter ---
    if top_n_mode == "top50":
        candidate_edges = sorted(candidate_edges, key=lambda e: e["data"].get("weight", 0), reverse=True)[:50]
    elif top_n_mode == "top100":
        candidate_edges = sorted(candidate_edges, key=lambda e: e["data"].get("weight", 0), reverse=True)[:100]

    if display_mode == "hide":
        return [n for n in nodes if n["data"]["id"] in visible_node_ids] + candidate_edges

    # dim mode: keep all elements but mark filtered-out ones with "dimmed"
    candidate_edge_ids = {e["data"]["id"] for e in candidate_edges}
    dimmed_nodes = [
        n if n["data"]["id"] in visible_node_ids else _append_class(n, "dimmed")
        for n in nodes
    ]
    dimmed_edges = [
        e if e["data"]["id"] in candidate_edge_ids else _append_class(e, "dimmed")
        for e in edges
    ]
    return dimmed_nodes + dimmed_edges


# ---------------------------------------------------------------------------
# Server-side callback — load collaboration network data into the store
# ---------------------------------------------------------------------------

@callback(
    [Output("collab-elements-store",  "data"),
     Output("collab-cytoscape",       "layout"),
     Output("collab-banner",          "children"),
     Output("collab-banner",          "style"),
     Output("collab-empty-state",     "style")],
    [Input("url", "search"),
     Input("url", "pathname")],
)
def load_collaboration_network(search: str | None, pathname: str | None):
    """Fetch raw elements into the store when this page is active.

    Note: prevent_initial_call is intentionally NOT set here.  In Dash's
    multi-page pattern the output components don't exist until the user
    navigates to this page.  When they first appear, Dash treats the callback
    fire as an "initial call" — which prevent_initial_call=True would suppress.
    Since url.pathname won't change again after navigation, the callback would
    never run.  The pathname guard handles all non-collaboration routes safely.
    """
    if pathname != "/app/collaboration":
        raise PreventUpdate

    logger.info("[COLLAB-PAGE] Loading collaboration network search=%r", search)

    params = parse_qs((search or "").lstrip("?"))
    hide = {"display": "none"}
    show = {"display": "block"}

    empty_state_style = {
        "textAlign": "center",
        "padding": "80px 16px",
        "color": "var(--color-text-secondary)",
        "fontSize": FONT_SIZE_SMALL,
    }

    try:
        config = CollaborationNetworkConfig.from_query_values({
            "layers":                     params.get("layers"),
            "lookback_days":              params.get("lookback_days",              [None])[0],
            "min_pair_score":             params.get("min_pair_score",             [None])[0],
            "top_n_edges_per_node":       params.get("top_n_edges_per_node",       [None])[0],
            "community_gap_x":            params.get("community_gap_x",            [None])[0],
            "community_gap_y":            params.get("community_gap_y",            [None])[0],
            "ensure_min_connection":      params.get("ensure_min_connection",      [None])[0],
            "exclude_bots":               params.get("exclude_bots",               [None])[0],
            "exclude_suffixes":           params.get("exclude_suffixes",           [None])[0],
            "w_reporter_assignee":        params.get("w_reporter_assignee",        [None])[0],
            "w_pr_reviews":               params.get("w_pr_reviews",               [None])[0],
            "w_shared_file_commits":      params.get("w_shared_file_commits",      [None])[0],
            "w_sprint_coworkers":         params.get("w_sprint_coworkers",         [None])[0],
            "w_explicit_review_requests": params.get("w_explicit_review_requests", [None])[0],
            "w_epic_overlap":             params.get("w_epic_overlap",             [None])[0],
        })

        data = get_collaboration_network(config=config)
        elements = data.elements

        if not elements:
            logger.warning("[COLLAB-PAGE] No elements returned")
            return [], _COLLABORATION_LAYOUT, [], hide, {**empty_state_style, "display": "block"}

        applied_config = data.config or {}
        lookback_days  = applied_config.get("lookback_days", 90)
        top_n          = applied_config.get("top_n_edges_per_node", 0)
        layer_count    = len(applied_config.get("enabled_layers", []))

        banner_content = create_alert(
            [
                html.Strong("Collaboration Network"),
                html.Span(f"  \u2014  Last {lookback_days} days  "),
                dbc.Badge(f"{data.num_people} people",                color="primary",   className="me-1"),
                dbc.Badge(f"{data.num_pairs} pairs",                  color="secondary", className="me-1"),
                dbc.Badge(f"{data.num_communities} communities",       color="success",   className="me-1"),
                dbc.Badge(f"modularity {data.modularity:.3f}",        color="info",      className="me-1"),
                dbc.Badge(f"{layer_count} layers",                    color="dark",      className="me-1"),
                dbc.Badge("Top-N off" if top_n <= 0 else f"top {top_n}/node", color="warning"),
            ],
            color="light",
            class_name="mb-0 py-2",
            style={"fontSize": FONT_SIZE_SMALL},
        )

        logger.info(
            "[COLLAB-PAGE] SUCCESS \u2014 %d elements, %d people, %d communities, modularity=%.3f",
            len(elements), data.num_people, data.num_communities, data.modularity,
        )

        return elements, _COLLABORATION_LAYOUT, [banner_content], {**show, "flex": "1"}, hide

    except ValueError as exc:
        logger.warning("[COLLAB-PAGE] No data: %s", exc)
        return [], _COLLABORATION_LAYOUT, [_error_banner(str(exc))], show, hide

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[COLLAB-PAGE] Unexpected error: %s", exc)
        return [], _COLLABORATION_LAYOUT, [_error_banner("An unexpected error occurred.")], show, hide


# ---------------------------------------------------------------------------
# Filter callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("collab-cytoscape", "elements"),
    [Input("collab-elements-store",          "data"),
     Input("collab-community-filter",        "value"),
     Input("collab-weight-threshold-slider", "value"),
     Input("collab-top-n-toggle",            "value"),
     Input("collab-filter-display-mode",     "value")],
)
def apply_collab_filters(elements, selected_communities, weight_threshold, top_n_mode, display_mode):
    """Translate raw store elements through the active filters \u2192 cytoscape."""
    if not elements:
        return []
    result = _compute_collab_filtered(
        elements,
        selected_communities or [],
        weight_threshold or 0,
        top_n_mode or "all",
        display_mode or "hide",
    )
    logger.debug(
        "[COLLAB-FILTER] communities=%s weight>=%s top_n=%s mode=%s \u2192 %d elements",
        selected_communities, weight_threshold, top_n_mode, display_mode, len(result),
    )
    return result


@callback(
    [Output("collab-community-filter",          "options"),
     Output("collab-community-filter",          "value"),
     Output("collab-community-available-store", "data")],
    Input("collab-elements-store", "data"),
)
def update_collab_community_filter(elements):
    """Populate the community checklist when new data loads.

    Note: no prev-state guard here.  On re-navigation the
    collab-community-available-store can still hold community IDs from the
    previous visit, which would cause prev_set == curr_set → PreventUpdate
    → checklist stays empty.  Since collab-elements-store only changes on
    page load (not on filter interactions), always repopulating is safe and
    does not clobber mid-session selections.
    """
    if not elements:
        return [], [], []
    community_ids = _get_communities(elements)
    options = [{"label": f"Community {cid}", "value": cid} for cid in community_ids]
    return options, community_ids, community_ids


@callback(
    Output("collab-weight-threshold-label", "children"),
    Input("collab-weight-threshold-slider", "value"),
)
def update_collab_weight_label(value):
    """Update the weight threshold label text."""
    return f"Show edges with weight \u2265 {value or 0}"


@callback(
    [Output("collab-filter-results-summary", "children"),
     Output("collab-filter-active-chips",    "children")],
    [Input("collab-elements-store",          "data"),
     Input("collab-community-filter",        "value"),
     Input("collab-weight-threshold-slider", "value"),
     Input("collab-top-n-toggle",            "value"),
     Input("collab-filter-display-mode",     "value")],
)
def update_collab_filter_feedback(elements, selected_communities, weight_threshold, top_n_mode, display_mode):
    """Keep the summary line and active-filter chips up to date."""
    if not elements:
        return (
            "Load a graph to refine it locally.",
            [html.Span("No active filters", className="graph-filter-empty-state")],
        )

    nodes, edges = _split_elements(elements)
    filtered = _compute_collab_filtered(
        elements,
        selected_communities or [],
        weight_threshold or 0,
        top_n_mode or "all",
        display_mode or "hide",
    )
    f_nodes, f_edges = _split_elements(filtered)

    summary = (
        f"Showing {len(f_nodes)} nodes / {len(f_edges)} edges"
        f" from {len(nodes)} nodes / {len(edges)} edges"
    )

    chips: list[Any] = []
    all_community_ids = _get_communities(elements)
    if selected_communities and set(selected_communities) != set(all_community_ids):
        chips.append(dbc.Badge(
            f"Communities: {len(selected_communities)} selected", color="primary", className="me-1"
        ))
    if (weight_threshold or 0) > 0:
        chips.append(dbc.Badge(f"Weight \u2265 {weight_threshold}", color="secondary", className="me-1"))
    if top_n_mode and top_n_mode != "all":
        label = "Top 50" if top_n_mode == "top50" else "Top 100"
        chips.append(dbc.Badge(label, color="info", className="me-1"))

    if not chips:
        chips = [html.Span("No active filters", className="graph-filter-empty-state")]

    return summary, chips


@callback(
    [Output("collab-community-filter",        "value",  allow_duplicate=True),
     Output("collab-weight-threshold-slider", "value",  allow_duplicate=True),
     Output("collab-top-n-toggle",            "value",  allow_duplicate=True)],
    Input("collab-clear-filters-btn", "n_clicks"),
    State("collab-community-filter",  "options"),
    prevent_initial_call=True,
)
def clear_collab_filters(n_clicks, community_options):
    """Reset all filter controls to their defaults."""
    all_communities = [opt["value"] for opt in (community_options or [])]
    return all_communities, 0, "all"


@callback(
    [Output("collab-filter-panel-collapse", "is_open"),
     Output("collab-filter-collapse-icon",  "className")],
    Input("collab-filter-toggle-btn", "n_clicks"),
    State("collab-filter-panel-collapse", "is_open"),
    prevent_initial_call=True,
)
def toggle_collab_filter_panel(n_clicks, is_open):
    """Toggle the filter panel open/closed."""
    new_open = not is_open
    icon_class = "fas fa-chevron-down me-2" if new_open else "fas fa-chevron-right me-2"
    return new_open, icon_class


# ---------------------------------------------------------------------------
# Clientside callback — cy.resize() + cy.fit() after initial data load
# ---------------------------------------------------------------------------

clientside_callback(
    """
    function(storeData) {
        if (!storeData || !Array.isArray(storeData) || storeData.length === 0) {
            return window.dash_clientside.no_update;
        }
        // Delay to allow apply_collab_filters to complete and Cytoscape to paint.
        window.setTimeout(function() {
            var elem = document.getElementById("collab-cytoscape");
            if (!elem || !elem._cyreg || !elem._cyreg.cy) { return; }
            var cy = elem._cyreg.cy;
            cy.resize();
            cy.fit(cy.elements(), 30);
        }, 400);
        return "fit-scheduled n=" + storeData.length;
    }
    """,
    Output("collab-render-trigger", "children"),
    Input("collab-elements-store",  "data"),
    prevent_initial_call=True,
)

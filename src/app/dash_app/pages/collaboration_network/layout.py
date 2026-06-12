"""Collaboration Network page layout and pure helper functions.

Layout builders and stateless filtering helpers are kept here so they can be
imported by both the package __init__ and the callbacks sub-package without
creating circular imports.
"""

from typing import Any

import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from dash import dcc, html

from app.dash_app.components.common import create_alert, create_controls_bar
from app.dash_app.pages.graph.styles import CYTOSCAPE_STYLESHEET
from app.dash_app.styles import (
    COLOR_GRAY_DARK,
    COLOR_GRAY_LIGHTER,
    FONT_SIZE_SMALL,
    FONT_SIZE_XSMALL,
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

def _create_right_panel_tab_bar() -> html.Div:
    """Return the sticky icon-only tab bar for the collab right panel (Filters only)."""
    return html.Div(
        id="collab-right-panel-tab-bar",
        className="graph-right-panel-tab-bar",
        children=[
            html.Button(
                html.I(className="fas fa-sliders fa-fw"),
                id="collab-right-tab-filters-btn",
                title="Filters",
                className="graph-right-panel-tab-icon",
                n_clicks=0,
            ),
        ],
    )


def _create_right_panel_tabs() -> html.Div:
    """Return the single accordion collapse panel for the Filters tab."""
    return html.Div([
        dbc.Collapse(
            id="collab-right-tab-filters-collapse",
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
    ])


def get_layout() -> html.Div:
    """Return the collaboration network page layout."""
    return html.Div(
        [
            # Stores
            dcc.Store(id="collab-elements-store", data=[]),
            dcc.Store(id="collab-community-available-store", data=[]),
            dcc.Store(id="collab-fullwidth-state", data=False),
            dcc.Store(id="collab-spotlight-debounced-store", data=""),

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

            # Main 2-column row: canvas (left) + filter + properties (right)
            dbc.Row([
                dbc.Col([
                    create_controls_bar("collab", layout_enabled=False),
                    cyto.Cytoscape(
                        id="collab-cytoscape",
                        elements=[],
                        layout=_COLLABORATION_LAYOUT,
                        style={
                            "width": "100%",
                            "height": "calc(100vh - 200px)",
                            "border": f"1px solid {COLOR_GRAY_LIGHTER}",
                            "borderRadius": "2px",
                        },
                        stylesheet=CYTOSCAPE_STYLESHEET,
                        userZoomingEnabled=True,
                        userPanningEnabled=True,
                        wheelSensitivity=0.3,
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
                ], id="collab-viz-col", width=8, style={"paddingRight": "16px"}),

                dbc.Col([
                    html.Div(
                        style={"overflowY": "auto", "maxHeight": "calc(75vh + 40px)", "position": "relative"},
                        children=[
                            _create_right_panel_tab_bar(),
                            _create_right_panel_tabs(),
                            html.Div(
                                id="collab-details-panel",
                                children=html.P(
                                    "Select a node or edge to see its properties.",
                                    className="text-muted text-center",
                                    style={"fontSize": FONT_SIZE_XSMALL, "padding": "16px 0"},
                                ),
                            ),
                        ],
                    ),
                ], id="collab-details-col", width=4, style={"borderLeft": f"1px solid {COLOR_GRAY_LIGHTER}", "paddingLeft": "16px"}),
            ], className="g-0"),

            # Hidden Output target for the clientside render callback.
            html.Div(id="collab-render-trigger", style={"display": "none"}),
        ],
        id="collab-page",
        className="mt-2",
        style={"padding": "0 8px"},
    )


# ---------------------------------------------------------------------------
# Pure helper functions (stateless — no Dash callbacks)
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

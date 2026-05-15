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

import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
from dash import Input, Output, callback, clientside_callback, dcc, html
from dash.exceptions import PreventUpdate

from app.analytics.collaboration.config import CollaborationNetworkConfig
from app.analytics.registry import COLLABORATION_NETWORK_ANALYTIC
from app.api.graph.v1.service import get_collaboration_network
from app.common.logger import logger
from app.dash_app.components.common import create_alert
from app.dash_app.pages.graph.styles import CYTOSCAPE_STYLESHEET
from app.dash_app.styles import FONT_SIZE_SMALL


_COLLABORATION_LAYOUT = {"name": "preset", "fit": False, "animate": False, "padding": 30}
"""Preset layout with fit:False.

fit:False is intentional: on first render the browser may not have finished laying
out the container, so letting Cytoscape auto-fit produces an invalid zoom.
The clientside render callback calls cy.resize() + cy.fit() explicitly once the
DOM is stable.
"""


def get_layout() -> html.Div:
    """Return the collaboration network page layout."""
    return html.Div(
        [
            dcc.Store(id="collab-elements-store", data=[]),

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

            # Graph canvas — always visible on this page (no hidden-container dance)
            cyto.Cytoscape(
                id="collab-cytoscape",
                elements=[],
                layout=_COLLABORATION_LAYOUT,
                style={
                    "width": "100%",
                    "height": "calc(100vh - 160px)",
                    "border": "1px solid #e0e0e0",
                    "borderRadius": "2px",
                },
                stylesheet=CYTOSCAPE_STYLESHEET,
                userZoomingEnabled=True,
                userPanningEnabled=True,
                wheelSensitivity=1.0,
                minZoom=0.1,
                maxZoom=3,
            ),

            # Empty-state (shown when query returns no data)
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

            # Hidden Output target for the clientside render-check callback.
            # Dash requires every Output component to exist in the layout.
            html.Div(id="collab-render-trigger", style={"display": "none"}),
        ],
        id="collab-page",
        className="mt-2",
        style={"padding": "0 8px"},
    )


# ---------------------------------------------------------------------------
# Server-side callback — load collaboration network data
# ---------------------------------------------------------------------------

@callback(
    [Output("collab-cytoscape", "elements"),
     Output("collab-cytoscape", "layout"),
     Output("collab-banner", "children"),
     Output("collab-banner", "style"),
     Output("collab-empty-state", "style")],
    [Input("url", "search"),
     Input("url", "pathname")],
)
def load_collaboration_network(search: str | None, pathname: str | None):
    """Fetch and render the collaboration network when this page is active.

    Note: prevent_initial_call is intentionally NOT set here.  In Dash's
    multi-page pattern the output components (collab-cytoscape etc.) don't
    exist until the user navigates to this page.  When they first appear,
    Dash treats the callback fire as an "initial call".  With
    prevent_initial_call=True that initial call would be suppressed, and
    url.pathname won't change again, so the callback would never run.
    The pathname guard below handles all non-collaboration routes safely.
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
        config = CollaborationNetworkConfig.from_query_values(
            {
                "layers": params.get("layers"),
                "lookback_days": params.get("lookback_days", [None])[0],
                "min_pair_score": params.get("min_pair_score", [None])[0],
                "top_n_edges_per_node": params.get("top_n_edges_per_node", [None])[0],
                "community_gap_x": params.get("community_gap_x", [None])[0],
                "community_gap_y": params.get("community_gap_y", [None])[0],
                "ensure_min_connection": params.get("ensure_min_connection", [None])[0],
                "exclude_bots": params.get("exclude_bots", [None])[0],
                "exclude_suffixes": params.get("exclude_suffixes", [None])[0],
                "w_reporter_assignee": params.get("w_reporter_assignee", [None])[0],
                "w_pr_reviews": params.get("w_pr_reviews", [None])[0],
                "w_shared_file_commits": params.get("w_shared_file_commits", [None])[0],
                "w_sprint_coworkers": params.get("w_sprint_coworkers", [None])[0],
                "w_explicit_review_requests": params.get("w_explicit_review_requests", [None])[0],
                "w_epic_overlap": params.get("w_epic_overlap", [None])[0],
            }
        )

        data = get_collaboration_network(config=config)
        elements = data.elements

        if not elements:
            logger.warning("[COLLAB-PAGE] No elements returned")
            return [], _COLLABORATION_LAYOUT, [], hide, {**empty_state_style, "display": "block"}

        applied_config = data.config or {}
        lookback_days = applied_config.get("lookback_days", 90)
        top_n = applied_config.get("top_n_edges_per_node", 0)
        layer_count = len(applied_config.get("enabled_layers", []))

        banner_content = create_alert(
            [
                html.Strong("Collaboration Network"),
                html.Span(f"  —  Last {lookback_days} days  "),
                dbc.Badge(f"{data.num_people} people", color="primary", className="me-1"),
                dbc.Badge(f"{data.num_pairs} pairs", color="secondary", className="me-1"),
                dbc.Badge(f"{data.num_communities} communities", color="success", className="me-1"),
                dbc.Badge(f"modularity {data.modularity:.3f}", color="info", className="me-1"),
                dbc.Badge(f"{layer_count} layers", color="dark", className="me-1"),
                dbc.Badge(
                    "Top-N off" if top_n <= 0 else f"top {top_n}/node",
                    color="warning",
                ),
            ],
            color="light",
            class_name="mb-0 py-2",
            style={"fontSize": FONT_SIZE_SMALL},
        )

        logger.info(
            "[COLLAB-PAGE] SUCCESS — %d elements, %d people, %d communities, modularity=%.3f",
            len(elements), data.num_people, data.num_communities, data.modularity,
        )

        return (
            elements,
            _COLLABORATION_LAYOUT,
            [banner_content],
            {**show, "flex": "1"},
            hide,
        )

    except ValueError as exc:
        logger.warning("[COLLAB-PAGE] No data: %s", exc)
        banner = [_error_banner(str(exc))]
        return [], _COLLABORATION_LAYOUT, banner, show, hide

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[COLLAB-PAGE] Unexpected error: %s", exc)
        banner = [_error_banner("An unexpected error occurred while loading the collaboration network.")]
        return [], _COLLABORATION_LAYOUT, banner, show, hide


def _error_banner(message: str) -> dbc.Alert:
    return create_alert(message, color="danger", class_name="mb-0")


# ---------------------------------------------------------------------------
# Clientside callback — cy.resize() + cy.fit() after elements land
# ---------------------------------------------------------------------------

clientside_callback(
    """
    function(elements) {
        const cytoscapeElements = Array.isArray(elements) ? elements : [];
        const isCollaboration = cytoscapeElements.some(function(el) {
            const classes = el && el.classes ? String(el.classes) : "";
            const data = el && el.data ? el.data : {};
            return classes.indexOf("collaboration-edge") !== -1 || data.community !== undefined;
        });

        if (!isCollaboration || cytoscapeElements.length === 0) {
            return window.dash_clientside.no_update;
        }

        const applyFit = function() {
            const elem = document.getElementById("collab-cytoscape");
            if (!elem || !elem._cyreg || !elem._cyreg.cy) { return; }
            const cy = elem._cyreg.cy;
            cy.resize();
            cy.fit(cy.elements(), 30);
        };

        window.requestAnimationFrame(function() {
            applyFit();
            window.setTimeout(applyFit, 150);
        });

        return "fit-scheduled nodes=" + cytoscapeElements.filter(function(el) {
            return el && el.data && el.data.id && !el.data.source;
        }).length;
    }
    """,
    Output("collab-render-trigger", "children"),
    Input("collab-cytoscape", "elements"),
    prevent_initial_call=True,
)

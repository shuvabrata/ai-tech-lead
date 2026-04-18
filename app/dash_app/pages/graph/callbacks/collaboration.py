"""Collaboration Network Callbacks

Handles auto-loading the collaboration network visualization when the graph
page is accessed with ?mode=collaboration in the URL query string.
"""

from urllib.parse import parse_qs

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html, no_update

from app.analytics.collaboration.config import CollaborationNetworkConfig
from app.analytics.registry import COLLABORATION_NETWORK_ANALYTIC
from app.common.logger import logger
from app.dash_app.styles import GRAPH_DETAILS_PANEL_STYLE
from app.api.graph.v1.service import get_collaboration_network


@callback(
    [Output("graph-cytoscape", "elements", allow_duplicate=True),
     Output("graph-cytoscape-container", "style", allow_duplicate=True),
     Output("graph-results-container", "children", allow_duplicate=True),
     Output("graph-results-container", "style", allow_duplicate=True),
     Output("graph-details-panel", "style", allow_duplicate=True),
     Output("unfiltered-elements-store", "data", allow_duplicate=True),
     Output("loaded-node-ids", "data", allow_duplicate=True),
     Output("expanded-nodes", "data", allow_duplicate=True),
     Output("expansion-debounce-store", "data", allow_duplicate=True),
     Output("collaboration-banner", "children"),
     Output("collaboration-banner", "style"),
     Output("graph-cytoscape", "layout", allow_duplicate=True)],
    [Input("url", "search"),
     Input("url", "pathname")],
    [State("graph-layout-selector", "value")],
    prevent_initial_call='initial_duplicate',
)
def load_collaboration_network(
    search: str | None,
    pathname: str | None,
    selected_layout: str | None,
):
    """Fetch and render the collaboration network when collaboration analytics mode is active."""
    params = parse_qs((search or "").lstrip("?"))
    mode = params.get("mode", [None])[0]
    is_collaboration_mode = mode in {"collaboration", COLLABORATION_NETWORK_ANALYTIC.key}

    def selector_to_layout(layout_name: str | None):
        name = layout_name or "cose"
        if name == "preset":
            return {"name": "preset", "fit": False, "animate": False, "padding": 30}
        return {"name": name, "animate": True}

    collaboration_layout = {"name": "preset", "fit": True, "animate": False, "padding": 30}

    if pathname != "/app/graph":
        return [no_update] * 12

    if not is_collaboration_mode:
        # Keep generic graph behavior tied to the user's selected layout.
        return [no_update] * 11 + [selector_to_layout(selected_layout)]

    logger.info("[COLLABORATION] Loading collaboration network")

    hide = {"display": "none"}
    show_block = {"display": "block"}
    banner_padding = {"display": "block", "padding": "0 16px"}

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
            logger.warning("[COLLABORATION] No elements returned")
            empty_msg = html.Div(
                "No collaboration data found for the last 90 days.",
                style={"textAlign": "center", "padding": "40px", "color": "var(--color-text-secondary)"},
            )
            return (
                [], hide, empty_msg, {"minHeight": "300px", "padding": "16px"},
                hide, [], [], {}, {}, [], hide, collaboration_layout,
            )

        num_people = data.num_people
        num_pairs = data.num_pairs
        num_communities = data.num_communities
        modularity = data.modularity
        applied_config = data.config or {}
        top_n = applied_config.get("top_n_edges_per_node", 0)
        layer_count = len(applied_config.get("enabled_layers", []))
        lookback_days = applied_config.get("lookback_days", 90)

        banner_children = dbc.Alert(
            [
                html.Strong("Collaboration Network"),
                html.Span(f"  —  Last {lookback_days} days  "),
                dbc.Badge(f"{num_people} people", color="primary", className="me-1"),
                dbc.Badge(f"{num_pairs} pairs", color="secondary", className="me-1"),
                dbc.Badge(f"{num_communities} communities", color="success", className="me-1"),
                dbc.Badge(f"modularity {modularity:.3f}", color="info", className="me-1"),
                dbc.Badge(f"{layer_count} layers", color="dark", className="me-1"),
                dbc.Badge(
                    "Top-N off" if top_n <= 0 else f"top {top_n}/node",
                    color="warning",
                ),
            ],
            color="light",
            className="mb-2 py-2",
        )

        logger.info(
            "[COLLABORATION] Loaded %d elements (%d people, %d communities, modularity=%.3f)",
            len(elements), num_people, num_communities, modularity,
        )

        return (
            elements,                  # cytoscape elements
            show_block,                # show graph container
            None,                      # clear empty-state children
            hide,                      # hide empty-state container
            GRAPH_DETAILS_PANEL_STYLE, # show details panel
            elements,                  # sync unfiltered baseline
            [],                        # reset loaded-node-ids
            {},                        # reset expanded-nodes
            {},                        # reset expansion-debounce
            [banner_children],         # banner content
            banner_padding,            # banner visible
            collaboration_layout,      # use deterministic preset positions
        )

    except ValueError as exc:
        logger.warning("[COLLABORATION] No data: %s", exc)
        banner = _error_banner(str(exc))
        return ([], hide, None, hide, hide, [], [], {}, {}, [banner], banner_padding, collaboration_layout)

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[COLLABORATION] Unexpected error: %s", exc)
        banner = _error_banner("An unexpected error occurred while loading the collaboration network.")
        return ([], hide, None, hide, hide, [], [], {}, {}, [banner], banner_padding, collaboration_layout)


def _error_banner(message: str):
    return dbc.Alert(message, color="danger", className="mb-2")

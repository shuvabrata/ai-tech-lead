"""Collaboration Network Callbacks

Handles auto-loading the collaboration network visualization when the graph
page is accessed with ?mode=collaboration in the URL query string.
"""

import requests
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, html, no_update

from app.settings import settings
from app.common.logger import logger
from app.dash_app.styles import GRAPH_DETAILS_PANEL_STYLE
from ..utils import get_graph_api_base_url

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT


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
     Output("collaboration-banner", "style")],
    [Input("url", "search"),
     Input("url", "pathname")],
    prevent_initial_call='initial_duplicate',
)
def load_collaboration_network(search: str | None, pathname: str | None):
    """Fetch and render the collaboration network when ?mode=collaboration is active."""
    if pathname != "/app/graph" or search != "?mode=collaboration":
        return [no_update] * 11

    api_base = get_graph_api_base_url()
    logger.info("[COLLABORATION] Loading collaboration network from %s", api_base)

    hide = {"display": "none"}
    show_block = {"display": "block"}
    banner_padding = {"display": "block", "padding": "0 16px"}

    try:
        response = requests.get(
            f"{api_base}/api/v1/graph/collaboration-network",
            timeout=TIMEOUT_SECONDS,
        )

        if response.status_code != 200:
            logger.warning("[COLLABORATION] API returned %s", response.status_code)
            banner = _error_banner(f"Failed to load collaboration network (HTTP {response.status_code}).")
            return ([], hide, None, hide, hide, [], [], {}, {}, [banner], banner_padding)

        data = response.json()
        elements = data.get("elements", [])

        if not elements:
            logger.warning("[COLLABORATION] No elements returned from API")
            empty_msg = html.Div(
                "No collaboration data found for the last 90 days.",
                style={"textAlign": "center", "padding": "40px", "color": "var(--color-text-secondary)"},
            )
            return (
                [], hide, empty_msg, {"minHeight": "300px", "padding": "16px"},
                hide, [], [], {}, {}, [], hide,
            )

        num_people = data.get("num_people", 0)
        num_pairs = data.get("num_pairs", 0)
        num_communities = data.get("num_communities", 0)
        modularity = data.get("modularity", 0.0)

        banner_children = dbc.Alert(
            [
                html.Strong("Collaboration Network"),
                html.Span("  —  Last 90 days  "),
                dbc.Badge(f"{num_people} people", color="primary", className="me-1"),
                dbc.Badge(f"{num_pairs} pairs", color="secondary", className="me-1"),
                dbc.Badge(f"{num_communities} communities", color="success", className="me-1"),
                dbc.Badge(f"modularity {modularity:.3f}", color="info"),
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
        )

    except requests.exceptions.ConnectionError:
        logger.error("[COLLABORATION] Connection error — is the backend running?")
        banner = _error_banner("Cannot connect to the backend API. Ensure the server is running.")
        return ([], hide, None, hide, hide, [], [], {}, {}, [banner], banner_padding)

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[COLLABORATION] Unexpected error: %s", exc)
        banner = _error_banner(f"An unexpected error occurred: {exc}")
        return ([], hide, None, hide, hide, [], [], {}, {}, [banner], banner_padding)


def _error_banner(message: str):
    return dbc.Alert(message, color="danger", className="mb-2")

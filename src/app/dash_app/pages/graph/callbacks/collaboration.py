"""Collaboration Network Callbacks

Handles auto-loading the collaboration network visualization when the graph
page is accessed with ?mode=collaboration in the URL query string.
"""

import time
from urllib.parse import parse_qs

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, callback_context, clientside_callback, html, no_update

from app.analytics.collaboration.config import CollaborationNetworkConfig
from app.analytics.registry import COLLABORATION_NETWORK_ANALYTIC
from app.common.logger import logger
from app.dash_app.components.common import create_alert
from app.dash_app.styles import FONT_SIZE_SMALL, GRAPH_DETAILS_PANEL_STYLE
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
     Output("graph-layout-selector", "value", allow_duplicate=True),
     Output("graph-cytoscape", "layout", allow_duplicate=True)],
    [Input("url", "search"),
     Input("url", "pathname")],
    [State("graph-layout-selector", "value")],
    # 'initial_duplicate' is required by Dash when any output uses allow_duplicate=True.
    # prevent_initial_call=False is forbidden with allow_duplicate — Dash raises
    # DuplicateCallback if you set it.  'initial_duplicate' prevents this callback
    # from competing with primary-owner callbacks on initial render, while still
    # allowing it to fire on every subsequent URL change (navigation/refresh triggers
    # a url.search / url.pathname input change that re-fires the callback normally).
    prevent_initial_call='initial_duplicate',
)
def load_collaboration_network(
    search: str | None,
    pathname: str | None,
    selected_layout: str | None,
):
    """Fetch and render the collaboration network when collaboration analytics mode is active."""
    render_id = f"collab-{int(time.time() * 1000) % 100000}"  # short correlation token

    # Log every invocation so we can see all triggers in the server log
    triggered = []
    try:
        ctx = callback_context
        triggered = [t["prop_id"] for t in (ctx.triggered or [])]
    except Exception:  # pylint: disable=broad-except
        pass
    logger.info(
        "[COLLABORATION:%s] callback fired — triggered=%s pathname=%r search=%r selected_layout=%r",
        render_id, triggered, pathname, search, selected_layout,
    )
    params = parse_qs((search or "").lstrip("?"))
    mode = params.get("mode", [None])[0]
    is_collaboration_mode = mode in {"collaboration", COLLABORATION_NETWORK_ANALYTIC.key}

    def selector_to_layout(layout_name: str | None):
        name = layout_name or "cose"
        if name == "preset":
            return {"name": "preset", "fit": False, "animate": False, "padding": 30}
        return {"name": name, "animate": True}

    # Use fit:False — the canvas may still be 0×0 when this layout prop lands because
    # the container was just transitioned from display:none.  fit:True on a 0×0 canvas
    # produces an undefined/infinite zoom.  The clientside render-check callback
    # calls cy.resize() then cy.fit() explicitly after the container is fully painted.
    collaboration_layout = {"name": "preset", "fit": False, "animate": False, "padding": 30}

    if pathname != "/app/graph":
        logger.debug("[COLLABORATION:%s] skipping — pathname=%r is not /app/graph", render_id, pathname)
        return [no_update] * 13

    if not is_collaboration_mode:
        # Keep generic graph behavior tied to the user's selected layout.
        logger.debug("[COLLABORATION:%s] non-collaboration mode=%r, syncing layout selector only", render_id, mode)
        return [no_update] * 12 + [selector_to_layout(selected_layout)]

    logger.info(
        "[COLLABORATION:%s] loading collaboration network — mode=%r selected_layout=%r",
        render_id, mode, selected_layout,
    )

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
        logger.debug("[COLLABORATION] Applied config: %s", config.to_summary())

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
                hide, [], [], {}, {}, [], hide, "preset", collaboration_layout,
            )

        num_people = data.num_people
        num_pairs = data.num_pairs
        num_communities = data.num_communities
        modularity = data.modularity
        applied_config = data.config or {}
        top_n = applied_config.get("top_n_edges_per_node", 0)
        layer_count = len(applied_config.get("enabled_layers", []))
        lookback_days = applied_config.get("lookback_days", 90)

        banner_children = create_alert(
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
            class_name="mb-2 py-2",
            style={"fontSize": FONT_SIZE_SMALL},
        )

        logger.info(
            "[COLLABORATION:%s] SUCCESS — sending %d elements (%d people, %d communities, modularity=%.3f)"
            " container=show layout=%s",
            render_id, len(elements), num_people, num_communities, modularity, collaboration_layout,
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
            "preset",                  # keep the selector aligned with positioned elements
            collaboration_layout,      # use deterministic preset positions
        )

    except ValueError as exc:
        logger.warning("[COLLABORATION:%s] No data: %s", render_id, exc)
        banner = _error_banner(str(exc))
        return ([], hide, None, hide, hide, [], [], {}, {}, [banner], banner_padding, "preset", collaboration_layout)

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("[COLLABORATION:%s] Unexpected error: %s", render_id, exc)
        banner = _error_banner("An unexpected error occurred while loading the collaboration network.")
        return ([], hide, None, hide, hide, [], [], {}, {}, [banner], banner_padding, "preset", collaboration_layout)


def _error_banner(message: str):
    return create_alert(message, color="danger", class_name="mb-2")


clientside_callback(
    """
    function(elements, layout, containerStyle) {
        const ts = Date.now();
        const cytoscapeElements = Array.isArray(elements) ? elements : [];
        const nodeElements = cytoscapeElements.filter(function(element) {
            const data = element && element.data ? element.data : {};
            return data.id && !data.source && !data.target;
        });
        const edgeElements = cytoscapeElements.filter(function(element) {
            const data = element && element.data ? element.data : {};
            return data.source && data.target;
        });
        const isCollaboration = cytoscapeElements.some(function(element) {
            const classes = element && element.classes ? String(element.classes) : "";
            const data = element && element.data ? element.data : {};
            return classes.indexOf("collaboration-edge") !== -1 || data.community !== undefined;
        });
        const layoutName = layout && layout.name ? layout.name : "unknown";

        console.debug("[COLLAB_RENDER] clientside_callback fired", {
            ts: ts,
            totalElements: cytoscapeElements.length,
            nodes: nodeElements.length,
            edges: edgeElements.length,
            isCollaboration: isCollaboration,
            layoutName: layoutName,
            containerStyle: containerStyle
        });

        if (!isCollaboration || nodeElements.length === 0 || layoutName !== "preset") {
            console.warn("[COLLAB_RENDER] skipping — isCollaboration=" + isCollaboration
                + " nodes=" + nodeElements.length + " layout=" + layoutName);
            return window.dash_clientside.no_update;
        }

        const runCheck = function(attempt) {
            const elem = document.getElementById("graph-cytoscape");
            const container = document.getElementById("graph-cytoscape-container");

            if (!elem || !elem._cyreg || !elem._cyreg.cy) {
                console.debug("[COLLAB_RENDER] attempt=" + attempt + " Cytoscape instance not ready yet", {
                    elemExists: !!elem,
                    hasCyreg: !!(elem && elem._cyreg),
                });
                return;
            }

            const cy = elem._cyreg.cy;
            const rect = elem.getBoundingClientRect();
            const containerRect = container ? container.getBoundingClientRect() : null;
            const presetPositions = {};
            nodeElements.forEach(function(element) {
                const data = element && element.data ? element.data : {};
                const position = element && element.position ? element.position : {};
                if (data.id && Number.isFinite(position.x) && Number.isFinite(position.y)) {
                    presetPositions[String(data.id)] = { x: position.x, y: position.y };
                }
            });

            // Always restore preset positions from element specs first (works even if
            // cy.nodes() is empty — batch becomes a no-op in that case).
            if (Object.keys(presetPositions).length > 0) {
                cy.batch(function() {
                    cy.nodes().forEach(function(node) {
                        const position = presetPositions[node.id()];
                        if (position) {
                            node.position(position);
                        }
                    });
                });
            }

            let invalidPositions = 0;
            let minX = Infinity;
            let maxX = -Infinity;
            let minY = Infinity;
            let maxY = -Infinity;

            cy.nodes().forEach(function(node) {
                const pos = node.position();
                if (!Number.isFinite(pos.x) || !Number.isFinite(pos.y)) {
                    invalidPositions += 1;
                    return;
                }
                minX = Math.min(minX, pos.x);
                maxX = Math.max(maxX, pos.x);
                minY = Math.min(minY, pos.y);
                maxY = Math.max(maxY, pos.y);
            });

            const rectOk = rect.width > 0 && rect.height > 0;
            const nodesOk = cy.nodes().length > 0;

            console.debug("[COLLAB_RENDER] attempt=" + attempt, {
                rectOk: rectOk,
                nodesOk: nodesOk,
                cyNodes: cy.nodes().length,
                cyEdges: cy.edges().length,
                rect: { width: rect.width, height: rect.height },
                containerRect: containerRect ? { width: containerRect.width, height: containerRect.height } : null,
                zoom: cy.zoom(),
                pan: cy.pan(),
                invalidPositions: invalidPositions,
                presetPositionsAvailable: Object.keys(presetPositions).length,
                positionBounds: Number.isFinite(minX) ? { x: [minX, maxX], y: [minY, maxY] } : null
            });

            if (rectOk && nodesOk) {
                cy.resize();
                cy.layout({ name: "preset", fit: false, animate: false, padding: 30 }).run();
                cy.fit(cy.elements(), 30);
                console.warn("[COLLAB_RENDER] attempt=" + attempt + " resize+fit APPLIED zoom=" + cy.zoom().toFixed(3)
                    + " pan=" + JSON.stringify(cy.pan()));
            } else {
                console.debug("[COLLAB_RENDER] attempt=" + attempt + " SKIPPED — rectOk=" + rectOk + " nodesOk=" + nodesOk);
            }
        };

        window.requestAnimationFrame(function() {
            runCheck(1);
            window.setTimeout(function() { runCheck(2); }, 80);
            window.setTimeout(function() { runCheck(3); }, 300);
            window.setTimeout(function() { runCheck(4); }, 700);
            window.setTimeout(function() { runCheck(5); }, 1200);
        });

        return "collab-render scheduled ts=" + ts + " nodes=" + nodeElements.length
            + " edges=" + edgeElements.length;
    }
    """,
    Output("collaboration-render-diagnostics", "children"),
    [Input("graph-cytoscape", "elements"),
     Input("graph-cytoscape", "layout"),
     Input("graph-cytoscape-container", "style")],
    prevent_initial_call=False,
)

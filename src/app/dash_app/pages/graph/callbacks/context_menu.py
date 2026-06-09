"""Context Menu Callbacks

Callbacks for right-click context menu functionality.
"""

import requests
from dash import html, Input, Output, State, callback, clientside_callback, callback_context
from dash.exceptions import PreventUpdate

from app.settings import settings
from common.logger import logger
from app.dash_app.components.common import create_alert
from app.dash_app.styles import CONTEXT_MENU_CONTAINER_STYLE
from ..utils import (
    execute_expansion_and_merge,
    create_expansion_success_alert,
    create_no_neighbors_alert,
    create_expansion_error_alert,
    is_edge_element,
)

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT


@callback(
    Output("context-menu", "style"),
    Input("rightclicked-node-store", "data"),
    prevent_initial_call=True
)
def show_context_menu(rightclick_data):
    """Show context menu at mouse position when node is right-clicked.

    Builds the style from scratch on every call so that React always sees a
    change to the ``display`` property and does not skip the DOM update.  The
    bug this fixes: the outside-click handler used to set
    ``menu.style.display = 'none'`` directly on the DOM without going through
    Dash/React.  The next time this callback ran, React thought ``display`` was
    still ``block`` (its last virtual-DOM value) and skipped updating it, so
    the menu stayed invisible.
    """
    if not rightclick_data or not isinstance(rightclick_data, dict):
        # Explicit hide: return the canonical hidden style so Dash/React always
        # drives display to 'none' through its own reconciliation path.
        return CONTEXT_MENU_CONTAINER_STYLE

    x = rightclick_data.get("x", 0)
    y = rightclick_data.get("y", 0)

    return {
        **CONTEXT_MENU_CONTAINER_STYLE,
        "display": "block",
        "left": f"{x}px",
        "top": f"{y}px",
    }


@callback(
    [Output("expansion-modal", "is_open", allow_duplicate=True),
     Output("selected-node-for-expansion", "data", allow_duplicate=True),
     Output("context-menu", "style", allow_duplicate=True)],
    Input("ctx-menu-expand", "n_clicks"),
    [State("rightclicked-node-store", "data"),
     State("context-menu", "style")],
    prevent_initial_call=True
)
def context_menu_expand_modal(n_clicks, rightclick_data, menu_style):
    """Open expansion modal from context menu"""
    if not n_clicks or not rightclick_data:
        raise PreventUpdate
    
    node_id = rightclick_data.get("node_id")
    
    # Hide menu
    updated_menu_style = menu_style.copy()
    updated_menu_style["display"] = "none"
    
    return True, node_id, updated_menu_style


@callback(
    [Output("graph-cytoscape", "elements", allow_duplicate=True),
    Output("unfiltered-elements-store", "data", allow_duplicate=True),
     Output("expanded-nodes", "data", allow_duplicate=True),
     Output("loaded-node-ids", "data", allow_duplicate=True),
     Output("context-menu", "style", allow_duplicate=True),
    Output("graph-status-strip", "children", allow_duplicate=True),
    Output("graph-status-strip", "style", allow_duplicate=True),
     Output("graph-layout-selector", "value", allow_duplicate=True)],
    [Input("ctx-menu-expand-incoming", "n_clicks"),
     Input("ctx-menu-expand-outgoing", "n_clicks")],
    [State("rightclicked-node-store", "data"),
     State("graph-cytoscape", "elements"),
     State("unfiltered-elements-store", "data"),
     State("loaded-node-ids", "data"),
     State("expanded-nodes", "data"),
     State("node-positions-store", "data"),
     State("context-menu", "style"),
     State("graph-layout-selector", "value")],
    prevent_initial_call=True
)
def context_menu_quick_expand(_n_clicks_incoming, _n_clicks_outgoing, rightclick_data,
                              current_elements, current_unfiltered, loaded_node_ids, expanded_nodes,
                              current_node_positions,
                              menu_style, current_layout):
    """Handle quick expansion from context menu"""
    show_style = {"display": "block"}
    hide_style = {"display": "none"}
    
    # Hide menu
    updated_menu_style = menu_style.copy()
    updated_menu_style["display"] = "none"
    
    if not rightclick_data:
        return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, updated_menu_style,
                None, hide_style, current_layout)
    
    # Determine which button was clicked
    ctx = callback_context
    if not ctx.triggered:
        raise PreventUpdate
    
    button_id = ctx.triggered[0]["prop_id"].split(".")[0]
    
    # Set direction based on button
    if button_id == "ctx-menu-expand-incoming":
        direction = "incoming"
    elif button_id == "ctx-menu-expand-outgoing":
        direction = "outgoing"
    else:
        raise PreventUpdate
    
    node_id = rightclick_data.get("node_id")
    if not node_id:
        return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, updated_menu_style,
                None, hide_style, current_layout)
    
    try:
        logger.info(
            "[GRAPH-DEBUG][context.expand] start "
            f"node_id={node_id} direction={direction} current_elements={len(current_elements or [])} "
            f"loaded_node_ids={len(loaded_node_ids or [])}"
        )
        result = execute_expansion_and_merge(
            node_id=node_id,
            direction=direction,
            limit=settings.GRAPH_UI_MAX_NODES_TO_EXPAND,
            loaded_node_ids=loaded_node_ids,
            expanded_nodes=expanded_nodes,
            current_elements=current_elements,
            current_node_positions=current_node_positions,
            timeout_seconds=TIMEOUT_SECONDS,
        )

        if not result["ok"]:
            error_alert = create_expansion_error_alert(f"Expansion failed: {result['error_message']}")
            return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, updated_menu_style,
                    error_alert, show_style, current_layout)

        merged_elements = result["merged_elements"]
        updated_loaded_ids = result["updated_loaded_ids"]
        updated_expanded = result["updated_expanded"]

        if result["new_nodes_count"] == 0:
            info_msg = create_no_neighbors_alert()
            return (merged_elements, merged_elements, updated_expanded, updated_loaded_ids, updated_menu_style,
                    info_msg, show_style, current_layout)

        success_msg = create_expansion_success_alert(
            result["new_nodes_count"],
            result["new_relationships_count"],
            result["has_more"],
        )

        logger.info(
            "[GRAPH-DEBUG][context.expand] complete "
            f"node_id={node_id} direction={direction} new_nodes={result['new_nodes_count']} "
            f"new_relationships={result['new_relationships_count']} merged_total={len(merged_elements)}"
        )
        return (merged_elements, merged_elements, updated_expanded, updated_loaded_ids, updated_menu_style,
            success_msg, show_style, "preset")
            
    except requests.exceptions.Timeout:
        logger.error(
            "[GRAPH-DEBUG][context.expand] timeout "
            f"node_id={node_id} direction={direction} timeout_seconds={TIMEOUT_SECONDS}"
        )
        error_alert = create_expansion_error_alert("Expansion timed out", error_type="timeout")
        return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, updated_menu_style,
               error_alert, show_style, current_layout)
    
    except requests.exceptions.ConnectionError:
        logger.error(
            "[GRAPH-DEBUG][context.expand] connection_error "
            f"node_id={node_id} direction={direction} timeout_seconds={TIMEOUT_SECONDS}"
        )
        error_alert = create_expansion_error_alert(
            "Could not connect to server. Please check your connection.",
            error_type="connection"
        )
        return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, updated_menu_style,
               error_alert, show_style, current_layout)
    
    except Exception as e:
        logger.exception(f"[GRAPH-DEBUG][context.expand] unexpected_error {e}")
        error_alert = create_expansion_error_alert(f"Expansion error: {str(e)}")
        return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, updated_menu_style,
               error_alert, show_style, current_layout)


# Clientside callback to copy node ID to clipboard
clientside_callback(
    """
    function(n_clicks, rightclick_data) {
        if (n_clicks && rightclick_data && rightclick_data.node_id) {
            // Copy to clipboard
            if (navigator.clipboard) {
                navigator.clipboard.writeText(rightclick_data.node_id);
                console.log('Copied node ID:', rightclick_data.node_id);
            }
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("ctx-menu-copy-id", "title"),
    Input("ctx-menu-copy-id", "n_clicks"),
    State("rightclicked-node-store", "data"),
    prevent_initial_call=True
)


@callback(
    Output("context-menu", "style", allow_duplicate=True),
    Input("ctx-menu-copy-id", "n_clicks"),
    State("context-menu", "style"),
    prevent_initial_call=True
)
def hide_menu_after_copy(n_clicks, menu_style):
    """Hide menu after copying node ID"""
    if n_clicks:
        updated_style = menu_style.copy()
        updated_style["display"] = "none"
        return updated_style
    raise PreventUpdate


@callback(
    [Output("graph-cytoscape", "elements", allow_duplicate=True),
     Output("unfiltered-elements-store", "data", allow_duplicate=True),
     Output("context-menu", "style", allow_duplicate=True),
    Output("graph-status-strip", "children", allow_duplicate=True),
    Output("graph-status-strip", "style", allow_duplicate=True)],
    Input("ctx-menu-remove", "n_clicks"),
    [State("rightclicked-node-store", "data"),
     State("graph-cytoscape", "elements"),
     State("unfiltered-elements-store", "data"),
     State("context-menu", "style")],
    prevent_initial_call=True
)
def context_menu_remove_node(n_clicks, rightclick_data, current_elements, current_unfiltered, menu_style):
    """Remove node from view"""
    show_style = {"display": "block"}
    
    # Hide menu
    updated_menu_style = menu_style.copy()
    updated_menu_style["display"] = "none"
    
    if not n_clicks or not rightclick_data:
        raise PreventUpdate
    
    node_id = rightclick_data.get("node_id")
    if not node_id:
        return current_elements, current_unfiltered, updated_menu_style, None, {"display": "none"}
    
    # Remove node and its edges from elements
    filtered_elements = []
    removed_count = 0
    
    for elem in current_elements:
        elem_id = elem['data'].get('id')
        
        # Skip the node itself
        if elem_id == node_id:
            removed_count += 1
            continue
        
        # Skip edges connected to this node
        if is_edge_element(elem):
            if elem['data']['source'] == node_id or elem['data']['target'] == node_id:
                removed_count += 1
                continue
        
        filtered_elements.append(elem)
    
    # Success message
    logger.info(
        "[GRAPH-DEBUG][context.remove] removed "
        f"node_id={node_id} removed_count={removed_count} "
        f"remaining_elements={len(filtered_elements)}"
    )
    success_msg = create_alert([
        html.I(className="fas fa-trash-alt me-2"),
        f"Removed node and {removed_count - 1} connected relationships from view"
    ], color="warning", class_name="mb-0", duration=3000)
    
    return filtered_elements, filtered_elements, updated_menu_style, success_msg, show_style


@callback(
    [Output("graph-cytoscape", "elements", allow_duplicate=True),
     Output("unfiltered-elements-store", "data", allow_duplicate=True),
     Output("loaded-node-ids", "data", allow_duplicate=True),
     Output("expanded-nodes", "data", allow_duplicate=True),
     Output("context-menu", "style", allow_duplicate=True),
     Output("graph-status-strip", "children", allow_duplicate=True),
     Output("graph-status-strip", "style", allow_duplicate=True)],
    Input("ctx-menu-keep-neighbours", "n_clicks"),
    [State("rightclicked-node-store", "data"),
     State("graph-cytoscape", "elements"),
     State("unfiltered-elements-store", "data"),
     State("loaded-node-ids", "data"),
     State("expanded-nodes", "data"),
     State("context-menu", "style")],
    prevent_initial_call=True
)
def context_menu_keep_neighbours(n_clicks, rightclick_data, current_elements,
                                  current_unfiltered, loaded_node_ids, expanded_nodes, menu_style):
    """Keep only the focal node and its immediate (1-hop) spoke edges.

    Nodes that are not the focal node or a direct neighbour are removed from
    both the visible graph and the unfiltered backup store.  They are also
    removed from ``loaded-node-ids`` so that expanding a spoke node later will
    re-fetch them from the backend as if they had never been loaded.

    Only edges directly connecting to the focal node are retained (spokes).
    Edges between neighbours are dropped together with any non-neighbour nodes.
    """
    show_style = {"display": "block"}
    hide_style = {"display": "none"}

    updated_menu_style = menu_style.copy()
    updated_menu_style["display"] = "none"

    if not n_clicks or not rightclick_data:
        raise PreventUpdate

    node_id = rightclick_data.get("node_id")
    if not node_id:
        return (current_elements, current_unfiltered, loaded_node_ids,
                expanded_nodes, updated_menu_style, None, hide_style)

    elements = current_elements or []

    # Collect IDs of direct neighbours via spoke edges (both directions).
    neighbour_ids: set[str] = set()
    for elem in elements:
        if not is_edge_element(elem):
            continue
        src = elem["data"].get("source", "")
        tgt = elem["data"].get("target", "")
        if src == node_id:
            neighbour_ids.add(tgt)
        elif tgt == node_id:
            neighbour_ids.add(src)

    keep_node_ids = neighbour_ids | {node_id}

    # Keep: focal node, direct neighbours, and edges that touch the focal node.
    retained = []
    removed_node_count = 0
    for elem in elements:
        if is_edge_element(elem):
            src = elem["data"].get("source", "")
            tgt = elem["data"].get("target", "")
            if src == node_id or tgt == node_id:
                retained.append(elem)
            # Drop edges between neighbours and edges to removed nodes silently.
        else:
            elem_id = elem["data"].get("id", "")
            if elem_id in keep_node_ids:
                retained.append(elem)
            else:
                removed_node_count += 1

    # Remove pruned nodes from loaded-node-ids so expansion can re-fetch them.
    pruned_ids = {
        elem["data"].get("id", "")
        for elem in elements
        if not is_edge_element(elem)
        and elem["data"].get("id", "") not in keep_node_ids
    }
    updated_loaded_ids = [nid for nid in (loaded_node_ids or []) if nid not in pruned_ids]

    # Remove pruned nodes from expanded-nodes so re-expansion works correctly.
    updated_expanded = {
        nid: state for nid, state in (expanded_nodes or {}).items()
        if nid not in pruned_ids
    }

    logger.info(
        "[GRAPH-DEBUG][context.keep_neighbours] "
        f"node_id={node_id} neighbours={len(neighbour_ids)} "
        f"removed_nodes={removed_node_count} retained_elements={len(retained)} "
        f"loaded_ids_before={len(loaded_node_ids or [])} loaded_ids_after={len(updated_loaded_ids)}"
    )

    success_msg = create_alert([
        html.I(className="fas fa-compress-arrows-alt me-2"),
        f"Kept {len(neighbour_ids)} neighbour(s) — removed {removed_node_count} distant node(s)"
    ], color="info", class_name="mb-0", duration=4000)

    return (retained, retained, updated_loaded_ids,
            updated_expanded, updated_menu_style, success_msg, show_style)


# Clientside callback to hide context menu on outside click
clientside_callback(
    """
    function(n_intervals) {
        // Add click listener to document to hide menu on outside click
        if (!window._contextMenuClickListenerAdded) {
            document.addEventListener('click', function(e) {
                const menu = document.getElementById('context-menu');
                if (menu && menu.style.display === 'block') {
                    // Check if click is outside the menu
                    if (!menu.contains(e.target)) {
                        // Use set_props to null the store instead of directly
                        // manipulating the DOM.  Direct DOM manipulation bypasses
                        // React's virtual DOM, so React never updates display back
                        // to 'block' on the next right-click (it sees no change).
                        // Routing through set_props keeps Dash and the DOM in sync.
                        if (window.dash_clientside && window.dash_clientside.set_props) {
                            window.dash_clientside.set_props('rightclicked-node-store', { data: null });
                        } else {
                            menu.style.display = 'none';  // fallback only
                        }
                    }
                }
            });
            
            // Add hover effects to menu items
            const menuItems = document.querySelectorAll('.context-menu-item');
            menuItems.forEach(item => {
                item.addEventListener('mouseenter', function() {
                    this.style.backgroundColor = getComputedStyle(this)
                        .getPropertyValue('--color-surface-active')
                        .trim();
                });
                item.addEventListener('mouseleave', function() {
                    this.style.backgroundColor = 'transparent';
                });
            });
            
            window._contextMenuClickListenerAdded = true;
            console.log('[Phase 1.1d] Context menu click and hover listeners attached');
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("context-menu", "className"),
    Input("graph-cytoscape", "elements"),
    prevent_initial_call=False
)

"""Context Menu Callbacks

Callbacks for right-click context menu functionality.
"""

from datetime import datetime
import requests
import dash_bootstrap_components as dbc
from dash import html, Input, Output, State, callback, clientside_callback, callback_context
from dash.exceptions import PreventUpdate

from app.settings import settings
from ..utils import neo4j_to_cytoscape

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT


@callback(
    Output("context-menu", "style"),
    Input("rightclicked-node-store", "data"),
    State("context-menu", "style"),
    prevent_initial_call=True
)
def show_context_menu(rightclick_data, current_menu_style):
    """Show context menu at mouse position when node is right-clicked"""
    if not rightclick_data or not isinstance(rightclick_data, dict):
        return current_menu_style
    
    x = rightclick_data.get("x", 0)
    y = rightclick_data.get("y", 0)
    
    # Update menu style to show it at the click position
    menu_style = current_menu_style.copy()
    menu_style["display"] = "block"
    menu_style["left"] = f"{x}px"
    menu_style["top"] = f"{y}px"
    
    return menu_style


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
     Output("expanded-nodes", "data", allow_duplicate=True),
     Output("loaded-node-ids", "data", allow_duplicate=True),
     Output("context-menu", "style", allow_duplicate=True),
     Output("graph-table-container", "children", allow_duplicate=True),
     Output("graph-table-container", "style", allow_duplicate=True),
     Output("graph-layout-selector", "value", allow_duplicate=True)],
    [Input("ctx-menu-expand-incoming", "n_clicks"),
     Input("ctx-menu-expand-outgoing", "n_clicks")],
    [State("rightclicked-node-store", "data"),
     State("graph-cytoscape", "elements"),
     State("loaded-node-ids", "data"),
     State("expanded-nodes", "data"),
     State("context-menu", "style"),
     State("graph-layout-selector", "value")],
    prevent_initial_call=True
)
def context_menu_quick_expand(n_clicks_incoming, n_clicks_outgoing, rightclick_data,
                              current_elements, loaded_node_ids, expanded_nodes, 
                              menu_style, current_layout):
    """Handle quick expansion from context menu"""
    show_style = {"display": "block"}
    hide_style = {"display": "none"}
    
    # Hide menu
    updated_menu_style = menu_style.copy()
    updated_menu_style["display"] = "none"
    
    if not rightclick_data:
        return (current_elements, expanded_nodes, loaded_node_ids, updated_menu_style,
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
        return (current_elements, expanded_nodes, loaded_node_ids, updated_menu_style,
                None, hide_style, current_layout)
    
    try:
        # Use default limit for quick expansion
        limit = settings.GRAPH_UI_MAX_NODES_TO_EXPAND
        
        # Prepare request payload
        exclude_ids = loaded_node_ids if loaded_node_ids else []
        payload = {
            "node_id": node_id,
            "direction": direction,
            "limit": limit,
            "offset": 0,
            "exclude_node_ids": exclude_ids,
            "relationship_types": None
        }
        
        # Call backend API
        api_url = "http://localhost:8000/api/v1/graph/expand"
        response = requests.post(api_url, json=payload, timeout=TIMEOUT_SECONDS)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract new nodes and relationships
            new_nodes = data.get("nodes", [])
            new_relationships = data.get("relationships", [])
            pagination = data.get("pagination", {})
            
            # Transform to Cytoscape format
            new_elements = neo4j_to_cytoscape({"nodes": new_nodes, "relationships": new_relationships})
            
            # Merge with existing elements (deduplicate by ID)
            existing_ids = {elem['data']['id'] for elem in current_elements}
            merged_elements = current_elements.copy()
            
            new_count = 0
            for elem in new_elements:
                elem_id = elem['data']['id']
                if elem_id not in existing_ids:
                    merged_elements.append(elem)
                    existing_ids.add(elem_id)
                    new_count += 1
            
            # Update loaded node IDs
            new_node_ids = [node['id'] for node in new_nodes]
            updated_loaded_ids = list(set(loaded_node_ids + new_node_ids)) if loaded_node_ids else new_node_ids
            
            # Update expanded nodes tracking
            updated_expanded = expanded_nodes.copy() if expanded_nodes else {}
            updated_expanded[node_id] = {
                "direction": direction,
                "count": len(new_nodes),
                "timestamp": datetime.now().isoformat()
            }
            
            # Edge case: No new neighbors found
            if len(new_nodes) == 0:
                direction_label = "Incoming" if direction == "incoming" else "Outgoing"
                info_msg = dbc.Alert([
                    html.I(className="fas fa-info-circle me-2"),
                    f"No new {direction_label.lower()} neighbors found."
                ], color="info", className="mb-0", dismissable=True, duration=4000)
                return (merged_elements, updated_expanded, updated_loaded_ids, updated_menu_style,
                       info_msg, show_style, current_layout)
            
            # Success message
            direction_label = "Incoming" if direction == "incoming" else "Outgoing"
            has_more = pagination.get("has_more", False)
            more_msg = " (More available)" if has_more else ""
            success_msg = dbc.Alert([
                html.I(className="fas fa-context-menu me-2"),
                f"{direction_label} expansion: Loaded {len(new_nodes)} new nodes, {len(new_relationships)} new relationships{more_msg}"
            ], color="success", className="mb-0", dismissable=True)
            
            # Return updated data
            return (merged_elements, updated_expanded, updated_loaded_ids, updated_menu_style,
                   success_msg, show_style, current_layout)
            
        else:
            # Handle error response
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("detail", {}).get("message", "Unknown error")
            
            error_alert = dbc.Alert([
                html.I(className="fas fa-exclamation-circle me-2"),
                f"Quick expansion failed: {error_msg}"
            ], color="danger", className="mb-0", dismissable=True)
            return (current_elements, expanded_nodes, loaded_node_ids, updated_menu_style,
                   error_alert, show_style, current_layout)
            
    except requests.exceptions.Timeout:
        error_alert = dbc.Alert([
            html.I(className="fas fa-clock me-2"),
            "Quick expansion timed out"
        ], color="warning", className="mb-0", dismissable=True)
        return (current_elements, expanded_nodes, loaded_node_ids, updated_menu_style,
               error_alert, show_style, current_layout)
    
    except requests.exceptions.ConnectionError:
        error_alert = dbc.Alert([
            html.I(className="fas fa-plug me-2"),
            "Could not connect to server. Please check your connection."
        ], color="danger", className="mb-0", dismissable=True)
        return (current_elements, expanded_nodes, loaded_node_ids, updated_menu_style,
               error_alert, show_style, current_layout)
    
    except Exception as e:
        error_alert = dbc.Alert([
            html.I(className="fas fa-exclamation-triangle me-2"),
            f"Quick expansion error: {str(e)}"
        ], color="danger", className="mb-0", dismissable=True)
        return (current_elements, expanded_nodes, loaded_node_ids, updated_menu_style,
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
     Output("context-menu", "style", allow_duplicate=True),
     Output("graph-table-container", "children", allow_duplicate=True),
     Output("graph-table-container", "style", allow_duplicate=True)],
    Input("ctx-menu-remove", "n_clicks"),
    [State("rightclicked-node-store", "data"),
     State("graph-cytoscape", "elements"),
     State("context-menu", "style")],
    prevent_initial_call=True
)
def context_menu_remove_node(n_clicks, rightclick_data, current_elements, menu_style):
    """Remove node from view"""
    show_style = {"display": "block"}
    
    # Hide menu
    updated_menu_style = menu_style.copy()
    updated_menu_style["display"] = "none"
    
    if not n_clicks or not rightclick_data:
        raise PreventUpdate
    
    node_id = rightclick_data.get("node_id")
    if not node_id:
        return current_elements, updated_menu_style, None, {"display": "none"}
    
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
        if 'source' in elem['data'] and 'target' in elem['data']:
            if elem['data']['source'] == node_id or elem['data']['target'] == node_id:
                removed_count += 1
                continue
        
        filtered_elements.append(elem)
    
    # Success message
    success_msg = dbc.Alert([
        html.I(className="fas fa-trash-alt me-2"),
        f"Removed node and {removed_count - 1} connected relationships from view"
    ], color="warning", className="mb-0", dismissable=True, duration=3000)
    
    return filtered_elements, updated_menu_style, success_msg, show_style


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
                        menu.style.display = 'none';
                    }
                }
            });
            
            // Add hover effects to menu items
            const menuItems = document.querySelectorAll('.context-menu-item');
            menuItems.forEach(item => {
                item.addEventListener('mouseenter', function() {
                    this.style.backgroundColor = '#f0f0f0';
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

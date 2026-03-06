"""Expansion Callbacks

Callbacks for node expansion (double-click and modal-based).
"""

from datetime import datetime
import requests
from dash import Input, Output, State, callback

from app.settings import settings
from ..utils import (
    neo4j_to_cytoscape,
    create_expansion_success_alert,
    create_no_neighbors_alert,
    create_expansion_error_alert
)

TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT


@callback(
    [Output("graph-cytoscape", "elements", allow_duplicate=True),
     Output("unfiltered-elements-store", "data", allow_duplicate=True),
     Output("expanded-nodes", "data", allow_duplicate=True),
     Output("loaded-node-ids", "data", allow_duplicate=True),
     Output("expansion-debounce-store", "data", allow_duplicate=True),
     Output("graph-table-container", "children", allow_duplicate=True),
     Output("graph-table-container", "style", allow_duplicate=True),
     Output("graph-layout-selector", "value", allow_duplicate=True)],
    Input("doubleclicked-node-store", "data"),
    [State("graph-cytoscape", "elements"),
     State("unfiltered-elements-store", "data"),
     State("loaded-node-ids", "data"),
     State("expanded-nodes", "data"),
     State("expansion-debounce-store", "data"),
     State("graph-layout-selector", "value")],
    prevent_initial_call=True
)
def execute_doubleclick_expansion(dblclick_data, current_elements, current_unfiltered,
                                  loaded_node_ids, expanded_nodes, debounce_store,
                                  current_layout):
    """Execute immediate expansion on double-click with default parameters"""
    show_style = {"display": "block"}
    hide_style = {"display": "none"}
    
    # Extract node_id from the store data
    if not dblclick_data or not isinstance(dblclick_data, dict):
        return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, debounce_store,
                None, hide_style, current_layout)
    
    node_id = dblclick_data.get("node_id")
    timestamp = dblclick_data.get("timestamp", 0)
    
    if not node_id:
        return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, debounce_store,
                None, hide_style, current_layout)
    
    # Debouncing: Check if this node was recently expanded (within 500ms)
    debounce_store = debounce_store or {}
    last_expansion_time = debounce_store.get(node_id, 0)
    time_since_last = timestamp - last_expansion_time
    
    DEBOUNCE_MS = 500  # 500ms debounce window
    if time_since_last < DEBOUNCE_MS:
        # Too soon, ignore this double-click
        return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, debounce_store,
                None, hide_style, current_layout)
    
    # Update debounce store
    updated_debounce = debounce_store.copy()
    updated_debounce[node_id] = timestamp
    
    try:
        # Use default parameters for double-click expansion
        direction = "both"
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
                info_msg = create_no_neighbors_alert()
                return (current_elements, current_unfiltered, updated_expanded, loaded_node_ids, updated_debounce,
                       info_msg, show_style, current_layout)
            
            # Success message
            has_more = pagination.get("has_more", False)
            success_msg = create_expansion_success_alert(len(new_nodes), len(new_relationships), has_more)
            
            # Return updated data
            return (merged_elements, merged_elements, updated_expanded, updated_loaded_ids, updated_debounce,
                    success_msg, show_style, current_layout)
            
        else:
            # Handle error response
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("detail", {}).get("message", "Unknown error")
            
            error_alert = create_expansion_error_alert(f"Expansion failed: {error_msg}")
            return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, updated_debounce,
                    error_alert, show_style, current_layout)
            
    except requests.exceptions.Timeout:
        error_alert = create_expansion_error_alert("Expansion timed out", error_type="timeout")
        return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, updated_debounce,
               error_alert, show_style, current_layout)
    
    except requests.exceptions.ConnectionError:
        error_alert = create_expansion_error_alert(
            "Could not connect to server. Please check your connection.",
            error_type="connection"
        )
        return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, updated_debounce,
               error_alert, show_style, current_layout)
        
    except Exception as e:
        error_alert = create_expansion_error_alert(f"Expansion error: {str(e)}")
        return (current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, updated_debounce,
               error_alert, show_style, current_layout)


@callback(
    [Output("expansion-modal", "is_open", allow_duplicate=True),
     Output("selected-node-for-expansion", "data")],
    Input("expand-node-btn", "n_clicks"),
    [State("graph-cytoscape", "selectedNodeData")],
    prevent_initial_call=True
)
def open_expansion_modal(n_clicks, selected_nodes):
    """Open the expansion modal and store the selected node ID"""
    if n_clicks and selected_nodes and len(selected_nodes) > 0:
        node_data = selected_nodes[0]
        node_id = node_data.get('id')
        return True, node_id
    return False, None


@callback(
    Output("expansion-modal", "is_open", allow_duplicate=True),
    Input("expansion-modal-cancel", "n_clicks"),
    prevent_initial_call=True
)
def close_expansion_modal(n_clicks):
    """Close the expansion modal"""
    if n_clicks:
        return False
    return True


@callback(
    [Output("graph-cytoscape", "elements", allow_duplicate=True),
    Output("unfiltered-elements-store", "data", allow_duplicate=True),
     Output("expanded-nodes", "data", allow_duplicate=True),
     Output("loaded-node-ids", "data", allow_duplicate=True),
     Output("expansion-modal", "is_open", allow_duplicate=True),
     Output("graph-table-container", "children", allow_duplicate=True),
     Output("graph-table-container", "style", allow_duplicate=True),
     Output("graph-layout-selector", "value", allow_duplicate=True),
     Output("graph-fit-trigger", "children", allow_duplicate=True)],
    Input("expansion-modal-expand", "n_clicks"),
    [State("selected-node-for-expansion", "data"),
     State("expansion-direction-selector", "value"),
     State("expansion-limit-input", "value"),
     State("expansion-auto-fit-checkbox", "value"),
     State("graph-cytoscape", "elements"),
    State("unfiltered-elements-store", "data"),
     State("loaded-node-ids", "data"),
     State("expanded-nodes", "data"),
     State("graph-layout-selector", "value"),
     State("graph-fit-trigger", "children")],
    prevent_initial_call=True
)
def execute_node_expansion(n_clicks, node_id, direction, limit, auto_fit, current_elements,
                     current_unfiltered, loaded_node_ids, expanded_nodes,
                     current_layout, current_fit_count):
    """Execute node expansion by calling backend API and merging results"""
    show_style = {"display": "block"}
    hide_style = {"display": "none"}
    fit_count = current_fit_count or 0
    
    if not n_clicks or not node_id:
        return current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, True, None, hide_style, current_layout, fit_count
    
    try:
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
                info_msg = create_no_neighbors_alert()
                # Close modal and return
                return current_elements, current_unfiltered, updated_expanded, loaded_node_ids, False, info_msg, show_style, current_layout, fit_count
            
            # Success message
            has_more = pagination.get("has_more", False)
            success_msg = create_expansion_success_alert(len(new_nodes), len(new_relationships), has_more)
            
            # Auto-fit if enabled
            if auto_fit:
                fit_count = fit_count + 1
            
            # Close modal and return updated data
            # Trigger layout re-run to accommodate new nodes
            return merged_elements, merged_elements, updated_expanded, updated_loaded_ids, False, success_msg, show_style, current_layout, fit_count
            
        else:
            # Handle error response
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("detail", {}).get("message", "Unknown error")
            
            error_alert = create_expansion_error_alert(f"Expansion failed: {error_msg}")
            return current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, True, error_alert, show_style, current_layout, fit_count
            
    except requests.exceptions.Timeout:
        error_alert = create_expansion_error_alert(
            "Request timed out. The expansion took too long.",
            error_type="timeout"
        )
        return current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, True, error_alert, show_style, current_layout, fit_count
    
    except requests.exceptions.ConnectionError:
        error_alert = create_expansion_error_alert(
            "Could not connect to server. Please check your connection.",
            error_type="connection"
        )
        return current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, True, error_alert, show_style, current_layout, fit_count
        
    except Exception as e:
        error_alert = create_expansion_error_alert(f"Error: {str(e)}")
        return current_elements, current_unfiltered, expanded_nodes, loaded_node_ids, True, error_alert, show_style, current_layout, fit_count

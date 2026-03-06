"""Filtering Callbacks (Phase 1.2.4)

Callbacks for relationship filtering UI controls.
"""

from dash import Input, Output, State, callback
from dash.exceptions import PreventUpdate


@callback(
    [Output("filter-panel-collapse", "is_open"),
     Output("filter-collapse-icon", "className")],
    Input("toggle-filter-collapse-btn", "n_clicks"),
    State("filter-panel-collapse", "is_open"),
    prevent_initial_call=True
)
def toggle_filter_panel(n_clicks, is_open):
    """Toggle filter panel collapse and update chevron icon"""
    if n_clicks:
        new_state = not is_open
        # Chevron right when collapsed, chevron down when open
        icon_class = "fas fa-chevron-down me-2" if new_state else "fas fa-chevron-right me-2"
        return new_state, icon_class
    raise PreventUpdate


@callback(
    [Output("relationship-type-filter", "options"),
     Output("relationship-type-filter", "value")],
    Input("unfiltered-elements-store", "data"),
    State("relationship-type-filter", "value"),
    prevent_initial_call=True
)
def update_relationship_type_filter(unfiltered_elements, current_values):
    """Dynamically populate relationship type checkboxes from unfiltered graph"""
    if not unfiltered_elements:
        return [], []
    
    # Extract unique relationship types from edges (using unfiltered data)
    rel_types = {}
    for elem in unfiltered_elements:
        data = elem.get("data", {})
        # Check if it's an edge (has source/target)
        if "source" in data and "target" in data:
            rel_type = data.get("relType", data.get("label", "Unknown"))
            if rel_type not in rel_types:
                rel_types[rel_type] = 0
            rel_types[rel_type] += 1
    
    # Create checkbox options with counts
    options = [
        {"label": f"{rel_type} ({count})", "value": rel_type}
        for rel_type, count in sorted(rel_types.items())
    ]
    
    # If this is the first load (no current values), select all
    # Otherwise, preserve the current selection
    if current_values is None or len(current_values) == 0:
        values = list(rel_types.keys())
    else:
        # Preserve existing selections, but only for types that still exist
        values = [v for v in current_values if v in rel_types]
    
    return options, values


@callback(
    [Output("node-type-filter", "options"),
     Output("node-type-filter", "value")],
    Input("unfiltered-elements-store", "data"),
    State("node-type-filter", "value"),
    prevent_initial_call=True
)
def update_node_type_filter(unfiltered_elements, current_values):
    """Dynamically populate node type checkboxes from unfiltered graph"""
    if not unfiltered_elements:
        return [], []
    
    # Extract unique node types from nodes (using unfiltered data)
    node_types = {}
    for elem in unfiltered_elements:
        data = elem.get("data", {})
        # Check if it's a node (no source/target)
        if "source" not in data and "target" not in data:
            node_type = data.get("nodeType", "Unknown")
            if node_type not in node_types:
                node_types[node_type] = 0
            node_types[node_type] += 1
    
    # Create checkbox options with counts
    options = [
        {"label": f"{node_type} ({count})", "value": node_type}
        for node_type, count in sorted(node_types.items())
    ]
    
    # If this is the first load (no current values), select all
    # Otherwise, preserve the current selection
    if current_values is None or len(current_values) == 0:
        values = list(node_types.keys())
    else:
        # Preserve existing selections, but only for types that still exist
        values = [v for v in current_values if v in node_types]
    
    return options, values


@callback(
    Output("weight-threshold-label", "children"),
    Input("weight-threshold-slider", "value")
)
def update_weight_threshold_label(threshold):
    """Update weight threshold label text"""
    return f"Show edges with weight ≥ {threshold}"


@callback(
    [Output("node-type-filter", "value", allow_duplicate=True),
     Output("relationship-type-filter", "value", allow_duplicate=True),
     Output("weight-threshold-slider", "value"),
     Output("top-n-toggle", "value")],
    Input("clear-filters-btn", "n_clicks"),
    [State("node-type-filter", "options"),
     State("relationship-type-filter", "options")],
    prevent_initial_call=True
)
def clear_all_filters(n_clicks, node_type_options, rel_type_options):
    """Reset all filters to default values"""
    if not n_clicks:
        raise PreventUpdate
    
    # Select all node types
    all_node_types = [opt["value"] for opt in node_type_options] if node_type_options else []
    
    # Select all relationship types
    all_rel_types = [opt["value"] for opt in rel_type_options] if rel_type_options else []
    
    return all_node_types, all_rel_types, 0, "all"


@callback(
    Output("graph-cytoscape", "elements", allow_duplicate=True),
    [Input("node-type-filter", "value"),
     Input("relationship-type-filter", "value"),
     Input("weight-threshold-slider", "value"),
     Input("top-n-toggle", "value")],
    State("unfiltered-elements-store", "data"),
    prevent_initial_call=True
)
def apply_relationship_filters(selected_node_types, selected_rel_types, weight_threshold, top_n_mode, unfiltered_elements):
    """Apply all filters (node types, relationship types, weight, top-N) to graph elements"""
    if not unfiltered_elements:
        raise PreventUpdate
    
    # Start with all elements
    filtered_elements = []
    
    # Separate nodes and edges
    nodes = []
    edges = []
    
    for elem in unfiltered_elements:
        data = elem.get("data", {})
        if "source" in data and "target" in data:
            edges.append(elem)
        else:
            nodes.append(elem)
    
    # Filter nodes by type
    if selected_node_types:
        filtered_nodes = [
            node for node in nodes
            if node.get("data", {}).get("nodeType", "Unknown") in selected_node_types
        ]
    else:
        filtered_nodes = []
    
    # Create set of visible node IDs for edge filtering
    visible_node_ids = {node.get("data", {}).get("id") for node in filtered_nodes}
    
    # Filter edges by relationship type
    if selected_rel_types:
        filtered_edges = [
            edge for edge in edges
            if edge.get("data", {}).get("relType", edge.get("data", {}).get("label", "Unknown")) in selected_rel_types
        ]
    else:
        filtered_edges = []
    
    # Filter edges to only show ones where both endpoints are visible
    filtered_edges = [
        edge for edge in filtered_edges
        if edge.get("data", {}).get("source") in visible_node_ids
        and edge.get("data", {}).get("target") in visible_node_ids
    ]
    
    # Filter by weight threshold
    if weight_threshold > 0:
        filtered_edges = [
            edge for edge in filtered_edges
            if edge.get("data", {}).get("weight", 0) >= weight_threshold
        ]
    
    # Apply Top-N limit
    if top_n_mode == "top50":
        # Sort by weight descending, take top 50
        filtered_edges = sorted(
            filtered_edges,
            key=lambda e: e.get("data", {}).get("weight", 0),
            reverse=True
        )[:50]
    elif top_n_mode == "top100":
        # Sort by weight descending, take top 100
        filtered_edges = sorted(
            filtered_edges,
            key=lambda e: e.get("data", {}).get("weight", 0),
            reverse=True
        )[:100]
    
    # Combine filtered nodes and filtered edges
    filtered_elements = filtered_nodes + filtered_edges
    
    return filtered_elements

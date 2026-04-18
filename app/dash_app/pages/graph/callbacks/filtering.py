"""Filtering Callbacks (Phase 1.2.4)

Callbacks for relationship filtering UI controls.
"""

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html
from dash.exceptions import PreventUpdate
from app.common.logger import logger
from ..utils import is_edge_data, is_node_data


def _split_elements(elements):
    """Return node and edge lists from a Cytoscape element collection."""
    nodes = []
    edges = []

    for elem in elements or []:
        data = elem.get("data", {})
        if is_edge_data(data):
            edges.append(elem)
        else:
            nodes.append(elem)

    return nodes, edges


def _has_weighted_edges(elements):
    """Return True when the current graph contains edge weights."""
    for elem in elements or []:
        data = elem.get("data", {})
        if is_edge_data(data) and data.get("weight") is not None:
            return True
    return False


def _format_counts_summary(filtered_elements, unfiltered_elements):
    """Build a compact before/after summary for the current filter state."""
    if not unfiltered_elements:
        return "Load a graph to refine it locally."

    filtered_nodes, filtered_edges = _split_elements(filtered_elements)
    all_nodes, all_edges = _split_elements(unfiltered_elements)

    return (
        f"Showing {len(filtered_nodes)} nodes / {len(filtered_edges)} edges "
        f"from {len(all_nodes)} nodes / {len(all_edges)} edges"
    )


def _summarize_selection(selected_values, option_values, label):
    """Return a compact chip label for a checklist selection, or None if unfiltered."""
    available = option_values or []
    selected = selected_values or []

    if not available or set(selected) == set(available):
        return None

    if not selected:
        return f"{label}: none"

    if len(selected) <= 2:
        return f"{label}: {', '.join(sorted(selected))}"

    return f"{label}: {len(selected)}/{len(available)}"


def _build_active_filter_chips(
    selected_node_types,
    selected_rel_types,
    weight_threshold,
    top_n_mode,
    node_type_options,
    rel_type_options,
    has_weighted_edges,
):
    """Return badge components for the currently active filters."""
    node_option_values = [opt["value"] for opt in (node_type_options or [])]
    rel_option_values = [opt["value"] for opt in (rel_type_options or [])]

    labels = [
        _summarize_selection(selected_node_types, node_option_values, "Node types"),
        _summarize_selection(selected_rel_types, rel_option_values, "Relationship types"),
    ]

    if has_weighted_edges and weight_threshold > 0:
        labels.append(f"Weight ≥ {weight_threshold}")

    if has_weighted_edges and top_n_mode == "top50":
        labels.append("Top 50 edges")
    elif has_weighted_edges and top_n_mode == "top100":
        labels.append("Top 100 edges")

    labels = [label for label in labels if label]

    if not labels:
        return [html.Span("No active filters", className="graph-filter-empty-state")]

    return [
        dbc.Badge(
            label,
            color="light",
            className="graph-filter-chip me-1 mb-1",
        )
        for label in labels
    ]


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
     Output("relationship-type-filter", "value"),
     Output("relationship-type-available-store", "data")],
    Input("unfiltered-elements-store", "data"),
    [State("relationship-type-filter", "value"),
     State("relationship-type-available-store", "data")],
    prevent_initial_call=True
)
def update_relationship_type_filter(unfiltered_elements, current_values, previous_available):
    """Dynamically populate relationship type checkboxes from unfiltered graph"""
    if not unfiltered_elements:
        return [], [], []
    
    # Extract unique relationship types from edges (using unfiltered data)
    rel_types = {}
    for elem in unfiltered_elements:
        data = elem.get("data", {})
        if is_edge_data(data):
            rel_type = data.get("relType", data.get("label", "Unknown"))
            if rel_type not in rel_types:
                rel_types[rel_type] = 0
            rel_types[rel_type] += 1
    
    # Create checkbox options with counts
    options = [
        {"label": f"{rel_type} ({count})", "value": rel_type}
        for rel_type, count in sorted(rel_types.items())
    ]

    available_values = [opt["value"] for opt in options]
    available_set = set(available_values)
    previous_available_set = set(previous_available or [])
    current_set = set(current_values or [])
    
    # Differentiate between first load (None) and user intentionally unchecking all ([])
    if previous_available is None:
        # True first load
        values = available_values
    elif previous_available_set == current_set:
        # User had EVERYTHING selected previously ("Show All" intent). 
        # Keep "Show All" behavior for newly discovered types too.
        values = available_values
    else:
        # User had a specific subset selected (including empty subset). Preserve it.
        values = [v for v in current_values if v in available_set]

    logger.info(
        "[GRAPH-DEBUG][filter.rel_types] refresh "
        f"available={sorted(rel_types.keys())} current={current_values} selected={values}"
    )

    return options, values, available_values


@callback(
    [Output("node-type-filter", "options"),
     Output("node-type-filter", "value"),
     Output("node-type-available-store", "data")],
    Input("unfiltered-elements-store", "data"),
    [State("node-type-filter", "value"),
     State("node-type-available-store", "data")],
    prevent_initial_call=True
)
def update_node_type_filter(unfiltered_elements, current_values, previous_available):
    """Dynamically populate node type checkboxes from unfiltered graph"""
    if not unfiltered_elements:
        return [], [], []
    
    # Extract unique node types from nodes (using unfiltered data)
    node_types = {}
    for elem in unfiltered_elements:
        data = elem.get("data", {})
        if is_node_data(data):
            node_type = data.get("nodeType", "Unknown")
            if node_type not in node_types:
                node_types[node_type] = 0
            node_types[node_type] += 1
    
    # Create checkbox options with counts
    options = [
        {"label": f"{node_type} ({count})", "value": node_type}
        for node_type, count in sorted(node_types.items())
    ]

    available_values = [opt["value"] for opt in options]
    available_set = set(available_values)
    previous_available_set = set(previous_available or [])
    current_set = set(current_values or [])
    
    if previous_available is None:
        # True first load
        values = available_values
    elif previous_available_set == current_set:
        # User had EVERYTHING selected previously ("Show All" intent).
        values = available_values
    else:
        # User had a specific subset selected. Preserve it.
        values = [v for v in current_values if v in available_set]

    hidden_types = [t for t in node_types if t not in values]
    logger.info(
        "[GRAPH-DEBUG][filter.node_types] refresh "
        f"available={sorted(node_types.keys())} previous_available={sorted(previous_available_set)} "
        f"current={current_values} selected={values} "
        f"hidden_types={sorted(hidden_types)}"
    )

    return options, values, available_values


@callback(
    Output("weight-threshold-label", "children"),
    Input("weight-threshold-slider", "value")
)
def update_weight_threshold_label(threshold):
    """Update weight threshold label text"""
    return f"Show edges with weight ≥ {threshold}"


@callback(
    [Output("filter-results-summary", "children"),
     Output("filter-active-chips", "children"),
     Output("weight-based-filter-group", "style"),
     Output("weight-filter-unavailable-note", "style")],
    [Input("graph-cytoscape", "elements"),
     Input("unfiltered-elements-store", "data"),
     Input("node-type-filter", "value"),
     Input("relationship-type-filter", "value"),
     Input("weight-threshold-slider", "value"),
     Input("top-n-toggle", "value"),
     Input("node-type-filter", "options"),
     Input("relationship-type-filter", "options")]
)
def update_filter_panel_feedback(
    current_elements,
    unfiltered_elements,
    selected_node_types,
    selected_rel_types,
    weight_threshold,
    top_n_mode,
    node_type_options,
    rel_type_options,
):
    """Update local-only filter feedback, chips, and weighted-control visibility."""
    has_weighted_edges = _has_weighted_edges(unfiltered_elements)
    summary = _format_counts_summary(current_elements or [], unfiltered_elements or [])
    chips = _build_active_filter_chips(
        selected_node_types,
        selected_rel_types,
        weight_threshold,
        top_n_mode,
        node_type_options,
        rel_type_options,
        has_weighted_edges,
    )

    weight_group_style = {} if has_weighted_edges else {"display": "none"}
    weight_note_style = {"display": "none"} if has_weighted_edges or not unfiltered_elements else {"display": "block"}

    return summary, chips, weight_group_style, weight_note_style


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
    
    # Separate nodes and edges
    nodes, edges = _split_elements(unfiltered_elements)
    has_weighted_edges = _has_weighted_edges(unfiltered_elements)

    logger.info(
        "[GRAPH-DEBUG][filter.apply] start "
        f"nodes={len(nodes)} edges={len(edges)} selected_node_types={selected_node_types} "
        f"selected_rel_types={selected_rel_types} weight_threshold={weight_threshold} "
        f"top_n_mode={top_n_mode} has_weighted_edges={has_weighted_edges}"
    )

    # Filter nodes by type
    if selected_node_types:
        filtered_nodes = [
            node for node in nodes
            if node.get("data", {}).get("nodeType", "Unknown") in selected_node_types
        ]
    else:
        filtered_nodes = []

    logger.info(
        "[GRAPH-DEBUG][filter.apply] nodes_after_type_filter "
        f"visible={len(filtered_nodes)} removed={len(nodes) - len(filtered_nodes)}"
    )

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

    logger.info(
        "[GRAPH-DEBUG][filter.apply] edges_after_rel_type_filter "
        f"visible={len(filtered_edges)} removed={len(edges) - len(filtered_edges)}"
    )

    # Filter edges to only show ones where both endpoints are visible
    filtered_edges = [
        edge for edge in filtered_edges
        if edge.get("data", {}).get("source") in visible_node_ids
        and edge.get("data", {}).get("target") in visible_node_ids
    ]

    logger.info(
        "[GRAPH-DEBUG][filter.apply] edges_after_visibility_filter "
        f"visible={len(filtered_edges)}"
    )

    # Filter by weight threshold
    if has_weighted_edges and weight_threshold > 0:
        before_weight = len(filtered_edges)
        filtered_edges = [
            edge for edge in filtered_edges
            if edge.get("data", {}).get("weight", 0) >= weight_threshold
        ]
        logger.info(
            "[GRAPH-DEBUG][filter.apply] edges_after_weight_filter "
            f"threshold={weight_threshold} visible={len(filtered_edges)} removed={before_weight - len(filtered_edges)}"
        )
    
    # Apply Top-N limit
    if has_weighted_edges and top_n_mode == "top50":
        # Sort by weight descending, take top 50
        before_topn = len(filtered_edges)
        filtered_edges = sorted(
            filtered_edges,
            key=lambda e: e.get("data", {}).get("weight", 0),
            reverse=True
        )[:50]
        logger.info(
            "[GRAPH-DEBUG][filter.apply] edges_after_topn "
            f"mode=top50 visible={len(filtered_edges)} removed={before_topn - len(filtered_edges)}"
        )
    elif has_weighted_edges and top_n_mode == "top100":
        # Sort by weight descending, take top 100
        before_topn = len(filtered_edges)
        filtered_edges = sorted(
            filtered_edges,
            key=lambda e: e.get("data", {}).get("weight", 0),
            reverse=True
        )[:100]
        logger.info(
            "[GRAPH-DEBUG][filter.apply] edges_after_topn "
            f"mode=top100 visible={len(filtered_edges)} removed={before_topn - len(filtered_edges)}"
        )
    
    # Combine filtered nodes and filtered edges
    filtered_elements = filtered_nodes + filtered_edges

    logger.info(
        "[GRAPH-DEBUG][filter.apply] final "
        f"elements={len(filtered_elements)} nodes={len(filtered_nodes)} edges={len(filtered_edges)}"
    )
    
    return filtered_elements

"""Filtering Callbacks (Phase 1.2.4)

Callbacks for local graph refinement UI controls.
"""

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html
from dash.exceptions import PreventUpdate
from common.logger import logger
from ..utils import is_edge_data, is_node_data
from ..utils.time_helpers import _format_day_label, _parse_days_since_epoch, compute_time_range


class FilteringDataValidationError(ValueError):
    """Raised when loaded graph elements violate callback assumptions."""


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


def _require_element_ids(elements):
    """Validate that all nodes and edges carry stable ids."""
    for elem in elements or []:
        data = elem.get("data", {})
        element_kind = "edge" if is_edge_data(data) else "node"
        element_id = data.get("id")
        if element_id is None:
            raise FilteringDataValidationError(
                f"Graph {element_kind} is missing required 'id' field for filtering/dimming"
            )


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


def _summarize_time_filter(range_value, full_range, label_prefix):
    """Return a chip label string for a time filter, or None if slider is at full range.

    Parameters
    ----------
    range_value : list[int, int] | None
        Current slider value (e.g. ``[150, 200]``).
    full_range : list[int, int] | None
        Full available range for this property.
    label_prefix : str
        Label prefix (e.g. ``"Created"``, ``"Updated"``, ``"Seen"``).

    Returns
    -------
    str | None
        ``"Created: Jan 15 – Mar 20, 2026"`` when narrowed, ``None`` otherwise.
    """
    if not range_value or not full_range:
        return None
    if range_value == full_range:
        return None
    lo = _format_day_label(range_value[0])
    hi = _format_day_label(range_value[1])
    return f"{label_prefix}: {lo} – {hi}"


def _build_active_filter_chips(
    selected_node_types,
    selected_rel_types,
    weight_threshold,
    top_n_mode,
    node_type_options,
    rel_type_options,
    has_weighted_edges,
    created_range=None,
    updated_range=None,
    seen_range=None,
    full_ranges=None,
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

    # Time filter chips
    fr = full_ranges or {}
    chip_created = _summarize_time_filter(created_range, fr.get("_created_at"), "Created")
    chip_updated = _summarize_time_filter(updated_range, fr.get("_last_updated_at"), "Updated")
    chip_seen = _summarize_time_filter(seen_range, fr.get("_last_seen_at"), "Seen")
    labels.extend(c for c in [chip_created, chip_updated, chip_seen] if c)

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


def _filter_nodes_by_time(nodes, created_range=None, updated_range=None, seen_range=None, full_ranges=None):
    """Filter a list of nodes by time-based filters.

    Returns the subset of nodes that pass all active time filters.
    When a slider is at its full range (or ranges are None), no filtering
    is applied for that property.
    """
    if not nodes:
        return nodes

    visible_nodes = list(nodes)

    time_configs = [
        ("_created_at", created_range, full_ranges),
        ("_last_updated_at", updated_range, full_ranges),
        ("_last_seen_at", seen_range, full_ranges),
    ]

    for prop, current_range, ranges in time_configs:
        if current_range is None or ranges is None:
            continue
        full = ranges.get(prop)
        if full is None or current_range == full:
            continue  # Slider at full range = no filter active

        filtered = []
        for node in visible_nodes:
            raw = node.get("data", {}).get(prop, "")
            if not raw:
                filtered.append(node)  # Missing property = include
                continue
            days = _parse_days_since_epoch(raw)
            if days is None:
                filtered.append(node)  # Unparseable = include
                continue
            if current_range[0] <= days <= current_range[1]:
                filtered.append(node)
        visible_nodes = filtered

    return visible_nodes


def _compute_filtered_graph(
    selected_node_types,
    selected_rel_types,
    weight_threshold,
    top_n_mode,
    unfiltered_elements,
    created_range=None,
    updated_range=None,
    seen_range=None,
    full_ranges=None,
):
    """Compute the visible graph subset from the loaded baseline.

    Parameters
    ----------
    created_range : list[int, int] | None
        ``[min_days, max_days]`` for ``_created_at``, or None.
    updated_range : list[int, int] | None
        ``[min_days, max_days]`` for ``_last_updated_at``, or None.
    seen_range : list[int, int] | None
        ``[min_days, max_days]`` for ``_last_seen_at``, or None.
    full_ranges : dict | None
        ``{"_created_at": [min, max], ...}`` — used to detect when a slider
        is at its full range (no active filter).
    """
    _require_element_ids(unfiltered_elements)
    nodes, edges = _split_elements(unfiltered_elements)
    has_weighted_edges = _has_weighted_edges(unfiltered_elements)

    # Filter nodes by type
    if selected_node_types:
        visible_nodes = [
            node for node in nodes
            if node.get("data", {}).get("nodeType", "Unknown") in selected_node_types
        ]
    else:
        visible_nodes = []

    # Apply time-based filters
    visible_nodes = _filter_nodes_by_time(
        visible_nodes,
        created_range=created_range,
        updated_range=updated_range,
        seen_range=seen_range,
        full_ranges=full_ranges,
    )

    # Create set of visible node IDs for edge filtering
    visible_node_ids = {node.get("data", {}).get("id") for node in visible_nodes}

    # Filter edges by relationship type
    if selected_rel_types:
        visible_edges = [
            edge for edge in edges
            if edge.get("data", {}).get("relType", edge.get("data", {}).get("label", "Unknown")) in selected_rel_types
        ]
    else:
        visible_edges = []

    # Filter edges to only show ones where both endpoints are visible
    visible_edges = [
        edge for edge in visible_edges
        if edge.get("data", {}).get("source") in visible_node_ids
        and edge.get("data", {}).get("target") in visible_node_ids
    ]

    # Filter by weight threshold
    if has_weighted_edges and weight_threshold > 0:
        visible_edges = [
            edge for edge in visible_edges
            if edge.get("data", {}).get("weight", 0) >= weight_threshold
        ]

    # Apply Top-N limit
    if has_weighted_edges and top_n_mode == "top50":
        visible_edges = sorted(
            visible_edges,
            key=lambda e: e.get("data", {}).get("weight", 0),
            reverse=True
        )[:50]
    elif has_weighted_edges and top_n_mode == "top100":
        visible_edges = sorted(
            visible_edges,
            key=lambda e: e.get("data", {}).get("weight", 0),
            reverse=True
        )[:100]

    return {
        "all_nodes": nodes,
        "all_edges": edges,
        "visible_nodes": visible_nodes,
        "visible_edges": visible_edges,
        "has_weighted_edges": has_weighted_edges,
    }


@callback(
    [Output("relationship-type-filter", "options"),
     Output("relationship-type-filter", "value"),
     Output("relationship-type-available-store", "data")],
    [Input("unfiltered-elements-store", "data"),
     Input("time-slider-created", "value"),
     Input("time-slider-updated", "value"),
     Input("time-slider-seen", "value")],
    [State("relationship-type-filter", "value"),
     State("relationship-type-available-store", "data"),
     State("time-filter-full-ranges", "data")],
    prevent_initial_call=True
)
def update_relationship_type_filter(unfiltered_elements, created_range, updated_range, seen_range,
                                    current_values, previous_available, full_ranges):
    """Dynamically populate relationship type checkboxes from the unfiltered graph.

    Called whenever the unfiltered baseline changes (new query or expansion)
    OR when time filter sliders move. Counts reflect only edges whose
    source/target nodes survive the active time filters.

    Uses a three-way intent model to decide which types to select:

    1. ``previous_available is None``  → true first load; select all.
    2. ``previous_available == current`` → user had "show all"; keep showing all
       (including any newly discovered types from expansion).
    3. Otherwise → user had a specific subset; preserve only their *explicit*
       deselections. Types that are brand-new (never seen before this call) are
       auto-selected because the user never chose to hide them.

    ``previous_available`` acts as a sentinel: ``None`` means the store has never
    been populated (first load), while ``[]`` means the user explicitly cleared
    all selections. This distinction prevents a fresh query from being treated
    as "show all" when the user had deliberately deselected everything.
    """
    if not unfiltered_elements:
        return [], [], []

    # Determine which nodes survive time filters
    all_nodes = [e for e in unfiltered_elements if is_node_data(e.get("data", {}))]
    time_filtered_nodes = _filter_nodes_by_time(
        all_nodes,
        created_range=created_range,
        updated_range=updated_range,
        seen_range=seen_range,
        full_ranges=full_ranges,
    )
    time_filtered_node_ids = {n.get("data", {}).get("id") for n in time_filtered_nodes}

    # Count relationship types from edges whose endpoints survive time filtering
    rel_types = {}
    for elem in unfiltered_elements:
        data = elem.get("data", {})
        if is_edge_data(data):
            source = data.get("source")
            target = data.get("target")
            # Only count edges where both endpoints are in the time-filtered set
            if source in time_filtered_node_ids and target in time_filtered_node_ids:
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
        # User had a specific subset. Preserve only *explicit* deselections.
        # Brand-new relationship types the user has never seen before are
        # auto-selected — the user never chose to hide them.
        newly_added = [v for v in available_values if v not in previous_available_set]
        values = [v for v in current_values if v in available_set] + newly_added

    logger.info(
        "[GRAPH-DEBUG][filter.rel_types] refresh "
        f"available={sorted(rel_types.keys())} current={current_values} selected={values}"
    )

    return options, values, available_values


@callback(
    [Output("node-type-filter", "options"),
     Output("node-type-filter", "value"),
     Output("node-type-available-store", "data")],
    [Input("unfiltered-elements-store", "data"),
     Input("time-slider-created", "value"),
     Input("time-slider-updated", "value"),
     Input("time-slider-seen", "value")],
    [State("node-type-filter", "value"),
     State("node-type-available-store", "data"),
     State("time-filter-full-ranges", "data")],
    prevent_initial_call=True
)
def update_node_type_filter(unfiltered_elements, created_range, updated_range, seen_range,
                            current_values, previous_available, full_ranges):
    """Dynamically populate node type checkboxes from the unfiltered graph.

    Called whenever the unfiltered baseline changes (new query or expansion)
    OR when time filter sliders move. Counts reflect only nodes that survive
    the active time filters.

    Uses a three-way intent model to decide which types to select:

    1. ``previous_available is None``  → true first load; select all.
    2. ``previous_available == current`` → user had "show all"; keep showing all
       (including any newly discovered types from expansion).
    3. Otherwise → user had a specific subset; preserve only their *explicit*
       deselections. Types that are brand-new (never seen before this call) are
       auto-selected because the user never chose to hide them.

    ``previous_available`` acts as a sentinel: ``None`` means the store has never
    been populated (first load), while ``[]`` means the user explicitly cleared
    all selections. This distinction prevents a fresh query from being treated
    as "show all" when the user had deliberately deselected everything.
    """
    if not unfiltered_elements:
        return [], [], []

    # Determine which nodes survive time filters
    all_nodes = [e for e in unfiltered_elements if is_node_data(e.get("data", {}))]
    time_filtered_nodes = _filter_nodes_by_time(
        all_nodes,
        created_range=created_range,
        updated_range=updated_range,
        seen_range=seen_range,
        full_ranges=full_ranges,
    )

    # Count node types from the time-filtered subset
    node_types = {}
    for node in time_filtered_nodes:
        data = node.get("data", {})
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
        # User had a specific subset. Preserve only *explicit* deselections.
        # Brand-new node types the user has never seen before are auto-selected
        # — the user never chose to hide them.
        newly_added = [v for v in available_values if v not in previous_available_set]
        values = [v for v in current_values if v in available_set] + newly_added

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
    [Input("unfiltered-elements-store", "data"),
     Input("node-type-filter", "value"),
     Input("relationship-type-filter", "value"),
     Input("weight-threshold-slider", "value"),
     Input("top-n-toggle", "value"),
     Input("node-type-filter", "options"),
     Input("relationship-type-filter", "options"),
     Input("time-slider-created", "value"),
     Input("time-slider-updated", "value"),
     Input("time-slider-seen", "value"),
     Input("time-filter-full-ranges", "data")]
)
def update_filter_panel_feedback(
    unfiltered_elements,
    selected_node_types,
    selected_rel_types,
    weight_threshold,
    top_n_mode,
    node_type_options,
    rel_type_options,
    created_range,
    updated_range,
    seen_range,
    full_ranges,
):
    """Update local-only filter feedback, chips, and weighted-control visibility."""
    filtered_graph = _compute_filtered_graph(
        selected_node_types,
        selected_rel_types,
        weight_threshold,
        top_n_mode,
        unfiltered_elements or [],
        created_range=created_range,
        updated_range=updated_range,
        seen_range=seen_range,
        full_ranges=full_ranges,
    )
    logical_filtered_elements = filtered_graph["visible_nodes"] + filtered_graph["visible_edges"]
    has_weighted_edges = filtered_graph["has_weighted_edges"]
    summary = _format_counts_summary(logical_filtered_elements, unfiltered_elements or [])
    chips = _build_active_filter_chips(
        selected_node_types,
        selected_rel_types,
        weight_threshold,
        top_n_mode,
        node_type_options,
        rel_type_options,
        has_weighted_edges,
        created_range=created_range,
        updated_range=updated_range,
        seen_range=seen_range,
        full_ranges=full_ranges,
    )

    weight_group_style = {} if has_weighted_edges else {"display": "none"}
    weight_note_style = {"display": "none"} if has_weighted_edges or not unfiltered_elements else {"display": "block"}

    return (
        summary,
        chips,
        weight_group_style,
        weight_note_style,
    )


@callback(
    [Output("node-type-filter", "value", allow_duplicate=True),
     Output("relationship-type-filter", "value", allow_duplicate=True),
     Output("weight-threshold-slider", "value"),
     Output("top-n-toggle", "value"),
     Output("time-slider-created", "value", allow_duplicate=True),
     Output("time-slider-updated", "value", allow_duplicate=True),
     Output("time-slider-seen", "value", allow_duplicate=True)],
    Input("clear-filters-btn", "n_clicks"),
    [State("node-type-filter", "options"),
     State("relationship-type-filter", "options"),
     State("time-filter-full-ranges", "data")],
    prevent_initial_call=True
)
def clear_all_filters(n_clicks, node_type_options, rel_type_options, full_ranges):
    """Reset all filters to default values"""
    if not n_clicks:
        raise PreventUpdate

    # Select all node types
    all_node_types = [opt["value"] for opt in node_type_options] if node_type_options else []

    # Select all relationship types
    all_rel_types = [opt["value"] for opt in rel_type_options] if rel_type_options else []

    # Reset time sliders to full ranges
    fr = full_ranges or {}
    created_reset = fr.get("_created_at", [0, 1])
    updated_reset = fr.get("_last_updated_at", [0, 1])
    seen_reset = fr.get("_last_seen_at", [0, 1])

    return all_node_types, all_rel_types, 0, "all", created_reset, updated_reset, seen_reset


@callback(
    Output("graph-cytoscape", "elements", allow_duplicate=True),
    [Input("node-type-filter", "value"),
     Input("relationship-type-filter", "value"),
     Input("weight-threshold-slider", "value"),
     Input("top-n-toggle", "value"),
     # Promoted from State → Input so that expansion writes to this store
     # automatically re-trigger the filter, keeping the filtered view in sync
     # with the unfiltered baseline after every expansion.
     Input("unfiltered-elements-store", "data"),
     # Time filter inputs
     Input("time-slider-created", "value"),
     Input("time-slider-updated", "value"),
     Input("time-slider-seen", "value")],
    State("time-filter-full-ranges", "data"),
    prevent_initial_call=True
)
def apply_relationship_filters(
    selected_node_types,
    selected_rel_types,
    weight_threshold,
    top_n_mode,
    unfiltered_elements,
    created_range,
    updated_range,
    seen_range,
    full_ranges,
):
    """Apply all filters (node types, relationship types, weight, top-N) to graph elements.

    ``unfiltered-elements-store`` is an **Input** (not State) so that this
    callback fires automatically whenever expansion writes new nodes to the
    store.  Without this, re-enabling a previously hidden node type after an
    expansion would show nothing, because the store change would not trigger
    a re-filter.

    Expansion callbacks write ``no_update`` for ``graph-cytoscape.elements``
    and let this callback drive the visible update, ensuring the active filter
    is always respected regardless of which path added nodes to the store.
    """
    if not unfiltered_elements:
        raise PreventUpdate

    filtered_graph = _compute_filtered_graph(
        selected_node_types,
        selected_rel_types,
        weight_threshold,
        top_n_mode,
        unfiltered_elements,
        created_range=created_range,
        updated_range=updated_range,
        seen_range=seen_range,
        full_ranges=full_ranges,
    )
    filtered_nodes = filtered_graph["visible_nodes"]
    filtered_edges = filtered_graph["visible_edges"]
    has_weighted_edges = filtered_graph["has_weighted_edges"]

    logger.info(
        "[GRAPH-DEBUG][filter.apply] start "
        f"nodes={len(filtered_graph['all_nodes'])} edges={len(filtered_graph['all_edges'])} "
        f"selected_node_types={selected_node_types} selected_rel_types={selected_rel_types} "
        f"weight_threshold={weight_threshold} top_n_mode={top_n_mode} "
        f"has_weighted_edges={has_weighted_edges}"
    )

    logger.info(
        "[GRAPH-DEBUG][filter.apply] nodes_after_type_filter "
        f"visible={len(filtered_nodes)} removed={len(filtered_graph['all_nodes']) - len(filtered_nodes)}"
    )

    logger.info(
        "[GRAPH-DEBUG][filter.apply] edges_after_rel_type_filter "
        f"visible={len(filtered_edges)} removed={len(filtered_graph['all_edges']) - len(filtered_edges)}"
    )

    logger.info(
        "[GRAPH-DEBUG][filter.apply] edges_after_visibility_filter "
        f"visible={len(filtered_edges)}"
    )

    if has_weighted_edges and weight_threshold > 0:
        logger.info(
            "[GRAPH-DEBUG][filter.apply] edges_after_weight_filter "
            f"threshold={weight_threshold} visible={len(filtered_edges)}"
        )

    if has_weighted_edges and top_n_mode in {"top50", "top100"}:
        logger.info(
            "[GRAPH-DEBUG][filter.apply] edges_after_topn "
            f"mode={top_n_mode} visible={len(filtered_edges)}"
        )

    logger.info(
        "[GRAPH-DEBUG][filter.apply] final "
        f"elements={len(filtered_nodes) + len(filtered_edges)} "
        f"visible_nodes={len(filtered_nodes)} visible_edges={len(filtered_edges)}"
    )

    return filtered_nodes + filtered_edges


@callback(
    [Output("time-filters-collapse", "is_open"),
     Output("time-filters-collapse-toggle", "children")],
    Input("time-filters-collapse-toggle", "n_clicks"),
    State("time-filters-collapse", "is_open"),
    prevent_initial_call=True
)
def toggle_time_filters_collapse(n_clicks, is_open):
    """Toggle the Time Filters collapsible section."""
    if not n_clicks:
        raise PreventUpdate
    new_state = not is_open
    chevron = "chevron-down" if new_state else "chevron-right"
    children = [
        html.I(className=f"fas fa-{chevron} collapse-toggle-chevron me-1"),
        "Time Filters",
    ]
    return new_state, children


@callback(
    [Output("time-filter-full-ranges", "data"),
     Output("time-slider-created", "min"),
     Output("time-slider-created", "max"),
     Output("time-slider-created", "value"),
     Output("time-slider-created", "marks"),
     Output("time-slider-updated", "min"),
     Output("time-slider-updated", "max"),
     Output("time-slider-updated", "value"),
     Output("time-slider-updated", "marks"),
     Output("time-slider-seen", "min"),
     Output("time-slider-seen", "max"),
     Output("time-slider-seen", "value"),
     Output("time-slider-seen", "marks")],
    Input("unfiltered-elements-store", "data"),
    State("time-filter-full-ranges", "data"),
    prevent_initial_call=True,
)
def update_time_filter_ranges(unfiltered_elements, previous_ranges):
    """Compute slider ranges from all unfiltered nodes.

    Called whenever the unfiltered baseline changes (new query or expansion).
    Uses Interpretation A: range is always the full min/max from
    unfiltered-elements-store regardless of other active filters.

    When a property is absent from ALL nodes, slider is set to [0, 1]
    which is effectively inert (no nodes excluded).
    """
    if not unfiltered_elements:
        raise PreventUpdate

    nodes = [e for e in unfiltered_elements if is_node_data(e.get("data", {}))]

    # Compute ranges for each time property
    ranges = {}
    for prop in ("_created_at", "_last_updated_at", "_last_seen_at"):
        min_days, max_days = compute_time_range(nodes, prop)
        # When min == max, pad by ±1 day so both handles remain visible
        # (Dash stacks identical-value handles on top of each other)
        if min_days == max_days:
            min_days = max(0, min_days - 1)
            max_days = max_days + 1
        ranges[prop] = [min_days, max_days]

    full_ranges_data = previous_ranges or {}

    def _slider_outputs(prop):
        r = ranges[prop]
        marks = None
        # Preserve previous value if available, else full range
        prev = full_ranges_data.get(prop)
        value = prev if prev and prev == r else r
        return r[0], r[1], value, marks

    outputs = []
    for prop in ("_created_at", "_last_updated_at", "_last_seen_at"):
        outputs.extend(_slider_outputs(prop))

    return ranges, *outputs


@callback(
    [Output("time-slider-created-label", "children"),
     Output("time-slider-updated-label", "children"),
     Output("time-slider-seen-label", "children")],
    [Input("time-slider-created", "value"),
     Input("time-slider-updated", "value"),
     Input("time-slider-seen", "value"),
     Input("time-filter-full-ranges", "data")],
)
def update_time_filter_labels(created_val, updated_val, seen_val, full_ranges):
    """Format the selected range as human-readable labels below each slider."""
    if not full_ranges:
        return "", "", ""

    def _label(prop, val):
        full = full_ranges.get(prop, [0, 1])
        lo = _format_day_label(val[0])
        hi = _format_day_label(val[1])
        if val == full:
            return f"All dates ({lo} – {hi})"
        return f"{lo} – {hi}"

    return (
        _label("_created_at", created_val),
        _label("_last_updated_at", updated_val),
        _label("_last_seen_at", seen_val),
    )

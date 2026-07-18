"""Integration tests for graph time-based filter logic.

Covers ``_compute_filtered_graph`` with time-range parameters
to ensure nodes are properly filtered and edge visibility is
maintained correctly.
"""

import pytest

from app.dash_app.pages.graph.callbacks.filtering import (
    _compute_filtered_graph,
    FilteringDataValidationError,
)


pytestmark = pytest.mark.unit


def _make_node(node_id, **props):
    """Build a minimal Cytoscape node element dict."""
    data = {"id": node_id, "elementType": "node", **props}
    return {"data": data}


def _make_edge(edge_id, source, target, **props):
    """Build a minimal Cytoscape edge element dict."""
    data = {"id": edge_id, "elementType": "edge", "source": source, "target": target, **props}
    return {"data": data}


# ── No time filters (existing behavior) ──────────────────────────────────


def test_compute_filtered_graph_no_time_filters():
    """Without time filters, behavior must be identical to before."""
    elements = [
        _make_node("n1", nodeType="Person", _created_at="2025-01-15T00:00:00Z"),
        _make_node("n2", nodeType="Person", _created_at="2025-06-01T00:00:00Z"),
        _make_node("n3", nodeType="Repository", _created_at="2025-12-01T00:00:00Z"),
        _make_edge("e1", "n1", "n2", relType="KNOWS", weight=5),
        _make_edge("e2", "n2", "n3", relType="WORKS_ON", weight=3),
    ]

    result = _compute_filtered_graph(
        selected_node_types=["Person", "Repository"],
        selected_rel_types=["KNOWS", "WORKS_ON"],
        weight_threshold=0,
        top_n_mode="all",
        unfiltered_elements=elements,
        created_range=None,
        updated_range=None,
        seen_range=None,
        full_ranges=None,
    )

    assert len(result["visible_nodes"]) == 3
    assert len(result["visible_edges"]) == 2


# ── Created At filter ────────────────────────────────────────────────────


def test_compute_filtered_graph_created_filter():
    """Narrowing Created At slider should exclude nodes outside the range."""
    elements = [
        _make_node("n1", nodeType="Person", _created_at="2025-01-15T00:00:00Z"),
        _make_node("n2", nodeType="Person", _created_at="2025-06-01T00:00:00Z"),
        _make_node("n3", nodeType="Person", _created_at="2025-12-01T00:00:00Z"),
        _make_edge("e1", "n1", "n2", relType="KNOWS"),
        _make_edge("e2", "n2", "n3", relType="KNOWS"),
    ]

    # Narrow to only June–Dec 2025 (days 20235–20423)
    result = _compute_filtered_graph(
        selected_node_types=["Person"],
        selected_rel_types=["KNOWS"],
        weight_threshold=0,
        top_n_mode="all",
        unfiltered_elements=elements,
        created_range=[20235, 20423],
        updated_range=None,
        seen_range=None,
        full_ranges={"_created_at": [20103, 20423]},
    )

    visible_ids = {n.get("data", {}).get("id") for n in result["visible_nodes"]}
    assert "n1" not in visible_ids  # Jan 15 is before range
    assert "n2" in visible_ids
    assert "n3" in visible_ids


# ── Missing property included ────────────────────────────────────────────


def test_compute_filtered_graph_missing_property_included():
    """Nodes missing _created_at should remain visible when slider is narrowed."""
    elements = [
        _make_node("n1", nodeType="Person", _created_at="2025-01-15T00:00:00Z"),
        _make_node("n2", nodeType="Person"),  # no _created_at
        _make_node("n3", nodeType="Person", _created_at="2025-12-01T00:00:00Z"),
        _make_edge("e1", "n1", "n2", relType="KNOWS"),
    ]

    result = _compute_filtered_graph(
        selected_node_types=["Person"],
        selected_rel_types=["KNOWS"],
        weight_threshold=0,
        top_n_mode="all",
        unfiltered_elements=elements,
        created_range=[20400, 20423],  # Only Dec 2025
        updated_range=None,
        seen_range=None,
        full_ranges={"_created_at": [20103, 20423]},
    )

    visible_ids = {n.get("data", {}).get("id") for n in result["visible_nodes"]}
    assert "n1" not in visible_ids  # Jan 15 is before range
    assert "n2" in visible_ids  # Missing property included
    assert "n3" in visible_ids


# ── Combined filters ─────────────────────────────────────────────────────


def test_compute_filtered_graph_combined():
    """Node-type filter + created filter should both apply."""
    elements = [
        _make_node("n1", nodeType="Person", _created_at="2025-01-15T00:00:00Z"),
        _make_node("n2", nodeType="Person", _created_at="2025-06-01T00:00:00Z"),
        _make_node("n3", nodeType="Repository", _created_at="2025-12-01T00:00:00Z"),
        _make_edge("e1", "n1", "n2", relType="KNOWS"),
        _make_edge("e2", "n2", "n3", relType="WORKS_ON"),
    ]

    # Only Person nodes, and only those created after June 2025
    result = _compute_filtered_graph(
        selected_node_types=["Person"],
        selected_rel_types=["KNOWS", "WORKS_ON"],
        weight_threshold=0,
        top_n_mode="all",
        unfiltered_elements=elements,
        created_range=[20235, 20423],  # June–Dec 2025
        updated_range=None,
        seen_range=None,
        full_ranges={"_created_at": [20103, 20423]},
    )

    visible_ids = {n.get("data", {}).get("id") for n in result["visible_nodes"]}
    assert "n1" not in visible_ids  # Person but before range
    assert "n2" in visible_ids      # Person and in range
    assert "n3" not in visible_ids  # Repository


# ── Edge visibility ──────────────────────────────────────────────────────


def test_compute_filtered_graph_edge_visibility():
    """Edges to hidden nodes should be removed."""
    elements = [
        _make_node("n1", nodeType="Person", _created_at="2025-01-15T00:00:00Z"),
        _make_node("n2", nodeType="Person", _created_at="2025-06-01T00:00:00Z"),
        _make_edge("e1", "n1", "n2", relType="KNOWS"),
    ]

    result = _compute_filtered_graph(
        selected_node_types=["Person"],
        selected_rel_types=["KNOWS"],
        weight_threshold=0,
        top_n_mode="all",
        unfiltered_elements=elements,
        created_range=[20235, 20423],  # Only June+
        updated_range=None,
        seen_range=None,
        full_ranges={"_created_at": [20103, 20423]},
    )

    visible_ids = {n.get("data", {}).get("id") for n in result["visible_nodes"]}
    assert "n1" not in visible_ids  # Hidden
    assert "n2" in visible_ids

    # Edge e1 should be hidden because n1 is hidden
    visible_edge_ids = {e.get("data", {}).get("id") for e in result["visible_edges"]}
    assert "e1" not in visible_edge_ids
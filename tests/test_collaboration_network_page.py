"""Unit tests for the collaboration network page module.

Tests cover the pure helper functions in
app/dash_app/pages/collaboration_network.py — no Dash server, no Neo4j
connection required.

Run with: pytest tests/test_collaboration_network_page.py -v
"""

import pytest

from app.dash_app.pages.collaboration_network.layout import (
    _compute_collab_filtered,
    _get_communities,
    _split_elements,
)


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures — shared synthetic Cytoscape element data
# ---------------------------------------------------------------------------

def _node(node_id: str, community: int, hub_score: float = 1.0) -> dict:
    return {
        "data": {
            "id": node_id,
            "label": node_id,
            "community": community,
            "hub_score": hub_score,
            "nodeType": "Person",
            "elementType": "node",
        },
        "classes": f"community-{community % 20}",
        "position": {"x": 0, "y": 0},
    }


def _edge(src: str, tgt: str, weight: float) -> dict:
    return {
        "data": {
            "id": f"collab:{src}:{tgt}",
            "source": src,
            "target": tgt,
            "weight": weight,
            "relType": "COLLABORATES",
        },
        "classes": "collaboration-edge",
    }


# Two communities: {alice, bob} in community 0, {carol, dave} in community 1.
# Edges with varying weights.
NODES = [
    _node("alice", 0, hub_score=15),
    _node("bob",   0, hub_score=10),
    _node("carol", 1, hub_score=8),
    _node("dave",  1, hub_score=5),
]
EDGES = [
    _edge("alice", "bob",   weight=20),
    _edge("alice", "carol", weight=8),
    _edge("bob",   "carol", weight=5),
    _edge("carol", "dave",  weight=12),
]
ALL_ELEMENTS = NODES + EDGES


# ---------------------------------------------------------------------------
# _split_elements
# ---------------------------------------------------------------------------

class TestSplitElements:
    def test_separates_nodes_and_edges(self):
        nodes, edges = _split_elements(ALL_ELEMENTS)
        assert len(nodes) == 4
        assert len(edges) == 4

    def test_nodes_have_no_source_field(self):
        nodes, _ = _split_elements(ALL_ELEMENTS)
        for n in nodes:
            assert "source" not in n["data"]

    def test_edges_have_source_field(self):
        _, edges = _split_elements(ALL_ELEMENTS)
        for e in edges:
            assert "source" in e["data"]

    def test_empty_list_returns_two_empty_lists(self):
        nodes, edges = _split_elements([])
        assert nodes == []
        assert edges == []

    def test_nodes_only_input(self):
        nodes, edges = _split_elements(NODES)
        assert len(nodes) == 4
        assert edges == []

    def test_edges_only_input(self):
        nodes, edges = _split_elements(EDGES)
        assert nodes == []
        assert len(edges) == 4


# ---------------------------------------------------------------------------
# _get_communities
# ---------------------------------------------------------------------------

class TestGetCommunities:
    def test_returns_sorted_list(self):
        communities = _get_communities(ALL_ELEMENTS)
        assert communities == sorted(communities)

    def test_returns_unique_ids(self):
        communities = _get_communities(ALL_ELEMENTS)
        assert len(communities) == len(set(communities))

    def test_correct_community_ids(self):
        communities = _get_communities(ALL_ELEMENTS)
        assert communities == [0, 1]

    def test_edges_excluded(self):
        # Edges have no community field — they must not contribute to the list.
        communities = _get_communities(EDGES)
        assert communities == []

    def test_empty_elements(self):
        communities = _get_communities([])
        assert communities == []

    def test_single_community(self):
        elements = [_node("alice", 3), _node("bob", 3)]
        communities = _get_communities(elements)
        assert communities == [3]



# ---------------------------------------------------------------------------
# _compute_collab_filtered — no filters (baseline)
# ---------------------------------------------------------------------------

class TestComputeCollabFilteredBaseline:
    def test_no_filters_returns_all_elements(self):
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[],
            weight_threshold=0,
            top_n_mode="all",
        )
        assert len(result) == len(ALL_ELEMENTS)

    def test_empty_elements_returns_empty(self):
        result = _compute_collab_filtered(
            [],
            selected_communities=[],
            weight_threshold=0,
            top_n_mode="all",
        )
        assert result == []

    def test_result_contains_nodes_and_edges(self):
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[],
            weight_threshold=0,
            top_n_mode="all",
        )
        nodes, edges = _split_elements(result)
        assert len(nodes) == 4
        assert len(edges) == 4


# ---------------------------------------------------------------------------
# _compute_collab_filtered — community filter
# ---------------------------------------------------------------------------

class TestComputeCollabFilteredCommunity:
    def test_single_community_hides_other_nodes_and_cross_edges(self):
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[0],
            weight_threshold=0,
            top_n_mode="all",
        )
        nodes, edges = _split_elements(result)
        node_ids = {n["data"]["id"] for n in nodes}
        assert node_ids == {"alice", "bob"}
        # alice-carol and bob-carol cross community edges must be absent
        edge_ids = {e["data"]["id"] for e in edges}
        assert "collab:alice:carol" not in edge_ids
        assert "collab:bob:carol" not in edge_ids

    def test_selected_communities_empty_shows_all(self):
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[],
            weight_threshold=0,
            top_n_mode="all",
        )
        nodes, _ = _split_elements(result)
        assert len(nodes) == 4

    def test_both_communities_selected_shows_all_nodes(self):
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[0, 1],
            weight_threshold=0,
            top_n_mode="all",
        )
        nodes, _ = _split_elements(result)
        assert len(nodes) == 4

    def test_nonexistent_community_returns_no_nodes(self):
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[99],
            weight_threshold=0,
            top_n_mode="all",
        )
        nodes, edges = _split_elements(result)
        assert len(nodes) == 0
        assert len(edges) == 0


# ---------------------------------------------------------------------------
# _compute_collab_filtered — weight threshold
# ---------------------------------------------------------------------------

class TestComputeCollabFilteredWeight:
    def test_weight_threshold_removes_light_edges(self):
        # Weights: alice-bob=20, alice-carol=8, bob-carol=5, carol-dave=12
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[],
            weight_threshold=10,
            top_n_mode="all",
        )
        _, edges = _split_elements(result)
        weights = [e["data"]["weight"] for e in edges]
        assert all(w >= 10 for w in weights)

    def test_weight_threshold_zero_keeps_all_edges(self):
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[],
            weight_threshold=0,
            top_n_mode="all",
        )
        _, edges = _split_elements(result)
        assert len(edges) == 4

    def test_weight_threshold_above_max_returns_no_edges(self):
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[],
            weight_threshold=100,
            top_n_mode="all",
        )
        _, edges = _split_elements(result)
        assert len(edges) == 0


# ---------------------------------------------------------------------------
# _compute_collab_filtered — top-N filter
# ---------------------------------------------------------------------------

class TestComputeCollabFilteredTopN:
    def _make_many_edges(self, n: int) -> list[dict]:
        """Create n+2 nodes and n+1 edges with incrementing weights."""
        nodes = [_node(f"p{i}", 0) for i in range(n + 1)]
        edges = [_edge("p0", f"p{i+1}", weight=float(i + 1)) for i in range(n)]
        return nodes + edges

    def test_top50_limits_to_fifty_edges(self):
        elements = self._make_many_edges(80)
        result = _compute_collab_filtered(
            elements,
            selected_communities=[],
            weight_threshold=0,
            top_n_mode="top50",
        )
        _, edges = _split_elements(result)
        assert len(edges) <= 50

    def test_top100_limits_to_hundred_edges(self):
        elements = self._make_many_edges(150)
        result = _compute_collab_filtered(
            elements,
            selected_communities=[],
            weight_threshold=0,
            top_n_mode="top100",
        )
        _, edges = _split_elements(result)
        assert len(edges) <= 100

    def test_top50_selects_heaviest_edges(self):
        elements = self._make_many_edges(80)
        result = _compute_collab_filtered(
            elements,
            selected_communities=[],
            weight_threshold=0,
            top_n_mode="top50",
        )
        _, edges = _split_elements(result)
        weights = sorted([e["data"]["weight"] for e in edges], reverse=True)
        # All returned edges must be from the top 50 heaviest
        if len(weights) == 50:
            assert weights[-1] >= 80 - 50 + 1  # minimum weight among top-50

    def test_top_all_returns_all_edges(self):
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[],
            weight_threshold=0,
            top_n_mode="all",
        )
        _, edges = _split_elements(result)
        assert len(edges) == 4

    def test_fewer_edges_than_top_n_returns_all(self):
        # ALL_ELEMENTS has only 4 edges — top50 should return all 4
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[],
            weight_threshold=0,
            top_n_mode="top50",
        )
        _, edges = _split_elements(result)
        assert len(edges) == 4



# ---------------------------------------------------------------------------
# _compute_collab_filtered — combined filters
# ---------------------------------------------------------------------------

class TestComputeCollabFilteredCombined:
    def test_community_and_weight_combined(self):
        # Community 0 only, weight >= 15 — should keep only alice-bob (weight=20)
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[0],
            weight_threshold=15,
            top_n_mode="all",
        )
        nodes, edges = _split_elements(result)
        node_ids = {n["data"]["id"] for n in nodes}
        assert node_ids == {"alice", "bob"}
        assert len(edges) == 1
        assert edges[0]["data"]["id"] == "collab:alice:bob"

    def test_weight_and_top_n_combined(self):
        # weight >= 8 leaves 3 edges (alice-bob=20, alice-carol=8, carol-dave=12)
        # top50 on 3 edges → still 3
        result = _compute_collab_filtered(
            ALL_ELEMENTS,
            selected_communities=[],
            weight_threshold=8,
            top_n_mode="top50",
        )
        _, edges = _split_elements(result)
        assert len(edges) == 3


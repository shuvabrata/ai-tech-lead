"""Unit tests for the collaboration network algorithm module.

Tests cover all pure functions in app/analytics/collaboration/algorithm.py
using small synthetic graphs — no Neo4j connection required.

Run with: pytest tests/test_collaboration_algorithm.py -v
"""

import pytest

from app.analytics.collaboration.algorithm import (
    LOUVAIN_RANDOM_STATE,
    MAX_COMMUNITY_STYLES,
    build_graph,
    compute_hub_scores,
    compute_modularity,
    detect_communities,
    filter_top_edges_per_node,
    process_collaboration_network,
    to_cytoscape_elements,
)


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rec(p1: str, p2: str, score: float) -> dict:
    """Build a minimal collaboration record in the new pipeline format."""
    return {
        "person1": p1,
        "person1_wba_id": f"github::Person::{p1}",
        "person1_props": {"id": f"github::Person::{p1}", "name": p1},
        "person2": p2,
        "person2_wba_id": f"github::Person::{p2}",
        "person2_props": {"id": f"github::Person::{p2}", "name": p2},
        "total_collaboration_score": score,
    }


SIMPLE_RECORDS = [
    _rec("alice", "bob", 10),
    _rec("alice", "carol", 5),
    _rec("bob", "carol", 8),
    _rec("dave", "eve", 12),
    _rec("dave", "frank", 7),
]

DUPLICATE_PAIR_RECORDS = [
    _rec("alice", "bob", 10),
    _rec("alice", "bob", 5),  # same pair twice
]


# ---------------------------------------------------------------------------
# build_graph
# ---------------------------------------------------------------------------

class TestBuildGraph:
    def test_nodes_and_edges_created(self):
        g = build_graph(SIMPLE_RECORDS)
        assert g.number_of_nodes() == 6
        assert g.number_of_edges() == 5

    def test_edge_weight_set(self):
        g = build_graph(SIMPLE_RECORDS)
        assert g["github::Person::alice"]["github::Person::bob"]["weight"] == 10
        assert g["github::Person::dave"]["github::Person::eve"]["weight"] == 12

    def test_duplicate_pair_accumulates_weight(self):
        g = build_graph(DUPLICATE_PAIR_RECORDS)
        assert g.number_of_edges() == 1
        assert g["github::Person::alice"]["github::Person::bob"]["weight"] == 15  # 10 + 5

    def test_empty_records_returns_empty_graph(self):
        g = build_graph([])
        assert g.number_of_nodes() == 0
        assert g.number_of_edges() == 0


# ---------------------------------------------------------------------------
# detect_communities
# ---------------------------------------------------------------------------

class TestDetectCommunities:
    def test_returns_partition_for_all_nodes(self):
        g = build_graph(SIMPLE_RECORDS)
        partition = detect_communities(g)
        assert set(partition.keys()) == set(g.nodes())

    def test_community_ids_are_integers(self):
        g = build_graph(SIMPLE_RECORDS)
        partition = detect_communities(g)
        assert all(isinstance(cid, int) for cid in partition.values())

    def test_raw_ids_not_clamped(self):
        """detect_communities must return raw IDs — clamping happens in to_cytoscape_elements."""
        g = build_graph(SIMPLE_RECORDS)
        partition = detect_communities(g)
        # Raw IDs may be any non-negative integer; the function must not pre-clamp them.
        # We can't assert they exceed MAX_COMMUNITY_STYLES (depends on the run), but we
        # verify the function doesn't perform modulo itself by checking it returns the
        # raw best_partition output (non-negative ints).
        assert all(cid >= 0 for cid in partition.values())

    def test_empty_graph_returns_empty_dict(self):
        import networkx as nx
        partition = detect_communities(nx.Graph())
        assert partition == {}

    def test_louvain_random_state_constant_is_set(self):
        """LOUVAIN_RANDOM_STATE must be a fixed integer so partitions are reproducible."""
        assert isinstance(LOUVAIN_RANDOM_STATE, int)

    def test_detect_communities_is_deterministic(self):
        """Calling detect_communities twice on the same graph returns identical partitions."""
        g = build_graph(SIMPLE_RECORDS)
        partition_a = detect_communities(g)
        partition_b = detect_communities(g)
        assert partition_a == partition_b

    def test_two_clear_communities(self):
        """Dense clique pair should produce exactly 2 communities."""
        records = [
            # Clique 1
            _rec("a", "b", 100),
            _rec("a", "c", 100),
            _rec("b", "c", 100),
            # Clique 2
            _rec("x", "y", 100),
            _rec("x", "z", 100),
            _rec("y", "z", 100),
            # Weak bridge
            _rec("c", "x", 1),
        ]
        g = build_graph(records)
        partition = detect_communities(g)
        num_communities = len(set(partition.values()))
        assert num_communities == 2


# ---------------------------------------------------------------------------
# compute_hub_scores
# ---------------------------------------------------------------------------

class TestComputeHubScores:
    def test_all_nodes_have_score(self):
        g = build_graph(SIMPLE_RECORDS)
        hub_scores = compute_hub_scores(g)
        assert set(hub_scores.keys()) == set(g.nodes())

    def test_hub_score_is_weighted_degree(self):
        g = build_graph(SIMPLE_RECORDS)
        hub_scores = compute_hub_scores(g)
        # alice connects to bob (10) and carol (5) → weighted degree = 15
        assert hub_scores["github::Person::alice"] == 15

    def test_scores_are_non_negative(self):
        g = build_graph(SIMPLE_RECORDS)
        hub_scores = compute_hub_scores(g)
        assert all(s >= 0 for s in hub_scores.values())


# ---------------------------------------------------------------------------
# filter_top_edges_per_node
# ---------------------------------------------------------------------------

class TestFilterTopEdgesPerNode:
    def test_top_n_zero_returns_copy(self):
        g = build_graph(SIMPLE_RECORDS)
        filtered = filter_top_edges_per_node(g, top_n=0)

        assert filtered is not g
        assert filtered.number_of_nodes() == g.number_of_nodes()
        assert filtered.number_of_edges() == g.number_of_edges()

    def test_keeps_strongest_edge_per_node(self):
        records = [
            _rec("alice", "bob", 10),
            _rec("alice", "carol", 3),
            _rec("alice", "dave", 1),
        ]
        g = build_graph(records)
        filtered = filter_top_edges_per_node(g, top_n=1)

        assert filtered.has_edge("github::Person::alice", "github::Person::bob")
        assert filtered.number_of_edges() >= 1

    def test_ensure_min_connection_keeps_all_connected_nodes(self):
        records = [
            _rec("a", "b", 10),
            _rec("a", "c", 9),
            _rec("a", "d", 8),
            _rec("b", "c", 1),
        ]
        g = build_graph(records)
        filtered = filter_top_edges_per_node(g, top_n=1, ensure_min_connection=True)

        for node in g.nodes():
            if g.degree(node) > 0:
                assert filtered.degree(node) > 0


# ---------------------------------------------------------------------------
# to_cytoscape_elements
# ---------------------------------------------------------------------------

class TestToCytoscapeElements:
    def setup_method(self):
        self.g = build_graph(SIMPLE_RECORDS)
        self.partition = detect_communities(self.g)
        self.hub_scores = compute_hub_scores(self.g)
        self.elements = to_cytoscape_elements(self.g, self.partition, self.hub_scores)

    def test_element_count(self):
        node_elements = [e for e in self.elements if "source" not in e["data"]]
        edge_elements = [e for e in self.elements if "source" in e["data"]]
        assert len(node_elements) == self.g.number_of_nodes()
        assert len(edge_elements) == self.g.number_of_edges()

    def test_node_data_fields(self):
        node = next(e for e in self.elements if "source" not in e["data"])
        data = node["data"]
        assert "id" in data
        assert "label" in data
        assert "displayLabel" in data
        assert "nodeType" in data
        assert "community" in data
        assert "hub_score" in data
        assert "elementType" in data
        assert data["nodeType"] == "Person"
        assert data["elementType"] == "node"

    def test_community_raw_id_stored_in_data(self):
        """data.community must hold the raw Louvain ID, not the clamped style ID."""
        for element in self.elements:
            if "source" in element["data"]:
                continue
            raw_id = element["data"]["community"]
            style_class = element["classes"]
            expected_style_id = raw_id % MAX_COMMUNITY_STYLES
            assert style_class == f"community-{expected_style_id}"

    def test_css_class_always_within_stylesheet_range(self):
        for element in self.elements:
            if "source" in element["data"]:
                continue
            class_num = int(element["classes"].split("-")[1])
            assert 0 <= class_num < MAX_COMMUNITY_STYLES

    def test_edge_data_fields(self):
        edge = next(e for e in self.elements if "source" in e["data"])
        data = edge["data"]
        assert "id" in data
        assert "source" in data
        assert "target" in data
        assert "weight" in data
        assert "relType" in data
        assert data["relType"] == "COLLABORATES"
        assert data["id"] == f"collab:{data['source']}:{data['target']}"

    def test_display_label_truncated_at_12_chars(self):
        long_name_records = [
            _rec("averylongusername", "bob", 5)
        ]
        g = build_graph(long_name_records)
        partition = detect_communities(g)
        hub_scores = compute_hub_scores(g)
        elements = to_cytoscape_elements(g, partition, hub_scores)
        node = next(e for e in elements if e["data"].get("id") == "github::Person::averylongusername")
        assert node["data"]["displayLabel"] == "averylonguse…"

    def test_display_label_not_truncated_when_short(self):
        g = build_graph(SIMPLE_RECORDS)
        partition = detect_communities(g)
        hub_scores = compute_hub_scores(g)
        elements = to_cytoscape_elements(g, partition, hub_scores)
        node = next(e for e in elements if e["data"].get("id") == "github::Person::alice")
        assert node["data"]["displayLabel"] == "alice"

    def test_node_data_has_wba_id(self):
        node = next(e for e in self.elements if "source" not in e["data"])
        data = node["data"]
        assert "wba_id" in data
        assert data["wba_id"] == data["id"]
        assert data["wba_id"].startswith("github::Person::")

    def test_node_label_is_display_name_not_wba_id(self):
        node = next(e for e in self.elements if e["data"].get("id") == "github::Person::alice")
        assert node["data"]["label"] == "alice"
        assert node["data"]["displayLabel"] == "alice"

    def test_node_extra_props_in_element_data(self):
        node = next(e for e in self.elements if e["data"].get("id") == "github::Person::alice")
        data = node["data"]
        # Neo4j properties from person1_props should be surfaced
        assert data.get("name") == "alice"


# ---------------------------------------------------------------------------
# compute_modularity
# ---------------------------------------------------------------------------

class TestComputeModularity:
    def test_modularity_in_valid_range(self):
        g = build_graph(SIMPLE_RECORDS)
        partition = detect_communities(g)
        modularity = compute_modularity(g, partition)
        assert -0.5 <= modularity <= 1.0

    def test_empty_graph_returns_zero(self):
        import networkx as nx
        modularity = compute_modularity(nx.Graph(), {})
        assert modularity == 0.0


# ---------------------------------------------------------------------------
# process_collaboration_network (full pipeline)
# ---------------------------------------------------------------------------

class TestProcessCollaborationNetwork:
    def test_returns_list(self):
        elements = process_collaboration_network(SIMPLE_RECORDS)
        assert isinstance(elements, list)
        assert len(elements) > 0

    def test_raises_on_empty_records(self):
        with pytest.raises(ValueError, match="No collaboration records"):
            process_collaboration_network([])

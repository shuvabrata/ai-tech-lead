"""Unit tests for collab spotlight _apply_spotlight_classes helper.

Tests the pure class-manipulation logic with no Dash server or ES required.
"""

import pytest

from app.dash_app.pages.collaboration_network.callbacks.spotlight import (
    _apply_spotlight_classes,
)


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _node(cyto_id: str, wba_id: str, classes: str = "") -> dict:
    return {"data": {"id": cyto_id, "wba_id": wba_id, "elementType": "node"}, "classes": classes}


def _edge(edge_id: str, source: str, target: str, classes: str = "") -> dict:
    return {"data": {"id": edge_id, "source": source, "target": target, "elementType": "edge"}, "classes": classes}


ELEMENTS = [
    _node("n1", "wba::Person::alice"),
    _node("n2", "wba::Person::bob"),
    _node("n3", "wba::Person::charlie"),
    _edge("e1", "n1", "n2"),   # both endpoints match when alice+bob match
    _edge("e2", "n1", "n3"),   # partial match when only alice matches
    _edge("e3", "n2", "n3"),   # partial match when only bob matches
]


# ---------------------------------------------------------------------------
# Node class application
# ---------------------------------------------------------------------------

class TestNodeSpotlightClasses:
    def test_matching_node_gets_spotlight_match(self):
        result = _apply_spotlight_classes(ELEMENTS, {"wba::Person::alice"})
        alice = next(e for e in result if e["data"].get("id") == "n1")
        assert "spotlight-match" in alice["classes"].split()

    def test_non_matching_node_gets_spotlight_dim(self):
        result = _apply_spotlight_classes(ELEMENTS, {"wba::Person::alice"})
        bob = next(e for e in result if e["data"].get("id") == "n2")
        assert "spotlight-dim" in bob["classes"].split()

    def test_matching_node_does_not_get_dim(self):
        result = _apply_spotlight_classes(ELEMENTS, {"wba::Person::alice"})
        alice = next(e for e in result if e["data"].get("id") == "n1")
        assert "spotlight-dim" not in alice["classes"].split()

    def test_all_nodes_match_all_get_spotlight_match(self):
        all_wba = {"wba::Person::alice", "wba::Person::bob", "wba::Person::charlie"}
        result = _apply_spotlight_classes(ELEMENTS, all_wba)
        nodes = [e for e in result if "source" not in e["data"]]
        for node in nodes:
            assert "spotlight-match" in node["classes"].split()


# ---------------------------------------------------------------------------
# Edge class application
# ---------------------------------------------------------------------------

class TestEdgeSpotlightClasses:
    def test_edge_both_endpoints_match_gets_spotlight_match(self):
        """e1 connects alice and bob — both match."""
        result = _apply_spotlight_classes(
            ELEMENTS, {"wba::Person::alice", "wba::Person::bob"}
        )
        e1 = next(e for e in result if e["data"].get("id") == "e1")
        assert "spotlight-match" in e1["classes"].split()

    def test_edge_one_endpoint_matches_gets_spotlight_dim(self):
        """e2 connects alice and charlie — only alice matches."""
        result = _apply_spotlight_classes(ELEMENTS, {"wba::Person::alice"})
        e2 = next(e for e in result if e["data"].get("id") == "e2")
        assert "spotlight-dim" in e2["classes"].split()

    def test_edge_no_endpoint_matches_gets_spotlight_dim(self):
        """e3 connects bob and charlie — neither matches when only alice matches."""
        result = _apply_spotlight_classes(ELEMENTS, {"wba::Person::alice"})
        e3 = next(e for e in result if e["data"].get("id") == "e3")
        assert "spotlight-dim" in e3["classes"].split()


# ---------------------------------------------------------------------------
# Clear mode (match_wba_ids is None)
# ---------------------------------------------------------------------------

class TestClearMode:
    def test_clear_strips_spotlight_match(self):
        elements_with_classes = [
            _node("n1", "wba::Person::alice", "spotlight-match"),
            _node("n2", "wba::Person::bob", "spotlight-dim"),
        ]
        result = _apply_spotlight_classes(elements_with_classes, None)
        for elem in result:
            classes = elem["classes"].split()
            assert "spotlight-match" not in classes
            assert "spotlight-dim" not in classes

    def test_clear_preserves_non_spotlight_classes(self):
        elements_with_classes = [
            _node("n1", "wba::Person::alice", "dimmed spotlight-match community-1"),
        ]
        result = _apply_spotlight_classes(elements_with_classes, None)
        classes = result[0]["classes"].split()
        assert "dimmed" in classes
        assert "community-1" in classes
        assert "spotlight-match" not in classes

    def test_empty_elements_returns_empty(self):
        assert _apply_spotlight_classes([], None) == []

    def test_none_elements_returns_empty(self):
        assert _apply_spotlight_classes(None, None) == []


# ---------------------------------------------------------------------------
# Class preservation
# ---------------------------------------------------------------------------

class TestClassPreservation:
    def test_existing_non_spotlight_classes_preserved_on_match(self):
        elements = [_node("n1", "wba::Person::alice", "dimmed community-2")]
        result = _apply_spotlight_classes(elements, {"wba::Person::alice"})
        classes = result[0]["classes"].split()
        assert "dimmed" in classes
        assert "community-2" in classes
        assert "spotlight-match" in classes

    def test_existing_spotlight_classes_replaced(self):
        """Old spotlight-dim should be replaced by spotlight-match when now matching."""
        elements = [_node("n1", "wba::Person::alice", "spotlight-dim")]
        result = _apply_spotlight_classes(elements, {"wba::Person::alice"})
        classes = result[0]["classes"].split()
        assert "spotlight-match" in classes
        assert "spotlight-dim" not in classes

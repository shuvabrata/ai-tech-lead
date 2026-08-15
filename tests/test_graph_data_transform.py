"""Unit tests for graph data transformation utilities.

Tests cover:
  - neo4j_to_cytoscape: node label resolution, edge construction, hidden edges
  - _resolve_display_name: fallback chain for nodes without _display_name
  - _compact_node_label: truncation and ::-prefix stripping
  - parse_error_response: error categorization
"""

import pytest

from app.dash_app.pages.graph.utils.data_transform import (
    _compact_node_label,
    _resolve_display_name,
    neo4j_to_cytoscape,
    parse_error_response,
)


# ---------------------------------------------------------------------------
# _resolve_display_name
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResolveDisplayName:
    """Tests for the display name resolution fallback chain.

    This is the critical function that determines what label Cytoscape
    renders on each node.  Regressions here cause blank node labels.
    """

    def test_connector_display_name_takes_priority(self):
        """_display_name from connector pipeline wins over everything."""
        props = {"_display_name": "Alice", "name": "Bob", "id": "123"}
        result = _resolve_display_name(props, "wba::Person::alice", "Person")
        assert result == "Alice"

    def test_falls_back_to_lowercase_name(self):
        """When _display_name is missing, lowercase 'name' is used."""
        props = {"name": "Alice"}
        result = _resolve_display_name(props, "wba::Person::alice", "Person")
        assert result == "Alice"

    def test_falls_back_to_lowercase_title(self):
        props = {"title": "Fix login bug"}
        result = _resolve_display_name(props, "wba::Issue::123", "Issue")
        assert result == "Fix login bug"

    def test_falls_back_to_lowercase_id(self):
        props = {"id": "person-42"}
        result = _resolve_display_name(props, "wba::Person::person-42", "Person")
        assert result == "person-42"

    def test_falls_back_to_lowercase_key(self):
        props = {"key": "PROJ-123"}
        result = _resolve_display_name(props, "wba::Project::PROJ-123", "Project")
        assert result == "PROJ-123"

    def test_falls_back_to_lowercase_summary(self):
        props = {"summary": "Migrate to Kubernetes"}
        result = _resolve_display_name(props, "wba::Epic::epic-1", "Epic")
        assert result == "Migrate to Kubernetes"

    # --- Case-insensitive fallback (regression guard) ---

    def test_case_insensitive_name_capital_N(self):
        """Property 'Name' (capital N) should match via case-insensitive lookup."""
        props = {"Name": "Epic"}
        result = _resolve_display_name(props, "wba::Epic::-201", "Epic")
        assert result == "Epic"

    def test_case_insensitive_id_capital_I(self):
        """Property 'Id' (capital I) should match via case-insensitive lookup.

        This is the exact regression scenario: nodes with {Name: "Epic", Id: -201}
        had empty labels because the old code only checked lowercase 'id'.
        """
        props = {"Name": "Epic", "Id": -201}
        result = _resolve_display_name(props, "wba::Epic::-201", "Epic")
        assert result == "Epic"  # 'name' is checked before 'id'

    def test_case_insensitive_title_capital_T(self):
        props = {"Title": "Important Document"}
        result = _resolve_display_name(props, "wba::Doc::1", "Document")
        assert result == "Important Document"

    def test_case_insensitive_key_capital_K(self):
        props = {"Key": "JIRA-456"}
        result = _resolve_display_name(props, "wba::Issue::JIRA-456", "Issue")
        assert result == "JIRA-456"

    def test_case_insensitive_summary_capital_S(self):
        props = {"Summary": "A summary text"}
        result = _resolve_display_name(props, "wba::Epic::e1", "Epic")
        assert result == "A summary text"

    # --- wba_id fallback ---

    def test_falls_back_to_wba_id_when_no_known_properties(self):
        """When no known property exists, wba_id is used."""
        props = {"unknown_field": "some_value"}
        result = _resolve_display_name(props, "github::Person::alice", "Person")
        assert result == "github::Person::alice"

    def test_falls_back_to_wba_id_when_properties_empty(self):
        result = _resolve_display_name({}, "github::Person::bob", "Person")
        assert result == "github::Person::bob"

    # --- Node label last resort ---

    def test_falls_back_to_node_label_when_nothing_else(self):
        """When wba_id is empty/falsy, node label is the last resort."""
        result = _resolve_display_name({}, "", "Person")
        assert result == "Person"

    def test_falls_back_to_node_label_when_wba_id_is_none(self):
        result = _resolve_display_name({}, None, "Repository")
        assert result == "Repository"

    # --- Priority ordering ---

    def test_name_beats_id_in_priority(self):
        """'name' is checked before 'id' in the fallback chain."""
        props = {"name": "Alice", "id": "person-42"}
        result = _resolve_display_name(props, "wba::Person::alice", "Person")
        assert result == "Alice"

    def test_title_beats_summary_in_priority(self):
        """'title' is checked before 'summary'."""
        props = {"title": "Short title", "summary": "Long summary text"}
        result = _resolve_display_name(props, "wba::Issue::1", "Issue")
        assert result == "Short title"

    def test_display_name_beats_case_insensitive_match(self):
        """_display_name always wins, even over case-insensitive matches."""
        props = {"_display_name": "Pipeline Name", "Name": "Raw Name"}
        result = _resolve_display_name(props, "wba::Person::p1", "Person")
        assert result == "Pipeline Name"


# ---------------------------------------------------------------------------
# _compact_node_label
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCompactNodeLabel:
    def test_strips_connector_prefix(self):
        assert _compact_node_label("github::Person::alice") == "alice"

    def test_truncates_long_labels(self):
        # Default GRAPH_UI_MAX_NODE_LABEL_CHARS is 10
        result = _compact_node_label("averylonglabel")
        assert len(result) <= 10
        assert result.endswith("...")

    def test_preserves_short_labels(self):
        assert _compact_node_label("Alice") == "Alice"

    def test_handles_none(self):
        assert _compact_node_label(None) == ""

    def test_handles_empty_string(self):
        assert _compact_node_label("") == ""

    def test_handles_integer(self):
        assert _compact_node_label(-201) == "-201"


# ---------------------------------------------------------------------------
# neo4j_to_cytoscape — node label rendering (regression guard)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNeo4jToCytoscapeNodeLabels:
    """Tests that neo4j_to_cytoscape produces nodes with non-empty displayLabel.

    These guard against the regression where nodes with mixed-case property
    names (e.g. {Name: "Epic", Id: -201}) rendered with blank labels.
    """

    def _make_node(self, element_id, wba_id, labels, properties):
        return {
            "elementId": element_id,
            "wba_id": wba_id,
            "labels": labels,
            "properties": properties,
        }

    def _get_node_by_id(self, elements, node_id):
        for el in elements:
            if el.get("data", {}).get("id") == node_id:
                return el
        raise AssertionError(f"Node {node_id} not found in elements")

    def test_node_with_name_and_id_properties_has_label(self):
        """Node with {Name: 'Epic', Id: -201} must have a non-empty displayLabel."""
        response = {
            "nodes": [
                self._make_node("4:abc:1", "wba::Epic::-201", ["Epic"],
                                {"Name": "Epic", "Id": -201}),
            ],
            "relationships": [],
        }
        elements = neo4j_to_cytoscape(response)
        node = self._get_node_by_id(elements, "4:abc:1")
        data = node["data"]
        assert data["displayLabel"] != "", (
            "displayLabel must not be empty — regression: mixed-case property "
            "names caused blank node labels"
        )
        assert data["displayLabel"] == "Epic"
        assert data["label"] == "Epic"
        assert data["nodeType"] == "Epic"

    def test_node_with_only_id_property_has_label(self):
        """Node with only {id: '123'} should use id as label."""
        response = {
            "nodes": [
                self._make_node("4:abc:2", "wba::Issue::123", ["Issue"],
                                {"id": "123"}),
            ],
            "relationships": [],
        }
        elements = neo4j_to_cytoscape(response)
        node = self._get_node_by_id(elements, "4:abc:2")
        assert node["data"]["displayLabel"] == "123"

    def test_node_with_display_name_uses_it(self):
        """Node with _display_name should use it as label."""
        response = {
            "nodes": [
                self._make_node("4:abc:3", "wba::Person::alice", ["Person"],
                                {"_display_name": "Alice Johnson", "name": "alice"}),
            ],
            "relationships": [],
        }
        elements = neo4j_to_cytoscape(response)
        node = self._get_node_by_id(elements, "4:abc:3")
        assert node["data"]["displayLabel"] == "Alice J..."  # truncated to 10 chars (3 dots)
        assert node["data"]["label"] == "Alice Johnson"

    def test_node_with_no_known_properties_uses_wba_id(self):
        """Node with no known properties falls back to wba_id."""
        response = {
            "nodes": [
                self._make_node("4:abc:4", "github::Person::bob", ["Person"],
                                {"unknown": "value"}),
            ],
            "relationships": [],
        }
        elements = neo4j_to_cytoscape(response)
        node = self._get_node_by_id(elements, "4:abc:4")
        assert node["data"]["displayLabel"] != ""
        assert "bob" in node["data"]["displayLabel"]

    def test_node_with_empty_properties_uses_wba_id(self):
        """Node with empty properties falls back to wba_id."""
        response = {
            "nodes": [
                self._make_node("4:abc:5", "wba::Repo::my-repo", ["Repository"],
                                {}),
            ],
            "relationships": [],
        }
        elements = neo4j_to_cytoscape(response)
        node = self._get_node_by_id(elements, "4:abc:5")
        assert node["data"]["displayLabel"] != ""
        assert "my-repo" in node["data"]["displayLabel"]

    def test_all_nodes_have_non_empty_display_label(self):
        """Every node produced must have a non-empty displayLabel."""
        response = {
            "nodes": [
                self._make_node("4:a:1", "wba::Epic::-201", ["Epic"],
                                {"Name": "Epic", "Id": -201}),
                self._make_node("4:a:2", "wba::Person::alice", ["Person"],
                                {"_display_name": "Alice", "name": "alice"}),
                self._make_node("4:a:3", "wba::Issue::123", ["Issue"],
                                {"id": "123"}),
                self._make_node("4:a:4", "wba::Repo::r", ["Repository"],
                                {}),
                self._make_node("4:a:5", "wba::Doc::d", ["Document"],
                                {"Title": "My Doc"}),
            ],
            "relationships": [],
        }
        elements = neo4j_to_cytoscape(response)
        nodes = [e for e in elements if e.get("group") == "nodes"]
        assert len(nodes) == 5
        for node in nodes:
            data = node["data"]
            assert data.get("displayLabel"), (
                f"Node {data.get('id')} has empty displayLabel — "
                f"properties={data.get('id')}"
            )
            assert data.get("label"), (
                f"Node {data.get('id')} has empty label"
            )

    # --- Edge construction (sanity) ---

    def test_edges_constructed_correctly(self):
        response = {
            "nodes": [
                self._make_node("4:n:1", "wba::Person::alice", ["Person"],
                                {"name": "Alice"}),
                self._make_node("4:n:2", "wba::Person::bob", ["Person"],
                                {"name": "Bob"}),
            ],
            "relationships": [
                {
                    "id": "4:r:1",
                    "type": "COLLABORATES",
                    "startNode": "4:n:1",
                    "endNode": "4:n:2",
                    "properties": {"weight": 5},
                }
            ],
        }
        elements = neo4j_to_cytoscape(response)
        edges = [e for e in elements if e.get("group") == "edges"]
        assert len(edges) == 1
        edge = edges[0]
        assert edge["data"]["source"] == "4:n:1"
        assert edge["data"]["target"] == "4:n:2"
        assert edge["data"]["relType"] == "COLLABORATES"
        assert edge["data"]["weight"] == 5

    def test_hidden_edges_are_skipped(self):
        response = {
            "nodes": [
                self._make_node("4:n:1", "wba::Person::alice", ["Person"],
                                {"name": "Alice"}),
                self._make_node("4:n:2", "wba::Person::bob", ["Person"],
                                {"name": "Bob"}),
            ],
            "relationships": [
                {
                    "id": "4:r:1",
                    "type": "COLLABORATES",
                    "startNode": "4:n:1",
                    "endNode": "4:n:2",
                    "properties": {"_display_in_graph": False},
                }
            ],
        }
        elements = neo4j_to_cytoscape(response)
        edges = [e for e in elements if e.get("group") == "edges"]
        assert len(edges) == 0


# ---------------------------------------------------------------------------
# parse_error_response
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestParseErrorResponse:
    def test_write_operation_error(self):
        msg, hint, link, alert_type = parse_error_response(
            {"detail": {"error": "ValidationError",
                         "message": "Write operation detected"}},
            400,
        )
        assert "Write operations" in msg
        assert "read-only" in hint.lower()
        assert "neo4j.com" in link
        assert alert_type == "danger"

    def test_generic_400_error(self):
        msg, hint, link, alert_type = parse_error_response(
            {"detail": {"error": "BadRequest", "message": "Invalid syntax"}},
            400,
        )
        assert msg != ""
        assert hint != ""
        assert alert_type == "warning"

    def test_500_error(self):
        msg, hint, link, alert_type = parse_error_response(
            {"detail": {"error": "InternalError", "message": "DB down"}},
            500,
        )
        assert "Query Execution Failed" in msg
        assert alert_type == "danger"

    def test_unknown_error(self):
        msg, hint, link, alert_type = parse_error_response(
            {"detail": {}},
            418,
        )
        assert "Unexpected Error" in msg
        assert alert_type == "danger"
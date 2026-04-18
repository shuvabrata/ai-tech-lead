"""Unit tests for graph filter query builder pushdown logic."""

from app.api.graph.v1.model import GraphFilterRequest
from app.api.graph.v1.query import build_filtered_cypher_query


def test_build_filtered_cypher_query_includes_core_clauses():
    """Builder should include type and property/date predicates in query text."""
    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 500",
        nodeTypeFilters=["Person"],
        relationshipTypeFilters=["WORKS_ON"],
        nodePropertyFilters=[
            {"label": "Person", "property": "name", "operator": "CONTAINS", "value": "ali"}
        ],
        relationshipPropertyFilters=[
            {"type": "REVIEWED_BY", "property": "state", "operator": "=", "value": "APPROVED"}
        ],
        dateRangeFilters=[
            {
                "scope": "node",
                "label": "Person",
                "property": "created_at",
                "from": "2025-01-01",
                "to": "2025-12-31",
            }
        ],
    )

    query, params = build_filtered_cypher_query(request)

    assert "CALL {" in query
    assert "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 500" in query
    assert "WHERE" in query
    assert "labels(n)" in query
    assert "type(r) IN $relationship_type_filters" in query
    assert "toString(n[$node_prop_key_0]) CONTAINS" in query
    assert "r[$rel_prop_key_0] = $rel_prop_val_0" in query
    assert "toString(n[$date_prop_key_0]) >= $date_start_0" in query
    assert " OR " in query

    assert params["node_type_filters"] == ["Person"]
    assert params["relationship_type_filters"] == ["WORKS_ON"]
    assert params["node_prop_key_0"] == "name"
    assert params["node_prop_val_0"] == "ali"
    assert params["rel_prop_key_0"] == "state"
    assert params["rel_prop_val_0"] == "APPROVED"
    assert params["date_prop_key_0"] == "created_at"


def test_build_filtered_cypher_query_without_filters_returns_passthrough_shape():
    """Builder should keep subquery wrapper even when no filters are provided."""
    request = GraphFilterRequest(
        baseQuery="MATCH (n) RETURN n LIMIT 10",
    )

    query, params = build_filtered_cypher_query(request)

    assert "CALL {" in query
    assert "MATCH (n) RETURN n LIMIT 10" in query
    assert "RETURN *" in query
    assert "WHERE" not in query
    assert params == {}


def test_build_filtered_cypher_query_should_not_overconstrain_mismatched_node_labels():
    """Node type and node-label property constraints should be grouped with OR semantics."""
    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m",
        nodeTypeFilters=["Project"],
        nodePropertyFilters=[
            {
                "label": "Person",
                "property": "name",
                "operator": "CONTAINS",
                "value": "ali",
            }
        ],
    )

    query, params = build_filtered_cypher_query(request)

    assert "node_type_filters" in query
    assert "node_group_label_0" in query
    assert " OR " in query


def test_build_filtered_cypher_query_node_mismatch_uses_or_group_shape():
    """Node mismatch should produce separate node groups instead of strict AND constraints."""
    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m",
        nodeTypeFilters=["Project"],
        nodePropertyFilters=[
            {
                "label": "Person",
                "property": "name",
                "operator": "CONTAINS",
                "value": "ali",
            }
        ],
    )

    query, params = build_filtered_cypher_query(request)

    assert "(n IS NOT NULL AND any(lbl IN labels(n) WHERE lbl IN $node_type_filters))" in query
    assert "(n IS NOT NULL AND any(lbl IN labels(n) WHERE lbl = $node_group_label_0)" in query
    assert " OR " in query
    assert params["node_type_filters"] == ["Project"]
    assert params["node_group_label_0"] == "Person"


def test_build_filtered_cypher_query_combines_multiple_node_labels_with_or():
    """Node property filters for different labels should be grouped and ORed."""
    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m",
        nodePropertyFilters=[
            {
                "label": "Person",
                "property": "name",
                "operator": "CONTAINS",
                "value": "ali",
            },
            {
                "label": "Project",
                "property": "status",
                "operator": "=",
                "value": "active",
            },
        ],
    )

    query, params = build_filtered_cypher_query(request)

    assert "node_group_label_0" in query
    assert "node_group_label_1" in query
    assert " OR " in query


def test_build_filtered_cypher_query_relationship_date_range_scope_generates_expected_predicate():
    """Relationship-scoped date range should use relationship type guard and date bounds."""
    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m",
        dateRangeFilters=[
            {
                "scope": "relationship",
                "type": "REVIEWED_BY",
                "property": "reviewed_at",
                "from": "2025-01-01",
                "to": "2025-03-31",
            }
        ],
    )

    query, params = build_filtered_cypher_query(request)

    assert "r IS NOT NULL AND type(r) = $relationship_group_type_0" in query
    assert "toString(r[$date_prop_key_0]) >= $date_start_0" in query
    assert "toString(r[$date_prop_key_0]) <= $date_end_0" in query
    assert params["relationship_group_type_0"] == "REVIEWED_BY"
    assert params["date_prop_key_0"] == "reviewed_at"


def test_build_filtered_cypher_query_should_not_overconstrain_mismatched_relationship_types():
    """Relationship type and relationship property type constraints should use OR grouping."""
    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m",
        relationshipTypeFilters=["WORKS_ON"],
        relationshipPropertyFilters=[
            {
                "type": "REVIEWED_BY",
                "property": "state",
                "operator": "=",
                "value": "APPROVED",
            }
        ],
    )

    query, params = build_filtered_cypher_query(request)

    assert "type(r) IN $relationship_type_filters" in query
    assert "type(r) = $relationship_group_type_0" in query
    assert " OR " in query
    assert params["relationship_type_filters"] == ["WORKS_ON"]
    assert params["relationship_group_type_0"] == "REVIEWED_BY"


def test_build_filtered_cypher_query_should_or_node_property_filters_across_labels():
    """Node property filters for different labels should be OR-grouped by label."""
    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m",
        nodePropertyFilters=[
            {
                "label": "Person",
                "property": "name",
                "operator": "CONTAINS",
                "value": "ali",
            },
            {
                "label": "Project",
                "property": "status",
                "operator": "=",
                "value": "active",
            },
        ],
    )

    query, _ = build_filtered_cypher_query(request)

    assert "node_group_label_0" in query
    assert "node_group_label_1" in query
    assert " OR " in query

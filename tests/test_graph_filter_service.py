"""Unit tests for graph filter service logic."""

import pytest

from app.api.graph.v1.model import (
    GraphFilterRequest,
    GraphNode,
    GraphRelationship,
    GraphResponse,
)
from app.api.graph.v1 import service


@pytest.fixture(autouse=True)
def _mock_pushdown_path(monkeypatch):
    """Keep service tests unit-level by disabling live pushdown execution."""

    def _raise_pushdown_unavailable(*_args, **_kwargs):
        raise RuntimeError("pushdown disabled in service unit tests")

    monkeypatch.setattr(service, "execute_filtered_cypher_query", _raise_pushdown_unavailable)


def _sample_graph_response() -> GraphResponse:
    return GraphResponse(
        nodes=[
            GraphNode(id="n1", labels=["Person"], properties={"name": "Alice", "role": "Engineer", "created_at": "2025-01-05"}),
            GraphNode(id="n2", labels=["Person"], properties={"name": "Bob", "role": "Manager", "created_at": "2025-03-01"}),
            GraphNode(id="n3", labels=["File"], properties={"path": "src/main.py", "language": "Python"}),
        ],
        relationships=[
            GraphRelationship(id="r1", type="WORKS_ON", startNode="n1", endNode="n3", properties={}),
            GraphRelationship(id="r2", type="WORKS_ON", startNode="n2", endNode="n3", properties={}),
            GraphRelationship(id="r3", type="REVIEWED_BY", startNode="n3", endNode="n1", properties={"state": "APPROVED", "created_at": "2025-01-10"}),
        ],
        rawResults=[],
        isGraph=True,
        resultCount=3,
    )


def test_execute_and_filter_query_applies_type_filters(monkeypatch):
    """Should keep only selected node and relationship types."""
    monkeypatch.setattr(service, "execute_and_format_query", lambda _q: _sample_graph_response())

    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100",
        nodeTypeFilters=["Person"],
        relationshipTypeFilters=["WORKS_ON"],
    )

    response = service.execute_and_filter_query(request)

    assert {node.id for node in response.nodes} == {"n1", "n2"}
    assert response.relationships == []
    assert response.metadata.filteredResultCounts == {"nodes": 2, "relationships": 0}


def test_execute_and_filter_query_applies_node_property_filters(monkeypatch):
    """Should apply supported node property filters from registry."""
    monkeypatch.setattr(service, "execute_and_format_query", lambda _q: _sample_graph_response())

    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100",
        nodePropertyFilters=[
            {"label": "Person", "property": "name", "operator": "CONTAINS", "value": "Ali"}
        ],
    )

    response = service.execute_and_filter_query(request)

    assert {node.id for node in response.nodes} == {"n1", "n3"}
    assert {rel.id for rel in response.relationships} == {"r1", "r3"}


def test_execute_and_filter_query_applies_date_range_filters(monkeypatch):
    """Should filter nodes by date range when requested."""
    monkeypatch.setattr(service, "execute_and_format_query", lambda _q: _sample_graph_response())

    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100",
        dateRangeFilters=[
            {
                "scope": "node",
                "label": "Person",
                "property": "created_at",
                "from": "2025-01-01",
                "to": "2025-01-31",
            }
        ],
    )

    response = service.execute_and_filter_query(request)

    assert {node.id for node in response.nodes} == {"n1", "n3"}


def test_execute_and_filter_query_rejects_unsupported_property_filter(monkeypatch):
    """Should reject filters not present in the server registry."""
    monkeypatch.setattr(service, "execute_and_format_query", lambda _q: _sample_graph_response())

    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100",
        nodePropertyFilters=[
            {"label": "Person", "property": "unknown_property", "operator": "=", "value": "x"}
        ],
    )

    try:
        service.execute_and_filter_query(request)
        assert False, "Expected ValueError for unsupported registry property"
    except ValueError as exc:
        assert "Unsupported server-side node property filter" in str(exc)


def test_execute_and_filter_query_enforces_result_limits(monkeypatch):
    """Should truncate responses when resultOptions limits are exceeded."""
    monkeypatch.setattr(service, "execute_and_format_query", lambda _q: _sample_graph_response())

    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100",
        resultOptions={"limitNodes": 1, "limitRelationships": 1, "includeImplicitRelationships": True},
    )

    response = service.execute_and_filter_query(request)

    assert len(response.nodes) == 1
    assert len(response.relationships) == 1
    assert response.metadata.truncated is True
    assert any("Node results were truncated" in warning for warning in response.metadata.warnings)
    assert any("Relationship results were truncated" in warning for warning in response.metadata.warnings)


def test_execute_and_filter_query_adds_soft_element_threshold_warning(monkeypatch):
    """Should add soft warning when filtered graph exceeds 2k elements."""
    large_response = GraphResponse(
        nodes=[
            GraphNode(
                id=f"n{i}",
                labels=["Person"],
                properties={"name": f"Person {i}"},
            )
            for i in range(2101)
        ],
        relationships=[],
        rawResults=[],
        isGraph=True,
        resultCount=2101,
    )
    monkeypatch.setattr(service, "execute_and_format_query", lambda _q: large_response)

    request = GraphFilterRequest(
        baseQuery="MATCH (n) RETURN n LIMIT 5000",
        resultOptions={
            "limitNodes": 5000,
            "limitRelationships": 5000,
            "includeImplicitRelationships": True,
        },
    )
    response = service.execute_and_filter_query(request)

    assert any(
        "moderately high (>2000 elements)" in warning
        for warning in response.metadata.warnings
    )
    assert response.metadata.thresholdStatus.elementSeverity == "soft"
    assert response.metadata.thresholdStatus.recommendedMode == "local"
    assert "element_count_soft" in response.metadata.thresholdStatus.reasons


def test_execute_and_filter_query_adds_payload_threshold_warning(monkeypatch):
    """Should add payload warning when estimated response exceeds 1MB."""
    big_text = "x" * 6000
    payload_heavy_response = GraphResponse(
        nodes=[
            GraphNode(
                id=f"n{i}",
                labels=["File"],
                properties={"path": f"/tmp/{i}", "blob": big_text},
            )
            for i in range(220)
        ],
        relationships=[],
        rawResults=[],
        isGraph=True,
        resultCount=220,
    )
    monkeypatch.setattr(service, "execute_and_format_query", lambda _q: payload_heavy_response)

    request = GraphFilterRequest(baseQuery="MATCH (n) RETURN n LIMIT 500")
    response = service.execute_and_filter_query(request)

    assert any(
        "Estimated payload is high (>1MB)" in warning
        or "Estimated payload is large (>2MB)" in warning
        for warning in response.metadata.warnings
    )
    assert response.metadata.thresholdStatus.payloadSeverity in {"soft", "high"}


def test_execute_and_filter_query_sets_database_recommendation_for_high_threshold(monkeypatch):
    """Should recommend database mode when high threshold is reached."""
    high_volume_response = GraphResponse(
        nodes=[
            GraphNode(
                id=f"n{i}",
                labels=["Person"],
                properties={"name": f"Person {i}"},
            )
            for i in range(5200)
        ],
        relationships=[],
        rawResults=[],
        isGraph=True,
        resultCount=5200,
    )
    monkeypatch.setattr(service, "execute_and_format_query", lambda _q: high_volume_response)

    request = GraphFilterRequest(
        baseQuery="MATCH (n) RETURN n LIMIT 6000",
        resultOptions={
            "limitNodes": 10000,
            "limitRelationships": 5000,
            "includeImplicitRelationships": True,
        },
    )

    response = service.execute_and_filter_query(request)

    assert response.metadata.thresholdStatus.elementSeverity == "high"
    assert response.metadata.thresholdStatus.recommendedMode == "database"
    assert "element_count_high" in response.metadata.thresholdStatus.reasons


def test_execute_and_filter_query_surfaces_pushdown_validation_error(monkeypatch):
    """ValueError from pushdown path should be raised, not silently downgraded to fallback."""

    def _raise_validation_error(*_args, **_kwargs):
        raise ValueError("Unsupported property identifier for query builder: bad-name")

    monkeypatch.setattr(service, "execute_filtered_cypher_query", _raise_validation_error)
    monkeypatch.setattr(
        service,
        "execute_and_format_query",
        lambda _q: (_ for _ in ()).throw(AssertionError("fallback path should not execute")),
    )

    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m",
        nodePropertyFilters=[
            {
                "label": "Person",
                "property": "name",
                "operator": "CONTAINS",
                "value": "Ali",
            }
        ],
    )

    with pytest.raises(ValueError, match="Unsupported property identifier"):
        service.execute_and_filter_query(request)


def test_execute_and_filter_query_surfaces_unexpected_pushdown_exception(monkeypatch):
    """Unexpected pushdown exceptions should propagate rather than silently fallback."""

    def _raise_unexpected(*_args, **_kwargs):
        raise KeyError("unexpected pushdown state")

    monkeypatch.setattr(service, "execute_filtered_cypher_query", _raise_unexpected)
    monkeypatch.setattr(
        service,
        "execute_and_format_query",
        lambda _q: (_ for _ in ()).throw(AssertionError("fallback path should not execute")),
    )

    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m",
        nodePropertyFilters=[
            {
                "label": "Person",
                "property": "name",
                "operator": "CONTAINS",
                "value": "Ali",
            }
        ],
    )

    with pytest.raises(KeyError, match="unexpected pushdown state"):
        service.execute_and_filter_query(request)


def test_execute_and_filter_query_pushdown_path_uses_or_grouped_builder(monkeypatch):
    """Service should use pushdown builder output with OR-grouped node/relationship filters."""
    from app.api.graph.v1.query import build_filtered_cypher_query

    captured_query = {"text": ""}

    def _fake_pushdown(request, timeout):
        query, _ = build_filtered_cypher_query(request)
        captured_query["text"] = query
        return [{"sentinel": 1}]

    monkeypatch.setattr(service, "execute_filtered_cypher_query", _fake_pushdown)
    monkeypatch.setattr(
        service,
        "_format_query_results",
        lambda raw_results, include_implicit_relationships: _sample_graph_response(),
    )
    monkeypatch.setattr(
        service,
        "execute_and_format_query",
        lambda _q: (_ for _ in ()).throw(AssertionError("fallback path should not execute")),
    )

    request = GraphFilterRequest(
        baseQuery="MATCH (n)-[r]->(m) RETURN n, r, m",
        nodeTypeFilters=["Project"],
        relationshipTypeFilters=["WORKS_ON"],
        nodePropertyFilters=[
            {"label": "Person", "property": "name", "operator": "CONTAINS", "value": "Ali"}
        ],
        relationshipPropertyFilters=[
            {"type": "REVIEWED_BY", "property": "state", "operator": "=", "value": "APPROVED"}
        ],
    )

    response = service.execute_and_filter_query(request)

    query_text = captured_query["text"]
    assert query_text
    assert "node_type_filters" in query_text
    assert "relationship_type_filters" in query_text
    assert "node_group_label_0" in query_text
    assert "relationship_group_type_0" in query_text
    assert " OR " in query_text
    assert not any("pushdown query-builder path was not applied" in w for w in response.metadata.warnings)

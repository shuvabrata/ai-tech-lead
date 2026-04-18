"""Unit tests for graph filter service logic."""

from app.api.graph.v1.model import (
    GraphFilterRequest,
    GraphNode,
    GraphRelationship,
    GraphResponse,
)
from app.api.graph.v1 import service


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
    assert len(response.metadata.warnings) == 2

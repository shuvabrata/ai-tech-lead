"""Unit tests for graph filter metadata service logic."""

from app.api.graph.v1 import service
from app.api.graph.v1.model import GraphNode, GraphRelationship, GraphResponse


def _sample_graph_response() -> GraphResponse:
    return GraphResponse(
        nodes=[
            GraphNode(
                id="n1",
                labels=["Person", "Contributor"],
                properties={
                    "name": "Alice",
                    "email": "alice@example.com",
                    "custom_score": 42,
                },
            ),
            GraphNode(
                id="n2",
                labels=["Issue"],
                properties={
                    "status": "In Progress",
                    "created_at": "2025-01-10",
                },
            ),
        ],
        relationships=[
            GraphRelationship(
                id="r1",
                type="REVIEWED_BY",
                startNode="n1",
                endNode="n2",
                properties={"state": "APPROVED", "reviewed_at": "2025-01-12"},
            )
        ],
        rawResults=[],
        isGraph=True,
        resultCount=2,
    )


def test_get_graph_filter_metadata_without_source_query_uses_registry_only():
    """Should return registry metadata with no discovery when no base query is provided."""
    response = service.get_graph_filter_metadata(base_query=None)

    assert response.sourceQueryApplied is False
    assert response.discovered.nodeLabels == []
    assert response.discovered.relationshipTypes == []

    assert "Person" in response.mergedNodeProperties
    assert "name" in response.mergedNodeProperties["Person"]
    assert response.mergedNodeProperties["Person"]["name"].serverFilterable is True


def test_get_graph_filter_metadata_merges_discovery_and_registry(monkeypatch):
    """Should include discovered-only props and mark registry-backed properties as server-filterable."""
    monkeypatch.setattr(service, "execute_and_format_query", lambda _q: _sample_graph_response())

    response = service.get_graph_filter_metadata(base_query="MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100")

    assert response.sourceQueryApplied is True
    assert "Person" in response.discovered.nodeLabels
    assert "REVIEWED_BY" in response.discovered.relationshipTypes

    # Registry-backed property: discovered + server filterable
    person_name = response.mergedNodeProperties["Person"]["name"]
    assert person_name.discovered is True
    assert person_name.serverFilterable is True
    assert person_name.type == "string"

    # Discovered-only property: local only, not server filterable
    custom_score = response.mergedNodeProperties["Person"]["custom_score"]
    assert custom_score.discovered is True
    assert custom_score.serverFilterable is False
    assert custom_score.localFilterable is True
    assert custom_score.type == "number"

    # Label only found in discovery should still appear
    assert "Contributor" in response.mergedNodeProperties
    assert "name" in response.mergedNodeProperties["Contributor"]


def test_get_graph_filter_metadata_rejects_non_graph_base_query(monkeypatch):
    """Should fail if base query does not return graph payload."""
    tabular_response = GraphResponse(
        nodes=[],
        relationships=[],
        rawResults=[{"count": 2}],
        isGraph=False,
        resultCount=1,
    )
    monkeypatch.setattr(service, "execute_and_format_query", lambda _q: tabular_response)

    try:
        service.get_graph_filter_metadata(base_query="MATCH (n) RETURN count(n) as count")
        assert False, "Expected ValueError for non-graph baseQuery"
    except ValueError as exc:
        assert "must return graph data" in str(exc)

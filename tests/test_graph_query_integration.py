"""Pytest integration tests for graph API query module.

These tests assume Neo4j server is running and accessible.
Run with: pytest tests/test_graph_query_integration.py -v
"""

import pytest

from app.api.graph.v1.query import execute_cypher_query
from app.settings import settings


pytestmark = [pytest.mark.integration, pytest.mark.neo4j]


@pytest.mark.skipif(
    not settings.NEO4J_ENABLED,
    reason="Neo4j is not enabled (NEO4J_ENABLED=false)"
)
class TestQueryExecution:
    """Integration tests for query execution against real Neo4j."""

    def test_execute_simple_query(self):
        """Test executing a simple query returns results."""
        query = "MATCH (n) RETURN n LIMIT 5"
        results = execute_cypher_query(query, timeout=10)

        assert isinstance(results, list)
        assert len(results) <= 5

    def test_execute_relationship_query(self):
        """Test executing query with relationships."""
        query = "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 2"
        results = execute_cypher_query(query, timeout=10)

        assert isinstance(results, list)

        if results:
            record = results[0]
            assert "n" in record
            assert "r" in record
            assert "m" in record

            node = record["n"]
            assert hasattr(node, "element_id")
            assert hasattr(node, "labels")

            rel = record["r"]
            assert hasattr(rel, "element_id")
            assert hasattr(rel, "type")
            assert hasattr(rel, "start_node")
            assert hasattr(rel, "end_node")

    def test_execute_query_with_no_results(self):
        """Test executing query that returns no results."""
        query = "MATCH (n:NonExistentLabelXYZ123) RETURN n"
        results = execute_cypher_query(query, timeout=10)

        assert isinstance(results, list)
        assert len(results) == 0

    def test_execute_query_with_aggregation(self):
        """Test executing query with aggregation functions."""
        query = "MATCH (n) RETURN count(n) as nodeCount"
        results = execute_cypher_query(query, timeout=10)

        assert isinstance(results, list)
        assert len(results) == 1
        assert "nodeCount" in results[0]
        assert isinstance(results[0]["nodeCount"], int)

    def test_execute_query_with_properties(self):
        """Test that node properties are accessible."""
        query = """
        MATCH (n)
        WHERE n.name IS NOT NULL
        RETURN n LIMIT 1
        """
        results = execute_cypher_query(query, timeout=10)

        if results:
            node = results[0]["n"]
            props = dict(node)
            assert "name" in props
            assert isinstance(props["name"], str)

    def test_syntax_error_handling(self):
        """Test that syntax errors are caught and reported."""
        query = "INVALID CYPHER SYNTAX HERE"

        with pytest.raises(ValueError) as exc_info:
            execute_cypher_query(query, timeout=5)

        assert "syntax error" in str(exc_info.value).lower()

    def test_timeout_setting(self):
        """Test that timeout parameter is accepted."""
        query = "MATCH (n) RETURN n LIMIT 1"
        results = execute_cypher_query(query, timeout=5)
        assert isinstance(results, list)

    def test_neo4j_disabled_raises_error(self, monkeypatch):
        """Test that error is raised when Neo4j is disabled."""
        monkeypatch.setattr(settings, "NEO4J_ENABLED", False)

        query = "MATCH (n) RETURN n LIMIT 1"

        with pytest.raises(RuntimeError) as exc_info:
            execute_cypher_query(query, timeout=5)

        assert "not enabled" in str(exc_info.value).lower()

    def test_connection_error_handling(self, monkeypatch):
        """Test that connection errors are handled gracefully."""
        original_uri = settings.NEO4J_URI
        monkeypatch.setattr(settings, "NEO4J_URI", "bolt://invalid-host:7687")

        query = "MATCH (n) RETURN n LIMIT 1"

        with pytest.raises(RuntimeError) as exc_info:
            execute_cypher_query(query, timeout=5)

        monkeypatch.setattr(settings, "NEO4J_URI", original_uri)

        assert "unable to connect" in str(exc_info.value).lower()

    def test_query_returns_multiple_types(self):
        """Test query returning different data types."""
        query = """
        RETURN
            'text' as string_val,
            123 as int_val,
            3.14 as float_val,
            true as bool_val,
            [1, 2, 3] as list_val,
            {key: 'value'} as map_val
        """
        results = execute_cypher_query(query, timeout=10)

        assert len(results) == 1
        record = results[0]

        assert record["string_val"] == "text"
        assert record["int_val"] == 123
        assert record["float_val"] == 3.14
        assert record["bool_val"] is True
        assert record["list_val"] == [1, 2, 3]
        assert record["map_val"] == {"key": "value"}


@pytest.mark.skipif(
    not settings.NEO4J_ENABLED,
    reason="Neo4j is not enabled"
)
def test_execute_with_parameters_placeholder():
    """Test executing query with literal values (parameters are not exposed in this API)."""
    query = "RETURN 'test' as value"
    results = execute_cypher_query(query, timeout=5)

    assert len(results) == 1
    assert results[0]["value"] == "test"

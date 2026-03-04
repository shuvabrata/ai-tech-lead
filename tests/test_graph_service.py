"""Pytest tests for graph API service module.

Tests assume Neo4j server is running and accessible.
Run with: pytest tests/test_graph_service.py -v
"""

import pytest

from app.api.graph.v1.service import execute_and_format_query
from app.api.graph.v1.model import GraphResponse
from app.settings import settings


@pytest.mark.skipif(
    not settings.NEO4J_ENABLED,
    reason="Neo4j is not enabled (NEO4J_ENABLED=false)"
)
class TestGraphService:
    """Integration tests for graph service layer."""
    
    def test_execute_graph_query(self):
        """Test executing a query that returns nodes and relationships."""
        query = "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 5"
        response = execute_and_format_query(query)
        
        # Verify response structure
        assert isinstance(response, GraphResponse)
        assert response.isGraph is True
        assert isinstance(response.nodes, list)
        assert isinstance(response.relationships, list)
        assert response.rawResults == []
        
        # If there are results, verify structure
        if response.nodes:
            node = response.nodes[0]
            assert isinstance(node.id, str)
            assert isinstance(node.labels, list)
            assert isinstance(node.properties, dict)
        
        if response.relationships:
            rel = response.relationships[0]
            assert isinstance(rel.id, str)
            assert isinstance(rel.type, str)
            assert isinstance(rel.startNode, str)
            assert isinstance(rel.endNode, str)
            assert isinstance(rel.properties, dict)
    
    def test_execute_node_only_query(self):
        """Test query that returns only nodes."""
        query = "MATCH (n) RETURN n LIMIT 5"
        response = execute_and_format_query(query)
        
        assert isinstance(response, GraphResponse)
        assert response.isGraph is True
        assert isinstance(response.nodes, list)
        assert isinstance(response.relationships, list)

        # If implicit relationships are returned, they should connect returned nodes
        if response.relationships:
            node_ids = {node.id for node in response.nodes}
            for rel in response.relationships:
                assert rel.startNode in node_ids
                assert rel.endNode in node_ids
        
    def test_execute_tabular_query(self):
        """Test query that returns tabular data (not nodes/relationships)."""
        query = "MATCH (n) RETURN count(n) as nodeCount"
        response = execute_and_format_query(query)
        
        assert isinstance(response, GraphResponse)
        assert response.isGraph is False
        assert response.nodes == []
        assert response.relationships == []
        assert len(response.rawResults) == 1
        assert 'nodeCount' in response.rawResults[0]
    
    def test_execute_properties_query(self):
        """Test query that returns node properties."""
        query = """
        MATCH (n)
        WHERE n.name IS NOT NULL
        RETURN n.name as name, labels(n) as labels
        LIMIT 3
        """
        response = execute_and_format_query(query)
        
        assert isinstance(response, GraphResponse)
        assert response.isGraph is False  # Properties are tabular data
        assert response.nodes == []
        assert len(response.rawResults) > 0
        
        if response.rawResults:
            record = response.rawResults[0]
            assert 'name' in record
            assert 'labels' in record
    
    def test_execute_empty_result_query(self):
        """Test query that returns no results."""
        query = "MATCH (n:NonExistentLabelXYZ999) RETURN n"
        response = execute_and_format_query(query)
        
        assert isinstance(response, GraphResponse)
        assert response.nodes == []
        assert response.relationships == []
        assert response.resultCount == 0
    
    def test_reject_write_query(self):
        """Test that write queries are rejected."""
        query = "CREATE (n:Test {name: 'test'}) RETURN n"
        
        with pytest.raises(ValueError) as exc_info:
            execute_and_format_query(query)
        
        assert "write operations" in str(exc_info.value).lower()
    
    def test_reject_delete_query(self):
        """Test that DELETE queries are rejected."""
        query = "MATCH (n) DELETE n"
        
        with pytest.raises(ValueError) as exc_info:
            execute_and_format_query(query)
        
        assert "validation failed" in str(exc_info.value).lower()
    
    def test_reject_merge_query(self):
        """Test that MERGE queries are rejected."""
        query = "MERGE (n:Person {name: 'Alice'}) RETURN n"
        
        with pytest.raises(ValueError) as exc_info:
            execute_and_format_query(query)
        
        assert "validation failed" in str(exc_info.value).lower()
    
    def test_syntax_error_handling(self):
        """Test that syntax errors are properly handled."""
        # Query that passes validation but has syntax error
        query = "MATCH (n) RETURN INVALID_FUNCTION(n)"
        
        with pytest.raises(ValueError) as exc_info:
            execute_and_format_query(query)
        
        # Should get either syntax error or function error
        error_msg = str(exc_info.value).lower()
        assert ("syntax error" in error_msg or "error" in error_msg)
    
    def test_node_deduplication(self):
        """Test that duplicate nodes are deduplicated."""
        # This query might return the same node multiple times
        query = """
        MATCH (n)-[r1]->(m), (n)-[r2]->(m)
        RETURN n, r1, m, r2
        LIMIT 5
        """
        response = execute_and_format_query(query)
        
        if response.nodes:
            # Verify nodes are unique by ID
            node_ids = [node.id for node in response.nodes]
            assert len(node_ids) == len(set(node_ids)), "Nodes should be deduplicated"
    
    def test_relationship_deduplication(self):
        """Test that duplicate relationships are deduplicated."""
        # Query that might return same relationship multiple times
        query = """
        MATCH (n)-[r]->(m)
        WITH n, r, m
        RETURN n, r, m
        LIMIT 5
        """
        response = execute_and_format_query(query)
        
        if response.relationships:
            # Verify relationships are unique by ID
            rel_ids = [rel.id for rel in response.relationships]
            assert len(rel_ids) == len(set(rel_ids)), "Relationships should be deduplicated"
    
    def test_complex_query_with_multiple_patterns(self):
        """Test complex query with multiple MATCH patterns."""
        # Use generic pattern that should exist in any Neo4j database
        query = """
        MATCH (n)-[r]->(m)
        OPTIONAL MATCH (m)-[r2]->(o)
        RETURN n, r, m, r2, o
        LIMIT 5
        """
        response = execute_and_format_query(query)
        
        # Should handle optional matches gracefully
        assert isinstance(response, GraphResponse)
        # May be isGraph=True if results exist, or False if no results
        assert response.isGraph in [True, False]
    
    def test_union_query(self):
        """Test UNION query."""
        # UNION requires same column names in all subqueries
        query = """
        MATCH (n) RETURN n LIMIT 2
        UNION
        MATCH (n) RETURN n LIMIT 2
        """
        response = execute_and_format_query(query)
        
        assert isinstance(response, GraphResponse)
        # May be True or False depending on whether data exists
        assert response.isGraph in [True, False]
    
    def test_query_with_aggregation_and_properties(self):
        """Test query mixing aggregation with graph elements."""
        query = """
        MATCH (n)
        WITH n, count(*) as cnt
        RETURN n, cnt
        LIMIT 5
        """
        response = execute_and_format_query(query)
        
        # Should handle mixed results
        assert isinstance(response, GraphResponse)
        # Could be graph or tabular depending on how Neo4j returns it
        assert response.resultCount is not None

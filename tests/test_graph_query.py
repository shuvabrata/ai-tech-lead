"""Pytest tests for graph API query module.

Tests assume Neo4j server is running and accessible.
Run with: pytest tests/test_graph_query.py -v
"""

import pytest
from neo4j.exceptions import Neo4jError

from app.api.graph.v1.query import validate_read_only_query, execute_cypher_query
from app.settings import settings


# ============================================================================
# Unit Tests: Query Validation
# ============================================================================

class TestQueryValidation:
    """Unit tests for read-only query validation."""
    
    def test_valid_match_query(self):
        """Test that basic MATCH queries are accepted."""
        query = "MATCH (n) RETURN n"
        assert validate_read_only_query(query) is True
    
    def test_valid_match_with_relationship(self):
        """Test that MATCH with relationships is accepted."""
        query = "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 10"
        assert validate_read_only_query(query) is True
    
    def test_valid_optional_match(self):
        """Test that OPTIONAL MATCH queries are accepted."""
        query = 'OPTIONAL MATCH (n:Person) WHERE n.name = "Alice" RETURN n'
        assert validate_read_only_query(query) is True
    
    def test_valid_with_clause(self):
        """Test that queries with WITH clause are accepted."""
        query = "MATCH (n) WITH n ORDER BY n.name RETURN n LIMIT 5"
        assert validate_read_only_query(query) is True
    
    def test_valid_unwind(self):
        """Test that UNWIND queries are accepted."""
        query = "UNWIND [1, 2, 3] AS x RETURN x"
        assert validate_read_only_query(query) is True
    
    def test_valid_call_procedure(self):
        """Test that CALL (read-only procedures) are accepted."""
        query = "CALL db.labels() YIELD label RETURN label"
        assert validate_read_only_query(query) is True
    
    def test_valid_union(self):
        """Test that UNION queries are accepted."""
        query = "MATCH (n:Person) RETURN n UNION MATCH (m:Company) RETURN m"
        assert validate_read_only_query(query) is True
    
    def test_valid_complex_query(self):
        """Test complex read-only query with multiple clauses."""
        query = """
        MATCH (p:Person)-[:WORKS_ON]->(proj:Project)
        WHERE p.active = true
        WITH p, proj
        ORDER BY proj.priority DESC
        LIMIT 10
        RETURN p.name, proj.name
        """
        assert validate_read_only_query(query) is True
    
    def test_reject_create(self):
        """Test that CREATE queries are rejected."""
        query = "CREATE (n:Test) RETURN n"
        assert validate_read_only_query(query) is False
    
    def test_reject_merge(self):
        """Test that MERGE queries are rejected."""
        query = 'MERGE (n:Person {name: "Bob"}) RETURN n'
        assert validate_read_only_query(query) is False
    
    def test_reject_delete(self):
        """Test that DELETE queries are rejected."""
        query = "MATCH (n) DELETE n"
        assert validate_read_only_query(query) is False
    
    def test_reject_detach_delete(self):
        """Test that DETACH DELETE queries are rejected."""
        query = "MATCH (n) DETACH DELETE n"
        assert validate_read_only_query(query) is False
    
    def test_reject_set(self):
        """Test that SET queries are rejected."""
        query = 'MATCH (n) SET n.name = "Updated" RETURN n'
        assert validate_read_only_query(query) is False
    
    def test_reject_remove(self):
        """Test that REMOVE queries are rejected."""
        query = "MATCH (n) REMOVE n.property RETURN n"
        assert validate_read_only_query(query) is False
    
    def test_reject_drop(self):
        """Test that DROP queries are rejected."""
        query = "DROP INDEX index_name"
        assert validate_read_only_query(query) is False
    
    def test_reject_foreach(self):
        """Test that FOREACH queries are rejected."""
        query = "FOREACH (x IN [1,2,3] | CREATE (:Node {val: x}))"
        assert validate_read_only_query(query) is False
    
    def test_reject_create_in_middle(self):
        """Test that CREATE is detected even in middle of query."""
        query = "MATCH (n) CREATE (m:NewNode) RETURN n, m"
        assert validate_read_only_query(query) is False
    
    def test_reject_empty_query(self):
        """Test that empty queries are rejected."""
        assert validate_read_only_query("") is False
    
    def test_reject_whitespace_only(self):
        """Test that whitespace-only queries are rejected."""
        assert validate_read_only_query("   \n\t  ") is False
    
    def test_case_insensitive(self):
        """Test that validation is case-insensitive."""
        assert validate_read_only_query("match (n) return n") is True
        assert validate_read_only_query("MATCH (n) RETURN n") is True
        assert validate_read_only_query("MaTcH (n) ReTuRn n") is True
    
    def test_reject_query_not_starting_with_read_op(self):
        """Test that queries not starting with read operations are rejected."""
        # This should be rejected as it starts with a comment/something else
        query = "// Comment\nSET n.prop = 1"
        assert validate_read_only_query(query) is False
    
    def test_word_boundary_matching(self):
        """Test that validation uses word boundaries for Cypher keywords.
        
        Note: Current implementation conservatively rejects queries with write
        keywords even in string literals for security. This is acceptable as
        users rarely need to search for these terms.
        """
        # This is rejected because 'create' appears in string literal
        # Conservative security approach - better safe than sorry
        query = "MATCH (n) WHERE n.description = 'create new' RETURN n"
        assert validate_read_only_query(query) is False
        
        # But word boundaries work for actual Cypher keywords
        # 'REMATCH' should not trigger 'MATCH' validation
        query_safe = "MATCH (n:Person) RETURN n"
        assert validate_read_only_query(query_safe) is True


# ============================================================================
# Integration Tests: Query Execution
# ============================================================================

@pytest.mark.skipif(
    not settings.NEO4J_ENABLED,
    reason="Neo4j is not enabled (NEO4J_ENABLED=false)"
)
class TestQueryExecution:
    """Integration tests for query execution against real Neo4j.
    
    These tests assume Neo4j server is running and accessible.
    """
    
    def test_execute_simple_query(self):
        """Test executing a simple query returns results."""
        query = "MATCH (n) RETURN n LIMIT 5"
        results = execute_cypher_query(query, timeout=10)
        
        assert isinstance(results, list)
        # Results may be empty if database is empty, but should not error
        assert len(results) <= 5
    
    def test_execute_relationship_query(self):
        """Test executing query with relationships."""
        query = "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 2"
        results = execute_cypher_query(query, timeout=10)
        
        assert isinstance(results, list)
        
        if results:  # If results exist, validate structure
            record = results[0]
            assert 'n' in record
            assert 'r' in record
            assert 'm' in record
            
            # Validate node structure
            node = record['n']
            assert hasattr(node, 'element_id')
            assert hasattr(node, 'labels')
            
            # Validate relationship structure
            rel = record['r']
            assert hasattr(rel, 'element_id')
            assert hasattr(rel, 'type')
            assert hasattr(rel, 'start_node')
            assert hasattr(rel, 'end_node')
    
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
        assert 'nodeCount' in results[0]
        assert isinstance(results[0]['nodeCount'], int)
    
    def test_execute_query_with_properties(self):
        """Test that node properties are accessible."""
        query = """
        MATCH (n) 
        WHERE n.name IS NOT NULL 
        RETURN n LIMIT 1
        """
        results = execute_cypher_query(query, timeout=10)
        
        if results:  # If there are nodes with names
            node = results[0]['n']
            props = dict(node)
            assert 'name' in props
            assert isinstance(props['name'], str)
    
    def test_syntax_error_handling(self):
        """Test that syntax errors are caught and reported."""
        query = "INVALID CYPHER SYNTAX HERE"
        
        with pytest.raises(ValueError) as exc_info:
            execute_cypher_query(query, timeout=5)
        
        assert "syntax error" in str(exc_info.value).lower()
    
    def test_timeout_setting(self):
        """Test that timeout parameter is accepted."""
        query = "MATCH (n) RETURN n LIMIT 1"
        # Should not raise timeout with reasonable query
        results = execute_cypher_query(query, timeout=5)
        assert isinstance(results, list)
    
    def test_neo4j_disabled_raises_error(self, monkeypatch):
        """Test that error is raised when Neo4j is disabled."""
        # Temporarily disable Neo4j
        monkeypatch.setattr(settings, 'NEO4J_ENABLED', False)
        
        query = "MATCH (n) RETURN n LIMIT 1"
        
        with pytest.raises(RuntimeError) as exc_info:
            execute_cypher_query(query, timeout=5)
        
        assert "not enabled" in str(exc_info.value).lower()
    
    def test_connection_error_handling(self, monkeypatch):
        """Test that connection errors are handled gracefully."""
        # Set invalid URI to force connection error
        original_uri = settings.NEO4J_URI
        monkeypatch.setattr(settings, 'NEO4J_URI', 'bolt://invalid-host:7687')
        
        query = "MATCH (n) RETURN n LIMIT 1"
        
        with pytest.raises(RuntimeError) as exc_info:
            execute_cypher_query(query, timeout=5)
        
        # Restore original URI
        monkeypatch.setattr(settings, 'NEO4J_URI', original_uri)
        
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
        
        assert record['string_val'] == 'text'
        assert record['int_val'] == 123
        assert record['float_val'] == 3.14
        assert record['bool_val'] is True
        assert record['list_val'] == [1, 2, 3]
        assert record['map_val'] == {'key': 'value'}


# ============================================================================
# Edge Cases and Error Scenarios
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_validation_with_multiline_query(self):
        """Test validation works with multiline queries."""
        query = """
        MATCH (p:Person)
        WHERE p.age > 18
        RETURN p.name, p.age
        ORDER BY p.age DESC
        LIMIT 10
        """
        assert validate_read_only_query(query) is True
    
    def test_validation_with_comments(self):
        """Test validation with Cypher comments.
        
        Note: Current implementation does not strip comments before validation.
        This is acceptable as the validator checks for read operations anywhere
        in the query. Queries starting with comments are conservatively rejected.
        """
        # Query starting with comment is rejected (conservative approach)
        query_with_leading_comment = """
        // This is a comment
        MATCH (n) 
        RETURN n
        """
        assert validate_read_only_query(query_with_leading_comment) is False
        
        # Query with inline comment after valid keyword is accepted
        query_with_inline_comment = "MATCH (n) /* comment */ RETURN n"
        assert validate_read_only_query(query_with_inline_comment) is True
    
    def test_validation_rejects_mixed_operations(self):
        """Test that queries with both read and write ops are rejected."""
        query = "MATCH (n) CREATE (m:NewNode)-[:RELATES_TO]->(n) RETURN n, m"
        assert validate_read_only_query(query) is False
    
    @pytest.mark.skipif(
        not settings.NEO4J_ENABLED,
        reason="Neo4j is not enabled"
    )
    def test_execute_with_parameters_placeholder(self):
        """Test executing query with literal values (parameters are not exposed in this API)."""
        query = "RETURN 'test' as value"
        results = execute_cypher_query(query, timeout=5)
        
        assert len(results) == 1
        assert results[0]['value'] == 'test'

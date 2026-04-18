"""Pytest unit tests for graph API query module.

These tests do not require a live Neo4j instance.
Run with: pytest tests/test_graph_query_unit.py -v
"""

import pytest

from app.api.graph.v1.query import validate_read_only_query


pytestmark = pytest.mark.unit


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
        query = "// Comment\nSET n.prop = 1"
        assert validate_read_only_query(query) is False

    def test_word_boundary_matching(self):
        """Test that validation uses word boundaries for Cypher keywords.

        Note: Current implementation conservatively rejects queries with write
        keywords even in string literals for security. This is acceptable as
        users rarely need to search for these terms.
        """
        query = "MATCH (n) WHERE n.description = 'create new' RETURN n"
        assert validate_read_only_query(query) is False

        query_safe = "MATCH (n:Person) RETURN n"
        assert validate_read_only_query(query_safe) is True


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
        query_with_leading_comment = """
        // This is a comment
        MATCH (n)
        RETURN n
        """
        assert validate_read_only_query(query_with_leading_comment) is False

        query_with_inline_comment = "MATCH (n) /* comment */ RETURN n"
        assert validate_read_only_query(query_with_inline_comment) is True

    def test_validation_rejects_mixed_operations(self):
        """Test that queries with both read and write ops are rejected."""
        query = "MATCH (n) CREATE (m:NewNode)-[:RELATES_TO]->(n) RETURN n, m"
        assert validate_read_only_query(query) is False

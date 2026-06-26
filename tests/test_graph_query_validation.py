"""Tests for Cypher query validation."""

import pytest
from app.api.graph.v1.query import validate_read_only_query


@pytest.mark.unit
class TestValidateReadOnlyQuery:
    """Tests for the read-only Cypher query validator."""

    @pytest.mark.parametrize("query", [
        "MATCH (n) RETURN n",
        "MATCH (n)-[r]->(m) RETURN n, r, m",
        "OPTIONAL MATCH (n) RETURN n",
        "CALL db.labels() YIELD label RETURN label",
        "WITH 1 AS x RETURN x",
        "UNWIND [1,2,3] AS x RETURN x",
    ])
    def test_valid_read_queries(self, query):
        assert validate_read_only_query(query) is True

    @pytest.mark.parametrize("query,keyword", [
        ("CREATE (n:Test) RETURN n", "CREATE"),
        ("MATCH (n) DELETE n", "DELETE"),
        ("MATCH (n) DETACH DELETE n", "DETACH"),
        ("MATCH (n) SET n.x = 1", "SET"),
        ("MERGE (n:Test) RETURN n", "MERGE"),
        ("MATCH (n) REMOVE n.x", "REMOVE"),
        ("DROP INDEX idx", "DROP"),
    ])
    def test_rejects_write_queries(self, query, keyword):
        assert validate_read_only_query(query) is False

    def test_rejects_empty_query(self):
        assert validate_read_only_query("") is False
        assert validate_read_only_query("   ") is False

    def test_rejects_apoc_write_procedures(self):
        assert validate_read_only_query("CALL apoc.cypher.doIt('CREATE (n)')") is False

"""Unit tests for query limiter behavior in QueryExecutor."""

from tests.neo4j_queries.helpers.query_executor import QueryExecutor


def _executor() -> QueryExecutor:
    """Create executor without a live Neo4j session for pure helper tests."""
    return QueryExecutor(session=None)


def test_add_limit_appends_for_regular_match_query():
    executor = _executor()

    query = "MATCH (n) RETURN n"
    limited = executor._add_limit_if_missing(query, limit=100)

    assert limited.endswith("\nLIMIT 100")


def test_add_limit_skips_when_limit_already_present():
    executor = _executor()

    query = "MATCH (n) RETURN n LIMIT 100"
    limited = executor._add_limit_if_missing(query, limit=10)

    assert limited == query


def test_add_limit_skips_for_standalone_call_query():
    executor = _executor()

    query = "CALL db.schema.visualization()"
    limited = executor._add_limit_if_missing(query, limit=10)

    assert limited == query


def test_add_limit_appends_for_call_query_with_return_pipeline():
    executor = _executor()

    query = "CALL db.labels() YIELD label RETURN label"
    limited = executor._add_limit_if_missing(query, limit=10)

    assert limited.endswith("\nLIMIT 10")

"""Integration test: verify Neo4j and Elasticsearch document counts match per index.

Requires live Neo4j and Elasticsearch instances.  Run with::

    pytest -m "integration and elasticsearch and neo4j" tests/test_es_neo4j_parity.py -v

Environment variables (defaults match local docker-compose setup)
-----------------------------------------------------------------
ELASTICSEARCH_URL   Default: ``http://localhost:9200``
ELASTIC_PASSWORD    Default: empty (security disabled)
NEO4J_URI           Default: ``bolt://localhost:7687``
NEO4J_USERNAME      Default: ``neo4j``
NEO4J_PASSWORD      Default: ``password123``
"""

from __future__ import annotations

import os

import pytest
from elasticsearch import Elasticsearch
from neo4j import GraphDatabase

from app.scripts.create_es_indexes import MANAGED_INDEXES, _index_name


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def es_client():
    url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
    password = os.environ.get("ELASTIC_PASSWORD", "")
    client = Elasticsearch(url, basic_auth=("elastic", password)) if password else Elasticsearch(url)
    yield client


@pytest.fixture(scope="module")
def neo4j_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password123")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    yield driver
    driver.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _neo4j_count(driver, source: str, entity_type: str) -> int:
    """Return the number of *full* Neo4j nodes for a given source + entity_type.

    Stub nodes are unconditionally excluded from the count for all entity types.
    A stub node is created by the sync module when it writes a relationship edge
    whose target entity does not yet exist in Neo4j — the module MERGEs a bare
    placeholder node containing only the ``id`` property so the relationship can
    be stored.  No ``ActivitySignal`` is ever published for these placeholders,
    so the consumer never indexes them into Elasticsearch.  Including stubs in
    the Neo4j count would produce a false parity failure (Neo4j count > ES count)
    even when the pipeline is working correctly.

    A node is considered a stub when it has exactly one property (``id``) and
    nothing else — no ``source``, no ``summary``, no ``status``, etc.  No
    legitimate fully-indexed entity node should ever have only ``id``, so this
    filter is safe to apply universally rather than per entity type.

    Confirmed stub-forming entity types observed after a fresh full scan:
    - ``jira / Issue``  — Issues referenced by Epics, Sprints, or other Issues
                          that fall outside the producer's fetch scope.
    - ``jira / Person`` — Persons referenced in issue assignments / reporters
                          that were not directly emitted as Person signals.
    Other entity types may form stubs in the future; the unconditional filter
    handles them automatically without requiring code changes here.
    """
    prefix = f"{source}::{entity_type}::"
    # Exclude stub nodes (only 'id' property set) for all entity types.
    # See docstring for the rationale behind making this unconditional.
    with driver.session() as session:
        result = session.run(
            f"MATCH (n:{entity_type}) "
            "WHERE n.id STARTS WITH $prefix "
            "AND size(keys(n)) > 1 "
            "RETURN count(n) AS cnt",
            prefix=prefix,
        )
        record = result.single()
        return record["cnt"] if record else 0


def _es_count(client: Elasticsearch, index: str) -> int:
    """Return the number of documents in an ES index (0 if the index doesn't exist)."""
    try:
        resp = client.count(index=index)
        return resp["count"]
    except Exception:  # pylint: disable=broad-except
        return 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.neo4j
@pytest.mark.parametrize("source,entity_type", MANAGED_INDEXES)
def test_es_neo4j_count_parity(source, entity_type, es_client, neo4j_driver):
    """ES document count must equal Neo4j node count for each (source, entity_type) pair."""
    index = _index_name(source, entity_type)
    neo4j_cnt = _neo4j_count(neo4j_driver, source, entity_type)
    es_cnt = _es_count(es_client, index)

    assert es_cnt == neo4j_cnt, (
        f"Count mismatch for {index}: "
        f"Neo4j has {neo4j_cnt} full nodes but ES has {es_cnt} documents. "
        f"Note: stub nodes (relationship-target placeholders with only an 'id' "
        f"property) are excluded from the Neo4j count — see _neo4j_count(). "
        f"Run scripts/reconcile_es.py to sync genuine drift."
    )

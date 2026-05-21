#!/usr/bin/env python3
"""Reconcile Elasticsearch indexes with the live Neo4j graph.

This is a **development / operational utility** — not part of the
production runtime.  Run it manually when you suspect the ES indexes are
out of sync with Neo4j (e.g. after a partial consumer failure, after running
simulation data directly into Neo4j, or after re-setting the ES indexes).

Algorithm
---------
1. For each ``(source, entity_type)`` pair in ``MANAGED_INDEXES``:
   a. Load every node of that type from Neo4j (matched by label + the
      ``source`` property stored on the node).
   b. Upsert each node into the corresponding ES index using
      ``wba_id`` as the document ``_id``.
2. After upserting, query ES for all ``_id`` values in the index and
   delete any that are not present in Neo4j (stale documents).

Usage
-----
Activate the virtual environment, then: if running on the host machine:

    ELASTICSEARCH_URL=http://localhost:9200 \
    NEO4J_URI=bolt://localhost:7687 \
    PYTHONPATH=src python scripts/reconcile_es.py

    Optionally: DRY_RUN=true 

All required connection strings are read from environment variables.

Environment variables
---------------------
ELASTICSEARCH_URL       ES base URL.  Default: ``http://localhost:9200``.
ELASTIC_PASSWORD        ES password.  Leave empty when security is off.
NEO4J_URI               Bolt URI.     Default: ``bolt://localhost:7687``.
NEO4J_USERNAME          Neo4j user.   Default: ``neo4j``.
NEO4J_PASSWORD          Neo4j password.
DRY_RUN                 Set to ``true`` to log deletes without executing them.
"""

from __future__ import annotations

import os
import sys

# Add src/ to path so common/connectors packages are importable when run
# directly from the workspace root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from elasticsearch import Elasticsearch
from neo4j import GraphDatabase
from neo4j.time import Date, DateTime, Time, Duration

from app.scripts.create_es_indexes import MANAGED_INDEXES, _index_name


def _coerce_value(v: object) -> object:
    """Convert Neo4j-native types to JSON-serializable Python types."""
    if isinstance(v, (Date, DateTime)):
        return v.iso_format()
    if isinstance(v, Time):
        return v.iso_format()
    if isinstance(v, Duration):
        return str(v)
    if isinstance(v, list):
        return [_coerce_value(item) for item in v]
    return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_es_client() -> Elasticsearch:
    url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
    password = os.environ.get("ELASTIC_PASSWORD", "")
    if password:
        return Elasticsearch(url, basic_auth=("elastic", password))
    return Elasticsearch(url)


def _build_neo4j_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USERNAME", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password")
    return GraphDatabase.driver(uri, auth=(user, password))


def _neo4j_label(entity_type: str) -> str:
    """Return the Neo4j label for an entity type (labels match entity type names)."""
    return entity_type


def _fetch_neo4j_nodes(session, source: str, entity_type: str) -> dict[str, dict]:
    """Return a dict of {wba_id: properties + relationship_ids} for all nodes of this type + source.

    Relationship IDs are the ``id`` property values of all directly connected
    neighbour nodes, mirroring the ``relationship_ids`` list the consumer builds
    from ``ActivitySignal.relationships``.
    """
    label = _neo4j_label(entity_type)
    prefix = f"{source}::{entity_type}::"
    # Fetch properties and all directly connected neighbour IDs in one query.
    # OPTIONAL MATCH ensures nodes with no relationships are still returned.
    query = (
        f"MATCH (n:{label}) "
        "WHERE n.source = $source OR n.id STARTS WITH $prefix "
        "OPTIONAL MATCH (n)--(neighbour) "
        "WHERE neighbour.id IS NOT NULL "
        "RETURN n.id AS wba_id, properties(n) AS props, "
        "collect(neighbour.id) AS neighbour_ids"
    )
    result = session.run(query, source=source, prefix=prefix)
    nodes: dict[str, dict] = {}
    for record in result:
        wba_id = record["wba_id"]
        if wba_id and wba_id.startswith(prefix):
            props = dict(record["props"])
            # Deduplicate and filter out any None values from the collect().
            neighbour_ids = list({
                nid for nid in record["neighbour_ids"] if nid
            })
            props["_relationship_ids"] = neighbour_ids
            nodes[wba_id] = props
    return nodes


def _build_es_doc_from_neo4j(wba_id: str, props: dict) -> dict:
    """Build an ES document from a Neo4j property map.

    Strips internal Neo4j fields, coerces Neo4j-native temporal types to ISO
    strings, and promotes the ``_relationship_ids`` sentinel key (populated by
    ``_fetch_neo4j_nodes``) to the top-level ``relationship_ids`` field —
    matching the shape the consumer produces from ``ActivitySignal.relationships``.
    """
    # Extract relationship_ids before building the doc (it's stored under a
    # sentinel key prefixed with _ so the k.startswith("_") filter would drop it).
    relationship_ids = props.get("_relationship_ids", [])

    doc: dict = {
        k: _coerce_value(v)
        for k, v in props.items()
        if not k.startswith("_")
    }
    # Ensure wba_id is present (it is the Neo4j id property).
    doc["wba_id"] = wba_id
    # Parse source / entity_type from the canonical key if not already stored.
    if "source" not in doc or "entity_type" not in doc:
        parts = wba_id.split("::")
        if len(parts) >= 2:
            doc.setdefault("source", parts[0])
            doc.setdefault("entity_type", parts[1])
    # Include relationship IDs, matching the consumer's document shape.
    doc["relationship_ids"] = relationship_ids
    return doc


def _scroll_es_ids(client: Elasticsearch, index: str) -> set[str]:
    """Return the set of all document _id values in *index* using the scroll API."""
    ids: set[str] = set()
    try:
        page = client.search(
            index=index,
            body={"query": {"match_all": {}}, "_source": False, "size": 1000},
            scroll="2m",
        )
    except Exception as exc:  # pylint: disable=broad-except
        print(f"    WARN: Could not fetch IDs from {index}: {exc}")
        return ids

    scroll_id = page.get("_scroll_id")
    hits = page.get("hits", {}).get("hits", [])
    while hits:
        for hit in hits:
            ids.add(hit["_id"])
        if not scroll_id:
            break
        try:
            page = client.scroll(scroll_id=scroll_id, scroll="2m")
            scroll_id = page.get("_scroll_id")
            hits = page.get("hits", {}).get("hits", [])
        except Exception as exc:  # pylint: disable=broad-except
            print(f"    WARN: Scroll error for {index}: {exc}")
            break

    if scroll_id:
        try:
            client.clear_scroll(scroll_id=scroll_id)
        except Exception:  # pylint: disable=broad-except
            pass
    return ids


# ---------------------------------------------------------------------------
# Main reconciliation logic
# ---------------------------------------------------------------------------

def reconcile(dry_run: bool = False) -> None:
    """Run the full reconciliation."""
    es = _build_es_client()
    driver = _build_neo4j_driver()

    total_upserted = 0
    total_deleted = 0

    try:
        with driver.session() as session:
            for source, entity_type in MANAGED_INDEXES:
                index = _index_name(source, entity_type)
                print(f"\nReconciling {index} ...")

                # Step 1: load Neo4j nodes.
                neo4j_nodes = _fetch_neo4j_nodes(session, source, entity_type)
                print(f"  Neo4j nodes found: {len(neo4j_nodes)}")

                # Step 2: upsert each Neo4j node into ES.
                upserted = 0
                for wba_id, props in neo4j_nodes.items():
                    doc = _build_es_doc_from_neo4j(wba_id, props)
                    if not dry_run:
                        try:
                            es.index(index=index, id=wba_id, document=doc)
                            upserted += 1
                        except Exception as exc:  # pylint: disable=broad-except
                            print(f"    ERROR upserting {wba_id}: {exc}")
                    else:
                        upserted += 1  # count as if done in dry-run
                print(f"  {'[DRY-RUN] Would upsert' if dry_run else 'Upserted'}: {upserted}")
                total_upserted += upserted

                # Step 3: find and delete stale ES documents.
                es_ids = _scroll_es_ids(es, index)
                neo4j_ids = set(neo4j_nodes.keys())
                stale_ids = es_ids - neo4j_ids
                print(f"  Stale ES documents to delete: {len(stale_ids)}")
                for wba_id in stale_ids:
                    if not dry_run:
                        try:
                            es.delete(index=index, id=wba_id)
                            total_deleted += 1
                        except Exception as exc:  # pylint: disable=broad-except
                            print(f"    ERROR deleting {wba_id}: {exc}")
                    else:
                        print(f"    [DRY-RUN] Would delete: {wba_id}")
                        total_deleted += 1

    finally:
        driver.close()

    print(f"\nReconciliation complete.")
    print(f"  Total upserted : {total_upserted}")
    print(f"  Total deleted  : {total_deleted}")
    if dry_run:
        print("  (DRY-RUN — no changes were made)")


if __name__ == "__main__":
    dry = os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes")
    if dry:
        print("DRY-RUN mode enabled — no writes will occur.")
    reconcile(dry_run=dry)

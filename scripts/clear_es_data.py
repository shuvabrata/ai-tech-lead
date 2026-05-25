#!/usr/bin/env python3
"""Clear all Elasticsearch documents by deleting and recreating all managed indexes.

Deleting an index removes all documents and its mapping in one operation.
The indexes are immediately recreated empty with the correct mappings and the
``wba_all`` alias, ready to receive new data.

Usage (from workspace root)::

    PYTHONPATH=src python scripts/clear_es_data.py

Environment variables
---------------------
ELASTICSEARCH_URL   ES base URL.  Default: ``http://localhost:9200``.
ELASTIC_PASSWORD    ES password.  Leave empty when security is off.
"""

from __future__ import annotations

from elasticsearch.exceptions import NotFoundError

from app.scripts.create_es_indexes import (
    MANAGED_INDEXES,
    _build_client,
    _index_name,
    create_indexes,
)


def clear_and_recreate() -> None:
    client = _build_client()

    print("Clearing Elasticsearch indexes...")
    for source, entity_type in MANAGED_INDEXES:
        idx = _index_name(source, entity_type)
        resp = client.options(ignore_status=404).indices.delete(index=idx)
        if resp.get("acknowledged"):
            print(f"  Deleted: {idx}")
        else:
            print(f"  Not found (skipped): {idx}")

    print("Recreating Elasticsearch indexes and wba_all alias...")
    create_indexes(client)
    print("Elasticsearch cleared and indexes recreated.")


if __name__ == "__main__":
    clear_and_recreate()

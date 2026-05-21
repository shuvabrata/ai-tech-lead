"""Elasticsearch sink for ActivitySignal consumers.

Builds a flat ES document from an ``ActivitySignal`` and upserts it using
``client.index()``.  The document ``_id`` is the WBA canonical key so
indexing the same signal twice is a natural upsert — no deduplication logic
is required.

Design constraints
------------------
* The ES write is **non-fatal**.  Any exception is logged at WARNING level
  and the caller continues.  The caller must NOT nack the RabbitMQ message
  on an ES failure.
* When ``ELASTICSEARCH_ENABLED`` is ``false`` (or unset) this module is a
  no-op; the function returns immediately without touching Elasticsearch.
* Relationships are stored as a list of WBA canonical key strings
  (``"{source}::{entity_type}::{id}"``), not as nested objects.
* All attribute fields are flattened to the top level of the document.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from elasticsearch import Elasticsearch

from common.activity_signal.models import ActivitySignal
from common.activity_signal.wba_node_id import wba_node_id, wba_format

logger = logging.getLogger(__name__)


def _build_relationship_ids(signal: ActivitySignal) -> list[str]:
    """Return a list of WBA canonical key strings for all relationships."""
    result: list[str] = []
    for rel in signal.relationships:
        t = rel.target
        source = t.source or signal.source
        entity_type = t.entity_type or ""
        raw_id = t.id or ""
        if entity_type and raw_id:
            result.append(wba_format(source, entity_type, raw_id))
    return result


def _build_document(signal: ActivitySignal) -> dict[str, Any]:
    """Build the flat ES document from an ``ActivitySignal``."""
    wba_id = wba_node_id(signal)

    # Flatten all attribute fields to the top level.
    attr_dict = signal.attributes.model_dump()
    # entity_type is excluded from model_dump() via Field(exclude=True) on each
    # *Attributes model, but is available via signal.entity_type (computed_field).
    attr_dict.pop("entity_type", None)
    attr_dict.pop("custom", None)  # not indexed; arbitrary nested data not mapped

    doc: dict[str, Any] = {
        # Envelope fields
        "wba_id": wba_id,
        "source": signal.source,
        "entity_type": signal.entity_type,
        "source_config": signal.source_config,
        "event_time": signal.event_time.isoformat() if signal.event_time else None,
        # Relationship identifiers
        "relationship_ids": _build_relationship_ids(signal),
    }

    # Merge attribute fields (flat, top-level).
    doc.update(attr_dict)

    return doc


def index_signal(client: Elasticsearch, signal: ActivitySignal) -> None:
    """Upsert *signal* into its Elasticsearch index.

    The target index name is derived from the signal:
    ``{signal.source}_{signal.entity_type.lower()}_index``.

    The ``_id`` is the WBA canonical key (``wba_node_id(signal)``).

    This function is synchronous and should be called inside
    ``asyncio.to_thread()`` from the async consumer loop.

    Args:
        client:  An initialised ``Elasticsearch`` client.
        signal:  The ``ActivitySignal`` to index.
    """
    index_name = f"{signal.source}_{signal.entity_type.lower()}_index"
    wba_id = wba_node_id(signal)
    doc = _build_document(signal)

    client.index(index=index_name, id=wba_id, document=doc)
    logger.debug(
        "Indexed signal wba_id=%s into index=%s",
        wba_id,
        index_name,
    )


def _enrich_canonical_document(
    client: Elasticsearch,
    signal: ActivitySignal,
    canonical_wba_id: str,
) -> None:
    """Partially update the canonical ES document when cross-provider Person dedup occurred.

    Cross-provider dedup context
    ----------------------------
    When a Person arrives from a second provider (e.g. ``jira::Person::abc123``)
    and the Neo4j identity resolver finds an existing node from a prior provider
    (e.g. ``github::Person::alice``) with the same email, Neo4j reuses the
    existing node and enriches it additively — ``jira::Person::abc123`` is never
    created in Neo4j.  See ``neo4j_sink._handle_person`` and
    ``connectors/commons/identity_resolver.get_or_create_person``.

    ES must mirror this behaviour exactly:
    - Do NOT create a document under ``jira::Person::abc123`` (no Neo4j node exists).
    - DO enrich the existing ``github::Person::alice`` document with any new
      non-null attributes from the Jira signal.

    ES ``update`` with ``doc`` is used instead of ``index`` because it performs a
    **partial merge** — only the supplied fields are updated; all existing fields
    not present in the update are preserved.  This mirrors the additive Neo4j
    ``merge_person`` Cypher pattern (SET only when value is non-null).

    Args:
        client:           An initialised ``Elasticsearch`` client.
        signal:           The incoming ``ActivitySignal`` whose attributes enrich
                          the canonical document.
        canonical_wba_id: The ``id`` of the Neo4j node that was actually written
                          (returned by ``upsert_signal``).  This is used as the
                          ES document ``_id``.
    """
    parts = canonical_wba_id.split("::", 2)
    canonical_source = parts[0] if len(parts) >= 1 else signal.source
    canonical_entity_type = parts[1] if len(parts) >= 2 else signal.entity_type
    index_name = f"{canonical_source}_{canonical_entity_type.lower()}_index"

    # Build partial update from non-null attribute fields only, so we never
    # overwrite existing data (e.g. GitHub login) with null Jira counterparts.
    attr_dict = signal.attributes.model_dump()
    attr_dict.pop("entity_type", None)
    attr_dict.pop("custom", None)
    partial_attrs = {k: v for k, v in attr_dict.items() if v is not None}

    if not partial_attrs:
        logger.debug(
            "Skipping dedup ES update for canonical_wba_id=%s: no non-null attributes",
            canonical_wba_id,
        )
        return

    client.update(index=index_name, id=canonical_wba_id, doc=partial_attrs)
    logger.debug(
        "Enriched canonical ES doc wba_id=%s from dedup signal source=%s id=%s",
        canonical_wba_id,
        signal.source,
        signal.id,
    )


def index_signal_with_canonical_id(
    client: Elasticsearch,
    signal: ActivitySignal,
    canonical_wba_id: str,
) -> None:
    """Index *signal* into Elasticsearch, honouring cross-provider Person dedup.

    This is the primary entry point for the consumer.  It replaces direct calls
    to ``index_signal`` so that the canonical wba_id returned by
    ``neo4j_sink.upsert_signal`` is respected.

    Dispatch logic
    --------------
    * **No dedup** (``canonical_wba_id == wba_node_id(signal)``): standard
      ``client.index()`` full-document upsert under the signal's own wba_id.
    * **Dedup occurred** (ids differ): the signal's wba_id has no Neo4j node.
      Call ``_enrich_canonical_document`` to partially update the existing
      canonical ES document instead (see that function's docstring for detail).

    Args:
        client:           An initialised ``Elasticsearch`` client.
        signal:           The ``ActivitySignal`` to index.
        canonical_wba_id: The wba_id actually stored in Neo4j, as returned by
                          ``neo4j_sink.upsert_signal``.
    """
    signal_wba_id = wba_node_id(signal)

    if canonical_wba_id == signal_wba_id:
        # Happy path — no dedup, index normally.
        index_signal(client, signal)
    else:
        # Cross-provider Person dedup: signal's wba_id was collapsed into an
        # existing node.  Enrich that node's ES document instead of creating a
        # stale document under the non-existent signal wba_id.
        logger.info(
            "Person dedup detected: signal wba_id=%s merged into canonical wba_id=%s — "
            "enriching canonical ES document instead of creating new entry",
            signal_wba_id,
            canonical_wba_id,
        )
        _enrich_canonical_document(client, signal, canonical_wba_id)


def build_es_client() -> Elasticsearch | None:
    """Build an Elasticsearch client from environment variables.

    Returns ``None`` when ``ELASTICSEARCH_ENABLED`` is falsy so the consumer
    can skip ES writes without any extra branch logic.

    Environment variables
    ---------------------
    ELASTICSEARCH_ENABLED   Must be ``true`` / ``1`` / ``yes`` (case-insensitive)
                            to enable the sink.
    ELASTICSEARCH_URL       Base URL.  Default: ``http://localhost:9200``.
    ELASTIC_PASSWORD        Password for the ``elastic`` built-in user.
                            Leave empty when security is disabled.
    """
    enabled = os.environ.get("ELASTICSEARCH_ENABLED", "").strip().lower()
    if enabled not in ("1", "true", "yes"):
        return None

    url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
    password = os.environ.get("ELASTIC_PASSWORD", "")
    if password:
        return Elasticsearch(url, basic_auth=("elastic", password))
    return Elasticsearch(url)

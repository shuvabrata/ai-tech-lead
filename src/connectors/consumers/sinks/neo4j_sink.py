"""Neo4j sink for ActivitySignal consumers.

Responsibilities
----------------
- MERGE nodes using ``external_id`` as ``id``, matching the key used by all
  producers.  The legacy ``merge_*`` functions in ``neo4j_db/models.py`` also
  key on ``id``, so the two systems are compatible during the deprecation
  window.
- Apply idempotency: skip property updates when the incoming ``event_time`` is
  not newer than the ``_last_event_time`` already stored on the node.
  Relationship MERGEs are always applied (additive and idempotent).
- Create stub nodes for relationship targets that don't exist yet.  A stub
  contains only ``{id, source, _stub: true}`` and is filled in when the
  full signal for that node arrives (the MERGE + SET will remove ``_stub``).
- Handle the three direction semantics:
    * ``direction=None`` → undirected convention: store as ``(node)-[:REL]->(target)``
      but Cypher queries use undirected pattern ``-[:REL]-``.
    * ``direction="OUT"`` → ``(node)-[:REL]->(target)``
    * ``direction="IN"``  → ``(target)-[:REL]->(node)``

Relationship types currently emitted by producers
--------------------------------------------------
GitHub:  PART_OF, AUTHORED_BY, MERGED_INTO, REVIEWS
Jira:    PART_OF, ASSIGNED_TO
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from neo4j import Session

from common.activity_signal.models import ActivitySignal, Relationship

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node label mapping
# ---------------------------------------------------------------------------

# entity_type → Neo4j label.  All producers use the same names so this is a
# 1:1 mapping, but keeping it explicit makes future changes safe.
_ENTITY_LABEL: dict[str, str] = {
    "Repository": "Repository",
    "Branch": "Branch",
    "Commit": "Commit",
    "PullRequest": "PullRequest",
    "Person": "Person",
    "Team": "Team",
    "Project": "Project",
    "Initiative": "Initiative",
    "Epic": "Epic",
    "Sprint": "Sprint",
    "Issue": "Issue",
}


def _label(entity_type: str) -> str:
    """Return the Neo4j label for *entity_type*, defaulting to the type itself."""
    return _ENTITY_LABEL.get(entity_type, entity_type)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def upsert_signal(session: Session, signal: ActivitySignal) -> None:
    """Upsert an ActivitySignal into Neo4j.

    Steps:
    1. MERGE the primary node by ``id = signal.external_id``.
    2. If the signal's ``event_time`` is newer than the stored
       ``_last_event_time``, update all node properties from
       ``signal.extra_attributes()`` plus the idempotency meta-fields.
    3. For each relationship in ``signal.relationships``, MERGE the target
       node as a stub if it doesn't exist, then MERGE the relationship edge.

    Args:
        session: An active synchronous Neo4j ``Session``.
        signal:  A fully validated ``ActivitySignal`` with ``ingestion_time``
                 already set by the caller.
    """
    node_label = _label(signal.entity_type)
    node_id = signal.external_id
    event_time = signal.event_time.isoformat()
    ingestion_time = (
        signal.ingestion_time.isoformat() if signal.ingestion_time else None
    )
    signal_id = signal.signal_id
    source = signal.source

    # Collect all attributes (mandatory + extra) as a flat dict.
    attrs = signal.extra_attributes()
    # Remove the discriminator key — it's stored as the Neo4j label, not a property.
    attrs.pop("entity_type", None)

    _upsert_node(
        session=session,
        node_label=node_label,
        node_id=node_id,
        source=source,
        attrs=attrs,
        event_time=event_time,
        ingestion_time=ingestion_time,
        signal_id=signal_id,
    )

    for rel in signal.relationships:
        _upsert_relationship(
            session=session,
            from_label=node_label,
            from_id=node_id,
            relationship=rel,
        )

    logger.debug(
        "Upserted signal signal_id=%s entity_type=%s id=%s",
        signal_id,
        signal.entity_type,
        node_id,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _upsert_node(
    *,
    session: Session,
    node_label: str,
    node_id: str,
    source: str,
    attrs: dict[str, Any],
    event_time: str,
    ingestion_time: Optional[str],
    signal_id: str,
) -> None:
    """MERGE a node and conditionally update its properties.

    Property updates are skipped when the stored ``_last_event_time`` is equal
    to or newer than the incoming ``event_time`` (last-write-wins semantics).
    The idempotency meta-fields (``_last_signal_id``, ``_last_event_time``) are
    always written so the guard remains accurate.
    """
    # Build a flat param dict for the attributes; prefix with "attr_" to avoid
    # clashing with reserved Cypher parameter names.
    attr_params: dict[str, Any] = {f"attr_{k}": v for k, v in attrs.items()}

    # Property SET clause: every key in attrs becomes a node property.
    set_attr_clause = ", ".join(
        f"n.`{k}` = $attr_{k}" for k in attrs
    )

    # Meta-field SET clause is always applied.
    meta_clause = (
        "n._last_signal_id = $signal_id, "
        "n._last_event_time = $event_time, "
        "n.source = $source"
    )
    if ingestion_time is not None:
        meta_clause += ", n._last_ingestion_time = $ingestion_time"

    if set_attr_clause:
        conditional_set = (
            f"WITH n\n"
            f"WHERE n._last_event_time IS NULL OR n._last_event_time < $event_time\n"
            f"SET {set_attr_clause}"
        )
    else:
        conditional_set = ""

    query = f"""
MERGE (n:{node_label} {{id: $node_id}})
ON CREATE SET n._stub = false, n.source = $source
SET {meta_clause}
{conditional_set}
"""

    params: dict[str, Any] = {
        "node_id": node_id,
        "source": source,
        "event_time": event_time,
        "ingestion_time": ingestion_time,
        "signal_id": signal_id,
        **attr_params,
    }

    session.run(query, **params)


def _upsert_relationship(
    *,
    session: Session,
    from_label: str,
    from_id: str,
    relationship: Relationship,
) -> None:
    """Ensure the target stub exists and MERGE the relationship edge.

    Direction semantics:
    - ``None`` or ``"OUT"`` → ``(from)-[:REL]->(to)``
    - ``"IN"``              → ``(to)-[:REL]->(from)``

    The target node is created as a stub if it does not yet exist so that
    out-of-order signals never fail.
    """
    target = relationship.target

    # Target must have at least an external_id to be upsertable.
    if not target.external_id:
        logger.warning(
            "Skipping relationship %s from %s/%s: target has no external_id",
            relationship.type,
            from_label,
            from_id,
        )
        return

    target_id = target.external_id
    target_source = target.source or ""
    target_entity_type = target.entity_type or ""
    target_label = _label(target_entity_type) if target_entity_type else "Node"
    rel_type = relationship.type
    direction = relationship.direction  # None | "OUT" | "IN"

    # Ensure the target stub node exists.
    stub_query = f"""
MERGE (t:{target_label} {{id: $target_id}})
ON CREATE SET t._stub = true, t.source = $target_source
"""
    session.run(stub_query, target_id=target_id, target_source=target_source)

    # MERGE the relationship edge.
    if direction == "IN":
        # (target)-[:REL]->(from)
        rel_query = f"""
MATCH (from:{from_label} {{id: $from_id}})
MATCH (to:{target_label} {{id: $target_id}})
MERGE (to)-[:{rel_type}]->(from)
"""
    else:
        # None or "OUT" → (from)-[:REL]->(to)
        rel_query = f"""
MATCH (from:{from_label} {{id: $from_id}})
MATCH (to:{target_label} {{id: $target_id}})
MERGE (from)-[:{rel_type}]->(to)
"""

    session.run(rel_query, from_id=from_id, target_id=target_id)

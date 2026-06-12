"""Neo4j sink for ActivitySignal consumers.

Maps incoming ``ActivitySignal`` events to the canonical ``neo4j_db``
dataclasses and delegates to the corresponding ``merge_*`` functions.  This
preserves the node-creation logic established by the original sync modules
(``modules/github/``, ``modules/jira/``) — no raw Cypher is generated here.

Direction semantics for relationships (preserved from producer contracts):
- ``None`` or ``"OUT"`` → forward edge  ``(from)-[:REL]->(to)``
- ``"IN"``              → reverse edge: swap from/to so
  ``merge_relationship`` always writes a forward-directed edge.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, List, Optional

from neo4j import Session

from common.activity_signal.models import ActivitySignal
from common.activity_signal.models import Relationship as SignalRelationship
from common.activity_signal.wba_node_id import wba_format, wba_node_id
from connectors.commons.person_cache import PersonCache
from connectors.neo4j_db.models import (
    Blogpost,
    Commit,
    Epic,
    File,
    Initiative,
    Issue,
    Person,
    Project,
    Page,
    PullRequest,
    Repository,
    Sprint,
    Space,
    Team,
    Relationship as DbRelationship,
    merge_blogpost,
    merge_commit,
    merge_epic,
    merge_file,
    merge_initiative,
    merge_issue,
    merge_person,
    merge_project,
    merge_page,
    merge_pull_request,
    merge_relationship,
    merge_repository,
    merge_sprint,
    merge_space,
    merge_team,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Label helper
# ---------------------------------------------------------------------------


def _label(entity_type: str) -> str:
    """Return the Neo4j node label for *entity_type*.

    All entity_type strings used in this codebase map 1:1 to their Neo4j
    label, so the value is returned unchanged.  The function exists as a
    stable hook for future overrides and for test assertions.
    """
    return entity_type


def _sync_timestamp(signal: ActivitySignal) -> str:
    """Return the sync timestamp to persist on nodes updated by the consumer."""
    ingestion_time = signal.ingestion_time
    if ingestion_time is not None:
        return ingestion_time.isoformat()
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Relationship conversion
# ---------------------------------------------------------------------------


def _to_db_relationships(
    session: Session,
    signal_rels: List[SignalRelationship],
    from_id: str,
    from_type: str,
) -> List[DbRelationship]:
    """Convert ``ActivitySignal`` relationships to ``neo4j_db.Relationship`` objects.

    Direction handling:
    - ``None`` / ``"OUT"`` → ``(from)-[:REL]->(to)``
    - ``"IN"``             → swap from/to so the stored edge is
      ``(target)-[:REL]->(from)``, i.e. ``(to)-[:REL]->(from)`` after swap.

    Target node resolution priority:
    1. ``entity_type == "Person"`` and ``target.email`` set → look up by email.
    2. ``target.url`` set → look up node by url.
    3. ``entity_type == "Person"`` and ``target.source`` is a Jira/Confluence provider
       → look up the canonical Person via shared Atlassian account_id (IdentityMapping
       or existing Person node). Jira and Confluence share the same account_id namespace,
       so ``jira::Person::X`` and ``confluence::Person::X`` are the same individual.
    4. ``target.id`` set → ``{source}::{entity_type}::{id}`` canonical key.

    Relationships with no resolvable target identifier are skipped with a warning.
    """
    result: List[DbRelationship] = []
    for rel in signal_rels:
        target = rel.target

        if not (target.id or target.email or target.url):
            logger.warning(
                "Skipping relationship %s from %s/%s: target has no identifier",
                rel.type,
                from_type,
                from_id,
            )
            continue

        # Resolve to_id using priority order
        to_id: Optional[str] = None

        if target.entity_type == "Person" and target.email:
            row = session.run(
                "MATCH (p:Person) WHERE p.email = $email RETURN p.id AS id LIMIT 1",
                email=target.email,
            ).single()
            if row:
                to_id = row["id"]

        if to_id is None and target.url:
            row = session.run(
                "MATCH (n) WHERE n.url = $url RETURN n.id AS id LIMIT 1",
                url=target.url,
            ).single()
            if row:
                to_id = row["id"]

        # Step 3: For Jira/Confluence Person targets, resolve via shared Atlassian
        # account_id before falling back to raw wba_format. Jira and Confluence share
        # the same account_id namespace, so the same individual may already exist as a
        # Person node from the other provider (or from GitHub via email dedup).
        # Checking IdentityMapping first avoids creating a disconnected stub.
        if (
            to_id is None
            and target.entity_type == "Person"
            and target.source in ("jira", "confluence")
            and target.id
        ):
            account_id = target.id
            identity_ids = [
                wba_format("jira", "IdentityMapping", account_id),
                wba_format("confluence", "IdentityMapping", account_id),
            ]
            person_ids = [
                wba_format("jira", "Person", account_id),
                wba_format("confluence", "Person", account_id),
            ]
            row = session.run(
                (
                    "MATCH (im:IdentityMapping)-[:MAPS_TO]->(p:Person) "
                    "WHERE im.id IN $identity_ids "
                    "RETURN p.id AS id LIMIT 1"
                ),
                identity_ids=identity_ids,
            ).single()
            if row:
                to_id = row["id"]
            else:
                row = session.run(
                    "MATCH (p:Person) WHERE p.id IN $person_ids RETURN p.id AS id LIMIT 1",
                    person_ids=person_ids,
                ).single()
                if row:
                    to_id = row["id"]

        if to_id is None and target.source and target.entity_type and target.id:
            to_id = wba_format(target.source, target.entity_type, target.id)

        if to_id is None:
            logger.warning(
                "Skipping relationship %s from %s/%s: target identifier could not be resolved",
                rel.type,
                from_type,
                from_id,
            )
            continue

        to_type = _label(target.entity_type) if target.entity_type else "Node"

        if rel.direction == "IN":
            # Signal says (source)<-[:REL]-(target); store as (target)-[:REL]->(source)
            db_rel = DbRelationship(
                type=rel.type,
                from_id=to_id,
                to_id=from_id,
                from_type=to_type,
                to_type=from_type,
                properties=rel.properties or {},
            )
        else:
            # None or "OUT" → (from)-[:REL]->(to)
            db_rel = DbRelationship(
                type=rel.type,
                from_id=from_id,
                to_id=to_id,
                from_type=from_type,
                to_type=to_type,
                properties=rel.properties or {},
            )
        result.append(db_rel)
    return result


def _rehome_person_stub(session: Session, stale_person_id: str, canonical_person_id: str) -> None:
    """Move relationships from a stale Person stub onto the canonical Person node.

    This handles the case where content relationships created a bare
    ``confluence::Person::<account_id>`` node before the later Person signal was
    deduplicated onto an existing canonical Person (for example, a Jira-backed
    Person with the same Atlassian account_id).
    """
    if stale_person_id == canonical_person_id:
        return

    outgoing = session.run(
        (
            "MATCH (stale:Person {id: $stale_id})-[r]->(other) "
            "RETURN type(r) AS rel_type, labels(other) AS other_labels, "
            "other.id AS other_id, properties(r) AS props"
        ),
        stale_id=stale_person_id,
    ).data()
    incoming = session.run(
        (
            "MATCH (other)-[r]->(stale:Person {id: $stale_id}) "
            "RETURN type(r) AS rel_type, labels(other) AS other_labels, "
            "other.id AS other_id, properties(r) AS props"
        ),
        stale_id=stale_person_id,
    ).data()

    migrated = 0
    for row in outgoing:
        other_labels = row.get("other_labels") or []
        if not other_labels:
            continue
        merge_relationship(
            session,
            DbRelationship(
                type=row["rel_type"],
                from_id=canonical_person_id,
                to_id=row["other_id"],
                from_type="Person",
                to_type=other_labels[0],
                properties=row.get("props") or {},
            ),
        )
        migrated += 1

    for row in incoming:
        other_labels = row.get("other_labels") or []
        if not other_labels:
            continue
        merge_relationship(
            session,
            DbRelationship(
                type=row["rel_type"],
                from_id=row["other_id"],
                to_id=canonical_person_id,
                from_type=other_labels[0],
                to_type="Person",
                properties=row.get("props") or {},
            ),
        )
        migrated += 1

    session.run(
        "MATCH (stale:Person {id: $stale_id}) DETACH DELETE stale",
        stale_id=stale_person_id,
    )
    logger.info(
        "Rehomed stale Person stub stale_id=%s canonical_id=%s relationships_migrated=%s",
        stale_person_id,
        canonical_person_id,
        migrated,
    )


# ---------------------------------------------------------------------------
# Entity-type handlers
# ---------------------------------------------------------------------------


def _handle_repository(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()  # type: ignore[union-attr]
    node_id = wba_node_id(signal)
    repo = Repository(
        id=node_id,
        name=signal.id,
        url=attrs.get("url", ""),
        language=attrs.get("language", ""),
        is_private=attrs.get("is_private", False),
        topics=attrs.get("topics") or [],
        created_at=attrs.get("created_at", ""),
    )
    db_rels = _to_db_relationships(session, signal.relationships, node_id, "Repository")
    merge_repository(session, repo, relationships=db_rels)


def _handle_space(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()  # type: ignore[union-attr]
    node_id = wba_node_id(signal)
    space = Space(
        id=node_id,
        key=attrs.get("key", ""),
        name=attrs.get("name", ""),
        type=attrs.get("type"),
        url=attrs.get("url"),
        _last_synced_at=_sync_timestamp(signal),
    )
    db_rels = _to_db_relationships(session, signal.relationships, node_id, "Space")
    merge_space(session, space, relationships=db_rels)


def _handle_page(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()  # type: ignore[union-attr]
    node_id = wba_node_id(signal)
    page = Page(
        id=node_id,
        title=attrs.get("title", ""),
        created_at=attrs.get("created_at", ""),
        last_updated_at=attrs.get("last_updated_at"),
        url=attrs.get("url"),
        version=attrs.get("version"),
        status=attrs.get("status"),
        _last_synced_at=_sync_timestamp(signal),
    )
    db_rels = _to_db_relationships(session, signal.relationships, node_id, "Page")
    merge_page(session, page, relationships=db_rels)


def _handle_blogpost(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()  # type: ignore[union-attr]
    node_id = wba_node_id(signal)
    blogpost = Blogpost(
        id=node_id,
        title=attrs.get("title", ""),
        created_at=attrs.get("created_at", ""),
        last_updated_at=attrs.get("last_updated_at"),
        url=attrs.get("url"),
        version=attrs.get("version"),
        status=attrs.get("status"),
        _last_synced_at=_sync_timestamp(signal),
    )
    db_rels = _to_db_relationships(session, signal.relationships, node_id, "Blogpost")
    merge_blogpost(session, blogpost, relationships=db_rels)


def _handle_commit(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()
    node_id = wba_node_id(signal)
    commit = Commit(
        id=node_id,
        sha=attrs.get("sha", ""),
        message=attrs.get("message", ""),
        created_at=attrs.get("created_at", ""),
        additions=attrs.get("additions", 0),
        deletions=attrs.get("deletions", 0),
        files_changed=attrs.get("files_changed", 0),
        url=attrs.get("url"),
    )
    db_rels = _to_db_relationships(session, signal.relationships, node_id, "Commit")
    merge_commit(session, commit, relationships=db_rels)


def _handle_pull_request(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()
    node_id = wba_node_id(signal)
    pr = PullRequest(
        id=node_id,
        number=attrs.get("pull_request_number", 0),
        title=attrs.get("title", ""),
        state=attrs.get("state", ""),
        created_at=attrs.get("created_at", ""),
        updated_at=attrs.get("updated_at", ""),
        merged_at=attrs.get("merged_at"),
        closed_at=attrs.get("closed_at"),
        commits_count=attrs.get("commits_count", 0),
        additions=attrs.get("additions", 0),
        deletions=attrs.get("deletions", 0),
        changed_files=attrs.get("changed_files", 0),
        comments=attrs.get("comments", 0),
        review_comments=attrs.get("review_comments", 0),
        head_branch_name=attrs.get("head_branch_name", ""),
        base_branch_name=attrs.get("base_branch_name", ""),
        labels=attrs.get("labels") or [],
        mergeable_state=attrs.get("mergeable_state", ""),
        url=attrs.get("url"),
    )
    db_rels = _to_db_relationships(session, signal.relationships, node_id, "PullRequest")
    merge_pull_request(session, pr, relationships=db_rels)


def _handle_person(
    session: Session,
    signal: ActivitySignal,
    person_cache: Optional[PersonCache] = None,
) -> Optional[str]:
    """Write a Person signal to Neo4j and return the canonical wba_id that was stored.

    Cross-provider deduplication
    ----------------------------
    When a Person arrives from a second provider (e.g. ``jira::Person::abc123``)
    and the identity resolver finds an existing node from a prior provider
    (e.g. ``github::Person::alice``) with the same email address, Neo4j reuses
    the existing node — ``jira::Person::abc123`` is **never created**.  The
    existing node is enriched additively via ``merge_person`` (null / missing
    fields are filled in; non-empty fields are overwritten by the richer value).
    See ``connectors/commons/identity_resolver.py :: get_or_create_person``.

    The returned canonical wba_id reflects what actually exists in Neo4j.  When
    deduplication occurred the returned id differs from ``wba_node_id(signal)``;
    callers (e.g. the Elasticsearch sink) must use the returned id — **not** the
    signal's own wba_id — to avoid creating stale documents pointing to nodes
    that do not exist in Neo4j.
    """
    attrs = signal.attributes.model_dump()  # type: ignore[union-attr]

    if person_cache is not None:
        if signal.source == "github":
            login = attrs.get("login", "")
            name = attrs.get("full_name") or login
            raw_email = attrs.get("email")
            email = raw_email.lower() if raw_email else None
            url = attrs.get("url")

            person_id, _ = person_cache.get_or_create_person(
                session,
                email=email if email else None,
                name=name,
                provider="github",
                external_id=login,
                url=url,
            )
            if person_id:
                signal_node_id = wba_node_id(signal)
                if person_id != signal_node_id:
                    logger.info(
                        "Deduplicated Person signal source=%s signal_id=%s signal_node_id=%s canonical_id=%s",
                        signal.source,
                        signal.id,
                        signal_node_id,
                        person_id,
                    )
                    _rehome_person_stub(session, signal_node_id, person_id)
                identity_id = wba_format("github", "IdentityMapping", login)
                person_cache.queue_identity_mapping(
                    person_id=person_id,
                    identity_id=identity_id,
                    provider="GitHub",
                    username=login,
                    email=email or "",
                    last_updated_at=datetime.now(timezone.utc).isoformat(),
                )
                if signal.relationships:
                    db_rels = _to_db_relationships(session, signal.relationships, person_id, "Person")
                    for rel in db_rels:
                        merge_relationship(session, rel)
            return person_id

        elif signal.source == "jira":
            account_id = attrs.get("account_id", "")
            name = attrs.get("full_name", "")
            raw_email = attrs.get("email")
            email = raw_email.lower() if raw_email else None

            person_id, _ = person_cache.get_or_create_person(
                session,
                email=email if email else None,
                name=name,
                provider="jira",
                external_id=account_id,
                account_id=account_id,
            )
            if person_id:
                signal_node_id = wba_node_id(signal)
                if person_id != signal_node_id:
                    logger.info(
                        "Deduplicated Person signal source=%s signal_id=%s signal_node_id=%s canonical_id=%s",
                        signal.source,
                        signal.id,
                        signal_node_id,
                        person_id,
                    )
                    _rehome_person_stub(session, signal_node_id, person_id)
                identity_id = wba_format("jira", "IdentityMapping", account_id)
                person_cache.queue_identity_mapping(
                    person_id=person_id,
                    identity_id=identity_id,
                    provider="Jira",
                    username=name,
                    email=email or "",
                    last_updated_at=datetime.now(timezone.utc).isoformat(),
                )
                if signal.relationships:
                    db_rels = _to_db_relationships(session, signal.relationships, person_id, "Person")
                    for rel in db_rels:
                        merge_relationship(session, rel)
            return person_id

        elif signal.source == "confluence":
            account_id = attrs.get("account_id", "")
            name = attrs.get("full_name", "") or account_id
            raw_email = attrs.get("email")
            email = raw_email.lower() if raw_email else None
            url = attrs.get("url")

            person_id, _ = person_cache.get_or_create_person(
                session,
                email=email if email else None,
                name=name,
                provider="confluence",
                external_id=account_id,
                url=url,
                account_id=account_id,
            )
            if person_id:
                signal_node_id = wba_node_id(signal)
                if person_id != signal_node_id:
                    logger.info(
                        "Deduplicated Person signal source=%s signal_id=%s signal_node_id=%s canonical_id=%s",
                        signal.source,
                        signal.id,
                        signal_node_id,
                        person_id,
                    )
                    _rehome_person_stub(session, signal_node_id, person_id)
                identity_id = wba_format("confluence", "IdentityMapping", account_id)
                person_cache.queue_identity_mapping(
                    person_id=person_id,
                    identity_id=identity_id,
                    provider="Confluence",
                    username=name,
                    email=email or "",
                    last_updated_at=datetime.now(timezone.utc).isoformat(),
                )
                if signal.relationships:
                    db_rels = _to_db_relationships(session, signal.relationships, person_id, "Person")
                    for rel in db_rels:
                        merge_relationship(session, rel)
            return person_id

    # Fallback: no PersonCache — original behaviour, no cross-provider dedup.
    raw_email = attrs.get("email")
    node_id = wba_node_id(signal)
    person = Person(
        id=node_id,
        name=attrs.get("full_name"),
        email=raw_email.lower() if raw_email else None,
        url=attrs.get("url"),
    )
    db_rels = _to_db_relationships(session, signal.relationships, node_id, "Person")
    merge_person(session, person, relationships=db_rels)
    return node_id


def _handle_team(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()
    node_id = wba_node_id(signal)
    team = Team(
        id=node_id,
        name=attrs.get("name"),
        source=signal.source,
        created_at=attrs.get("created_at"),
        url=attrs.get("url"),
    )
    db_rels = _to_db_relationships(session, signal.relationships, node_id, "Team")
    merge_team(session, team, relationships=db_rels)


def _handle_project(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()
    project = Project(
        id=wba_node_id(signal),
        key=attrs.get("project_key", ""),
        name=attrs.get("project_name", ""),
        status=attrs.get("status"),
        project_type=attrs.get("project_type"),
        url=attrs.get("url"),
    )
    db_rels = _to_db_relationships(session, signal.relationships, wba_node_id(signal), "Project")
    merge_project(session, project, relationships=db_rels)


def _handle_initiative(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()
    initiative = Initiative(
        id=wba_node_id(signal),
        key=attrs.get("key", ""),
        summary=attrs.get("summary", ""),
        priority=attrs.get("priority", ""),
        status=attrs.get("status", ""),
        created_at=attrs.get("created_at", ""),
        updated_at=attrs.get("updated_at", ""),
        duedate=attrs.get("duedate"),
        labels=attrs.get("labels") or [],
        components=attrs.get("components") or [],
        url=attrs.get("url"),
        _last_synced_at=datetime.now(timezone.utc).isoformat(),
    )
    db_rels = _to_db_relationships(session, signal.relationships, wba_node_id(signal), "Initiative")
    merge_initiative(session, initiative, relationships=db_rels)


def _handle_epic(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()
    epic = Epic(
        id=wba_node_id(signal),
        key=attrs.get("key", ""),
        summary=attrs.get("summary", ""),
        priority=attrs.get("priority", ""),
        status=attrs.get("status", ""),
        start_date=attrs.get("start_date", ""),
        due_date=attrs.get("due_date", ""),
        created_at=attrs.get("created_at", ""),
        updated_at=attrs.get("updated_at"),
        url=attrs.get("url"),
        _last_synced_at=datetime.now(timezone.utc).isoformat(),
    )
    db_rels = _to_db_relationships(session, signal.relationships, wba_node_id(signal), "Epic")
    merge_epic(session, epic, relationships=db_rels)


def _handle_sprint(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()
    sprint = Sprint(
        id=wba_node_id(signal),
        name=attrs.get("name", ""),
        goal=attrs.get("goal") or "",
        start_date=attrs.get("start_date") or "",
        end_date=attrs.get("end_date") or "",
        status=attrs.get("status", ""),
        url=attrs.get("url"),
    )
    db_rels = _to_db_relationships(session, signal.relationships, wba_node_id(signal), "Sprint")
    merge_sprint(session, sprint, relationships=db_rels)


def _handle_issue(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()
    issue = Issue(
        id=wba_node_id(signal),
        key=attrs.get("key", ""),
        type=attrs.get("type", ""),
        summary=attrs.get("summary", ""),
        priority=attrs.get("priority", ""),
        status=attrs.get("status", ""),
        story_points=attrs.get("story_points", 0),
        created_at=attrs.get("created_at", ""),
        updated_at=attrs.get("updated_at"),
        url=attrs.get("url"),
        _last_synced_at=datetime.now(timezone.utc).isoformat(),
    )
    db_rels = _to_db_relationships(session, signal.relationships, wba_node_id(signal), "Issue")
    merge_issue(session, issue, relationships=db_rels)


def _handle_file(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()
    node_id = wba_node_id(signal)
    file_node = File(
        id=node_id,
        path=attrs.get("path", ""),
        repo_name=attrs.get("repo_name", ""),
        name=attrs.get("name"),
        extension=attrs.get("extension"),
        language=attrs.get("language"),
        is_test=attrs.get("is_test"),
        last_updated_at=attrs.get("last_updated_at"),
        url=attrs.get("url"),
    )
    db_rels = _to_db_relationships(session, signal.relationships, node_id, "File")
    merge_file(session, file_node, relationships=db_rels)


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_HANDLERS: dict[str, Callable[[Session, ActivitySignal], None]] = {
    "Repository": _handle_repository,
    "Commit": _handle_commit,
    "PullRequest": _handle_pull_request,
    # Person is handled directly in upsert_signal to support PersonCache injection
    "Space": _handle_space,
    "Page": _handle_page,
    "Blogpost": _handle_blogpost,
    "Team": _handle_team,
    "Project": _handle_project,
    "Initiative": _handle_initiative,
    "Epic": _handle_epic,
    "Sprint": _handle_sprint,
    "Issue": _handle_issue,
    "File": _handle_file,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def upsert_signal(
    session: Session,
    signal: ActivitySignal,
    person_cache: Optional[PersonCache] = None,
) -> str:
    """Upsert an ActivitySignal into Neo4j and return the canonical wba_id stored.

    Dispatches to the correct entity-type handler which builds the appropriate
    ``neo4j_db`` dataclass and calls the corresponding ``merge_*`` function,
    preserving the node/relationship creation logic from the original sync
    modules (``modules/github/``, ``modules/jira/``).

    When *person_cache* is provided, Person signals use ``PersonCache`` for
    identity resolution and IdentityMapping creation, and
    ``flush_identity_mappings`` is called after every signal.

    Return value — canonical wba_id
    --------------------------------
    The returned string is the ``id`` property of the Neo4j node that was
    actually written.  For most entity types this equals ``wba_node_id(signal)``.
    For Person signals with cross-provider deduplication (see ``_handle_person``),
    the returned id may differ from the signal's own wba_id — callers must use
    this value when writing to downstream stores (e.g. Elasticsearch) to avoid
    creating documents under wba_ids that do not exist in Neo4j.

    Args:
        session:      An active synchronous Neo4j ``Session``.
        signal:       A fully validated ``ActivitySignal`` with ``ingestion_time``
                      already set by the caller.
        person_cache: Optional ``PersonCache`` instance scoped to the current
                      consumer task.  When supplied, Person signals use the
                      cache for identity resolution.
    """
    entity_type = signal.entity_type
    canonical_wba_id: str = wba_node_id(signal)

    if entity_type == "Person":
        resolved_id = _handle_person(session, signal, person_cache=person_cache)
        if resolved_id:
            canonical_wba_id = resolved_id
    else:
        handler = _HANDLERS.get(entity_type)
        if handler is None:
            logger.warning(
                "No handler for entity_type=%s signal_id=%s — skipping",
                entity_type,
                signal.signal_id,
            )
            return canonical_wba_id
        handler(session, signal)

    if person_cache is not None:
        person_cache.flush_identity_mappings(session)

    logger.info(
        "Upserted signal_id=%s entity_type=%s id=%s canonical_wba_id=%s",
        signal.signal_id,
        entity_type,
        signal.id,
        canonical_wba_id,
    )
    return canonical_wba_id

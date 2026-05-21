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
    Branch,
    Commit,
    Epic,
    File,
    Initiative,
    Issue,
    Person,
    Project,
    PullRequest,
    Repository,
    Sprint,
    Team,
    Relationship as DbRelationship,
    merge_branch,
    merge_commit,
    merge_epic,
    merge_file,
    merge_initiative,
    merge_issue,
    merge_person,
    merge_project,
    merge_pull_request,
    merge_repository,
    merge_sprint,
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
    3. ``target.id`` set → ``{source}::{entity_type}::{id}`` canonical key.

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


def _handle_branch(session: Session, signal: ActivitySignal) -> None:
    attrs = signal.attributes.model_dump()
    node_id = wba_node_id(signal)
    branch = Branch(
        id=node_id,
        name=attrs.get("branch_name", ""),
        is_default=attrs.get("is_default", False),
        is_protected=attrs.get("is_protected", False),
        is_deleted=attrs.get("is_deleted", False),
        is_external=attrs.get("is_external", False),
        last_commit_sha=attrs.get("last_commit_sha", ""),
        last_commit_timestamp=attrs.get("last_commit_timestamp", ""),
        url=attrs.get("url"),
    )
    db_rels = _to_db_relationships(session, signal.relationships, node_id, "Branch")
    merge_branch(session, branch, relationships=db_rels)


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
) -> None:
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
                identity_id = wba_format("github", "IdentityMapping", login)
                person_cache.queue_identity_mapping(
                    person_id=person_id,
                    identity_id=identity_id,
                    provider="GitHub",
                    username=login,
                    email=email or "",
                    last_updated_at=datetime.now(timezone.utc).isoformat(),
                )
            return

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
            )
            if person_id:
                identity_id = wba_format("jira", "IdentityMapping", account_id)
                person_cache.queue_identity_mapping(
                    person_id=person_id,
                    identity_id=identity_id,
                    provider="Jira",
                    username=name,
                    email=email or "",
                    last_updated_at=datetime.now(timezone.utc).isoformat(),
                )
            return

    # Fallback: no PersonCache — original behaviour
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
        size=attrs.get("size"),
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
    "Branch": _handle_branch,
    "Commit": _handle_commit,
    "PullRequest": _handle_pull_request,
    # Person is handled directly in upsert_signal to support PersonCache injection
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
) -> None:
    """Upsert an ActivitySignal into Neo4j using the canonical merge_* functions.

    Dispatches to the correct entity-type handler which builds the appropriate
    ``neo4j_db`` dataclass and calls the corresponding ``merge_*`` function,
    preserving the node/relationship creation logic from the original sync
    modules (``modules/github/``, ``modules/jira/``).

    When *person_cache* is provided, Person signals use ``PersonCache`` for
    identity resolution and IdentityMapping creation, and
    ``flush_identity_mappings`` is called after every signal.

    Args:
        session:      An active synchronous Neo4j ``Session``.
        signal:       A fully validated ``ActivitySignal`` with ``ingestion_time``
                      already set by the caller.
        person_cache: Optional ``PersonCache`` instance scoped to the current
                      consumer task.  When supplied, Person signals use the
                      cache for identity resolution.
    """
    entity_type = signal.entity_type

    if entity_type == "Person":
        _handle_person(session, signal, person_cache=person_cache)
    else:
        handler = _HANDLERS.get(entity_type)
        if handler is None:
            logger.warning(
                "No handler for entity_type=%s signal_id=%s — skipping",
                entity_type,
                signal.signal_id,
            )
            return
        handler(session, signal)

    if person_cache is not None:
        person_cache.flush_identity_mappings(session)

    logger.info(
        "Upserted signal_id=%s entity_type=%s id=%s",
        signal.signal_id,
        entity_type,
        signal.id,
    )




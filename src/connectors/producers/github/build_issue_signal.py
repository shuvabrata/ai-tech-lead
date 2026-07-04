"""Signal builder for GitHub Issues.

Builds a single ``ActivitySignal`` per issue containing the Issue node and ALL
relationships: ``ASSIGNED_TO`` (per assignee), ``REPORTED_BY``, ``PART_OF``
(→ Repository), ``MENTIONS``, ``REFERENCES`` (→ Jira issues), ``RELATES_TO``
(→ GitHub issues), and ``COMMENTED_ON`` (per comment, direction="IN").

This mirrors ``build_pull_request_signal.py`` exactly — one signal per entity
with all relationships, including comment-derived edges.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from common.logger import logger

from common.activity_signal.models import (
    ActivitySignal,
    IssueAttributes,
    Relationship,
    RelationshipTarget,
)

from connectors.producers.github.constants import (
    _SOURCE,
    _VERSION,
    _connector_url,
    _truncate,
)


def build_issue_signal(
    issue_data: Dict[str, Any],
    repo_data: Dict[str, Any],
    assignee_logins: List[str],
    mention_logins: List[str],
    referenced_jira_keys: List[str],
    referenced_github_issue_ids: List[str],
    relates_to_ids: List[str],
    comments_data: Optional[List[Dict[str, Any]]] = None,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub Issue.

    Args:
        issue_data: Normalized issue dict from ``map_issue()``. Must contain
            ``key``, ``number``, ``summary``, ``status``, ``created_at``,
            ``updated_at``, ``assignee``, ``reporter``, ``labels``, ``url``,
            ``repo_full_name``.
        repo_data: Normalized repo dict. Must contain ``full_name``.
        assignee_logins: List of all assignee login strings (one ASSIGNED_TO
            edge per login).
        mention_logins: List of @mentioned login strings (one MENTIONS edge
            per login, excluding self-refs).
        referenced_jira_keys: List of Jira issue keys (one REFERENCES edge
            per key).
        referenced_github_issue_ids: List of GitHub issue ref strings in the
            format ``<repo>#<number>`` (one REFERENCES edge per ref). These
            are cross-source refs to GitHub issues, emitted as REFERENCES
            (not RELATES_TO) — see decision #8 in the plan.
        relates_to_ids: List of GitHub issue ref strings in the format
            ``<repo>#<number>`` (one RELATES_TO edge per ref, excluding
            self-refs).
        comments_data: Optional list of comment dicts, each with ``login``
            and ``timestamp`` keys. One COMMENTED_ON edge per comment.

    Returns:
        ``ActivitySignal`` with ``IssueAttributes`` and all relationships,
        or ``None`` on validation failure.
    """
    try:
        repo_full_name = issue_data.get("repo_full_name") or repo_data.get("full_name", "unknown")
        number = issue_data.get("number", 0)
        issue_id = f"{repo_full_name}#{number}"
        reporter_login = issue_data.get("reporter") or "unknown"

        # Event time — from updated_at, fallback to created_at, fallback to now
        raw_updated = issue_data.get("updated_at")
        raw_created = issue_data.get("created_at")
        event_time = _parse_event_time(raw_updated, raw_created)

        logger.info(
            "Building Issue signal for '%s#%d' (state=%s, assignees=%d, mentions=%d, "
            "jira_refs=%d, github_refs=%d, relates_to=%d, comments=%d)",
            repo_full_name,
            number,
            issue_data.get("status", "?"),
            len(assignee_logins),
            len(mention_logins),
            len(referenced_jira_keys),
            len(referenced_github_issue_ids),
            len(relates_to_ids),
            len(comments_data or []),
        )

        attrs = IssueAttributes(
            key=issue_data.get("key", issue_id),
            summary=_truncate(issue_data.get("summary", "")),
            priority=issue_data.get("priority", "None"),
            status=issue_data.get("status", "open"),
            type=issue_data.get("type", "Issue"),
            created_at=issue_data.get("created_at", ""),
            updated_at=issue_data.get("updated_at"),
            story_points=None,
            assignee=issue_data.get("assignee"),
            reporter=reporter_login,
            labels=issue_data.get("labels"),
            url=issue_data.get("url"),
            custom=None,
        )

        rels: List[Relationship] = []

        # ASSIGNED_TO → each assignee (undirected)
        for assignee_login in assignee_logins:
            rels.append(
                Relationship(
                    type="ASSIGNED_TO",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        id=assignee_login,
                    ),
                )
            )

        # REPORTED_BY → issue author (undirected)
        rels.append(
            Relationship(
                type="REPORTED_BY",
                direction=None,
                target=RelationshipTarget(
                    source=_SOURCE,
                    entity_type="Person",
                    id=reporter_login,
                ),
            )
        )

        # PART_OF → Repository (undirected)
        rels.append(
            Relationship(
                type="PART_OF",
                direction=None,
                target=RelationshipTarget(
                    source=_SOURCE,
                    entity_type="Repository",
                    id=repo_full_name,
                ),
            )
        )

        # MENTIONS → each mentioned login (undirected, skip self-refs)
        for mention_login in mention_logins:
            if mention_login == reporter_login:
                logger.debug("Skipping self-mention: @%s is the issue author", mention_login)
                continue
            rels.append(
                Relationship(
                    type="MENTIONS",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        id=mention_login,
                    ),
                )
            )

        # REFERENCES → each Jira issue key (undirected, cross-source)
        for jira_key in referenced_jira_keys:
            rels.append(
                Relationship(
                    type="REFERENCES",
                    direction=None,
                    target=RelationshipTarget(
                        source="jira",
                        entity_type="Issue",
                        id=jira_key,
                    ),
                )
            )

        # REFERENCES → each GitHub issue ref (undirected, cross-source)
        # These are GitHub issue refs that point to a different repo's issues.
        for gh_ref in referenced_github_issue_ids:
            rels.append(
                Relationship(
                    type="REFERENCES",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Issue",
                        id=gh_ref,
                    ),
                )
            )

        # RELATES_TO → each GitHub issue ref in the same repo (undirected, skip self-refs)
        for relates_id in relates_to_ids:
            if relates_id == issue_id:
                logger.debug("Skipping self-reference: %s references itself", relates_id)
                continue
            rels.append(
                Relationship(
                    type="RELATES_TO",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Issue",
                        id=relates_id,
                    ),
                )
            )

        # COMMENTED_ON → each comment (direction="IN", with timestamp property)
        for comment in (comments_data or []):
            comment_login = comment.get("login")
            if not comment_login:
                continue
            rels.append(
                Relationship(
                    type="COMMENTED_ON",
                    direction="IN",
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        id=comment_login,
                    ),
                    properties={
                        "timestamp": comment.get("timestamp"),
                    },
                )
            )

        signal = ActivitySignal(
            source=_SOURCE,
            id=issue_id,
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=event_time,
            version=_VERSION,
            attributes=attrs,
            relationships=rels,
        )

        logger.debug(
            "Issue signal built: id=%s, event_time=%s, %d relationships "
            "(ASSIGNED_TO=%d, REPORTED_BY=1, PART_OF=1, MENTIONS=%d, REFERENCES=%d, "
            "RELATES_TO=%d, COMMENTED_ON=%d)",
            signal.id,
            event_time.isoformat() if isinstance(event_time, datetime) else str(event_time),
            len(rels),
            len(assignee_logins),
            len([r for r in rels if r.type == "MENTIONS"]),
            len(referenced_jira_keys) + len(referenced_github_issue_ids),
            len([r for r in rels if r.type == "RELATES_TO"]),
            len(comments_data or []),
        )

        return signal

    except Exception as exc:
        logger.warning(
            "Skipping Issue signal for '%s' (validation error): %s",
            issue_data.get("key", "?"),
            exc,
        )
        return None


def _parse_event_time(updated_at: Optional[str], created_at: Optional[str]) -> datetime:
    """Parse the event time from ``updated_at`` (preferred) or ``created_at``.

    Args:
        updated_at: ISO format datetime string (preferred).
        created_at: ISO format datetime string (fallback).

    Returns:
        UTC-aware datetime.
    """
    raw = updated_at or created_at
    if raw:
        try:
            ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc)

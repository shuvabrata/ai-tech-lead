
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from common.logger import logger

from common.activity_signal.models import (
    ActivitySignal,
    CommitAttributes,
    Relationship,
    RelationshipTarget,
)
from common.activity_signal.wba_node_id import wba_format

from connectors.producers.map_github import (
    extract_issue_keys,
    extract_issue_keys_from_branch,
)
from connectors.producers.github.constants import (
    _SOURCE,
    _VERSION,
    _connector_url,
    _truncate,
)

def build_commit_signal(
    commit_data: Dict[str, Any],
    author_data: Dict[str, Any],
    branch_data: Optional[Dict[str, Any]],
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub Commit."""
    try:
        sha = commit_data["sha"]
        event_time = (
            datetime.fromisoformat(commit_data["created_at"]).replace(tzinfo=timezone.utc)
            if commit_data.get("created_at")
            else datetime.now(timezone.utc)
        )
        login = author_data.get("login") or author_data.get("name", "unknown")

        attrs = CommitAttributes(
            sha=sha,
            message=_truncate(commit_data.get("message", "")),
            author=author_data.get("name") or login,
            created_at=commit_data.get("created_at", ""),
            additions=commit_data.get("additions", 0),
            deletions=commit_data.get("deletions", 0),
            files_changed=commit_data.get("files_changed", 0),
            url=commit_data.get("url"),
        )

        rels: List[Relationship] = [
            Relationship(
                type="AUTHORED_BY",
                direction=None,
                target=RelationshipTarget(
                    source=_SOURCE,
                    entity_type="Person",
                    id=login,
                ),
            )
        ]
        if branch_data:
            rels.append(
                Relationship(
                    type="PART_OF",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Branch",
                        id=f"{branch_data['repo_name']}::{branch_data['name']}",
                    ),
                )
            )  # Commit→Branch: PART_OF is correct (matches neo4j_db handler)

        # REFERENCES → Jira issues mentioned in the commit message or branch name
        issue_keys = extract_issue_keys(commit_data.get("message", ""))
        if branch_data:
            branch_keys = extract_issue_keys_from_branch(branch_data.get("name", ""))
            issue_keys = list({*issue_keys, *branch_keys})
        for issue_key in issue_keys:
            rels.append(
                Relationship(
                    type="REFERENCES",
                    direction=None,
                    target=RelationshipTarget(
                        source="jira",
                        entity_type="Issue",
                        id=issue_key,
                    ),
                )
            )

        return ActivitySignal(
            source=_SOURCE,
            id=sha,
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=event_time,
            version=_VERSION,
            attributes=attrs,
            relationships=rels,
        )
    except Exception as exc:
        logger.warning("Skipping Commit signal for sha '%s' (validation error): %s", commit_data.get("sha"), exc)
        return None


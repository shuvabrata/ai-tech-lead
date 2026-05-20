from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from common.logger import logger

from common.activity_signal.models import (
    ActivitySignal,
    PullRequestAttributes,
    Relationship,
    RelationshipTarget,
)

from connectors.producers.github.constants import (
    _SOURCE,
    _VERSION,
    _connector_url,
    _truncate,
)


def build_pull_request_signal(
    pr_data: Dict[str, Any],
    author_data: Dict[str, Any],
    reviewer_logins: List[str],
    repo_data: Dict[str, Any],
    requested_reviewer_logins: Optional[List[str]] = None,
    merger_login: Optional[str] = None,
    commit_shas: Optional[List[str]] = None,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub PullRequest."""
    try:
        event_time = (
            datetime.fromisoformat(pr_data["updated_at"]).replace(tzinfo=timezone.utc)
            if pr_data.get("updated_at")
            else datetime.now(timezone.utc)
        )
        author_login = author_data.get("login") or author_data.get("name", "unknown")
        author_person_id = author_login

        attrs = PullRequestAttributes(
            id=str(pr_data["id"]),
            number=int(pr_data["number"]),
            title=_truncate(pr_data.get("title", "")),
            state=pr_data.get("state", ""),
            created_at=pr_data.get("created_at", ""),
            updated_at=pr_data.get("updated_at"),
            merged_at=pr_data.get("merged_at"),
            closed_at=pr_data.get("closed_at"),
            commits_count=pr_data.get("commits_count"),
            additions=pr_data.get("additions"),
            deletions=pr_data.get("deletions"),
            changed_files=pr_data.get("changed_files"),
            comments=pr_data.get("comments"),
            review_comments=pr_data.get("review_comments"),
            head_branch_name=pr_data.get("head_branch_name"),
            base_branch_name=pr_data.get("base_branch_name"),
            labels=pr_data.get("labels"),
            mergeable_state=pr_data.get("mergeable_state"),
            user=author_login,
            # Extra
            url=pr_data.get("url"),
            base_branch_id=pr_data.get("base_branch_id"),
            head_branch_id=pr_data.get("head_branch_id"),
        )

        rels: List[Relationship] = [
            Relationship(
                type="CREATED_BY",
                direction=None,
                target=RelationshipTarget(
                    source=_SOURCE,
                    entity_type="Person",
                    id=author_person_id,
                ),
            )
        ]

        # TARGETS → base branch
        base_branch_id = pr_data.get("base_branch_id")
        if base_branch_id:
            rels.append(
                Relationship(
                    type="TARGETS",
                    direction="OUT",
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Branch",
                        id=base_branch_id,
                    ),
                )
            )

        # FROM → head branch (the feature/source branch of this PR)
        head_branch_id = pr_data.get("head_branch_id")
        if head_branch_id:
            rels.append(
                Relationship(
                    type="FROM",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Branch",
                        id=head_branch_id,
                    ),
                )
            )

        # REVIEWED_BY → each reviewer
        for reviewer_login in reviewer_logins:
            reviewer_person_id = reviewer_login
            rels.append(
                Relationship(
                    type="REVIEWED_BY",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        id=reviewer_person_id,
                    ),
                )
            )

        for rr_login in (requested_reviewer_logins or []):
            rr_person_id = rr_login
            rels.append(
                Relationship(
                    type="REQUESTED_REVIEWER",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        id=rr_person_id,
                    ),
                )
            )

        # MERGED_BY → merger person (only when the PR was merged)
        if pr_data.get("state") == "merged" and merger_login:
            merger_person_id = merger_login
            rels.append(
                Relationship(
                    type="MERGED_BY",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        id=merger_person_id,
                    ),
                )
            )

        # INCLUDES → each commit SHA associated with this PR
        repo_name = repo_data.get("name", "unknown")
        for sha in (commit_shas or []):
            commit_id = f"github_commit_{repo_name}_{sha[:8]}"
            rels.append(
                Relationship(
                    type="INCLUDES",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Commit",
                        external_id=commit_id,
                    ),
                )
            )

        return ActivitySignal(
            source=_SOURCE,
            external_id=str(pr_data["id"]),
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=event_time,
            version=_VERSION,
            attributes=attrs,
            relationships=rels,
        )
    except Exception as exc:
        logger.warning("Skipping PR signal for #%s (validation error): %s", pr_data.get("number"), exc)
        return None

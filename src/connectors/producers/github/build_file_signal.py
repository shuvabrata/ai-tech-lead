"""Build an ActivitySignal for a GitHub File node.

One signal is emitted per file per commit.  The signal carries a single
``MODIFIES`` relationship (direction="IN") pointing back to the commit, so
the consumer writes the directed edge ``(Commit)-[:MODIFIES]->(File)`` — which
is the form expected by the query catalog.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from common.logger import logger

from common.activity_signal.models import (
    ActivitySignal,
    FileAttributes,
    Relationship,
    RelationshipTarget,
)
from connectors.producers.github.constants import (
    _SOURCE,
    _VERSION,
    _connector_url,
)


def build_file_signal(
    file_data: Dict[str, Any],
    commit_data: Dict[str, Any],
    repo_data: Dict[str, Any],
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub File modified by a commit.

    Args:
        file_data: Normalised file dict from ``map_commit_files()`` — must
            contain at least ``filename``.
        commit_data: Normalised commit dict from ``map_commit()`` — must
            contain ``sha`` and ``created_at``.
        repo_data: Minimal repo info dict with at least ``name`` and optionally
            ``owner`` for URL generation.

    Returns:
        A validated ``ActivitySignal`` or ``None`` if required fields are
        missing (skips silently after logging a warning).
    """
    try:
        filename: str = file_data["filename"]
        repo_name: str = repo_data["name"]
        sha: str = commit_data["sha"]

        file_id = hashlib.sha256(f"{repo_name}::{filename}".encode()).hexdigest()

        logger.info(
            "[build_file_signal] id=%s  file=%r  repo=%r  sha=%s  ext=%r  lang=%r  add=%s  del=%s",
            file_id,
            filename,
            repo_name,
            sha[:8],
            file_data.get("extension"),
            file_data.get("language"),
            file_data.get("additions"),
            file_data.get("deletions"),
        )

        event_time = datetime.fromisoformat(commit_data["created_at"]).replace(
            tzinfo=timezone.utc
        )

        # Build optional GitHub URL anchored to the specific commit SHA so the
        # link is stable even if the file is later renamed, moved, or deleted.
        url: Optional[str] = None
        owner = repo_data.get("owner")
        if owner:
            url = f"https://github.com/{owner}/{repo_name}/blob/{sha}/{filename}"

        attrs = FileAttributes(
            path=filename,
            repo_name=repo_name,
            name=file_data.get("name"),
            extension=file_data.get("extension"),
            language=file_data.get("language"),
            is_test=file_data.get("is_test"),
            last_updated_at=commit_data["created_at"],
            url=url,
            additions=file_data.get("additions"),
            deletions=file_data.get("deletions"),
        )

        return ActivitySignal(
            source=_SOURCE,
            id=file_id,
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=event_time,
            version=_VERSION,
            attributes=attrs,
            relationships=[
                Relationship(
                    type="MODIFIES",
                    direction="IN",
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Commit",
                        id=sha,
                    ),
                    properties={
                        "additions": file_data.get("additions", 0),
                        "deletions": file_data.get("deletions", 0),
                    },
                )
            ],
        )
    except Exception as exc:
        logger.warning(
            "Skipping File signal for '%s' in commit '%s' (validation error): %s",
            file_data.get("filename"),
            commit_data.get("sha", "?")[:8] if commit_data.get("sha") else "?",
            exc,
        )
        return None

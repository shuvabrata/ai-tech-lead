from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from common.logger import logger

from common.activity_signal.models import (
    ActivitySignal,
    BranchAttributes,
    Relationship,
    RelationshipTarget,
)
from common.activity_signal.wba_node_id import wba_format

from connectors.producers.github.constants import (
    _SOURCE,
    _VERSION,
    _connector_url,
)


def build_branch_signal(
    branch_data: Dict[str, Any],
    repo_data: Dict[str, Any],
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub Branch."""
    try:
        repo_name = repo_data["name"]
        branch_name = branch_data["name"]
        branch_id = f"{repo_name}::{branch_name}"

        ts_raw = branch_data.get("last_commit_timestamp")
        event_time = (
            datetime.fromisoformat(ts_raw).replace(tzinfo=timezone.utc)
            if ts_raw
            else datetime.now(timezone.utc)
        )
        attrs = BranchAttributes(
            repo_name=repo_name,
            branch_name=branch_name,
            last_commit_sha=branch_data["last_commit_sha"],
            last_commit_timestamp=branch_data.get("last_commit_timestamp"),
            is_default=branch_data.get("is_default", False),
            is_protected=branch_data.get("is_protected", False),
            is_deleted=branch_data.get("is_deleted", False),
            is_external=branch_data.get("is_external", False),
            url=branch_data.get("url"),
        )
        signal = ActivitySignal(
            source=_SOURCE,
            id=branch_id,
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=event_time,
            version=_VERSION,
            attributes=attrs,
            relationships=[
                Relationship(
                    type="BRANCH_OF",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Repository",
                        id=repo_data["full_name"],
                    ),
                )
            ],
        )
        return signal
    except Exception as exc:
        logger.warning("Skipping Branch signal for '%s' (validation error): %s", branch_data.get("name"), exc)
        return None

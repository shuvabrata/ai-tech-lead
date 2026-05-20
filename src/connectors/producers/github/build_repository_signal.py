
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from common.activity_signal.models import ActivitySignal, RepositoryAttributes
from common.activity_signal.wba_node_id import wba_format
from common.logger import logger

from connectors.producers.github.constants import (
    _SOURCE,
    _VERSION,
    _connector_url,
)

def build_repository_signal(repo_data: Dict[str, Any]) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub Repository."""
    try:
        full_name = repo_data["full_name"]
        attrs = RepositoryAttributes(
            name=repo_data["name"],
            description=repo_data.get("description") or None,
            language=repo_data.get("language") or None,
            is_private=repo_data.get("is_private", False),
            topics=repo_data.get("topics") or [],
            url=repo_data.get("url"),
            created_at=repo_data.get("created_at"),
            updated_at=repo_data.get("updated_at"),
        )
        return ActivitySignal(
            source=_SOURCE,
            id=full_name,
            external_id=wba_format(_SOURCE, "Repository", full_name),
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=datetime.now(timezone.utc),
            version=_VERSION,
            attributes=attrs,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Skipping Repository signal (validation error): %s", exc)
        return None

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from common.activity_signal.models import ActivitySignal, RepositoryAttributes
from common.logger import logger

from connectors.producers.github.constants import (
    _SOURCE,
    _VERSION,
    _connector_url,
)

def build_repository_signal(repo_data: Dict[str, Any]) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub Repository."""
    try:
        attrs = RepositoryAttributes(
            id=repo_data["id"],
            full_name=repo_data["full_name"],
            name=repo_data["name"],
            created_at=repo_data["created_at"],
            updated_at=repo_data["updated_at"],
            url=repo_data["url"],
            # Extra fields (allowed by extra='allow')
            language=repo_data.get("language", ""),
            is_private=repo_data.get("is_private", False),
            topics=repo_data.get("topics", []),
        )
        return ActivitySignal(
            source=_SOURCE,
            external_id=repo_data["id"],
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=datetime.now(timezone.utc),
            version=_VERSION,
            attributes=attrs,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Skipping Repository signal (validation error): %s", exc)
        return None
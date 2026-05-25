from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from common.logger import logger

from common.activity_signal.models import (
    ActivitySignal,
    Relationship,
    RelationshipTarget,
    TeamAttributes,
)
from common.activity_signal.wba_node_id import wba_format

from connectors.producers.github.constants import (
    _SOURCE,
    _VERSION,
    _connector_url,
)


def build_team_signal(
    team_data: Dict[str, Any],
    repo_data: Dict[str, Any],
    permission: Optional[str] = None,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub Team."""
    try:
        slug = team_data["slug"]
        attrs = TeamAttributes(
            name=team_data["name"],
            url=team_data.get("url"),
            description=team_data.get("description"),
        )
        props: Optional[Dict[str, Any]] = {"permission": permission} if permission else None
        rels: List[Relationship] = [
            Relationship(
                type="COLLABORATOR",
                direction=None,
                target=RelationshipTarget(
                    source=_SOURCE,
                    entity_type="Repository",
                    id=repo_data["full_name"],
                ),
                properties=props,
            )
        ]
        return ActivitySignal(
            source=_SOURCE,
            id=slug,
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=datetime.now(timezone.utc),
            version=_VERSION,
            attributes=attrs,
            relationships=rels,
        )
    except Exception as exc:
        logger.warning("Skipping Team signal for '%s' (validation error): %s", team_data.get("name"), exc)
        return None

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


from common.activity_signal.models import (
    ActivitySignal,
    PersonAttributes,
    Relationship,
)
from common.logger import logger

from connectors.producers.github.constants import (
    _SOURCE,
    _VERSION,
    _connector_url
)

def build_person_signal(
    person_data: Dict[str, Any],
    extra_relationships: Optional[List[Relationship]] = None,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a Person (GitHub author/contributor)."""
    login = person_data.get("login") or person_data.get("name", "unknown")
    person_id = f"person_github_{login}"
    logger.debug(
        "[build_person_signal] id=%s  login=%r  name=%r  email=%r  extra_rels=%d",
        person_id,
        login,
        person_data.get("name"),
        person_data.get("email"),
        len(extra_relationships) if extra_relationships else 0,
    )
    try:
        attrs = PersonAttributes(
            id=person_id,
            name=person_data.get("name") or login,
            # Extra
            login=login,
            email=person_data.get("email") or "",
        )
        return ActivitySignal(
            source=_SOURCE,
            external_id=person_id,
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=datetime.now(timezone.utc),
            version=_VERSION,
            attributes=attrs,
            relationships=list(extra_relationships) if extra_relationships else [],
        )
    except Exception as exc:
        logger.warning("Skipping Person signal for '%s' (validation error): %s", login, exc)
        return None


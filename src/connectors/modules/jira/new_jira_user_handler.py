from typing import Any, Optional, Dict
from datetime import datetime, timezone

from connectors.commons.person_cache import PersonCache
from common.logger import logger
from connectors.producers.map_jira import map_jira_user

def new_jira_user_handler(
    session: Any,
    user_data: Dict[str, Any],
    person_cache: PersonCache
) -> Optional[str]:
    """Handle a Jira user by creating Person and IdentityMapping nodes using PersonCache.

    Args:
        session: Neo4j session
        user_data: Jira user object with attributes like accountId, displayName, emailAddress
        person_cache: PersonCache for batch operations (required for performance)

    Returns:
        person_id: The created Person node ID
    """
    try:
        user_map = map_jira_user(user_data)
        account_id = user_map["account_id"]
        display_name = user_map["display_name"]
        email = user_map["email"]

        if not account_id:
            logger.warning("      Jira user missing accountId, skipping")
            return None

        logger.debug(f"    Processing Jira user with PersonCache: {display_name} ({account_id})")

        person_id, is_new = person_cache.get_or_create_person(
            session,
            email=email if email else None,
            name=display_name,
            provider="jira",
            external_id=account_id
        )

        if not person_id:
            logger.error(f"      Failed to get/create person for {display_name}")
            return None

        logger.debug(f"      {'Created new' if is_new else 'Found existing'} Person: {person_id}")

        identity_id = f"identity_jira_{account_id}"
        person_cache.queue_identity_mapping(
            person_id=person_id,
            identity_id=identity_id,
            provider="Jira",
            username=display_name,
            email=email,
            last_updated_at=datetime.now(timezone.utc).isoformat()
        )

        logger.debug(f"      ✓ Created/updated Jira user: {display_name}")

        return person_id
        
    except Exception as e:
        logger.error(f"      ✗ Error processing Jira user: {str(e)}")
        logger.exception(e)
        return None

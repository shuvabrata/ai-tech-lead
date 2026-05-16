from typing import Any, Dict, Optional, Set, Dict
from datetime import datetime, timezone
from connectors.neo4j_db.models import Epic, Relationship, merge_epic
from connectors.modules.jira.new_jira_user_handler import new_jira_user_handler
from connectors.modules.jira.team_stub_handler import get_or_create_team_stub
from connectors.commons.person_cache import PersonCache
from app.common.logger import logger
from connectors.producers.map_jira import map_epic



def new_epic_handler(
    session: Any,
    issue_data: Dict[str, Any],
    initiative_id_map: Dict[str, str],
    person_cache: PersonCache,
    jira_base_url: Optional[str] = None,
    processed_epics: Optional[Set[str]] = None
) -> Optional[str]:
    """Handle a Jira epic by creating Epic node and relationships.

    Args:
        session: Neo4j session
        issue_data: Jira issue object from API
        initiative_id_map: Dictionary mapping Jira issue IDs to Neo4j initiative IDs
        person_cache: PersonCache for batch operations (required for performance)
        jira_base_url: Base URL of Jira instance (e.g., "https://yoursite.atlassian.net")
        processed_epics: Set of already processed epic IDs to avoid duplicates

    Returns:
        epic_id: The created Epic node ID
    """
    try:
        issue_id = issue_data.get('id')
        issue_key = issue_data.get('key')

        if not issue_id or not issue_key:
            logger.warning(f"    Epic missing id or key, skipping")
            return None

        if processed_epics is not None and issue_id in processed_epics:
            logger.debug(f"    Epic {issue_key} already processed, skipping")
            return f"epic_jira_{issue_id}"

        logger.info(f"  Processing epic: {issue_key}")

        if processed_epics is not None:
            processed_epics.add(issue_id)

        epic_map = map_epic(issue_data, jira_base_url)
        epic_id = epic_map["id"]

        # Create Epic node
        _last_synced_at = datetime.now(timezone.utc).isoformat()
        epic = Epic(
            id=epic_id,
            key=epic_map["key"],
            summary=epic_map["summary"],
            priority=epic_map["priority"],
            status=epic_map["status"],
            start_date=epic_map["start_date"],
            due_date=epic_map["due_date"],
            created_at=epic_map["created_at"],
            updated_at=epic_map["updated_at"],
            url=epic_map["url"],
            _last_synced_at=_last_synced_at
        )

        relationships = []

        # Handle assignee
        assignee = issue_data.get('fields', {}).get('assignee')
        if assignee:
            logger.debug(f"    Processing assignee: {assignee.get('displayName')}")
            assignee_person_id = new_jira_user_handler(session, assignee, person_cache)
            if assignee_person_id:
                relationships.append(Relationship(
                    type="ASSIGNED_TO",
                    from_id=epic_id,
                    to_id=assignee_person_id,
                    from_type="Epic",
                    to_type="Person"
                ))

        # PART_OF relationship to Initiative
        if epic_map["parent_jira_id"]:
            parent_initiative_id = initiative_id_map.get(epic_map["parent_jira_id"])
            if parent_initiative_id:
                relationships.append(Relationship(
                    type="PART_OF",
                    from_id=epic_id,
                    to_id=parent_initiative_id,
                    from_type="Epic",
                    to_type="Initiative"
                ))
                logger.debug(f"    Created PART_OF relationship to initiative")

        # TEAM relationship
        if epic_map["team_value"]:
            team_id = get_or_create_team_stub(session, epic_map["team_value"])
            relationships.append(Relationship(
                type="TEAM",
                from_id=epic_id,
                to_id=team_id,
                from_type="Epic",
                to_type="Team"
            ))
            logger.debug(f"    Created TEAM relationship to: {epic_map['team_value']}")

        logger.debug(f"    Merging Epic node: {epic_id}")
        merge_epic(session, epic, relationships=relationships)

        logger.info(f"    ✓ Created/updated epic: {issue_key}")

        return epic_id
        
    except Exception as e:
        logger.error(f"    ✗ Error processing epic {issue_data.get('key', 'unknown')}: {str(e)}")
        logger.exception(e)
        return None

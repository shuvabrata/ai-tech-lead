from typing import Any, Optional, Dict

from connectors.neo4j_db.models import Sprint, merge_sprint
from connectors.commons.logger import logger
from connectors.producers.map_jira import map_sprint




def new_sprint_handler(
    session: Any,
    sprint_data: Dict[str, Any],
    jira_base_url: Optional[str] = None # pylint: disable=unused-argument
) -> Optional[str]:
    """Handle a Jira sprint by creating Sprint node.

    Args:
        session: Neo4j session
        sprint_data: Jira sprint object from Agile API
        jira_base_url: Base URL of Jira instance (e.g., "https://yoursite.atlassian.net")

    Returns:
        sprint_id: The created Sprint node ID
    """
    try:
        jira_sprint_id = sprint_data.get('id')
        if not jira_sprint_id:
            logger.warning(f"    Sprint missing id, skipping: {sprint_data}")
            return None

        sprint_map = map_sprint(sprint_data)
        logger.info(f"  Processing sprint: {sprint_map['name']}")

        sprint = Sprint(
            id=sprint_map["id"],
            name=sprint_map["name"],
            goal=sprint_map["goal"],
            start_date=sprint_map["start_date"],
            end_date=sprint_map["end_date"],
            status=sprint_map["status"],
            url=sprint_map["url"]
        )

        merge_sprint(session, sprint)

        logger.info(f"    ✓ Created Sprint: {sprint_map['name']} ({sprint_map['status']})")
        return sprint_map["id"]
        
    except Exception as e:
        logger.error(f"    ✗ Error in new_sprint_handler: {str(e)}")
        logger.exception(e)
        return None

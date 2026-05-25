from typing import Any, Optional, Dict

from connectors.commons.person_cache import PersonCache
from common.logger import logger

from connectors.neo4j_db.models import Project, Relationship, merge_project
from connectors.modules.jira.new_jira_user_handler import new_jira_user_handler
from connectors.producers.map_jira import map_project


def new_project_handler(
    session: Any,
    project_data: Dict[str, Any],
    person_cache: PersonCache,
    jira_base_url: Optional[str] = None
) -> Optional[str]:
    """Handle a Jira project by creating Project node and relationships.

    Args:
        session: Neo4j session
        project_data: Jira project object from API
        person_cache: Cache for Jira user information
        jira_base_url: Base URL of Jira instance (e.g., "https://yoursite.atlassian.net")

    Returns:
        project_id: The created Project node ID
    """
    try:
        jira_project_id = project_data.get('id')
        project_key = project_data.get('key')

        if not jira_project_id or not project_key:
            logger.warning(f"    Project missing id or key, skipping: {project_data}")
            return None

        logger.info(f"  Processing project: {project_key} - {project_data.get('name', '')}")

        project_map = map_project(project_data, jira_base_url)
        project_id = project_map["id"]

        # Handle project lead
        lead_id = None
        lead = project_data.get('lead')
        if lead:
            logger.debug(f"    Processing project lead: {lead.get('displayName')}")
            lead_id = new_jira_user_handler(session, lead, person_cache)

        # Create Project node
        logger.debug(f"    Creating Project node with ID: {project_id}")
        project = Project(
            id=project_id,
            key=project_map["key"],
            name=project_map["name"],
            status=project_map["status"],
            project_type=project_map["project_type"],
            url=project_map["url"]
        )

        relationships = []

        if lead_id:
            relationships.append(Relationship(
                type="LEADS",
                from_id=lead_id,
                to_id=project_id,
                from_type="Person",
                to_type="Project"
            ))

        logger.debug(f"    Merging Project node: {project_id}")
        merge_project(session, project, relationships=relationships)

        logger.info(f"    ✓ Created/updated project: {project_key}")

        return project_id
        
    except Exception as e:
        logger.error(f"    ✗ Error processing project: {str(e)}")
        logger.exception(e)
        return None

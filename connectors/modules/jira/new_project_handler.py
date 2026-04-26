from typing import Any, Optional, Dict

from common.person_cache import PersonCache
from common.logger import logger

from db.models import Project, Relationship, merge_project
from modules.jira.new_jira_user_handler import new_jira_user_handler


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
        # Extract project information
        jira_project_id = project_data.get('id')
        project_key = project_data.get('key')
        project_name = project_data.get('name', '')
        
        if not jira_project_id or not project_key:
            logger.warning(f"    Project missing id or key, skipping: {project_data}")
            return None
        
        logger.info(f"  Processing project: {project_key} - {project_name}")
        
        # Create unique project ID
        project_id = f"project_jira_{jira_project_id}"
        
        # Extract optional fields
        description = project_data.get('description', '')
        project_type = project_data.get('projectTypeKey', '')
        style = project_data.get('style', '')
        
        # Determine status - Jira projects don't have explicit status, use style or default
        status = "Active" if style else None
        
        # Construct URL to view the project in Jira browser
        url = None
        if jira_base_url:
            url = f"{jira_base_url}/browse/{project_key}"
        
        # Handle project lead - create relationship directly
        lead_id = None
        lead = project_data.get('lead')
        if lead:
            logger.debug(f"    Processing project lead: {lead.get('displayName')}")
            lead_id = new_jira_user_handler(session, lead, person_cache)
        
        # Create Project node
        logger.debug(f"    Creating Project node with ID: {project_id}")
        project = Project(
            id=project_id,
            key=project_key,
            name=project_name,
            status=status,
            project_type=project_type if project_type else None,
            url=url
        )
        
        relationships = []
        
        # Create LEADS relationship if lead exists
        if lead_id:
            relationships.append(Relationship(
                type="LEADS",
                from_id=lead_id,
                to_id=project_id,
                from_type="Person",
                to_type="Project"
            ))
        
        # Merge project into Neo4j
        logger.debug(f"    Merging Project node: {project_id}")
        merge_project(session, project, relationships=relationships)
        
        logger.info(f"    ✓ Created/updated project: {project_key}")
        
        return project_id
        
    except Exception as e:
        logger.error(f"    ✗ Error processing project: {str(e)}")
        logger.exception(e)
        return None

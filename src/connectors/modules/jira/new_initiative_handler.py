from typing import Any, Dict, Optional, Set
from datetime import datetime, timezone

from connectors.neo4j_db.models import Initiative, Relationship, merge_initiative
from connectors.modules.jira.new_jira_user_handler import new_jira_user_handler
from connectors.commons.person_cache import PersonCache
from connectors.commons.logger import logger
from connectors.producers.map_jira import map_initiative

def new_initiative_handler(
    session: Any,
    issue_data: Dict[str, Any],
    project_id_map: Dict[str, str],
    person_cache: PersonCache,
    jira_connection: Any = None,
    jira_base_url: Optional[str] = None,
    initiative_id_map: Optional[Dict[str, str]] = None,
    processed_epics: Optional[Set[str]] = None
) -> Optional[str]:
    """Handle a Jira initiative by creating Initiative node and relationships.

    Args:
        session: Neo4j session
        issue_data: Jira issue object from API
        project_id_map: Dictionary mapping Jira project keys to Neo4j project IDs
        person_cache: PersonCache for batch operations (required for performance)
        jira_connection: Jira API connection object (for fetching child epics)
        jira_base_url: Base URL of Jira instance (e.g., "https://yoursite.atlassian.net")
        initiative_id_map: Dictionary mapping Jira issue IDs to Neo4j initiative IDs
        processed_epics: Set of already processed epic IDs to avoid duplicates

    Returns:
        initiative_id: The created Initiative node ID
    """
    try:
        issue_id = issue_data.get('id')
        issue_key = issue_data.get('key')
        fields = issue_data.get('fields', {})

        if not issue_id or not issue_key:
            logger.warning(f"    Initiative missing id or key, skipping")
            return None

        logger.info(f"  Processing initiative: {issue_key}")

        initiative_map = map_initiative(issue_data, jira_base_url)
        initiative_id = initiative_map["id"]

        # Get project ID for relationship
        project_id = project_id_map.get(initiative_map["project_key"]) if initiative_map["project_key"] else None

        # Create Initiative node
        _last_synced_at = datetime.now(timezone.utc).isoformat()
        initiative = Initiative(
            id=initiative_id,
            key=initiative_map["key"],
            summary=initiative_map["summary"],
            priority=initiative_map["priority"],
            status=initiative_map["status"],
            created_at=initiative_map["created_at"],
            updated_at=initiative_map["updated_at"],
            duedate=initiative_map["duedate"],
            project_id=project_id,
            labels=initiative_map["labels"],
            components=initiative_map["components"],
            url=initiative_map["url"],
            _last_synced_at=_last_synced_at
        )

        relationships = []

        # Handle assignee
        assignee = fields.get('assignee')
        if assignee:
            logger.debug(f"    Processing assignee: {assignee.get('displayName')}")
            assignee_person_id = new_jira_user_handler(session, assignee, person_cache)
            if assignee_person_id:
                relationships.append(Relationship(
                    type="ASSIGNED_TO",
                    from_id=initiative_id,
                    to_id=assignee_person_id,
                    from_type="Initiative",
                    to_type="Person"
                ))

        # Handle reporter
        reporter = fields.get('reporter')
        if reporter:
            logger.debug(f"    Processing reporter: {reporter.get('displayName')}")
            reporter_person_id = new_jira_user_handler(session, reporter, person_cache)
            if reporter_person_id:
                relationships.append(Relationship(
                    type="REPORTED_BY",
                    from_id=initiative_id,
                    to_id=reporter_person_id,
                    from_type="Initiative",
                    to_type="Person"
                ))

        # PART_OF / CONTAINS relationships to Project
        if project_id:
            relationships.append(Relationship(
                type="PART_OF",
                from_id=initiative_id,
                to_id=project_id,
                from_type="Initiative",
                to_type="Project"
            ))
            relationships.append(Relationship(
                type="CONTAINS",
                from_id=project_id,
                to_id=initiative_id,
                from_type="Project",
                to_type="Initiative"
            ))

        logger.debug(f"    Merging Initiative node: {initiative_id}")
        merge_initiative(session, initiative, relationships=relationships)

        logger.info(f"    ✓ Created/updated initiative: {issue_key}")

        if initiative_id_map is not None:
            initiative_id_map[issue_id] = initiative_id
        
        # Fetch and process child epics if jira_connection is provided
        if jira_connection and initiative_id_map is not None:
            try:
                logger.debug(f"    Fetching child epics for initiative {issue_key}...")
                
                # Import here to avoid circular dependency
                from modules.jira.new_epic_handler import new_epic_handler
                
                # JQL to find epics that are children of this initiative
                jql = f'parent = {issue_key} AND issuetype = Epic'
                child_issues = jira_connection.jql(jql=jql, limit=100)
                
                if child_issues and 'issues' in child_issues:
                    child_epics = child_issues['issues']
                    if child_epics:
                        logger.info(f"    Found {len(child_epics)} child epic(s) for {issue_key}")
                        
                        for child_epic_data in child_epics:
                            try:
                                new_epic_handler(
                                    session, 
                                    child_epic_data, 
                                    initiative_id_map,
                                    person_cache,
                                    jira_base_url=jira_base_url,
                                    processed_epics=processed_epics
                                )
                            except Exception as e:
                                logger.error(f"      ✗ Error processing child epic: {str(e)}")
                                logger.exception(e)
            except Exception as e:
                logger.warning(f"    Could not fetch child epics for {issue_key}: {str(e)}")
        
        return initiative_id
        
    except Exception as e:
        logger.error(f"    ✗ Error processing initiative {issue_data.get('key', 'unknown')}: {str(e)}")
        logger.exception(e)
        return None

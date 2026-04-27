from typing import Any, Dict, Optional, Set, Dict
from datetime import datetime, timezone
import os
from neo4j_db.models import Epic, Relationship, merge_epic
from modules.jira.new_jira_user_handler import new_jira_user_handler
from modules.jira.team_stub_handler import get_or_create_team_stub
from commons.person_cache import PersonCache
from commons.logger import logger



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
        # Extract issue information
        issue_id = issue_data.get('id')
        issue_key = issue_data.get('key')
        fields = issue_data.get('fields', {})
        
        if not issue_id or not issue_key:
            logger.warning(f"    Epic missing id or key, skipping")
            return None
        
        # Check if already processed
        if processed_epics is not None and issue_id in processed_epics:
            logger.debug(f"    Epic {issue_key} already processed, skipping")
            return f"epic_jira_{issue_id}"
        
        logger.info(f"  Processing epic: {issue_key}")
        
        # Create unique epic ID
        epic_id = f"epic_jira_{issue_id}"
        
        # Mark as processed
        if processed_epics is not None:
            processed_epics.add(issue_id)
        
        # Extract required fields
        summary = fields.get('summary', '')
        priority_obj = fields.get('priority', {})
        priority = priority_obj.get('name', 'None') if priority_obj else 'None'
        status_obj = fields.get('status', {})
        status = status_obj.get('name', 'Unknown') if status_obj else 'Unknown'
        
        # Get configurable field names from environment
        team_field_name = os.getenv('JIRA_EPIC_TEAM_FIELD', 'Team')
        start_date_field_name = os.getenv('JIRA_EPIC_START_DATE_FIELD', 'created')
        due_date_field_name = os.getenv('JIRA_EPIC_DUE_DATE_FIELD', 'duedate')
        
        # Extract dates
        created_at = fields.get('created', '')[:10] if fields.get('created') else ''  # Extract date part YYYY-MM-DD
        updated_at = fields.get('updated', '')[:10] if fields.get('updated') else ''  # Extract date part YYYY-MM-DD
        
        # Start date - use configured field or fall back to created date
        start_date = None
        if start_date_field_name == 'created':
            start_date = created_at
        else:
            custom_start = fields.get(start_date_field_name)
            start_date = custom_start[:10] if custom_start else created_at
        
        # Due date - use configured field
        due_date = fields.get(due_date_field_name)
        if due_date and len(due_date) >= 10:
            due_date = due_date[:10]  # Extract YYYY-MM-DD part
        
        # Extract team from custom field
        team_value = None
        team_field = fields.get(team_field_name)
        if team_field:
            # Team field could be a string or an object with 'value' or 'name'
            if isinstance(team_field, dict):
                team_value = team_field.get('value') or team_field.get('name')
            else:
                team_value = str(team_field)
        
        # Get parent initiative if exists
        parent_initiative_id = None
        parent_obj = fields.get('parent')
        if parent_obj:
            parent_jira_id = parent_obj.get('id')
            parent_initiative_id = initiative_id_map.get(parent_jira_id)
            if parent_initiative_id:
                logger.debug(f"    Epic linked to initiative: {parent_obj.get('key')}")
        
        # Construct URL to view the epic in Jira browser
        url = None
        if jira_base_url:
            url = f"{jira_base_url}/browse/{issue_key}"
        
        logger.debug(f"    Creating Epic node: {issue_key} - {summary}")
        
        # Create Epic node
        _last_synced_at = datetime.now(timezone.utc).isoformat()
        epic = Epic(
            id=epic_id,
            key=issue_key,
            summary=summary,
            priority=priority,
            status=status,
            start_date=start_date or created_at,  # Fallback to created if no start_date
            due_date=due_date if due_date else '',  # Empty string if no due date
            created_at=created_at,
            updated_at=updated_at,
            url=url,
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
                    from_id=epic_id,
                    to_id=assignee_person_id,
                    from_type="Epic",
                    to_type="Person"
                ))
        
        # Handle PART_OF relationship to Initiative (if parent exists)
        if parent_initiative_id:
            relationships.append(Relationship(
                type="PART_OF",
                from_id=epic_id,
                to_id=parent_initiative_id,
                from_type="Epic",
                to_type="Initiative"
            ))
            logger.debug(f"    Created PART_OF relationship to initiative")
        
        # Handle TEAM relationship (if team value exists)
        # Creates Team stub if doesn't exist - will be enriched when GitHub loads
        if team_value:
            # Get or create Team node (creates stub if doesn't exist)
            team_id = get_or_create_team_stub(session, team_value)
            
            relationships.append(Relationship(
                type="TEAM",
                from_id=epic_id,
                to_id=team_id,
                from_type="Epic",
                to_type="Team"
            ))
            logger.debug(f"    Created TEAM relationship to: {team_value}")
        
        # Merge epic into Neo4j
        logger.debug(f"    Merging Epic node: {epic_id}")
        merge_epic(session, epic, relationships=relationships)
        
        logger.info(f"    ✓ Created/updated epic: {issue_key}")
        
        return epic_id
        
    except Exception as e:
        logger.error(f"    ✗ Error processing epic {issue_data.get('key', 'unknown')}: {str(e)}")
        logger.exception(e)
        return None

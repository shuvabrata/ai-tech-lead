from typing import Any, Dict, Optional
from datetime import datetime, timezone

import os
from connectors.neo4j_db.models import Issue, Relationship, merge_issue
from connectors.modules.jira.new_jira_user_handler import new_jira_user_handler
from connectors.modules.jira.team_stub_handler import get_or_create_team_stub
from connectors.commons.person_cache import PersonCache
from connectors.commons.logger import logger



def new_issue_handler(
    session: Any,
    issue_data: Dict[str, Any],
    epic_id_map: Dict[str, str],
    sprint_id_map: Dict[str, str],
    person_cache: PersonCache,
    jira_base_url: Optional[str] = None
) -> Optional[str]:
    """Handle a Jira issue (all types) by creating Issue node and relationships.

    Args:
        session: Neo4j session
        issue_data: Jira issue object from API
        epic_id_map: Dictionary mapping Jira epic issue IDs to Neo4j epic IDs
        sprint_id_map: Dictionary mapping Jira sprint IDs to Neo4j sprint IDs
        person_cache: PersonCache for batch operations (required for performance)
        jira_connection: Jira API connection object (for fetching additional data)
        jira_base_url: Base URL of Jira instance (e.g., "https://yoursite.atlassian.net")

    Returns:
        issue_id: The created Issue node ID
    """
    try:
        # Extract issue information
        jira_issue_id = issue_data.get('id')
        issue_key = issue_data.get('key')
        fields = issue_data.get('fields', {})
        
        if not jira_issue_id or not issue_key:
            logger.warning(f"    Issue missing id or key, skipping")
            return None
        
        # Extract issue type
        issue_type_obj = fields.get('issuetype', {})
        issue_type = issue_type_obj.get('name', 'Unknown') if issue_type_obj else 'Unknown'
        
        logger.info(f"  Processing {issue_type}: {issue_key}")
        
        # Create unique issue ID
        issue_id = f"issue_jira_{jira_issue_id}"
        
        # Extract required fields
        summary = fields.get('summary', '')
        priority_obj = fields.get('priority', {})
        priority = priority_obj.get('name', 'None') if priority_obj else 'None'
        status_obj = fields.get('status', {})
        status = status_obj.get('name', 'Unknown') if status_obj else 'Unknown'
        created = fields.get('created', '') if fields.get('created') else ''
        updated_at = fields.get('updated', '') if fields.get('updated') else ''
        
        # Extract story points - field name varies by Jira configuration
        # Common field names: customfield_10016, story_points, Story Points
        story_points = 0
        for field_name in ['customfield_10016', 'customfield_10026', 'story_points']:
            if field_name in fields and fields[field_name] is not None:
                try:
                    story_points = int(float(fields[field_name]))
                    break
                except (ValueError, TypeError):
                    pass
        
        # Construct URL to view the issue in Jira browser
        url = None
        if jira_base_url:
            url = f"{jira_base_url}/browse/{issue_key}"
        
        # Create Issue object
        _last_synced_at = datetime.now(timezone.utc).isoformat()
        issue = Issue(
            id=issue_id,
            key=issue_key,
            type=issue_type,
            summary=summary,
            priority=priority,
            status=status,
            story_points=story_points,
            created_at=created,
            updated_at=updated_at,
            url=url,
            _last_synced_at=_last_synced_at
        )
        
        # Build relationships
        relationships = []
        
        # 1. PART_OF -> Epic
        # Check for epic link in various field locations
        epic_jira_id = None
        
        # Method 1: Epic Link field (common in older Jira)
        epic_link = fields.get('customfield_10014')  # Common epic link field
        if epic_link:
            # Epic link is usually the epic key, need to look it up
            # For now, we'll check if we have it in our map
            for jira_eid, neo4j_eid in epic_id_map.items():
                if epic_link in neo4j_eid or jira_eid == epic_link:
                    relationships.append(Relationship(
                        type="PART_OF",
                        from_id=issue_id,
                        to_id=neo4j_eid,
                        from_type="Issue",
                        to_type="Epic"
                    ))
                    break
        
        # Method 2: Parent field (for issues under epics in newer Jira)
        parent = fields.get('parent')
        if parent and not any(r.type == "PART_OF" for r in relationships):
            parent_id = parent.get('id')
            parent_key = parent.get('key', '')
            parent_type = parent.get('fields', {}).get('issuetype', {}).get('name', '')
            
            if parent_type == 'Epic' and parent_id in epic_id_map:
                relationships.append(Relationship(
                    type="PART_OF",
                    from_id=issue_id,
                    to_id=epic_id_map[parent_id],
                    from_type="Issue",
                    to_type="Epic"
                ))
        
        # 2. ASSIGNED_TO (undirected) - Person
        assignee = fields.get('assignee')
        if assignee:
            assignee_id = new_jira_user_handler(session, assignee, person_cache)
            if assignee_id:
                relationships.append(Relationship(
                    type="ASSIGNED_TO",
                    from_id=issue_id,
                    to_id=assignee_id,
                    from_type="Issue",
                    to_type="Person"
                ))
        
        # 3. REPORTED_BY (undirected) - Person
        reporter = fields.get('reporter')
        if reporter:
            reporter_id = new_jira_user_handler(session, reporter, person_cache)
            if reporter_id:
                relationships.append(Relationship(
                    type="REPORTED_BY",
                    from_id=issue_id,
                    to_id=reporter_id,
                    from_type="Issue",
                    to_type="Person"
                ))
        
        # 4. IN_SPRINT -> Sprint
        # Extract sprint information from sprint field (can have multiple sprints)
        sprint_field = fields.get('sprint') or fields.get('customfield_10020', [])
        if sprint_field:
            # Handle both single sprint object and array of sprints
            sprints = sprint_field if isinstance(sprint_field, list) else [sprint_field]
            
            for sprint in sprints:
                if isinstance(sprint, dict):
                    sprint_jira_id = str(sprint.get('id', ''))
                    if sprint_jira_id and sprint_jira_id in sprint_id_map:
                        relationships.append(Relationship(
                            type="IN_SPRINT",
                            from_id=issue_id,
                            to_id=sprint_id_map[sprint_jira_id],
                            from_type="Issue",
                            to_type="Sprint"
                        ))
        
        # 5. TEAM (undirected) - Team (if issue has a team assignment)
        # Get configurable field name from environment
        team_field_name = os.getenv('JIRA_ISSUE_TEAM_FIELD', 'Team')
        team_field = fields.get(team_field_name)
        if team_field:
            # Team field could be a string or an object with 'value' or 'name'
            team_value = None
            if isinstance(team_field, dict):
                team_value = team_field.get('value') or team_field.get('name')
            else:
                team_value = str(team_field)
            
            if team_value:
                logger.debug(f"    Processing team assignment: {team_value}")
                team_id = get_or_create_team_stub(session, team_value)
                relationships.append(Relationship(
                    type="TEAM",
                    from_id=issue_id,
                    to_id=team_id,
                    from_type="Issue",
                    to_type="Team"
                ))
        
        # 6. Issue Links: BLOCKS, DEPENDS_ON, RELATES_TO
        issue_links = fields.get('issuelinks', [])
        for link in issue_links:
            link_type = link.get('type', {})
            link_name = link_type.get('name', '').lower()
            
            # Determine relationship type and direction
            outward_issue = link.get('outwardIssue')
            inward_issue = link.get('inwardIssue')
            
            if 'block' in link_name:
                # This issue blocks another
                if outward_issue:
                    linked_issue_id = f"issue_jira_{outward_issue.get('id')}"
                    relationships.append(Relationship(
                        type="BLOCKS",
                        from_id=issue_id,
                        to_id=linked_issue_id,
                        from_type="Issue",
                        to_type="Issue"
                    ))
                    # Bidirectional - also create DEPENDS_ON from other side
                    relationships.append(Relationship(
                        type="DEPENDS_ON",
                        from_id=linked_issue_id,
                        to_id=issue_id,
                        from_type="Issue",
                        to_type="Issue"
                    ))
                
                # Another issue blocks this one
                if inward_issue:
                    linked_issue_id = f"issue_jira_{inward_issue.get('id')}"
                    relationships.append(Relationship(
                        type="DEPENDS_ON",
                        from_id=issue_id,
                        to_id=linked_issue_id,
                        from_type="Issue",
                        to_type="Issue"
                    ))
                    # Bidirectional
                    relationships.append(Relationship(
                        type="BLOCKS",
                        from_id=linked_issue_id,
                        to_id=issue_id,
                        from_type="Issue",
                        to_type="Issue"
                    ))
            
            elif 'relate' in link_name or 'cloner' in link_name:
                # Generic relationship (e.g., for bugs related to stories)
                if outward_issue:
                    linked_issue_id = f"issue_jira_{outward_issue.get('id')}"
                    relationships.append(Relationship(
                        type="RELATES_TO",
                        from_id=issue_id,
                        to_id=linked_issue_id,
                        from_type="Issue",
                        to_type="Issue"
                    ))
                
                if inward_issue:
                    linked_issue_id = f"issue_jira_{inward_issue.get('id')}"
                    relationships.append(Relationship(
                        type="RELATES_TO",
                        from_id=issue_id,
                        to_id=linked_issue_id,
                        from_type="Issue",
                        to_type="Issue"
                    ))
        
        # Merge issue with relationships
        merge_issue(session, issue, relationships=relationships)
        
        logger.info(f"    ✓ Created {issue_type}: {issue_key} ({status})")
        return issue_id
        
    except Exception as e:
        logger.error(f"    ✗ Error in new_issue_handler: {str(e)}")
        logger.exception(e)
        return None

from typing import Any, Dict, Optional
from datetime import datetime, timezone

from connectors.neo4j_db.models import Issue, Relationship, merge_issue
from connectors.modules.jira.new_jira_user_handler import new_jira_user_handler
from connectors.modules.jira.team_stub_handler import get_or_create_team_stub
from connectors.commons.person_cache import PersonCache
from app.common.logger import logger
from connectors.producers.map_jira import map_issue



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
        jira_issue_id = issue_data.get('id')
        issue_key = issue_data.get('key')
        fields = issue_data.get('fields', {})

        if not jira_issue_id or not issue_key:
            logger.warning(f"    Issue missing id or key, skipping")
            return None

        issue_map = map_issue(issue_data, jira_base_url)
        issue_id = issue_map["id"]
        issue_type = issue_map["type"]

        logger.info(f"  Processing {issue_type}: {issue_key}")

        # Create Issue object
        _last_synced_at = datetime.now(timezone.utc).isoformat()
        issue = Issue(
            id=issue_id,
            key=issue_map["key"],
            type=issue_type,
            summary=issue_map["summary"],
            priority=issue_map["priority"],
            status=issue_map["status"],
            story_points=issue_map["story_points"],
            created_at=issue_map["created_at"],
            updated_at=issue_map["updated_at"],
            url=issue_map["url"],
            _last_synced_at=_last_synced_at
        )

        # Build relationships
        relationships = []

        # 1. PART_OF -> Epic
        epic_link_raw = issue_map["epic_link_raw"]
        parent_jira_id = issue_map["parent_jira_id"]
        parent_type = issue_map["parent_type"]

        if epic_link_raw:
            # Epic link field — look up by key/id in epic_id_map
            for jira_eid, neo4j_eid in epic_id_map.items():
                if epic_link_raw in neo4j_eid or jira_eid == epic_link_raw:
                    relationships.append(Relationship(
                        type="PART_OF",
                        from_id=issue_id,
                        to_id=neo4j_eid,
                        from_type="Issue",
                        to_type="Epic"
                    ))
                    break

        if parent_jira_id and parent_type == 'Epic' and not any(r.type == "PART_OF" for r in relationships):
            if parent_jira_id in epic_id_map:
                relationships.append(Relationship(
                    type="PART_OF",
                    from_id=issue_id,
                    to_id=epic_id_map[parent_jira_id],
                    from_type="Issue",
                    to_type="Epic"
                ))

        # 2. ASSIGNED_TO - Person
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

        # 3. REPORTED_BY - Person
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
        for sprint_ref in issue_map["sprint_refs"]:
            sprint_jira_id = sprint_ref["id"]
            if sprint_jira_id in sprint_id_map:
                relationships.append(Relationship(
                    type="IN_SPRINT",
                    from_id=issue_id,
                    to_id=sprint_id_map[sprint_jira_id],
                    from_type="Issue",
                    to_type="Sprint"
                ))

        # 5. TEAM - Team stub
        if issue_map["team_value"]:
            logger.debug(f"    Processing team assignment: {issue_map['team_value']}")
            team_id = get_or_create_team_stub(session, issue_map["team_value"])
            relationships.append(Relationship(
                type="TEAM",
                from_id=issue_id,
                to_id=team_id,
                from_type="Issue",
                to_type="Team"
            ))

        # 6. Issue Links: BLOCKS, DEPENDS_ON, RELATES_TO
        issue_links = issue_map["issue_links_raw"]
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
        
        logger.info(f"    ✓ Created {issue_type}: {issue_key} ({issue_map['status']})")
        return issue_id
        
    except Exception as e:
        logger.error(f"    ✗ Error in new_issue_handler: {str(e)}")
        logger.exception(e)
        return None

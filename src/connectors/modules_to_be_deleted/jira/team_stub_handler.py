"""Shared team stub creation logic for Jira handlers."""
from common.logger import logger


from typing import Any

def get_or_create_team_stub(session: Any, team_name: str) -> str:
    """
    Get or create a stub Team node for a team name.
    
    Creates a minimal Team node if it doesn't exist. When the full GitHub data
    is loaded later, the MERGE operation will update this stub with complete data.
    This allows Epics and Issues to reference teams regardless of load order.
    
    Args:
        session: Neo4j session
        team_name: Team name (e.g., "Platform Team")
        
    Returns:
        str: Team ID (always returns a valid ID)
    """
    # Generate team ID from name (same format GitHub uses)
    team_id = f"team_{team_name.lower().replace(' ', '_').replace('-', '_')}"
    
    query = """
    MERGE (t:Team {id: $team_id})
    ON CREATE SET t.name = $team_name,
                  t.source = 'jira_reference',
                  t.created_at = date()
    RETURN t.id as team_id, t.source as source
    """
    result = session.run(query, team_id=team_id, team_name=team_name)
    record = result.single()
    
    if record and record['source'] == 'jira_reference':
        logger.debug(f"    Created stub Team node for '{team_name}' (will be enriched when GitHub loads)")
    
    return team_id

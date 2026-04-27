from datetime import datetime, timezone
from connectors.commons.logger import logger
 
from typing import Any, Optional, cast

def get__last_synced_at(session: Any, repo_id: str) -> Optional[datetime]:
    """Get the _last_synced_at timestamp from Repository node.

    Args:
        session: Neo4j session
        repo_id: Repository node ID

    Returns:
        datetime | None: Last sync timestamp or None if not found/never synced
    """
    query = """
    MATCH (r:Repository {id: $repo_id})
    RETURN r._last_synced_at as _last_synced_at
    """
    result = session.run(query, repo_id=repo_id).single()

    if result and result['_last_synced_at']:
        # Neo4j datetime object - convert to Python datetime
        return cast(datetime, result['_last_synced_at'].to_native())
    return None

def update__last_synced_at(session: Any, repo_id: str) -> None:
    """Update the _last_synced_at timestamp on Repository node.
    
    Args:
        session: Neo4j session
        repo_id: Repository node ID
    """
    query = """
    MATCH (r:Repository {id: $repo_id})
    SET r._last_synced_at = datetime($timestamp)
    RETURN r
    """
    timestamp: str = datetime.now(timezone.utc).isoformat()
    session.run(query, repo_id=repo_id, timestamp=timestamp)
    logger.info(f"    ✓ Updated _last_synced_at to {timestamp}")

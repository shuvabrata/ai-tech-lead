"""
Shared GitHub User Processing Module

Provides common functionality for processing GitHub users across different contexts
(repository collaborators, team members, etc.)
"""

from datetime import datetime, timezone

from neo4j_db.models import IdentityMapping, Relationship, merge_identity_mapping, merge_relationship
from commons.identity_resolver import get_or_create_person
from commons.logger import logger


from typing import Any, Dict, List, Optional, Tuple

def get_users_needing_refresh(
    session: Any,
    github_users: List[Any],
    refresh_days: int = 7
) -> Tuple[List[Any], int]:
    """Filter GitHub users to only those needing refresh based on last_updated_at.
    
    Args:
        session: Neo4j session
        github_users: List of GitHub user objects (with login attribute)
        refresh_days: Number of days before refreshing identity data (default 7)
        
    Returns:
        tuple: (users_to_process, skip_count)
            - users_to_process: List of users that need processing
            - skip_count: Number of users skipped due to recent update
    """
    if not github_users:
        return [], 0
    
    # Extract usernames for batch query
    usernames = [u.login for u in github_users]
    
    # Query Neo4j for IdentityMapping nodes with recent updates
    query = """
    UNWIND $usernames as username
    MATCH (i:IdentityMapping {provider: 'GitHub', username: username})
    WHERE i.last_updated_at IS NOT NULL
      AND i.last_updated_at >= datetime() - duration({days: $refresh_days})
    RETURN collect(i.username) as recent_usernames
    """
    
    result = session.run(query, usernames=usernames, refresh_days=refresh_days).single()
    recent_usernames = set(result['recent_usernames']) if result and result['recent_usernames'] else set()
    
    # Filter users
    users_to_process = [u for u in github_users if u.login not in recent_usernames]
    skip_count = len(github_users) - len(users_to_process)
    
    return users_to_process, skip_count


def process_github_user(
    session: Any,
    github_user: Any,
    processed_users_cache: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """Process a GitHub user: create/update Person and IdentityMapping nodes.
    
    This function handles the common identity resolution pattern used across
    different GitHub user contexts (collaborators, team members, etc.).
    
    Args:
        session: Neo4j session
        github_user: GitHub user object with attributes like login, name, email
        processed_users_cache: Optional dict to track processed users within transaction
                               (prevents duplicate processing in same session)
        
    Returns:
        str | None: person_id if successful, None if failed
    """
    try:
        # Check cache to avoid processing same user twice in same session
        github_login = github_user.login
        if processed_users_cache is not None and github_login in processed_users_cache:
            logger.debug(f"      Skipping {github_login} (already processed in this session)")
            return processed_users_cache[github_login]
        
        # Extract available information from GitHub user
        logger.debug(f"      Processing GitHub user: {github_login}")
        
        github_name = github_user.name if hasattr(github_user, 'name') and github_user.name else github_login
        github_email = github_user.email if hasattr(github_user, 'email') and github_user.email else ""
        # Normalize email to lowercase immediately at source for case-insensitive identity resolution
        github_email = github_email.lower() if github_email else ""
        github_url = github_user.html_url if hasattr(github_user, 'html_url') and github_user.html_url else f"https://github.com/{github_login}"
        logger.debug(f"        User details: name='{github_name}', email='{github_email}', url='{github_url}'")

        # Get or create Person using email-based identity resolution
        # This ensures a single Person node per individual across all systems
        person_id, is_new = get_or_create_person(
            session,
            email=github_email if github_email else None,
            name=github_name,
            provider="github",
            external_id=github_login,
            url=github_url
        )
        
        if not person_id:
            logger.error(f"        Failed to get/create person for {github_login}")
            return None
        
        logger.debug(f"        {'Created new' if is_new else 'Found existing'} Person: {person_id}")

        # Create IdentityMapping node for GitHub with timestamp
        identity_id = f"identity_github_{github_login}"
        logger.debug(f"        Creating/updating IdentityMapping node: {identity_id}")
        identity = IdentityMapping(
            id=identity_id,
            provider="GitHub",
            username=github_login,
            email=github_email,
            last_updated_at=datetime.now(timezone.utc).isoformat()
        )

        # Create MAPS_TO relationship (undirected) between IdentityMapping and Person
        logger.debug(f"        Creating MAPS_TO relationship between {identity_id} and {person_id}")
        maps_to_relationship = Relationship(
            type="MAPS_TO",
            from_id=identity.id,
            to_id=person_id,
            from_type="IdentityMapping",
            to_type="Person"
        )

        # Merge IdentityMapping node with MAPS_TO relationship
        logger.debug(f"        Merging IdentityMapping with MAPS_TO relationship")
        merge_identity_mapping(session, identity, relationships=[maps_to_relationship])
        
        logger.debug(f"        ✓ Successfully processed GitHub user: {github_login}")
        
        # Cache the person_id to prevent duplicate processing in same session
        if processed_users_cache is not None:
            processed_users_cache[github_login] = person_id
        
        return person_id

    except Exception as e:
        logger.error(f"        ✗ Error processing GitHub user {github_user.login}: {str(e)}")
        logger.exception(e)
        return None

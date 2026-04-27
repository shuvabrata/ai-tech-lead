from typing import Any, Optional, Dict
from connectors.neo4j_db.models import Relationship, merge_relationship
from connectors.modules.github.map_permissions_to_general import map_permissions_to_general
from connectors.modules.github.process_github_user import process_github_user
from connectors.commons.logger import logger

def new_user_handler(
    session: Any,
    collaborator: Any,
    repo_id: str,
    repo_created_at: str,
    processed_users_cache: Optional[Dict[str, Any]] = None
) -> None:
    """Handle a new user collaborator by creating Person, IdentityMapping nodes and COLLABORATOR relationship (undirected).

    Args:
        session: Neo4j session
        collaborator: GitHub collaborator object with attributes like login, name, email, type, permissions
        repo_id: Repository ID to create COLLABORATOR relationship with
        repo_created_at: Repository creation date for relationship timestamp
        processed_users_cache: Optional dict to prevent duplicate user processing in same session
    """
    try:
        # Extract available information from collaborator
        github_login = collaborator.login
        logger.debug(f"    Processing new user handler for: {github_login}")
        
        # Process GitHub user: create/update Person and IdentityMapping nodes
        person_id = process_github_user(session, collaborator, processed_users_cache)
        
        if not person_id:
            logger.error(f"      Failed to process user for {github_login}")
            return

        # Extract permissions and map to general READ/WRITE
        logger.debug(f"      Processing permissions for {github_login}: {collaborator.permissions.__dict__}")
        permission = map_permissions_to_general(collaborator.permissions.__dict__)
        logger.debug(f"      Mapped permission: {permission}")

        # Determine role based on permissions
        role = None
        if collaborator.permissions.admin:
            role = "admin"
        elif collaborator.permissions.maintain:
            role = "maintainer"
        elif collaborator.permissions.push:
            role = "contributor"
        logger.debug(f"      Determined role: {role}")

        # Create COLLABORATOR relationship (undirected) between Person and Repository
        collab_properties = {
            "permission": permission,
            "granted_at": repo_created_at
        }
        if role:
            collab_properties["role"] = role
        logger.debug(f"      COLLABORATOR relationship properties: {collab_properties}")

        logger.debug(f"      Creating COLLABORATOR relationship between {person_id} and {repo_id}")
        collaborator_relationship = Relationship(
            type="COLLABORATOR",
            from_id=person_id,
            to_id=repo_id,
            from_type="Person",
            to_type="Repository",
            properties=collab_properties
        )

        logger.debug(f"      Merging COLLABORATOR relationship")
        merge_relationship(session, collaborator_relationship)
        collaborator_relationship.print_cli()
        
        logger.info(f"    ✓ Successfully processed user: {github_login}")
        logger.debug(f"      Final summary: person_id='{person_id}', permission='{permission}', role='{role}'")

    except Exception as e:
        logger.info(f"    ✗ Error: Failed to create user {collaborator.login}: {str(e)}")
        logger.exception(e)

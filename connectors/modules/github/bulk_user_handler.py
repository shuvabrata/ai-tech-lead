from datetime import datetime, timezone

from db.models import IdentityMapping, Relationship, merge_relationship
from modules.github.map_permissions_to_general import map_permissions_to_general
import time

from common.logger import logger
from common.person_cache import PersonCache
from typing import Any, List, Dict, Optional
from neo4j import Session

def bulk_user_handler(
    session: Session,
    collaborators: List[Any],
    repo_id: str,
    repo_created_at: str,
    batch_size: int = 50,
    person_cache: Optional[PersonCache] = None
) -> None:
    """Handle multiple collaborators in batches for better performance.

    Args:
        session: Neo4j session
        collaborators: List of GitHub collaborator objects
        repo_id: Repository ID to create COLLABORATOR relationship with
        repo_created_at: Repository creation date for relationship timestamp
        batch_size: Number of collaborators to process in each batch
        person_cache: Optional PersonCache for identity resolution. If None, creates a new one.
    """
    total_collaborators = len(collaborators)
    logger.info(f"    Processing {total_collaborators} collaborators in batches of {batch_size}...")
    logger.debug(f"    Parameters: repo_id={repo_id}, repo_created_at={repo_created_at}, batch_size={batch_size}")
    
    # Use provided cache or create new one
    if person_cache is None:
        person_cache = PersonCache()
        logger.debug("    Created new PersonCache for bulk_user_handler")
    
    # Track performance
    start_time = time.time()
    processed_count = 0
    failed_count = 0
    
    # Process in batches
    for i in range(0, total_collaborators, batch_size):
        batch = collaborators[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_collaborators + batch_size - 1) // batch_size
        
        logger.info(f"      Batch {batch_num}/{total_batches}: Processing {len(batch)} collaborators...")
        logger.debug(f"        Batch details: batch_size={len(batch)}, start_index={i}, end_index={min(i+batch_size, total_collaborators)}")
        
        try:
            # Prepare batch data
            identities = []
            relationships = []
            
            for collaborator in batch:
                try:
                    # Extract user information - avoid API calls for optional fields
                    github_login = collaborator.login
                    logger.debug(f"          Processing collaborator: {github_login}")
                    
                    # Use getattr with default to avoid API calls if properties aren't loaded
                    github_name = getattr(collaborator, 'name', None) or github_login
                    github_email = getattr(collaborator, 'email', None) or ""
                    # Normalize email to lowercase for case-insensitive matching
                    github_email = github_email.lower() if github_email else ""
                    logger.debug(f"          Collaborator details: name='{github_name}', email='{github_email}'")
                    
                    # Skip if not a User type
                    collaborator_type = getattr(collaborator, 'type', 'User')
                    if collaborator_type != 'User':
                        logger.debug(f"          Skipping non-User collaborator: {github_login} (type: {collaborator_type})")
                        continue
                    
                    # Use PersonCache for identity resolution (critical for avoiding duplicates)
                    person_id, is_new = person_cache.get_or_create_person(
                        session=session,
                        email=github_email or None,  # Normalize empty string to None
                        name=github_name,
                        provider="github",
                        external_id=github_login,
                        url=f"https://github.com/{github_login}"
                    )
                    
                    if person_id is None:
                        logger.warning(f"          Failed to resolve person_id for {github_login}, skipping")
                        continue
                    
                    identity_id = f"identity_github_{github_login}"
                    logger.debug(f"          Resolved person_id='{person_id}' (is_new={is_new}), identity_id='{identity_id}'")
                    
                    # Create IdentityMapping node with timestamp
                    identity = IdentityMapping(
                        id=identity_id,
                        provider="GitHub",
                        username=github_login,
                        email=github_email,
                        last_updated_at=datetime.now(timezone.utc).isoformat()
                    )
                    identities.append(identity)
                    
                    # MAPS_TO relationship
                    maps_to_rel = Relationship(
                        type="MAPS_TO",
                        from_id=identity_id,
                        to_id=person_id,
                        from_type="IdentityMapping",
                        to_type="Person"
                    )
                    relationships.append(maps_to_rel)
                    
                    # COLLABORATOR relationship - handle permissions safely
                    try:
                        # Try to get permissions if available, otherwise use default
                        permissions = getattr(collaborator, 'permissions', None)
                        if permissions:
                            logger.debug(f"          Found permissions for {github_login}: admin={getattr(permissions, 'admin', False)}, maintain={getattr(permissions, 'maintain', False)}, push={getattr(permissions, 'push', False)}, pull={getattr(permissions, 'pull', False)}")
                            permission = map_permissions_to_general(permissions.__dict__)
                            role = None
                            if getattr(permissions, 'admin', False):
                                role = "admin"
                            elif getattr(permissions, 'maintain', False):
                                role = "maintainer"
                            elif getattr(permissions, 'push', False):
                                role = "contributor"
                            logger.debug(f"          Mapped permissions: permission='{permission}', role='{role}'")
                        else:
                            # Default permissions if not available
                            logger.debug(f"          No permissions found for {github_login}, using defaults")
                            permission = "READ"
                            role = "contributor"
                    except Exception as perm_ex:
                        # Fallback if permissions access fails
                        logger.debug(f"          Permission access failed for {github_login}: {str(perm_ex)}")
                        logger.exception(perm_ex)
                        permission = "READ"
                        role = "contributor"
                    
                    collab_properties = {
                        "permission": permission,
                        "granted_at": repo_created_at
                    }
                    if role:
                        collab_properties["role"] = role
                    
                    collaborator_rel = Relationship(
                        type="COLLABORATOR",
                        from_id=person_id,
                        to_id=repo_id,
                        from_type="Person",
                        to_type="Repository",
                        properties=collab_properties
                    )
                    relationships.append(collaborator_rel)
                    
                    processed_count += 1
                    
                except Exception as e:
                    logger.info(f"        Warning: Failed to prepare {collaborator.login}: {str(e)}")
                    logger.exception(e)
                    failed_count += 1
                    continue
            
            # Bulk merge into Neo4j in single transaction
            if identities or relationships:
                logger.debug(f"        Bulk merging batch {batch_num}: {len(identities)} identities, {len(relationships)} relationships")
                _bulk_merge_nodes(session, identities, relationships)
                logger.debug(f"        Successfully merged batch {batch_num}")
            else:
                logger.debug(f"        No valid collaborators in batch {batch_num}, skipping merge")
            
        except Exception as e:
            logger.info(f"        Error processing batch {batch_num}: {str(e)}")
            logger.exception(e)
            logger.debug(f"        Batch {batch_num} exception details", exc_info=True)
            failed_count += len(batch)
    
    # Flush PersonCache identity mappings
    try:
        person_cache.flush_identity_mappings(session)
        cache_stats = person_cache.get_stats()
        logger.debug(f"    PersonCache stats: {cache_stats['cache_hits']} hits, {cache_stats['cache_misses']} misses, hit rate: {cache_stats['hit_rate']}")
    except Exception as flush_ex:
        logger.warning(f"    Failed to flush PersonCache: {str(flush_ex)}")
    
    # Performance summary
    end_time = time.time()
    duration = end_time - start_time
    logger.info("    ✓ Bulk processing completed:")
    logger.info(f"      - Processed: {processed_count} collaborators")
    logger.info(f"      - Failed: {failed_count} collaborators") 
    logger.info(f"      - Duration: {duration:.2f}s")
    logger.info(f"      - Rate: {processed_count/duration:.1f} collaborators/second")


def _bulk_merge_nodes(
    session: Session,
    identities: List[IdentityMapping],
    relationships: List[Relationship]
) -> None:
    """Merge IdentityMapping nodes and relationships in bulk using single transaction.
    
    Note: Person nodes are created via PersonCache.get_or_create_person() which handles
    identity resolution. This function only creates IdentityMappings and relationships.
    """
    logger.debug(f"        Starting bulk merge: {len(identities)} identities, {len(relationships)} relationships")
    # Build bulk merge queries (Person nodes are handled by PersonCache)
    identity_query: str = """
    UNWIND $identities as identity_data
    MERGE (i:IdentityMapping {id: identity_data.id})
    SET i.provider = identity_data.provider,
        i.username = identity_data.username,
        i.email = identity_data.email,
        i.last_updated_at = CASE WHEN identity_data.last_updated_at IS NOT NULL 
                                  THEN datetime(identity_data.last_updated_at) 
                                  ELSE null END
    """
    
    relationship_query: str = """
    UNWIND $relationships as rel_data
    MATCH (from_node {id: rel_data.from_id})
    MATCH (to_node {id: rel_data.to_id})
    CALL apoc.create.relationship(from_node, rel_data.type, rel_data.properties, to_node)
    YIELD rel
    RETURN count(rel)
    """
    
    # Alternative relationship query for environments without APOC
    simple_relationship_query: str = """
    UNWIND $relationships as rel_data
    MATCH (from_node {id: rel_data.from_id})
    MATCH (to_node {id: rel_data.to_id})
    MERGE (from_node)-[r {type: rel_data.type}]->(to_node)
    SET r += rel_data.properties
    """
    
    try:
        # Convert to Neo4j format (Person nodes already created by PersonCache)
        identity_data: List[Dict[str, Any]] = [identity.to_neo4j_properties() for identity in identities]
        
        # Convert relationships
        rel_data: List[Dict[str, Any]] = []
        for rel in relationships:
            rel_dict: Dict[str, Any] = {
                "from_id": rel.from_id,
                "to_id": rel.to_id,
                "type": rel.type,
                "properties": rel.properties or {}
            }
            rel_data.append(rel_dict)
        
        # Execute bulk operations
        logger.debug(f"          Executing identity merge query for {len(identity_data)} identities")
        session.run(identity_query, identities=identity_data)
        
        # Try APOC relationship creation first, fall back to simple if not available
        try:
            logger.debug(f"          Executing APOC relationship query for {len(rel_data)} relationships")
            session.run(relationship_query, relationships=rel_data)
        except Exception as apoc_ex:
            # Fallback: create relationships one by one but in same transaction
            logger.debug(f"          APOC relationship creation failed: {str(apoc_ex)}, falling back to individual creation")
            logger.exception(apoc_ex)
            for rel in relationships:
                merge_relationship(session, rel)
            logger.debug(f"          Created {len(relationships)} relationships individually")
    
    except Exception as e:
        logger.info(f"        Error in bulk merge: {str(e)}")
        logger.exception(e)
        raise
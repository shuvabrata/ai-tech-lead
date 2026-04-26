"""
Session-level Person Cache

Provides in-memory caching of person lookups to avoid repeated database queries
when processing large batches of PRs, commits, or issues where the same users
appear repeatedly.

Usage:
    cache = PersonCache()
    person_id = cache.get_or_create_person(session, email, name, ...)
    
    # At end of batch processing
    cache.flush_identity_mappings(session)
"""

from typing import Optional, Tuple, Dict, Set
from db.models import Person, IdentityMapping, Relationship, merge_person, merge_identity_mapping
from common.logger import logger


from typing import Any

class PersonCache:
    """
    In-memory cache for Person lookups during batch operations.
    
    Caches both email-based and provider-specific lookups to avoid
    repeated database queries for the same users.
    
    Also batches IdentityMapping creation until flush() is called.
    """
    
    def __init__(self) -> None:
        # Cache: email -> person_id
        self._email_cache: Dict[str, str] = {}
        
        # Cache: (provider, external_id) -> person_id
        self._provider_cache: Dict[Tuple[str, str], str] = {}
        
        # Track IdentityMappings to create (deferred until flush)
        self._pending_identities: Dict[str, Tuple[IdentityMapping, Relationship]] = {}
        
        # Track which person_ids we've already flushed identities for
        self._flushed_persons: Set[str] = set()
        
        # Statistics
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.db_queries: int = 0
    
    def get_or_create_person(
        self,
        session: Any,
        email: Optional[str],
        name: str,
        provider: Optional[str] = None,
        external_id: Optional[str] = None,
        url: Optional[str] = None
    ) -> Tuple[str, bool]:
        """
        Get existing Person by email or create a new one.
        Uses in-memory cache to avoid repeated database queries.
        
        Args:
            session: Neo4j session
            email: Email address (canonical identifier)
            name: Display name or full name
            provider: System name ('github', 'jira', etc.)
            external_id: External system ID
            url: URL to user profile
            
        Returns:
            tuple: (person_id, is_new)
                - person_id: The canonical Person node ID
                - is_new: True if a new Person was created, False if existing
        """
        # Normalize email
        email = email if email else None
        
        # Try cache lookup first
        if email:
            if email in self._email_cache:
                self.cache_hits += 1
                person_id = self._email_cache[email]
                logger.debug(f"    ⚡ Cache hit for email: {email} -> {person_id}")
                return person_id, False
        elif provider and external_id:
            if (provider, external_id) in self._provider_cache:
                self.cache_hits += 1
                person_id = self._provider_cache[(provider, external_id)]
                logger.debug(f"    ⚡ Cache hit for {provider}:{external_id} -> {person_id}")
                return person_id, False
        
        # Cache miss - need to check database
        self.cache_misses += 1
        
        # Determine canonical person_id
        if email:
            person_id = f"person_{email}"
            logger.debug(f"    Using email-based person ID: {person_id}")
        elif provider and external_id:
            person_id = f"person_{provider}_{external_id}"
            logger.debug(f"    No email available, using provider-specific ID: {person_id}")
        else:
            raise ValueError("    Cannot create person_id: both email and provider/external_id are missing")
     
        # Check if Person already exists in database
        is_new = False
        if email:
            logger.debug(f"    Checking database for Person with email: {email}")
            self.db_queries += 1
            result = session.run(
                """
                MATCH (p:Person)
                WHERE p.email = $email AND p.email IS NOT NULL
                RETURN p.id as id
                LIMIT 1
                """,
                email=email
            )
            existing = result.single()
            
            if existing:
                existing_id = existing['id']
                logger.debug(f"    ✓ Found existing Person in DB: {existing_id}")
                person_id = existing_id
                # Cache it for future lookups
                self._email_cache[email] = person_id
                if provider and external_id:
                    self._provider_cache[(provider, external_id)] = person_id
                return person_id, False
        
        # Person doesn't exist - create new one
        logger.debug(f"    Creating new Person node: {person_id}")
        person = Person(
            id=person_id,
            name=name,
            email=email,
            title="",
            role="",
            seniority="",
            hire_date="",
            is_manager=False,
            url=url
        )
        
        merge_person(session, person)
        logger.debug(f"    ✓ Created new Person: {person_id}")
        is_new = True
        
        # Add to cache
        if email:
            self._email_cache[email] = person_id
        if provider and external_id:
            self._provider_cache[(provider, external_id)] = person_id
        
        return person_id, is_new
    
    def queue_identity_mapping(
        self,
        person_id: str,
        identity_id: str,
        provider: str,
        username: str,
        email: str,
        last_updated_at: str
    ) -> None:
        """
        Queue an IdentityMapping to be created on flush.
        Only creates one mapping per person_id to avoid redundant writes.
        
        Args:
            person_id: Person node ID
            identity_id: IdentityMapping node ID
            provider: Provider name (GitHub, Jira, etc.)
            username: External username
            email: Email address
            last_updated_at: ISO timestamp
        """
        # Skip if we've already created this identity mapping
        if identity_id in self._pending_identities:
            return
        
        # Skip if we've already flushed this person
        if person_id in self._flushed_persons:
            return
        
        identity = IdentityMapping(
            id=identity_id,
            provider=provider,
            username=username,
            email=email if email else "",
            last_updated_at=last_updated_at
        )
        
        maps_to_rel = Relationship(
            type="MAPS_TO",
            from_id=identity_id,
            to_id=person_id,
            from_type="IdentityMapping",
            to_type="Person"
        )
        
        self._pending_identities[identity_id] = (identity, maps_to_rel)
        logger.debug(f"    Queued IdentityMapping for {person_id}")
    
    def flush_identity_mappings(self, session: Any) -> None:
        """
        Create all pending IdentityMapping nodes and relationships.
        Call this after processing a batch of PRs/commits.
        """
        if not self._pending_identities:
            logger.debug("No pending identity mappings to flush")
            return
        
        count = len(self._pending_identities)
        logger.info(f"Flushing {count} identity mappings to database...")
        
        for identity_id, (identity, relationship) in self._pending_identities.items():
            merge_identity_mapping(session, identity, relationships=[relationship])
            # Track the person as flushed
            self._flushed_persons.add(relationship.to_id)
        
        self._pending_identities.clear()
        logger.info(f"✓ Flushed {count} identity mappings")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'db_queries': self.db_queries,
            'hit_rate': f"{(self.cache_hits / (self.cache_hits + self.cache_misses) * 100):.1f}%" if (self.cache_hits + self.cache_misses) > 0 else "0%",
            'pending_identities': len(self._pending_identities)
        }
    
    def clear(self) -> None:
        """Clear all caches."""
        self._email_cache.clear()
        self._provider_cache.clear()
        self._pending_identities.clear()
        self._flushed_persons.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        self.db_queries = 0

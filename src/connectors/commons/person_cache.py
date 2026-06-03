"""Session-level Person cache."""

from typing import Any, Dict, Optional, Set, Tuple

from common.activity_signal.wba_node_id import wba_format
from common.logger import logger
from connectors.neo4j_db.models import (
    IdentityMapping,
    Person,
    Relationship,
    merge_identity_mapping,
    merge_person,
)


_ATLASSIAN_PROVIDERS = {"jira", "confluence"}

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

        # Cache: Atlassian account_id -> person_id
        self._atlassian_account_cache: Dict[str, str] = {}
        
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
        provider: str = None,
        external_id: str = None,
        url: Optional[str] = None,
        account_id: Optional[str] = None,
    ) -> Tuple[str, bool]:
        """
        Get or create a Person node with cross-provider email deduplication.

          Lookup order:
          1. In-memory provider cache ``(provider, external_id)``.
          2. In-memory email cache.
          3. Database lookup by email.
          4. In-memory Atlassian account_id cache for Jira/Confluence.
          5. Database lookup by Atlassian account_id for Jira/Confluence.
          6. Database lookup by provider-scoped id.
          7. Create a new provider-scoped Person node.

        Args:
            session: Neo4j session
            email: Email address — stored as a property; used for deduplication
            name: Display name or full name
            provider: System name ('github', 'jira', etc.)
            external_id: External system ID
            url: URL to user profile

        Returns:
            tuple: (person_id, is_new)
                - person_id: The canonical Person node ID
                - is_new: True if a new Person was created, False if existing
        """
        if not (provider and external_id):
            raise ValueError("    Cannot create person_id: provider and external_id are required")

        email = email if email else None
        account_id = account_id if account_id else None
        if provider in _ATLASSIAN_PROVIDERS and account_id is None:
            account_id = external_id

        # ── 1. Provider cache (fastest) ───────────────────────────────────────
        if (provider, external_id) in self._provider_cache:
            self.cache_hits += 1
            person_id = self._provider_cache[(provider, external_id)]
            logger.debug(f"    ⚡ Cache hit (provider) {provider}:{external_id} -> {person_id}")
            return person_id, False

        # ── 2. Email cache (cross-provider, same batch) ───────────────────────
        if email and email in self._email_cache:
            self.cache_hits += 1
            person_id = self._email_cache[email]
            logger.debug(f"    ⚡ Cache hit (email) {email} -> {person_id}")
            self._provider_cache[(provider, external_id)] = person_id
            if account_id:
                self._atlassian_account_cache[account_id] = person_id
            return person_id, False

        self.cache_misses += 1
        fallback_person_id = wba_format(provider, "Person", external_id)

        # ── 3. DB lookup by email (cross-provider, prior sync runs) ──────────
        if email:
            self.db_queries += 1
            result = session.run(
                "MATCH (p:Person) WHERE p.email = $email RETURN p.id AS id LIMIT 1",
                email=email,
            )
            existing_by_email = result.single()
            if existing_by_email:
                person_id = existing_by_email["id"]
                logger.debug(
                    f"    ✓ Found existing Person by email '{email}': {person_id} — "
                    f"reusing instead of creating {fallback_person_id}"
                )
                person = Person(
                    id=person_id, name=name, email=email, url=url,
                )
                merge_person(session, person)
                self._email_cache[email] = person_id
                self._provider_cache[(provider, external_id)] = person_id
                if account_id:
                    self._atlassian_account_cache[account_id] = person_id
                return person_id, False

        # ── 4. Atlassian account cache / lookup ──────────────────────────────
        if provider in _ATLASSIAN_PROVIDERS and account_id:
            if account_id in self._atlassian_account_cache:
                self.cache_hits += 1
                person_id = self._atlassian_account_cache[account_id]
                logger.debug(f"    ⚡ Cache hit (atlassian_account) {account_id} -> {person_id}")
                self._provider_cache[(provider, external_id)] = person_id
                if email:
                    self._email_cache[email] = person_id
                return person_id, False

            self.db_queries += 1
            existing_by_account = self._lookup_by_atlassian_account(session, account_id)
            if existing_by_account:
                person_id = existing_by_account
                logger.debug(
                    "    ✓ Found existing Person by Atlassian account_id '%s': %s — reusing instead of creating %s",
                    account_id,
                    person_id,
                    fallback_person_id,
                )
                person = Person(
                    id=person_id, name=name, email=email, url=url,
                )
                merge_person(session, person)
                self._atlassian_account_cache[account_id] = person_id
                self._provider_cache[(provider, external_id)] = person_id
                if email:
                    self._email_cache[email] = person_id
                return person_id, False

        # ── 5 & 6. Provider-scoped lookup / create ────────────────────────────
        person_id = fallback_person_id
        logger.debug(f"    Using provider-scoped person ID: {person_id}")

        self.db_queries += 1
        existing_by_id = session.run(
            "MATCH (p:Person {id: $pid}) RETURN p.id AS id LIMIT 1", pid=person_id
        ).single()
        is_new = existing_by_id is None

        person = Person(
            id=person_id, name=name, email=email, url=url,
        )
        merge_person(session, person)
        logger.debug(f"    {'✓ Created' if is_new else '✓ Updated'} Person: {person_id}")

        if email:
            self._email_cache[email] = person_id
        if account_id:
            self._atlassian_account_cache[account_id] = person_id
        self._provider_cache[(provider, external_id)] = person_id
        return person_id, is_new

    def _lookup_by_atlassian_account(self, session: Any, account_id: str) -> Optional[str]:
        """Resolve a Jira/Confluence account_id to an existing canonical Person id."""
        identity_ids = [
            wba_format("jira", "IdentityMapping", account_id),
            wba_format("confluence", "IdentityMapping", account_id),
        ]
        person_ids = [
            wba_format("jira", "Person", account_id),
            wba_format("confluence", "Person", account_id),
        ]

        existing_by_identity = session.run(
            (
                "MATCH (im:IdentityMapping)-[:MAPS_TO]->(p:Person) "
                "WHERE im.id IN $identity_ids "
                "RETURN p.id AS id "
                "LIMIT 1"
            ),
            identity_ids=identity_ids,
        ).single()
        if existing_by_identity:
            return existing_by_identity["id"]

        existing_by_person_id = session.run(
            "MATCH (p:Person) WHERE p.id IN $person_ids RETURN p.id AS id LIMIT 1",
            person_ids=person_ids,
        ).single()
        if existing_by_person_id:
            return existing_by_person_id["id"]

        return None
    
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
        self._atlassian_account_cache.clear()
        self._provider_cache.clear()
        self._pending_identities.clear()
        self._flushed_persons.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        self.db_queries = 0

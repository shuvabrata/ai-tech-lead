"""
Identity Resolution Module

Provides provider-scoped identity resolution with cross-provider deduplication.

Strategy:
1. **Email deduplication (cross-provider)** — if an email is supplied, search
   for any existing Person node that already carries that email.  If found,
   that node is reused regardless of which provider originally created it.
   This merges ``person_github_alice`` and ``person_jira_alice`` into a single
   node as soon as both are seen with the same email address.

2. **Provider-scoped id for new nodes** — when no existing node is found by
   email, the id is always ``person_{provider}_{external_id}``
   (e.g. ``person_github_alice``).

3. **Additive property updates** — null/empty fields on an existing node are
   filled in whenever a richer record arrives.  Non-empty fields (name, url)
   are overwritten by the incoming value; only blank/missing values are
   preserved.
"""

from typing import Optional, Tuple
from neo4j import Session
from connectors.neo4j_db.models import Person, merge_person
from common.logger import logger


def get_or_create_person(
    session: Session,
    email: Optional[str],
    name: str,
    provider: str = None,
    external_id: str = None,
    url: Optional[str] = None
) -> Tuple[Optional[str], bool]:
    """
    Get or create a Person node using the provider-scoped id as the canonical key.

    The node id is always ``person_{provider}_{external_id}``.  Email is stored
    as an additional property and updated (additive only) whenever it is supplied.

    Args:
        session: Neo4j session
        email: Email address — stored as a property, not used as the node id
        name: Display name or full name
        provider: System name ('github', 'jira', etc.)
        external_id: External system ID (GitHub login, Jira account_id, etc.)
        url: URL to user profile

    Returns:
        tuple: (person_id, is_new)
            - person_id: The canonical Person node ID
            - is_new: True if a new Person was created, False if existing

    Examples:
        person_id, is_new = get_or_create_person(
            session,
            email="alice@company.com",
            name="Alice Smith",
            provider="github",
            external_id="alice",
        )
        # Returns: ("person_github_alice", True/False)
    """
    if not (provider and external_id):
        logger.error("    Cannot create person_id: provider and external_id are required")
        return None, False

    email = email if email else None
    person_id = f"{provider}::Person::{external_id}"

    # ── Step 1: cross-provider deduplication via email ───────────────────────
    # If we have an email, check whether any Person node already carries it.
    # This handles the case where the same individual was previously synced
    # from a different provider (e.g. person_github_alice already exists and
    # now person_jira_alice arrives with the same email).
    if email:
        result = session.run(
            "MATCH (p:Person) WHERE p.email = $email RETURN p.id AS id LIMIT 1",
            email=email,
        )
        existing_by_email = result.single()
        if existing_by_email:
            existing_id = existing_by_email["id"]
            logger.debug(
                f"    ✓ Found existing Person by email '{email}': {existing_id} — "
                f"reusing instead of creating {person_id}"
            )
            # Enrich with any properties this record adds (name, url, etc.)
            person = Person(
                id=existing_id,
                name=name,
                email=email,
                url=url,
            )
            merge_person(session, person)
            return existing_id, False

    # ── Step 2: provider-scoped lookup / create ──────────────────────────────
    logger.debug(f"    Using provider-scoped person ID: {person_id}")

    existing_by_id = session.run(
        "MATCH (p:Person {id: $pid}) RETURN p.id AS id LIMIT 1", pid=person_id
    ).single()
    is_new = existing_by_id is None

    person = Person(
        id=person_id,
        name=name,
        email=email,
        url=url,
    )
    merge_person(session, person)
    logger.debug(f"    {'✓ Created' if is_new else '✓ Updated'} Person: {person_id}")

    return person_id, is_new

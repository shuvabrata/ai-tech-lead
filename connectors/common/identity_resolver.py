"""
Identity Resolution Module

Provides email-based identity resolution to ensure a single Person node per individual
across multiple systems (GitHub, Jira, etc.).

Strategy: Email-as-Master-Key
- Use email address as the canonical identifier
- Before creating a Person node, check if one exists with that email
- Reuse existing Person nodes to prevent duplicates
- Fall back to provider-specific IDs when email is unavailable
"""

from typing import Optional, Tuple
from neo4j import Session
from db.models import Person, merge_person
from common.logger import logger


def get_or_create_person(
    session: Session,
    email: Optional[str],
    name: str,
    provider: Optional[str] = None,
    external_id: Optional[str] = None,
    url: Optional[str] = None
) -> Tuple[Optional[str], bool]:
    """
    Get existing Person by email or create a new one.
    
    This function implements email-based identity resolution to ensure that
    the same individual across different systems (GitHub, Jira, etc.) maps
    to a single Person node in the graph.
    
    Args:
        session: Neo4j session
        email: Email address (canonical identifier)
        name: Display name or full name
        provider: System name ('github', 'jira', etc.) - used for fallback ID
        external_id: External system ID - used for fallback ID when no email
        url: URL to user profile (preferably GitHub profile URL)
        
    Returns:
        tuple: (person_id, is_new)
            - person_id: The canonical Person node ID
            - is_new: True if a new Person was created, False if existing
            
    Examples:
        # User with email (will match across systems)
        person_id, is_new = get_or_create_person(
            session, 
            email="alice@company.com",
            name="Alice Smith",
            provider="github",
            external_id="alice",
            url="https://github.com/alice"
        )
        # Returns: ("person_alice@company.com", True/False)
        
        # User without email (falls back to provider-specific ID)
        person_id, is_new = get_or_create_person(
            session,
            email=None,
            name="Bot User",
            provider="github", 
            external_id="bot-123"
        )
        # Returns: ("person_github_bot-123", True)
    """
    
    # Normalize email: convert empty string to None for proper NULL handling in Neo4j
    # This allows multiple users without emails (UNIQUE constraint allows multiple NULLs)
    # NOTE: Email should already be lowercased at source (GitHub/Jira extractors)
    email = email if email else None
    
    # Determine canonical person_id
    if email:
        # Email-based canonical ID
        person_id = f"person_{email}"
        logger.debug(f"    Using email-based person ID: {person_id}")
    elif provider and external_id:
        # Fall back to provider-specific ID (for users without email)
        person_id = f"person_{provider}_{external_id}"
        logger.debug(f"    No email available, using provider-specific ID: {person_id}")
    else:
        logger.error("    Cannot create person_id: both email and provider/external_id are missing")
        return None, False
    
    # Check if Person already exists by email (canonical lookup)
    # Only lookup by email if email is not None
    if email:
        logger.debug(f"    Checking for existing Person with email: {email}")
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
            logger.debug(f"    ✓ Found existing Person: {existing_id}")
            return existing_id, False
    
    # No existing Person found - create new one
    logger.debug(f"    Creating new Person node: {person_id}")
    person = Person(
        id=person_id,
        name=name,
        email=email,  # None if no email (allows multiple NULLs with UNIQUE constraint)
        title="",
        role="",
        seniority="",
        hire_date="",
        is_manager=False,
        url=url
    )
    
    merge_person(session, person)
    logger.debug(f"    ✓ Created new Person: {person_id}")
    
    return person_id, True

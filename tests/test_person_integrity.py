"""Integration tests for Person node data integrity in Neo4j.

These tests verify the two invariants that must hold after every sync run:
1. Every Person node is linked to at least one IdentityMapping via MAPS_TO.
2. Every Person email stored in Neo4j is lowercase.

Requires a live Neo4j instance.

Run with::

    pytest tests/test_person_integrity.py -m neo4j -v
"""

import pytest

from app.api.graph.v1.query import execute_cypher_query
from app.settings import settings


pytestmark = [pytest.mark.integration, pytest.mark.neo4j]


@pytest.mark.skipif(
    not settings.NEO4J_ENABLED,
    reason="Neo4j is not enabled (NEO4J_ENABLED=false)",
)
class TestPersonIntegrity:
    """Data-integrity checks for Person nodes in Neo4j."""

    def test_every_person_has_identity_mapping(self) -> None:
        """Every Person node must have at least one incoming MAPS_TO edge from an IdentityMapping.

        A Person without an IdentityMapping means the consumer failed to create
        or link the identity record during the sync run.
        """
        results = execute_cypher_query(
            """
            MATCH (p:Person)
            WHERE NOT (:IdentityMapping)-[:MAPS_TO]->(p)
            RETURN p.id AS id, p.name AS name, p.email AS email
            ORDER BY p.id
            """,
            timeout=30,
        )

        violations = [dict(r) for r in results]
        assert violations == [], (
            f"{len(violations)} Person node(s) have no IdentityMapping link:\n"
            + "\n".join(
                f"  id={v['id']}  email={v['email'] or '(none)'}  name={v['name'] or ''}"
                for v in violations
            )
        )

    def test_all_person_emails_are_lowercase(self) -> None:
        """Every non-null Person email must already be stored in lowercase.

        Mixed-case emails (e.g. User@Flexera.com) break the email-based
        cross-provider deduplication that uses exact-match lookups.
        """
        results = execute_cypher_query(
            """
            MATCH (p:Person)
            WHERE p.email IS NOT NULL
              AND p.email <> toLower(p.email)
            RETURN p.id AS id, p.email AS email
            ORDER BY p.id
            """,
            timeout=30,
        )

        violations = [dict(r) for r in results]
        assert violations == [], (
            f"{len(violations)} Person node(s) have mixed-case email:\n"
            + "\n".join(
                f"  id={v['id']}  email={v['email']}"
                for v in violations
            )
        )

    def test_all_identity_mapping_emails_are_lowercase(self) -> None:
        """Every non-null IdentityMapping email must be stored in lowercase.

        IdentityMapping nodes carry their own email copy used for
        cross-provider matching; mixed case there causes the same deduplication
        failures as on the Person node itself.
        """
        results = execute_cypher_query(
            """
            MATCH (im:IdentityMapping)
            WHERE im.email IS NOT NULL
              AND im.email <> ''
              AND im.email <> toLower(im.email)
            RETURN im.id AS id, im.email AS email
            ORDER BY im.id
            """,
            timeout=30,
        )

        violations = [dict(r) for r in results]
        assert violations == [], (
            f"{len(violations)} IdentityMapping node(s) have mixed-case email:\n"
            + "\n".join(
                f"  id={v['id']}  email={v['email']}"
                for v in violations
            )
        )

    def test_no_duplicate_persons_sharing_identity_mapping(self) -> None:
        """No two Person nodes may share the same IdentityMapping node.

        A shared IdentityMapping means the consumer created or merged two
        separate Person nodes for the same individual, which breaks
        cross-provider deduplication and relationship queries.
        """
        results = execute_cypher_query(
            """
            MATCH (im:IdentityMapping)-[:MAPS_TO]->(p:Person)
            WITH im, collect(p.id) AS person_ids, count(p) AS cnt
            WHERE cnt > 1
            RETURN im.id AS identity_id, person_ids, cnt
            ORDER BY cnt DESC, im.id
            """,
            timeout=30,
        )

        violations = [dict(r) for r in results]
        assert violations == [], (
            f"{len(violations)} IdentityMapping node(s) point to multiple Person nodes:\n"
            + "\n".join(
                f"  identity={v['identity_id']}  persons={v['person_ids']}  count={v['cnt']}"
                for v in violations
            )
        )

    def test_no_stale_id_prefixes(self) -> None:
        """Person nodes must not use the legacy ID prefixes jira_person_* or github_person_*.

        The canonical format is person_jira_* and person_github_*. Stale-prefix
        nodes are stub nodes created when a producer emits relationship targets
        using the old naming convention, leaving them without email, name, or
        IdentityMapping.
        """
        results = execute_cypher_query(
            """
            MATCH (p:Person)
            WHERE p.id STARTS WITH 'jira_person_'
               OR p.id STARTS WITH 'github_person_'
            RETURN p.id AS id, p.name AS name, p.email AS email
            ORDER BY p.id
            """,
            timeout=30,
        )

        violations = [dict(r) for r in results]
        assert violations == [], (
            f"{len(violations)} Person node(s) use a stale ID prefix "
            f"(jira_person_* or github_person_*) — re-sync required:\n"
            + "\n".join(
                f"  id={v['id']}  email={v['email'] or '(none)'}  name={v['name'] or ''}"
                for v in violations
            )
        )

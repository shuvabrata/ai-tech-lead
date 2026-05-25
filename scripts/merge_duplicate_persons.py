"""
Report duplicate Person nodes in Neo4j for manual validation.

Writes a plain-text report to a file listing every suspected duplicate group
with each node's id and email so you can confirm before any fix is applied.

DETECTION STRATEGY
------------------
1. **Shared IdentityMapping** – two Person nodes that both have a
   ``MAPS_TO`` edge from the same IdentityMapping are definitively the
   same individual.
2. **Name match** (opt-in via --name-match) – a Person without an email
   whose name exactly matches a Person that has an email is a probable
   duplicate.

INTEGRITY AUDIT
---------------
Every Person node is expected to have:
  * A non-null email property.
  * At least one incoming ``MAPS_TO`` edge from an IdentityMapping node.
The report flags any Person that violates either expectation, and
highlights the especially suspicious case of a Person that *has* an
email yet is still unlinked from any IdentityMapping.

USAGE
-----
    python scripts/merge_duplicate_persons.py
    python scripts/merge_duplicate_persons.py --name-match
    python scripts/merge_duplicate_persons.py --output my_report.txt

Environment variables (or .env file):
    NEO4J_URI       bolt://localhost:7687
    NEO4J_USERNAME  neo4j
    NEO4J_PASSWORD  <password>
"""

import os
import sys
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from neo4j import GraphDatabase, Session  # type: ignore[import-untyped]
from dotenv import load_dotenv  # type: ignore[import-untyped]

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

_PROVIDER_ID_PREFIXES = ("person_github_", "person_jira_")

DEFAULT_OUTPUT = "duplicate_persons_report.txt"


def _is_provider_scoped(person_id: str) -> bool:
    return any(person_id.startswith(p) for p in _PROVIDER_ID_PREFIXES)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def query_all_persons(session: Session) -> list[dict]:
    """Return all Person nodes sorted by id."""
    result = session.run(
        "MATCH (p:Person) RETURN p.id AS id, p.name AS name, p.email AS email ORDER BY p.id"
    )
    return [dict(row) for row in result]


def query_shared_identity_mapping_groups(session: Session) -> list[dict]:
    """
    Return groups of Person nodes that share the same IdentityMapping.
    Each group is a dict: {identity_id, persons: [{id, name, email, rel_count}]}.
    """
    result = session.run(
        """
        MATCH (im:IdentityMapping)-[:MAPS_TO]->(p:Person)
        WITH im, collect(p) AS persons, count(p) AS cnt
        WHERE cnt > 1
        UNWIND persons AS p
        OPTIONAL MATCH (p)-[r]-()
        WITH im, p, count(r) AS rel_count
        WITH im, collect({id: p.id, name: p.name, email: p.email, rel_count: rel_count}) AS persons
        RETURN im.id AS identity_id, persons
        ORDER BY im.id
        """
    )
    return [dict(row) for row in result]


def query_persons_without_identity_mapping(session: Session) -> list[dict]:
    """
    Return Person nodes that have no incoming MAPS_TO edge from any IdentityMapping.
    Each dict: {id, name, email}.
    """
    result = session.run(
        """
        MATCH (p:Person)
        WHERE NOT (:IdentityMapping)-[:MAPS_TO]->(p)
        RETURN p.id AS id, p.name AS name, p.email AS email
        ORDER BY p.id
        """
    )
    return [dict(row) for row in result]


def query_name_match_groups(session: Session) -> list[dict]:
    """
    Return probable duplicate pairs: same name, one has email, one does not.
    Returns list of dicts: {name, persons: [{id, name, email, rel_count}]}.
    """
    result = session.run(
        """
        MATCH (p1:Person), (p2:Person)
        WHERE p1.name IS NOT NULL
          AND p1.name = p2.name
          AND p1.email IS NOT NULL
          AND p2.email IS NULL
          AND id(p1) < id(p2)
        OPTIONAL MATCH (p1)-[r1]-()
        WITH p1, p2, count(r1) AS rc1
        OPTIONAL MATCH (p2)-[r2]-()
        WITH p1, p2, rc1, count(r2) AS rc2
        RETURN
            p1.name AS name,
            [{id: p1.id, name: p1.name, email: p1.email, rel_count: rc1},
             {id: p2.id, name: p2.name, email: p2.email, rel_count: rc2}] AS persons
        ORDER BY p1.name
        """
    )
    return [dict(row) for row in result]


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


def write_report(
    output_path: str,
    all_persons: list[dict],
    shared_im_groups: list[dict],
    name_groups: list[dict],
    persons_without_im: list[dict],
    include_name_match: bool,
) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        def w(line: str = "") -> None:
            f.write(line + "\n")

        w(f"Duplicate Person Node Report")
        w(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        w(f"Neo4j URI : {NEO4J_URI}")
        w("=" * 70)
        w()

        # ── Summary ──────────────────────────────────────────────────────────
        total = len(all_persons)
        no_email = sum(1 for p in all_persons if not p["email"])
        no_email_bots = sum(1 for p in all_persons if not p["email"] and "[bot]" in (p["id"] or ""))
        no_email_humans = no_email - no_email_bots
        provider_scoped = sum(1 for p in all_persons if _is_provider_scoped(p["id"]))
        no_im = len(persons_without_im)
        has_email_no_im = sum(1 for p in persons_without_im if p["email"])
        w("SUMMARY")
        w("-" * 40)
        w(f"  Total Person nodes           : {total}")
        w(f"  Nodes without email          : {no_email}  ({no_email_bots} bots expected, {no_email_humans} humans unexpected)")
        w(f"  Provider-scoped ids          : {provider_scoped}  (person_github_* or person_jira_*)")
        w(f"  Without IdentityMapping link : {no_im}  (expected: 0)")
        w(f"    of which have an email     : {has_email_no_im}  ← should be 0; indicates a sync bug")
        w(f"  Duplicate groups (shared IM) : {len(shared_im_groups)}")
        if include_name_match:
            w(f"  Probable duplicates (name)   : {len(name_groups)}")
        w()

        # ── All persons ───────────────────────────────────────────────────────
        w("ALL PERSON NODES  (sorted by id)")
        w("-" * 70)
        w(f"  {'ID':<45}  {'EMAIL':<35}  NAME")
        w(f"  {'-'*45}  {'-'*35}  ----")
        for p in all_persons:
            pid = p["id"] or ""
            email = p["email"] or "(none)"
            name = p["name"] or ""
            w(f"  {pid:<45}  {email:<35}  {name}")
        w()

        # ── Integrity audit ──────────────────────────────────────────────────
        w("INTEGRITY AUDIT  (persons missing email or IdentityMapping link)")
        w("-" * 70)

        persons_no_email = [p for p in all_persons if not p["email"]]
        bots = [p for p in persons_no_email if "[bot]" in (p["id"] or "")]
        humans_no_email = [p for p in persons_no_email if "[bot]" not in (p["id"] or "")]
        w(f"  Persons without email  ({len(persons_no_email)})  [{len(bots)} bot(s) expected, {len(humans_no_email)} unexpected]")
        if not persons_no_email:
            w("    None — all persons have an email.")
        else:
            for p in persons_no_email:
                pid = p["id"] or ""
                name = p["name"] or ""
                flag = "  (bot — no email expected)" if "[bot]" in pid else "  *** UNEXPECTED — check sync"
                w(f"    id={pid:<45}  name={name}{flag}")
        w()

        w(f"  Persons without IdentityMapping link  ({len(persons_without_im)})")
        if not persons_without_im:
            w("    None — every person is linked to an IdentityMapping.")
        else:
            for p in persons_without_im:
                pid = p["id"] or ""
                email = p["email"] or "(no email)"
                name = p["name"] or ""
                flag = " *** HAS EMAIL — sync bug" if p["email"] else ""
                w(f"    id={pid:<45}  email={email:<35}  name={name}{flag}")
        w()

        # ── Definitive duplicates (shared IdentityMapping) ───────────────────
        w("DEFINITIVE DUPLICATES  (share the same IdentityMapping)")
        w("-" * 70)
        if not shared_im_groups:
            w("  None found.")
        else:
            for group in shared_im_groups:
                w(f"  IdentityMapping : {group['identity_id']}")
                for p in group["persons"]:
                    flag = "email-based  " if not _is_provider_scoped(p["id"]) else "provider-scoped"
                    email = p["email"] or "(none)"
                    w(f"    [{flag}]  id={p['id']:<45}  email={email:<35}  rels={p['rel_count']}")
                w()

        # ── Probable duplicates (name match) ─────────────────────────────────
        if include_name_match:
            w("PROBABLE DUPLICATES  (same name, one with email / one without)")
            w("-" * 70)
            if not name_groups:
                w("  None found.")
            else:
                for group in name_groups:
                    w(f"  Name : {group['name']}")
                    for p in group["persons"]:
                        flag = "email-based  " if not _is_provider_scoped(p["id"]) else "provider-scoped"
                        email = p["email"] or "(none)"
                        w(f"    [{flag}]  id={p['id']:<45}  email={email:<35}  rels={p['rel_count']}")
                    w()

        w("END OF REPORT")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output file path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--name-match",
        action="store_true",
        help="Also include probable duplicates detected by matching person names.",
    )
    args = parser.parse_args()

    if not NEO4J_PASSWORD:
        print("ERROR: NEO4J_PASSWORD is not set.", file=sys.stderr)
        sys.exit(1)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            print("Querying Neo4j...")
            all_persons = query_all_persons(session)
            shared_im_groups = query_shared_identity_mapping_groups(session)
            persons_without_im = query_persons_without_identity_mapping(session)
            name_groups = query_name_match_groups(session) if args.name_match else []
    finally:
        driver.close()

    write_report(args.output, all_persons, shared_im_groups, name_groups, persons_without_im, args.name_match)

    no_email = sum(1 for p in all_persons if not p["email"])
    has_email_no_im = sum(1 for p in persons_without_im if p["email"])
    print(f"Report written to: {args.output}")
    print(f"  Total persons             : {len(all_persons)}")
    print(f"  Without email             : {no_email}")
    print(f"  Without IdentityMapping   : {len(persons_without_im)}  (expected: 0)")
    print(f"    of which have email     : {has_email_no_im}  (expected: 0; indicates sync bug)")
    print(f"  Duplicate groups (IM)     : {len(shared_im_groups)}")
    if args.name_match:
        print(f"  Probable duplicates       : {len(name_groups)}")


if __name__ == "__main__":
    main()

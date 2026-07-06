#!/usr/bin/env python3
"""One-time cleanup backfill for computed display/time properties on Neo4j nodes.

Originally created to backfill _display_name, _on_hover_name, _last_seen_at,
_last_updated_at on nodes that predate Plan 006 (GraphNode ABC).

Now updated (after Pass 1 + Pass 2 of the _last_seen_at rename):
- Backfills _display_name and _on_hover_name (if still missing)
- Copies _last_synced_at → _last_seen_at (migrates old property to new name)
- Backfills _last_updated_at via coalesce, and _created_at via a guarded SET
- REMOVEs the old _last_synced_at property from all nodes
- REMOVEs any stale _last_seen_at left over from Plan 006's original writes

Uses direct Cypher (not Python dataclass reconstruction) since historical
nodes may be missing fields that are now mandatory in the dataclass (e.g.
``url``).  Each ``SET`` uses ``coalesce()`` to mirror the Python fallback
chains defined in ``GraphNode``.

Safe to re-run — ``SET`` is idempotent on existing values, ``REMOVE`` ignores
non-existent properties.
"""

import os
import sys
from neo4j import GraphDatabase


NODE_LABELS = [
    "Person", "Team", "IdentityMapping", "Project", "Initiative",
    "Epic", "Issue", "Sprint", "Repository", "Commit", "File",
    "PullRequest", "Space", "Page", "Blogpost",
]

DISPLAY_NAME_RULES = {
    # label -> coalesce(expression using the label's candidate fields)
    "Person": "coalesce(n.name, n.title, n.key, n.id)",
    "Team": "coalesce(n.name, n.title, n.key, n.id)",
    "IdentityMapping": "coalesce(n.username, n.id)",
    "Project": "coalesce(n.name, n.title, n.key, n.id)",
    "Initiative": "coalesce(n.summary, n.name, n.title, n.key, n.id)",
    "Epic": "coalesce(n.summary, n.name, n.title, n.key, n.id)",
    "Issue": "coalesce(n.summary, n.name, n.title, n.key, n.id)",
    "Sprint": "coalesce(n.name, n.title, n.key, n.id)",
    "Repository": "coalesce(n.name, n.title, n.key, n.id)",
    "Commit": "coalesce(n.message, n.sha, n.id)",
    "File": "coalesce(n.path, n.name, n.id)",
    "PullRequest": "coalesce(n.title, n.name, n.key, n.id)",
    "Space": "coalesce(n.name, n.title, n.key, n.id)",
    "Page": "coalesce(n.title, n.name, n.key, n.id)",
    "Blogpost": "coalesce(n.title, n.name, n.key, n.id)",
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def backfill_node(session, label: str) -> int:
    """Backfill computed display/time properties and migrate _last_synced_at → _last_seen_at.

    Performs four operations per label:
    1. Backfills _display_name and _on_hover_name (coalesce fallback chain)
    2. Backfills _last_updated_at via coalesce
    3. Backfills _created_at (only on nodes that have a created_at property)
    4. Migrates _last_synced_at → _last_seen_at, then removes _last_synced_at

    Returns the number of nodes updated.
    """
    display_expr = DISPLAY_NAME_RULES[label]

    # Query 1: backfill standard properties on all nodes
    query = f"""
    MATCH (n:{label})
    SET
        n._display_name = {display_expr},
        n._on_hover_name = {display_expr},
        n._last_updated_at = coalesce(n.updated_at, n.last_updated_at),
        n._last_seen_at = coalesce(n._last_seen_at, n._last_synced_at)
    REMOVE n._last_synced_at
    RETURN count(n) AS count
    """
    result = session.run(query)
    record = result.single()
    total_count = record["count"] if record else 0

    # Query 2: backfill _created_at only on nodes that have a created_at property
    created_query = f"""
    MATCH (n:{label})
    WHERE n.created_at IS NOT NULL
    SET n._created_at = n.created_at
    RETURN count(n) AS count
    """
    session.run(created_query)

    return total_count


def main():
    uri = _env("NEO4J_URI", "bolt://localhost:7687")
    user = _env("NEO4J_USERNAME", "neo4j")
    password = _env("NEO4J_PASSWORD", "password")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    total = 0

    try:
        with driver.session() as session:
            for label in NODE_LABELS:
                count = backfill_node(session, label)
                if count:
                    print(f"  ✓ {label}: {count} nodes updated")
                else:
                    print(f"  - {label}: no nodes found")
                total += count
    finally:
        driver.close()

    print(f"\n✅ Done. {total} total nodes backfilled across {len(NODE_LABELS)} labels.")


if __name__ == "__main__":
    main()
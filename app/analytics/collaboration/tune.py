#!/usr/bin/env python3
"""CLI tuning tool for the collaboration network community detection.

Run from the project root with the virtual environment active:

    python -m app.analytics.collaboration.tune

The tool connects to Neo4j, runs the collaboration score query, applies
Louvain community detection, and prints a diagnostic report so you can
tune the Cypher weights without touching the application server.

Exit codes:
  0  — success
  1  — Neo4j connection / query error
  2  — no data found (graph is empty)
"""

import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

# ---------------------------------------------------------------------------
# Path setup — allow running as a module from the project root
# ---------------------------------------------------------------------------
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))
load_dotenv(project_root / ".env")

# Import must come after sys.path adjustment
from app.analytics.collaboration.algorithm import (  # noqa: E402
    build_graph,
    detect_communities,
    compute_hub_scores,
    compute_modularity,
    MAX_COMMUNITY_STYLES,
)

# ---------------------------------------------------------------------------
# Neo4j helpers
# ---------------------------------------------------------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


def _load_query() -> str:
    query_path = Path(__file__).parent / "queries" / "collaboration_score.cypher"
    with open(query_path, "r", encoding="utf-8") as f:
        return f.read()


def _run_query() -> list:
    query = _load_query()
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            result = session.run(query)
            return [dict(r) for r in result]
    finally:
        driver.close()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _bar(value: float, max_value: float, width: int = 30) -> str:
    """Return a simple ASCII progress bar."""
    if max_value == 0:
        return " " * width
    filled = int(round(value / max_value * width))
    return "█" * filled + "░" * (width - filled)


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ---------------------------------------------------------------------------
# Diagnostic report
# ---------------------------------------------------------------------------

def run_diagnostics(records: list, verbose: bool = False) -> None:
    """Print the full diagnostic report for a set of collaboration records."""

    import networkx as nx

    _section("1 / 4  Graph Statistics")
    g = build_graph(records)

    num_nodes = g.number_of_nodes()
    num_edges = g.number_of_edges()
    scores = [d["weight"] for _, _, d in g.edges(data=True)]
    avg_score = sum(scores) / len(scores) if scores else 0
    max_score = max(scores) if scores else 0
    min_score = min(scores) if scores else 0
    density = nx.density(g)

    print(f"  Nodes (people)           : {num_nodes}")
    print(f"  Edges (collaborations)   : {num_edges}")
    print(f"  Graph density            : {density:.4f}  (0=sparse, 1=dense)")
    print(f"  Score range              : {min_score} – {max_score}")
    print(f"  Average score            : {avg_score:.1f}")

    # Hairball warning
    if density > 0.4:
        print("\n  ⚠  HIGH DENSITY — consider raising the score floor or tightening weights.")
    elif density < 0.02 and num_nodes > 10:
        print("\n  ⚠  VERY SPARSE — communities may be meaningless tiny clusters.")
    else:
        print("\n  ✓  Density looks reasonable.")

    # ---------------------------------------------------------------------------
    _section("2 / 4  Community Detection")
    partition = detect_communities(g)
    hub_scores = compute_hub_scores(g)
    modularity = compute_modularity(g, partition)

    community_members: dict = defaultdict(list)
    for node, cid in partition.items():
        community_members[cid].append(node)

    num_communities = len(community_members)
    community_sizes = sorted([len(m) for m in community_members.values()], reverse=True)

    print(f"  Communities detected     : {num_communities}")
    print(f"  Modularity score         : {modularity:.4f}  (>0.3 = meaningful structure)")

    if modularity > 0.5:
        print("  ✓  Strong community structure — boundaries are clear.")
    elif modularity > 0.3:
        print("  ✓  Reasonable community structure.")
    elif modularity > 0.1:
        print("  ⚠  Weak structure — communities overlap significantly.")
    else:
        print("  ✗  Very weak structure — weights or query may need tuning.")

    if num_communities > MAX_COMMUNITY_STYLES:
        print(f"\n  ⚠  {num_communities} communities exceed the {MAX_COMMUNITY_STYLES} colour slots.")
        print(     "     IDs will be clamped (mod). Consider raising weights to merge small groups.")

    # ---------------------------------------------------------------------------
    _section("3 / 4  Community Size Distribution")
    max_size = max(community_sizes) if community_sizes else 1

    for cid in sorted(community_members, key=lambda c: -len(community_members[c])):
        members = community_members[cid]
        size = len(members)
        bar = _bar(size, max_size)
        print(f"  Community {cid:>2}  [{bar}]  {size:>3} members")

    singletons = sum(1 for s in community_sizes if s == 1)
    if singletons > 0:
        print(f"\n  ⚠  {singletons} singleton community(ies) — isolated people with no collaborators.")
        print(     "     Check if bot names are leaking through the filter or if weights are too high.")

    # ---------------------------------------------------------------------------
    _section("4 / 4  Top Hubs (by weighted degree)")
    top_hubs = sorted(hub_scores.items(), key=lambda x: -x[1])[:15]
    max_hub = top_hubs[0][1] if top_hubs else 1

    for name, score in top_hubs:
        bar = _bar(score, max_hub)
        cid = partition.get(name, "?")
        print(f"  C{cid:<2}  [{bar}]  {score:>6.0f}  {name}")

    # ---------------------------------------------------------------------------
    if verbose:
        _section("VERBOSE — All Community Members")
        for cid in sorted(community_members, key=lambda c: -len(community_members[c])):
            members = sorted(community_members[cid])
            print(f"\n  Community {cid} ({len(members)} members):")
            for m in members:
                print(f"    • {m}")

    # ---------------------------------------------------------------------------
    _section("Summary")
    print(f"  People: {num_nodes}  |  Pairs: {num_edges}  |  Communities: {num_communities}  |  Modularity: {modularity:.3f}")
    if num_communities == 1:
        print("  ✗  Everything merged into one group — weights are too weak.")
    elif num_communities == num_nodes:
        print("  ✗  Every person is their own group — weights are too strong or time window too narrow.")
    elif 2 <= num_communities <= MAX_COMMUNITY_STYLES and modularity > 0.3:
        print("  ✓  Good configuration! Proceed with visualisation.")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Tune collaboration network community detection weights.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m app.analytics.collaboration.tune
  python -m app.analytics.collaboration.tune --verbose
        """,
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print all community members for every community.",
    )
    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════════════╗")
    print("║   Collaboration Network — Community Detection Tuner      ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"\nNeo4j   : {NEO4J_URI}")

    print("\nRunning collaboration score query …")
    t0 = time.time()
    try:
        records = _run_query()
    except Exception as exc:
        print(f"\n✗  Failed to connect or run query: {exc}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - t0
    print(f"Query returned {len(records)} pairs in {elapsed:.2f}s.")

    if not records:
        print("\n✗  No data returned. Check Neo4j connection and time window.", file=sys.stderr)
        sys.exit(2)

    run_diagnostics(records, verbose=args.verbose)


if __name__ == "__main__":
    main()

"""Collaboration network community detection using NetworkX and Louvain algorithm.

This module takes the raw output of the collaboration score Cypher query
(a list of person-pair records with weighted scores) and:
  1. Builds an undirected weighted NetworkX graph.
  2. Runs the Louvain modularity community detection algorithm.
  3. Computes per-node hub scores (weighted degree).
  4. Returns Cytoscape-compatible element dicts ready for rendering.
"""

from typing import Any, Dict, List

import networkx as nx
import community.community_louvain as community_louvain


# Number of distinct community colours supported in the Cytoscape stylesheet.
# Community IDs are clamped to this range so we never exceed the defined styles.
MAX_COMMUNITY_STYLES = 10


def build_graph(records: List[Dict[str, Any]]) -> nx.Graph:
    """Build a weighted, undirected NetworkX graph from collaboration query records.

    Args:
        records: List of dicts, each with keys 'person1', 'person2',
                 and 'total_collaboration_score'.

    Returns:
        An undirected NetworkX graph where each edge carries a 'weight' attribute
        equal to the collaboration score.
    """
    g = nx.Graph()
    for record in records:
        p1 = record["person1"]
        p2 = record["person2"]
        score = record["total_collaboration_score"]
        if g.has_edge(p1, p2):
            # Accumulate score if the pair somehow appears twice
            g[p1][p2]["weight"] += score
        else:
            g.add_edge(p1, p2, weight=score)
    return g


def detect_communities(g: nx.Graph) -> Dict[str, int]:
    """Run Louvain community detection on a weighted graph.

    Args:
        g: Undirected weighted NetworkX graph.

    Returns:
        Dict mapping node name -> community integer ID (0-indexed).
        Community IDs are clamped to [0, MAX_COMMUNITY_STYLES - 1] so the
        Cytoscape stylesheet always has a matching colour rule.
    """
    if g.number_of_nodes() == 0:
        return {}
    partition = community_louvain.best_partition(g, weight="weight")
    # Clamp IDs to prevent going beyond defined stylesheet classes
    return {node: cid % MAX_COMMUNITY_STYLES for node, cid in partition.items()}


def compute_hub_scores(g: nx.Graph) -> Dict[str, float]:
    """Compute a hub score for each node (weighted degree).

    Higher score = more total collaboration weight across all edges.
    Used to control node size in Cytoscape.

    Args:
        g: Undirected weighted NetworkX graph.

    Returns:
        Dict mapping node name -> weighted degree (float).
    """
    return dict(g.degree(weight="weight"))


def to_cytoscape_elements(
    g: nx.Graph,
    partition: Dict[str, int],
    hub_scores: Dict[str, float],
) -> List[Dict[str, Any]]:
    """Convert a NetworkX graph with community data into Cytoscape element dicts.

    Produces the list format expected by dash-cytoscape's 'elements' prop:
      - Each node carries: id, label, nodeType, community, hub_score
      - Each node gets a class string 'community-N' for CSS-like colour assignment
      - Each edge carries: source, target, weight (maps to line thickness in stylesheet)

    Args:
        g: Undirected weighted NetworkX graph.
        partition: Dict mapping node name -> community ID (from detect_communities).
        hub_scores: Dict mapping node name -> weighted degree (from compute_hub_scores).

    Returns:
        List of Cytoscape element dicts (nodes first, then edges).
    """
    elements: List[Dict[str, Any]] = []

    for node in g.nodes():
        community_id = partition.get(node, 0)
        elements.append({
            "data": {
                "id": node,
                "label": node,
                "displayLabel": node[:12] + "…" if len(node) > 12 else node,
                "nodeType": "Person",
                "community": community_id,
                "hub_score": hub_scores.get(node, 0.0),
                "elementType": "node",
            },
            "classes": f"community-{community_id}",
        })

    for source, target, edge_data in g.edges(data=True):
        elements.append({
            "data": {
                "source": source,
                "target": target,
                "weight": edge_data.get("weight", 1),
                "label": "COLLABORATES",
                "relType": "COLLABORATES",
                "elementType": "edge",
            }
        })

    return elements


def compute_modularity(g: nx.Graph, partition: Dict[str, int]) -> float:
    """Return the Louvain modularity score for a given partition.

    Modularity ranges from -0.5 to 1.0.  Values > 0.3 generally indicate
    meaningful community structure.

    Args:
        g: Undirected weighted NetworkX graph.
        partition: Dict mapping node name -> community ID.

    Returns:
        Float modularity score, or 0.0 if the graph is empty.
    """
    if g.number_of_nodes() == 0:
        return 0.0
    return community_louvain.modularity(partition, g, weight="weight")


def process_collaboration_network(
    records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Full pipeline: query records -> Cytoscape elements with communities.

    This is the main entry point used by the FastAPI service layer.

    Args:
        records: Raw list of dicts from the collaboration score Cypher query,
                 each with keys 'person1', 'person2', 'total_collaboration_score'.

    Returns:
        List of Cytoscape element dicts with community and hub_score attributes.

    Raises:
        ValueError: If records is empty.
    """
    if not records:
        raise ValueError("No collaboration records provided; cannot build network.")

    g = build_graph(records)
    partition = detect_communities(g)
    hub_scores = compute_hub_scores(g)
    return to_cytoscape_elements(g, partition, hub_scores)

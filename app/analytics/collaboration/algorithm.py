"""Collaboration network community detection using NetworkX and Louvain algorithm.

This module takes the raw output of the collaboration score Cypher query
(a list of person-pair records with weighted scores) and:
  1. Builds an undirected weighted NetworkX graph.
  2. Runs the Louvain modularity community detection algorithm.
  3. Computes per-node hub scores (weighted degree).
  4. Returns Cytoscape-compatible element dicts ready for rendering.
"""

import math
from collections import defaultdict
from typing import Any, Dict, List

import networkx as nx
import community.community_louvain as community_louvain


# Number of distinct community colours supported in the Cytoscape stylesheet.
# Community IDs are clamped to this range so we never exceed the defined styles.
MAX_COMMUNITY_STYLES = 20


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
        Dict mapping node name -> raw community integer ID (0-indexed).
        IDs are NOT clamped here so callers get the true community count.
        Clamping to [0, MAX_COMMUNITY_STYLES - 1] for stylesheet classes
        is done inside to_cytoscape_elements.
    """
    if g.number_of_nodes() == 0:
        return {}
    return community_louvain.best_partition(g, weight="weight")


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


def filter_top_edges_per_node(
    g: nx.Graph,
    top_n: int,
    ensure_min_connection: bool = True,
) -> nx.Graph:
    """Return a graph filtered to strongest edges per node.

    For each node, keep only its top-N weighted edges. Final edge set is the union
    across all nodes so a strong edge survives if selected by either endpoint.

    Args:
        g: Source undirected weighted graph.
        top_n: Maximum number of strongest edges to keep per node. Values <= 0
               disable filtering and return a shallow copy of the original graph.
        ensure_min_connection: If True, guarantees each node with at least one
                               original edge keeps at least one edge.

    Returns:
        Filtered graph containing all original nodes and selected edges.
    """
    if top_n <= 0 or g.number_of_edges() == 0:
        return g.copy()

    selected_edges: set[tuple[str, str]] = set()

    for node in g.nodes():
        neighbors = sorted(
            g.edges(node, data=True),
            key=lambda edge: edge[2].get("weight", 0),
            reverse=True,
        )
        if not neighbors:
            continue

        chosen = neighbors[:top_n]
        if ensure_min_connection and not chosen:
            chosen = [neighbors[0]]

        for source, target, _ in chosen:
            selected_edges.add(tuple(sorted((source, target))))

    filtered = nx.Graph()
    filtered.add_nodes_from(g.nodes(data=True))

    for source, target in selected_edges:
        if g.has_edge(source, target):
            filtered.add_edge(source, target, **g[source][target])

    if ensure_min_connection:
        for node in g.nodes():
            if g.degree(node) == 0 or filtered.degree(node) > 0:
                continue
            strongest = max(
                g.edges(node, data=True),
                key=lambda edge: edge[2].get("weight", 0),
            )
            source, target, _ = strongest
            filtered.add_edge(source, target, **g[source][target])

    return filtered


def to_cytoscape_elements(
    g: nx.Graph,
    partition: Dict[str, int],
    hub_scores: Dict[str, float],
    community_gap_x: float = 1560.0,
    community_gap_y: float = 1170.0,
) -> List[Dict[str, Any]]:
    """Convert a NetworkX graph with community data into Cytoscape element dicts.

    Produces the list format expected by dash-cytoscape's 'elements' prop:
      - Each node carries: id, label, nodeType, community (raw ID), hub_score
      - Each node gets a class string 'community-N' where N is the raw ID clamped
        to [0, MAX_COMMUNITY_STYLES - 1] for stylesheet lookup
      - Each edge carries: source, target, weight (maps to line thickness in stylesheet)

    Args:
        g: Undirected weighted NetworkX graph.
        partition: Dict mapping node name -> raw community ID (from detect_communities).
        hub_scores: Dict mapping node name -> weighted degree (from compute_hub_scores).

    Returns:
        List of Cytoscape element dicts (nodes first, then edges).
    """
    elements: List[Dict[str, Any]] = []
    positions = _compute_community_preset_positions(
        partition,
        hub_scores,
        community_gap_x=community_gap_x,
        community_gap_y=community_gap_y,
    )

    for node in g.nodes():
        community_id = partition.get(node, 0)
        style_id = community_id % MAX_COMMUNITY_STYLES
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
            "classes": f"community-{style_id}",
            "position": positions.get(node, {"x": 0.0, "y": 0.0}),
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
            },
            # Collaboration links are conceptually symmetric; keep canonical
            # source/target IDs for data consistency but render as undirected.
            "classes": "collaboration-edge",
        })

    return elements


def _compute_community_preset_positions(
    partition: Dict[str, int],
    hub_scores: Dict[str, float],
    community_gap_x: float,
    community_gap_y: float,
) -> Dict[str, Dict[str, float]]:
    """Generate deterministic node positions grouped by community for preset layout.

    Communities are placed on a coarse grid so clusters are spatially separated.
    Members within each community are placed in concentric rings, with high hub
    score nodes closest to the community center.
    """
    if not partition:
        return {}

    communities: dict[int, list[str]] = defaultdict(list)
    for node, community_id in partition.items():
        communities[community_id].append(node)

    sorted_communities = sorted(communities.items(), key=lambda item: item[0])

    positions: Dict[str, Dict[str, float]] = {}

    cols = max(1, math.ceil(math.sqrt(len(sorted_communities))))

    for idx, (_community_id, members) in enumerate(sorted_communities):
        col = idx % cols
        row = idx // cols
        center_x = col * community_gap_x
        center_y = row * community_gap_y

        sorted_members = sorted(members, key=lambda n: (-hub_scores.get(n, 0.0), n))

        # Place the first node at center, then concentric rings around it.
        for member_index, node in enumerate(sorted_members):
            if member_index == 0:
                positions[node] = {"x": center_x, "y": center_y}
                continue

            ring = math.floor(math.sqrt(member_index))
            radius = 140.0 * ring
            slots = max(6, ring * 8)
            angle = 2 * math.pi * ((member_index - 1) % slots) / slots

            positions[node] = {
                "x": center_x + radius * math.cos(angle),
                "y": center_y + radius * math.sin(angle),
            }

    return positions


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

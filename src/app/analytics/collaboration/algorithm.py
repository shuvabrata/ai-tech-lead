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
from matplotlib.colors import LinearSegmentedColormap

from app.common.node_size import apply_node_size


# ---------------------------------------------------------------------------
# JSON sanitizer for Neo4j temporal types
# ---------------------------------------------------------------------------

# Neo4j temporal classes vary between driver versions (neo4j.time.* vs.
# a specific subclass).  We use duck-typing: any value whose class name
# starts with "DateTime", "Date", "Time", or "Duration" under the neo4j
# package is converted to its ISO string representation.
_NEO4J_TEMPORAL_PREFIXES = ("DateTime", "Date", "Time", "Duration")


def _is_neo4j_temporal(value: object) -> bool:
    """Return True if *value* is a Neo4j temporal type that is not JSON-serializable."""
    cls = type(value)
    # Duck-type: check the fully-qualified class name rather than importing
    # neo4j.time (which may not be available in all environments).
    module = getattr(cls, "__module__", "") or ""
    if "neo4j" not in module:
        return False
    name = cls.__name__
    return any(name.startswith(p) for p in _NEO4J_TEMPORAL_PREFIXES)


def _sanitize_props(props: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy of *props* with Neo4j temporal values converted to ISO strings."""
    return {
        k: str(v) if _is_neo4j_temporal(v) else v
        for k, v in props.items()
    }


# ---------------------------------------------------------------------------
# Edge colour palette
# ---------------------------------------------------------------------------

# Sequential colormap across the full visible spectrum (VIBGYOR).
# Violet (weakest) → Indigo → Blue → Green → Yellow → Orange → Red (strongest).
# Using the full spectrum maximises perceptual colour range so collaborators
# at every strength level map to a visually distinct hue — far more readable
# than any single-hue or two-colour gradient in a dense graph.
COLLAB_EDGE_CMAP: LinearSegmentedColormap = LinearSegmentedColormap.from_list(
    "collab_edge",
    [
        "#7C3AED",  # 0.00 — violet   (weakest connections)
        "#4F46E5",  # 0.17 — indigo
        "#3B82F6",  # 0.33 — blue
        "#22C55E",  # 0.50 — green
        "#EAB308",  # 0.67 — yellow
        "#F97316",  # 0.83 — orange
        "#EF4444",  # 1.00 — red      (strongest connections)
    ],
)


def _weight_to_hex(normalized: float) -> str:
    """Map a normalized weight in [0, 1] to a CSS hex colour string.

    Args:
        normalized: Float in [0.0, 1.0] where 0 is the weakest edge and 1 is
                    the strongest edge in the current graph load.

    Returns:
        Six-digit CSS hex string, e.g. ``"#b91c1c"``.
    """
    r, g, b, _ = COLLAB_EDGE_CMAP(max(0.0, min(1.0, normalized)))
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))

# Number of distinct community colours supported in the Cytoscape stylesheet.
# Community IDs are clamped to this range so we never exceed the defined styles.
MAX_COMMUNITY_STYLES = 20

# Louvain can otherwise produce different valid partitions for the same graph.
LOUVAIN_RANDOM_STATE = 42


def build_graph(records: List[Dict[str, Any]]) -> nx.Graph:
    """Build a weighted, undirected NetworkX graph from collaboration query records.

    Each node uses the person's wba_id as its key. All Neo4j properties returned by
    the query (person1_props / person2_props) are stored as node attributes, along
    with a 'display_name' attribute mapped from the person's name field.

    Args:
        records: List of dicts, each with keys 'person1', 'person1_wba_id',
                 'person1_props', 'person2', 'person2_wba_id', 'person2_props',
                 and 'total_collaboration_score'.

    Returns:
        An undirected NetworkX graph where node keys are wba_ids and each edge
        carries a 'weight' attribute equal to the collaboration score.
    """
    g = nx.Graph()
    for record in records:
        p1_id = record["person1_wba_id"]
        p2_id = record["person2_wba_id"]
        score = record["total_collaboration_score"]
        print(f"Adding edge  weight={score:>10.2f}  {p1_id:<65} <->  {p2_id}")

        if p1_id not in g:
            p1_attrs = dict(record.get("person1_props") or {})
            p1_attrs["display_name"] = record["person1"]
            g.add_node(p1_id, **p1_attrs)

        if p2_id not in g:
            p2_attrs = dict(record.get("person2_props") or {})
            p2_attrs["display_name"] = record["person2"]
            g.add_node(p2_id, **p2_attrs)

        if g.has_edge(p1_id, p2_id):
            # Accumulate score if the pair somehow appears twice
            g[p1_id][p2_id]["weight"] += score
        else:
            g.add_edge(p1_id, p2_id, weight=score)
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
    return community_louvain.best_partition(g, weight="weight", random_state=LOUVAIN_RANDOM_STATE)


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
      - Each node carries: id (wba_id), wba_id, label (display name), all Neo4j
        properties from node attributes, nodeType, community (raw ID), hub_score
      - Each node gets a class string 'community-N' where N is the raw ID clamped
        to [0, MAX_COMMUNITY_STYLES - 1] for stylesheet lookup
      - Each edge carries: source, target, weight (maps to line thickness in stylesheet)

    Args:
        g: Undirected weighted NetworkX graph (node keys are wba_ids).
        partition: Dict mapping wba_id -> raw community ID (from detect_communities).
        hub_scores: Dict mapping wba_id -> weighted degree (from compute_hub_scores).

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

    # Pre-compute log-normalized _node_size multipliers in [0.25, 2.0].
    # log(score + 1) compresses large outlier scores so hubs don't dwarf peers.
    _NODE_SIZE_MIN = 0.25
    _NODE_SIZE_MAX = 2.0
    log_scores = {node: math.log(hub_scores.get(node, 0.0) + 1) for node in g.nodes()}
    ls_min = min(log_scores.values(), default=0.0)
    ls_max = max(log_scores.values(), default=0.0)
    ls_range = ls_max - ls_min

    def _node_size_for(node: str) -> float:
        """Return a _node_size multiplier in [0.25, 2.0] for the given node."""
        if ls_range == 0:
            return 1.0
        return _NODE_SIZE_MIN + (log_scores[node] - ls_min) / ls_range * (_NODE_SIZE_MAX - _NODE_SIZE_MIN)

    for node in g.nodes():
        node_attrs = g.nodes[node]
        display_name = node_attrs.get("display_name", node)
        community_id = partition.get(node, 0)
        style_id = community_id % MAX_COMMUNITY_STYLES
        # Spread all Neo4j properties into element data; override Cytoscape-internal
        # and computed fields explicitly. Exclude 'display_name' — surfaced as 'label'.
        extra_props = {k: v for k, v in node_attrs.items() if k != "display_name"}
        element = {
            "data": {
                **_sanitize_props(extra_props),
                "id": node,           # wba_id (Cytoscape element id)
                "wba_id": node,       # explicit for spotlight compatibility
                "label": display_name,
                "displayLabel": display_name[:12] + "\u2026" if len(display_name) > 12 else display_name,
                "nodeType": "Person",
                "community": community_id,
                "hub_score": hub_scores.get(node, 0.0),
                "_node_size": _node_size_for(node),
                "elementType": "node",
            },
            "classes": f"community-{style_id}",
            "position": positions.get(node, {"x": 0.0, "y": 0.0}),
        }
        apply_node_size(element)
        elements.append(element)

    # Pre-compute log-normalized display weights in [0, 100].
    # Raw edge weights are heavily skewed (e.g. max=17500, median=5), so linear
    # normalization makes all but the single heaviest edge look near-white.
    # log(w + 1) compresses the outlier without hiding the relative differences
    # between strong collaborators — exactly the same technique used for hub scores.
    all_edge_weights = [d.get("weight", 1) for _, _, d in g.edges(data=True)]
    max_log_weight = math.log(max(all_edge_weights, default=1) + 1) or 1  # guard against zero

    for source, target, edge_data in g.edges(data=True):
        canonical_source, canonical_target = sorted((source, target))
        edge_id = f"collab:{canonical_source}:{canonical_target}"
        raw_weight = edge_data.get("weight", 1)
        normalized_0_1 = math.log(raw_weight + 1) / max_log_weight
        elements.append({
            "data": {
                "id": edge_id,
                "source": canonical_source,
                "target": canonical_target,
                "weight": raw_weight,                                                             # raw — used by filters and details panel
                "normalized_weight": round(normalized_0_1 * 100, 1),                             # 0–100 log-scaled — retained for potential future use
                "line_color": _weight_to_hex(normalized_0_1),                                    # pre-computed hex — read directly by stylesheet via data(line_color)
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

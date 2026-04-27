"""Service layer for Graph API v1 - business logic and data transformation."""

from pathlib import Path as FilePath
from typing import Any, Dict, List, Set
from neo4j.graph import Node, Path, Relationship

from app.common.logger import logger
from app.settings import settings
from app.analytics.collaboration.algorithm import (
        build_graph,
        detect_communities,
        compute_hub_scores,
        compute_modularity,
    filter_top_edges_per_node,
        to_cytoscape_elements,
    )
from app.analytics.collaboration.config import CollaborationNetworkConfig
from .model import (
    CollaborationNetworkResponse, 
    GraphNode, GraphRelationship, GraphResponse, 
    NodeExpansionResponse, PaginationMeta
    )
from .query import (
    validate_read_only_query, 
    execute_cypher_query, 
    expand_node_query,
    fetch_relationships_between_nodes
    )


def execute_and_format_query(query: str) -> GraphResponse:
    """Execute a Cypher query and format results as GraphResponse.
    
    This function orchestrates the entire query execution flow:
    1. Validates the query is read-only
    2. Executes the query against Neo4j
    3. Detects whether results are graph or tabular data
    4. Transforms Neo4j objects to Pydantic models
    5. Returns a formatted GraphResponse
    
    Args:
        query: Cypher query string to execute
        
    Returns:
        GraphResponse with nodes, relationships, or raw tabular data
        
    Raises:
        ValueError: If query is not read-only or has validation errors
        RuntimeError: If Neo4j execution fails
        
    Examples:
        >>> response = execute_and_format_query("MATCH (n) RETURN n LIMIT 5")
        >>> response.isGraph
        True
        >>> len(response.nodes)
        5
    """
    # Step 1: Validate query is read-only
    if not validate_read_only_query(query):
        raise ValueError(
            "Query validation failed: Write operations are not allowed. "
            "Only read-only queries (MATCH, RETURN, etc.) are permitted."
        )
    
    # Step 2: Execute query
    logger.info(f"Executing query: {query[:100]}...")
    raw_results = execute_cypher_query(query, timeout=settings.NEO4J_QUERY_TIMEOUT)

    return _format_query_results(
        raw_results=raw_results,
        include_implicit_relationships=True,
    )


def _format_query_results(
    raw_results: List[Dict[str, Any]],
    include_implicit_relationships: bool,
) -> GraphResponse:
    """Format raw Neo4j records as GraphResponse (graph or tabular)."""
    # Detect result type and transform
    nodes_dict: Dict[str, GraphNode] = {}  # Keyed by element_id for deduplication
    relationships_list: List[GraphRelationship] = []
    relationship_ids: Set[str] = set()  # For deduplication
    is_graph = False
    
    # Extract graph objects from query results (supports nested values and Path objects)
    for record in raw_results:
        for value in record.values():
            extracted = _extract_graph_elements_from_value(
                value=value,
                nodes_dict=nodes_dict,
                relationships_list=relationships_list,
                relationship_ids=relationship_ids,
            )
            if extracted:
                is_graph = True
    
    # Step 4: Transform based on result type
    if is_graph:
        # Graph data: nodes and relationships are already extracted above
        logger.info("Detected graph data. Extracting nodes and relationships.")
        
        nodes_list = list(nodes_dict.values())
        logger.info(f"Extracted {len(nodes_list)} nodes and {len(relationships_list)} relationships from query results")
        
        # Step 4.5: Fetch relationships between the loaded nodes
        # This ensures that if nodes have relationships between them, those relationships
        # are also loaded, even if they weren't explicitly returned by the query
        if include_implicit_relationships and len(nodes_list) > 0:
            node_ids = [node.id for node in nodes_list]
            relationship_records = fetch_relationships_between_nodes(node_ids)
            
            # Add any new relationships we found
            relationship_ids = {rel.id for rel in relationships_list}  # Convert to set for dedup
            missing_endpoint_count = 0
            for record in relationship_records:
                if 'r' in record and record['r'] is not None:
                    neo4j_rel = record['r']
                    rel = _transform_relationship(neo4j_rel)
                    
                    # Defensive check: Cytoscape will fail to render if startNode or endNode is missing.
                    if rel.id not in relationship_ids and rel.startNode in nodes_dict and rel.endNode in nodes_dict:
                        relationships_list.append(rel)
                        relationship_ids.add(rel.id)
                    else:
                        if rel.startNode not in nodes_dict or rel.endNode not in nodes_dict:
                            missing_endpoint_count += 1
            
            logger.info(
                "After fetching implicit relationships: "
                f"{len(relationships_list)} total relationships "
                f"(dropped_missing_endpoints={missing_endpoint_count})"
            )
        
        return GraphResponse(
            nodes=nodes_list,
            relationships=relationships_list,
            rawResults=[],
            isGraph=True,
            resultCount=len(raw_results)
        )
    
    else:
        # Tabular data: convert to serializable format
        logger.info("Detected tabular data. Returning raw results.")
        serializable_results = []
        
        for record in raw_results:
            serializable_record = {}
            for key, value in record.items():
                # Convert any remaining Neo4j types to JSON-serializable
                serializable_record[key] = _make_serializable(value)
            serializable_results.append(serializable_record)
        
        return GraphResponse(
            nodes=[],
            relationships=[],
            rawResults=serializable_results,
            isGraph=False,
            resultCount=len(serializable_results)
        )


def _transform_node(neo4j_node: Node) -> GraphNode:
    """Transform a Neo4j Node to GraphNode model.
    
    Args:
        neo4j_node: Neo4j Node object
        
    Returns:
        GraphNode Pydantic model
    """
    # Serialize properties to handle Neo4j-specific types (DateTime, Date, etc.)
    serialized_props = {k: _make_serializable(v) for k, v in dict(neo4j_node).items()}
    
    return GraphNode(
        id=neo4j_node.element_id,
        labels=list(neo4j_node.labels),
        properties=serialized_props
    )


def _transform_relationship(neo4j_rel: Relationship) -> GraphRelationship:
    """Transform a Neo4j Relationship to GraphRelationship model.
    
    Args:
        neo4j_rel: Neo4j Relationship object
        
    Returns:
        GraphRelationship Pydantic model
    """
    # Serialize properties to handle Neo4j-specific types (DateTime, Date, etc.)
    serialized_props = {k: _make_serializable(v) for k, v in dict(neo4j_rel).items()}
    
    return GraphRelationship(
        id=neo4j_rel.element_id,
        type=neo4j_rel.type,
        startNode=neo4j_rel.start_node.element_id,
        endNode=neo4j_rel.end_node.element_id,
        properties=serialized_props
    )


def _extract_graph_elements_from_value(
    value: Any,
    nodes_dict: Dict[str, GraphNode],
    relationships_list: List[GraphRelationship],
    relationship_ids: Set[str],
) -> bool:
    """Recursively extract graph nodes/relationships from a Neo4j result value.

    Supports direct Node/Relationship values, Path objects, and nested structures
    (lists/tuples/sets/dicts) that may contain graph values.

    Args:
        value: Raw value from a Neo4j record
        nodes_dict: Target node map for deduplication
        relationships_list: Target relationship list
        relationship_ids: Target relationship ID set for deduplication

    Returns:
        True if at least one graph element was extracted, else False
    """
    extracted = False

    if isinstance(value, Node):
        node = _transform_node(value)
        nodes_dict[node.id] = node
        return True

    if isinstance(value, Relationship):
        rel = _transform_relationship(value)
        if rel.id not in relationship_ids:
            relationships_list.append(rel)
            relationship_ids.add(rel.id)

        start_node = _transform_node(value.start_node)
        end_node = _transform_node(value.end_node)
        nodes_dict[start_node.id] = start_node
        nodes_dict[end_node.id] = end_node
        return True

    if isinstance(value, Path):
        for node in value.nodes:
            transformed_node = _transform_node(node)
            nodes_dict[transformed_node.id] = transformed_node

        for relationship in value.relationships:
            transformed_rel = _transform_relationship(relationship)
            if transformed_rel.id not in relationship_ids:
                relationships_list.append(transformed_rel)
                relationship_ids.add(transformed_rel.id)

        return bool(value.nodes or value.relationships)

    if isinstance(value, (list, tuple, set)):
        for item in value:
            extracted = _extract_graph_elements_from_value(
                value=item,
                nodes_dict=nodes_dict,
                relationships_list=relationships_list,
                relationship_ids=relationship_ids,
            ) or extracted
        return extracted

    if isinstance(value, dict):
        for item in value.values():
            extracted = _extract_graph_elements_from_value(
                value=item,
                nodes_dict=nodes_dict,
                relationships_list=relationships_list,
                relationship_ids=relationship_ids,
            ) or extracted
        return extracted

    return False


def _make_serializable(value: Any) -> Any:
    """Convert Neo4j types to JSON-serializable Python types.
    
    Handles Node, Relationship, temporal types (DateTime, Date, Time), 
    and other Neo4j-specific types.
    
    Args:
        value: Value to convert
        
    Returns:
        JSON-serializable equivalent
    """
    if isinstance(value, Node):
        return {
            "id": value.element_id,
            "labels": list(value.labels),
            "properties": dict(value)
        }
    elif isinstance(value, Relationship):
        return {
            "id": value.element_id,
            "type": value.type,
            "startNode": value.start_node.element_id,
            "endNode": value.end_node.element_id,
            "properties": dict(value)
        }
    elif isinstance(value, Path):
        return {
            "nodes": [_make_serializable(node) for node in value.nodes],
            "relationships": [_make_serializable(rel) for rel in value.relationships],
        }
    elif isinstance(value, (list, tuple)):
        return [_make_serializable(item) for item in value]
    elif isinstance(value, dict):
        return {k: _make_serializable(v) for k, v in value.items()}
    elif hasattr(value, 'iso_format'):
        # Neo4j temporal types (DateTime, Date, Time, Duration)
        # They have an iso_format() method
        return value.iso_format()
    elif hasattr(value, '__str__') and type(value).__module__ == 'neo4j.time':
        # Fallback for any Neo4j time types
        return str(value)
    else:
        # Primitive types (str, int, float, bool, None) are already serializable
        return value


def expand_node(
    node_id: str,
    direction: str = "both",
    relationship_types: List[str] = None,
    limit: int = None,
    offset: int = 0,
    exclude_node_ids: List[str] = None
) -> NodeExpansionResponse:
    """Expand a node to retrieve and format connected nodes and relationships.
    
    This function orchestrates the node expansion flow:
    1. Queries Neo4j for connected nodes and relationships
    2. Transforms Neo4j objects to Pydantic models
    3. Calculates pagination metadata
    4. Returns formatted response
    
    Args:
        node_id: Element ID of the node to expand
        direction: Direction to follow ('incoming', 'outgoing', or 'both')
        relationship_types: Optional list of relationship types to filter by
        limit: Maximum number of connected nodes to return
        offset: Number of results to skip (for pagination)
        exclude_node_ids: Optional list of node IDs to exclude (already loaded)
        
    Returns:
        NodeExpansionResponse with connected nodes, relationships, and pagination info
        
    Raises:
        ValueError: If node_id is invalid or node not found
        RuntimeError: If Neo4j execution fails
        
    Examples:
        >>> response = expand_node("123", direction="outgoing", limit=10)
        >>> response.expanded_node_id
        '123'
        >>> len(response.nodes) <= 10
        True
    """
    # Use configured default if limit not provided
    if limit is None:
        limit = settings.GRAPH_UI_MAX_NODES_TO_EXPAND
    
    logger.info(f"Expanding node {node_id} in direction '{direction}' with limit={limit}, offset={offset}")
    
    # Execute expansion query
    result = expand_node_query(
        node_id=node_id,
        direction=direction,
        relationship_types=relationship_types,
        limit=limit,
        offset=offset,
        exclude_node_ids=exclude_node_ids
    )
    
    # Extract nodes and relationships from records
    nodes_dict: Dict[str, GraphNode] = {}  # Deduplicate by element_id
    relationships_dict: Dict[str, GraphRelationship] = {}  # Deduplicate by element_id
    
    for record in result["records"]:
        # Each record contains 'm' (connected node) and 'r' (relationship)
        # 'm' can be None when the node is already loaded but we still want the relationship
        if 'm' in record and record['m'] is not None:
            neo4j_node = record['m']
            node = _transform_node(neo4j_node)
            nodes_dict[node.id] = node
        
        if 'r' in record and record['r'] is not None:
            neo4j_rel = record['r']
            rel = _transform_relationship(neo4j_rel)
            relationships_dict[rel.id] = rel
    
    nodes_list = list(nodes_dict.values())
    relationships_list = list(relationships_dict.values())
    
    # Calculate pagination metadata
    total = result["total"]
    has_more = (offset + limit) < total
    
    pagination = PaginationMeta(
        total=total,
        limit=limit,
        offset=offset,
        has_more=has_more
    )
    
    logger.info(f"Expansion complete: {len(nodes_list)} nodes, "
               f"{len(relationships_list)} relationships, "
               f"total={total}, has_more={has_more}")
    
    return NodeExpansionResponse(
        nodes=nodes_list,
        relationships=relationships_list,
        expanded_node_id=node_id,
        pagination=pagination
    )


def get_collaboration_network(
    config: CollaborationNetworkConfig | None = None,
) -> CollaborationNetworkResponse:
    """Run the collaboration score query and return community-detected Cytoscape elements.

    Steps:
    1. Load the Cypher query from the collaboration queries directory.
    2. Execute it against Neo4j (returns tabular person-pair records).
    3. Pass records through the Louvain community detection pipeline.
    4. Return Cytoscape-ready elements plus summary statistics.

    Returns:
        CollaborationNetworkResponse with elements and summary stats.

    Raises:
        RuntimeError: If Neo4j is not enabled or query execution fails.
        ValueError: If the query returns no data.
    """
    config = config or CollaborationNetworkConfig()

    # Load the Cypher query from the analytics module
    query_path = (
        FilePath(__file__).resolve().parent.parent.parent.parent
        / "analytics" / "collaboration" / "queries" / "collaboration_score.cypher"
    )
    query = query_path.read_text()

    logger.info("Running collaboration score query...")
    records = execute_cypher_query(
        query,
        timeout=settings.NEO4J_QUERY_TIMEOUT,
        parameters=config.to_cypher_parameters(),
    )
    logger.info(f"Collaboration query returned {len(records)} pairs.")

    if not records:
        raise ValueError(
            "Collaboration query returned no data. "
            "Check Neo4j connectivity and that the 90-day time window contains activity."
        )

    # Run community detection pipeline
    g = build_graph(records)
    if config.top_n_edges_per_node > 0:
        g = filter_top_edges_per_node(
            g,
            top_n=config.top_n_edges_per_node,
            ensure_min_connection=config.ensure_min_connection,
        )
    partition = detect_communities(g)
    hub_scores = compute_hub_scores(g)
    modularity = compute_modularity(g, partition)
    elements = to_cytoscape_elements(
        g,
        partition,
        hub_scores,
        community_gap_x=config.community_gap_x,
        community_gap_y=config.community_gap_y,
    )

    num_communities = len(set(partition.values()))
    logger.info(
        f"Community detection complete: {g.number_of_nodes()} people, "
        f"{g.number_of_edges()} pairs, {num_communities} communities, "
        f"modularity={modularity:.3f}"
    )

    return CollaborationNetworkResponse(
        elements=elements,
        num_people=g.number_of_nodes(),
        num_pairs=g.number_of_edges(),
        num_communities=num_communities,
        modularity=round(modularity, 4),
        config=config.to_summary(),
    )

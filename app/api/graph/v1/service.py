"""Service layer for Graph API v1 - business logic and data transformation."""

from typing import Any, Dict, List, Set
from neo4j.graph import Node, Relationship

from app.common.logger import logger
from app.settings import settings
from .model import GraphNode, GraphRelationship, GraphResponse, NodeExpansionResponse, PaginationMeta
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
    
    # Step 3: Detect result type and transform
    nodes_dict: Dict[str, GraphNode] = {}  # Keyed by element_id for deduplication
    relationships_list: List[GraphRelationship] = []
    is_graph = False
    
    # Check if results contain graph objects (Node or Relationship)
    for record in raw_results:
        for value in record.values():
            if isinstance(value, (Node, Relationship)):
                is_graph = True
                break
        if is_graph:
            break
    
    # Step 4: Transform based on result type
    if is_graph:
        # Graph data: extract nodes and relationships
        logger.info("Detected graph data. Extracting nodes and relationships.")
        relationship_ids: Set[str] = set()  # For deduplication
        
        for record in raw_results:
            for value in record.values():
                if isinstance(value, Node):
                    # Add node (deduplicating by element_id)
                    node = _transform_node(value)
                    nodes_dict[node.id] = node
                    
                elif isinstance(value, Relationship):
                    # Add relationship (deduplicating by element_id)
                    rel = _transform_relationship(value)
                    if rel.id not in relationship_ids:
                        relationships_list.append(rel)
                        relationship_ids.add(rel.id)
                    
                    # Also add the start and end nodes
                    start_node = _transform_node(value.start_node)
                    end_node = _transform_node(value.end_node)
                    nodes_dict[start_node.id] = start_node
                    nodes_dict[end_node.id] = end_node
        
        nodes_list = list(nodes_dict.values())
        logger.info(f"Extracted {len(nodes_list)} nodes and {len(relationships_list)} relationships from query results")
        
        # Step 4.5: Fetch relationships between the loaded nodes
        # This ensures that if nodes have relationships between them, those relationships
        # are also loaded, even if they weren't explicitly returned by the query
        if len(nodes_list) > 0:
            node_ids = [node.id for node in nodes_list]
            relationship_records = fetch_relationships_between_nodes(node_ids)
            
            # Add any new relationships we found
            relationship_ids = {rel.id for rel in relationships_list}  # Convert to set for dedup
            for record in relationship_records:
                if 'r' in record and record['r'] is not None:
                    neo4j_rel = record['r']
                    rel = _transform_relationship(neo4j_rel)
                    if rel.id not in relationship_ids:
                        relationships_list.append(rel)
                        relationship_ids.add(rel.id)
            
            logger.info(f"After fetching implicit relationships: {len(relationships_list)} total relationships")
        
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

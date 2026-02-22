"""Service layer for Graph API v1 - business logic and data transformation."""

from typing import Any, Dict, List, Set
from neo4j.graph import Node, Relationship

from app.common.logger import logger
from .model import GraphNode, GraphRelationship, GraphResponse
from .query import validate_read_only_query, execute_cypher_query


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
    raw_results = execute_cypher_query(query, timeout=30)
    
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
        logger.info(f"Extracted {len(nodes_list)} nodes and {len(relationships_list)} relationships")
        
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

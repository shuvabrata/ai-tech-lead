"""Data transformation logic for Graph API v1."""

from typing import Any, Dict, List, Set, cast
from neo4j.graph import Node, Path, Relationship

from .model import GraphNode, GraphRelationship


def _transform_node(neo4j_node: Node) -> GraphNode:
    """Transform a Neo4j Node to GraphNode model.
    
    Args:
        neo4j_node: Neo4j Node object
        
    Returns:
        GraphNode Pydantic model
    """
    # Serialize properties to handle Neo4j-specific types (DateTime, Date, etc.)
    serialized_props = {k: _make_serializable(v) for k, v in dict(neo4j_node).items()}

    # Use the 'id' property from Neo4j data as the wba_id, fall back to element_id
    wba_id = serialized_props.get("id") or neo4j_node.element_id

    return GraphNode(
        wba_id=wba_id,
        elementId=neo4j_node.element_id,
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
    
    start_node = cast(Node, neo4j_rel.start_node)
    end_node = cast(Node, neo4j_rel.end_node)
    
    return GraphRelationship(
        id=neo4j_rel.element_id,
        type=neo4j_rel.type,
        startNode=start_node.element_id,
        endNode=end_node.element_id,
        properties=serialized_props
    )


def _extract_graph_elements_from_value(
    value: Any,
    nodes_dict: Dict[str, GraphNode],
    relationships_list: List[GraphRelationship],
    relationship_ids: Set[str],
) -> bool:
    """Recursively extract graph nodes/relationships from a Neo4j result value."""
    extracted = False

    if isinstance(value, Node):
        node = _transform_node(value)
        nodes_dict[node.elementId] = node
        return True

    if isinstance(value, Relationship):
        rel = _transform_relationship(value)
        if rel.id not in relationship_ids:
            relationships_list.append(rel)
            relationship_ids.add(rel.id)

        start_node = cast(Node, value.start_node)
        end_node = cast(Node, value.end_node)
        
        start_gnode = _transform_node(start_node)
        end_gnode = _transform_node(end_node)
        nodes_dict[start_gnode.elementId] = start_gnode
        nodes_dict[end_gnode.elementId] = end_gnode
        return True

    if isinstance(value, Path):
        for path_node in value.nodes:
            transformed_node = _transform_node(path_node)
            nodes_dict[transformed_node.elementId] = transformed_node

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
    """Convert Neo4j types to JSON-serializable Python types."""
    if isinstance(value, Node):
        return {
            "id": value.element_id,
            "labels": list(value.labels),
            "properties": dict(value)
        }
    elif isinstance(value, Relationship):
        start_node = cast(Node, value.start_node)
        end_node = cast(Node, value.end_node)
        return {
            "id": value.element_id,
            "type": value.type,
            "startNode": start_node.element_id,
            "endNode": end_node.element_id,
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
        return value.iso_format()
    elif hasattr(value, '__str__') and type(value).__module__ == 'neo4j.time':
        return str(value)
    else:
        return value

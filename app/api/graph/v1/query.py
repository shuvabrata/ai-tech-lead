"""Query layer for Neo4j graph database operations."""

import re
from typing import Any, Dict, List, Tuple
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.settings import settings
from app.common.logger import logger
from .model import GraphFilterRequest


# Read-only Cypher keywords (case-insensitive)
READ_ONLY_KEYWORDS = [
    'MATCH', 'OPTIONAL', 'WITH', 'UNWIND', 'RETURN', 
    'WHERE', 'ORDER', 'SKIP', 'LIMIT', 'UNION', 
    'CALL'  # CALL is allowed for read-only procedures
]

# Write operation keywords that should be rejected
WRITE_KEYWORDS = [
    'CREATE', 'MERGE', 'DELETE', 'DETACH', 'SET', 
    'REMOVE', 'DROP', 'FOREACH'
]


_FILTER_OPERATOR_MAP = {
    "=": "=",
    "!=": "<>",
    ">": ">",
    "<": "<",
    ">=": ">=",
    "<=": "<=",
}

_PROPERTY_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_read_only_query(query: str) -> bool:
    """Validate that a Cypher query is read-only (no write operations).
    
    This function checks if the query contains only read-only operations
    and rejects queries with write operations like CREATE, MERGE, DELETE, etc.
    
    Args:
        query: The Cypher query string to validate
        
    Returns:
        True if query is read-only, False if it contains write operations
        
    Examples:
        >>> validate_read_only_query("MATCH (n) RETURN n")
        True
        >>> validate_read_only_query("CREATE (n:Test) RETURN n")
        False
    """
    if not query or not query.strip():
        return False
    
    # Normalize query: uppercase and remove extra whitespace
    normalized = ' '.join(query.upper().split())
    
    # Check for write keywords using word boundaries to avoid false positives
    for write_keyword in WRITE_KEYWORDS:
        # Use word boundary regex to match whole words only
        pattern = r'\b' + re.escape(write_keyword) + r'\b'
        if re.search(pattern, normalized):
            logger.warning(f"Query validation failed: Contains write operation '{write_keyword}'")
            return False
    
    # Additional safety check: query should start with a read operation
    # (allowing comments with //)
    query_start = normalized.lstrip('/').lstrip('*').lstrip()
    
    starts_with_read = False
    for read_keyword in READ_ONLY_KEYWORDS:
        if query_start.startswith(read_keyword):
            starts_with_read = True
            break
    
    if not starts_with_read:
        logger.warning(f"Query validation failed: Does not start with read operation. Starts with: {query_start[:30]}")
        return False
    
    return True


def execute_cypher_query(
    query: str,
    timeout: int = 30,
    parameters: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """Execute a Cypher query against Neo4j and return raw results.
    
    This function creates a native Neo4j driver connection, executes the query
    with a timeout, and returns the raw result records. Each record contains
    Neo4j Node and Relationship objects.
    
    Args:
        query: The Cypher query to execute
        timeout: Maximum execution time in seconds (default: 30)
        
    Returns:
        List of result records as dictionaries. Each record contains the
        returned variables (nodes, relationships, or scalar values).
        
    Raises:
        ServiceUnavailable: If Neo4j connection fails
        Neo4jError: If query execution fails (syntax error, etc.)
        TimeoutError: If query execution exceeds timeout
        
    Examples:
        >>> results = execute_cypher_query("MATCH (n) RETURN n LIMIT 1")
        >>> len(results)
        1
    """
    if not settings.NEO4J_ENABLED:
        raise RuntimeError("Neo4j is not enabled. Set NEO4J_ENABLED=true in .env")
    
    # Create Neo4j driver
    driver = None
    try:
        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
        )
        
        # Verify connectivity
        driver.verify_connectivity()
        
        logger.info(f"Executing query with timeout={timeout}s")
        
        # Execute query with timeout
        with driver.session() as session:
            result = session.run(query, parameters=parameters or {}, timeout=timeout)
            
            # Convert to list of dictionaries
            # Neo4j driver returns Record objects that act like dicts
            records = []
            for record in result:
                records.append(dict(record))
            
            logger.info(f"Query executed successfully. Returned {len(records)} records")
            return records
            
    except ServiceUnavailable as e:
        logger.error(f"Neo4j connection failed: {e}")
        raise RuntimeError(f"Unable to connect to Neo4j database: {str(e)}") from e
    
    except Neo4jError as e:
        logger.error(f"Neo4j query execution failed: {e}")
        # Extract more helpful error message
        error_msg = str(e)
        if "SyntaxError" in error_msg:
            raise ValueError(f"Cypher syntax error: {error_msg}") from e
        else:
            raise RuntimeError(f"Query execution error: {error_msg}") from e
    
    except Exception as e:
        logger.error(f"Unexpected error executing query: {e}")
        raise RuntimeError(f"Unexpected error: {str(e)}") from e
    
    finally:
        if driver:
            driver.close()


def build_filtered_cypher_query(request: GraphFilterRequest) -> Tuple[str, Dict[str, Any]]:
    """Build a read-only Cypher query with validated filter predicates pushed down.

    The builder assumes the base query returns graph variables `n`, `r`, and `m`
    (the common graph query shape used by the graph page).
    """
    base_query = request.baseQuery.strip()

    where_clauses: List[str] = []
    params: Dict[str, Any] = {}

    node_group_clauses: List[str] = []
    if request.nodeTypeFilters:
        params["node_type_filters"] = request.nodeTypeFilters
        node_group_clauses.append(
            "(n IS NOT NULL AND any(lbl IN labels(n) WHERE lbl IN $node_type_filters))"
        )

    relationship_group_clauses: List[str] = []
    if request.relationshipTypeFilters:
        params["relationship_type_filters"] = request.relationshipTypeFilters
        relationship_group_clauses.append(
            "(r IS NOT NULL AND type(r) IN $relationship_type_filters)"
        )

    node_label_predicates: Dict[str, List[str]] = {}
    relationship_type_predicates: Dict[str, List[str]] = {}

    for idx, node_filter in enumerate(request.nodePropertyFilters):
        prop_val_param = f"node_prop_val_{idx}"
        label_param = f"node_prop_label_{idx}"
        params[prop_val_param] = node_filter.value
        params[label_param] = node_filter.label

        predicate = _build_property_predicate(
            entity="n",
            property_name=node_filter.property,
            property_value_param=prop_val_param,
            operator=node_filter.operator,
        )
        node_label_predicates.setdefault(node_filter.label, []).append(predicate)

    for idx, rel_filter in enumerate(request.relationshipPropertyFilters):
        prop_val_param = f"rel_prop_val_{idx}"
        type_param = f"rel_prop_type_{idx}"
        params[prop_val_param] = rel_filter.value
        params[type_param] = rel_filter.type

        predicate = _build_property_predicate(
            entity="r",
            property_name=rel_filter.property,
            property_value_param=prop_val_param,
            operator=rel_filter.operator,
        )
        relationship_type_predicates.setdefault(rel_filter.type, []).append(predicate)

    for idx, date_filter in enumerate(request.dateRangeFilters):
        entity = "n" if date_filter.scope == "node" else "r"
        property_ref = _build_property_reference(entity=entity, property_name=date_filter.property)

        range_predicates: List[str] = []
        if date_filter.from_value is not None:
            start_param = f"date_start_{idx}"
            params[start_param] = date_filter.from_value
            range_predicates.append(f"toString({property_ref}) >= ${start_param}")
        if date_filter.to is not None:
            end_param = f"date_end_{idx}"
            params[end_param] = date_filter.to
            range_predicates.append(f"toString({property_ref}) <= ${end_param}")

        if not range_predicates:
            continue

        if date_filter.scope == "node":
            if date_filter.label is not None:
                node_label_predicates.setdefault(date_filter.label, []).extend(range_predicates)
        else:
            if date_filter.type is not None:
                relationship_type_predicates.setdefault(date_filter.type, []).extend(range_predicates)

    for idx, (label, predicates) in enumerate(node_label_predicates.items()):
        label_param = f"node_group_label_{idx}"
        params[label_param] = label
        clause = (
            "(n IS NOT NULL "
            f"AND any(lbl IN labels(n) WHERE lbl = ${label_param}) "
            f"AND {' AND '.join(predicates)})"
        )
        node_group_clauses.append(clause)

    for idx, (rel_type, predicates) in enumerate(relationship_type_predicates.items()):
        rel_type_param = f"relationship_group_type_{idx}"
        params[rel_type_param] = rel_type
        clause = (
            "(r IS NOT NULL "
            f"AND type(r) = ${rel_type_param} "
            f"AND {' AND '.join(predicates)})"
        )
        relationship_group_clauses.append(clause)

    if node_group_clauses:
        where_clauses.append("(" + " OR ".join(node_group_clauses) + ")")

    if relationship_group_clauses:
        where_clauses.append("(" + " OR ".join(relationship_group_clauses) + ")")

    where_sql = ""
    if where_clauses:
        where_sql = "\nWHERE " + "\n  AND ".join(where_clauses)

    query = (
        "CALL {\n"
        f"{base_query}\n"
        "}\n"
        "WITH *"
        f"{where_sql}\n"
        "RETURN *"
    )

    return query, params


def execute_filtered_cypher_query(
    request: GraphFilterRequest,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """Execute a query with pushed-down filters generated from request metadata."""
    if not validate_read_only_query(request.baseQuery):
        raise ValueError(
            "Query validation failed: Write operations are not allowed. "
            "Only read-only queries (MATCH, RETURN, etc.) are permitted."
        )

    filtered_query, parameters = build_filtered_cypher_query(request)
    return execute_cypher_query(
        filtered_query,
        timeout=timeout,
        parameters=parameters,
    )


def _build_property_predicate(
    entity: str,
    property_name: str,
    property_value_param: str,
    operator: str,
) -> str:
    """Build a Cypher-safe predicate for one property operator."""
    entity_prop_ref = _build_property_reference(entity=entity, property_name=property_name)

    if operator in _FILTER_OPERATOR_MAP:
        return f"{entity_prop_ref} {_FILTER_OPERATOR_MAP[operator]} ${property_value_param}"
    if operator == "CONTAINS":
        return f"toString({entity_prop_ref}) CONTAINS toString(${property_value_param})"
    if operator == "STARTS WITH":
        return f"toString({entity_prop_ref}) STARTS WITH toString(${property_value_param})"
    if operator == "IN":
        return f"{entity_prop_ref} IN ${property_value_param}"

    raise ValueError(f"Unsupported filter operator for query builder: {operator}")


def _build_property_reference(entity: str, property_name: str) -> str:
    """Build a validated static Cypher property reference like `n.name`."""
    if not _PROPERTY_IDENTIFIER_PATTERN.match(property_name):
        raise ValueError(
            f"Unsupported property identifier for query builder: {property_name}"
        )
    return f"{entity}.{property_name}"


def fetch_relationships_between_nodes(node_ids: List[str]) -> List[Dict[str, Any]]:
    """Fetch all relationships between a given set of nodes.
    
    This function queries Neo4j to find all relationships where both the start
    and end nodes are in the provided list of node IDs. This is useful for
    displaying a connected graph when only node data is initially returned.
    
    Args:
        node_ids: List of node element IDs to find relationships between
        
    Returns:
        List of result records, each containing a relationship ('r')
        
    Raises:
        RuntimeError: If Neo4j execution fails
        
    Examples:
        >>> node_ids = ["4:abc:1", "4:abc:2", "4:abc:3"]
        >>> rels = fetch_relationships_between_nodes(node_ids)
        >>> all('r' in record for record in rels)
        True
    """
    if not settings.NEO4J_ENABLED:
        raise RuntimeError("Neo4j is not enabled. Set NEO4J_ENABLED=true in .env")
    
    if not node_ids or len(node_ids) == 0:
        logger.info("No node IDs provided, returning empty relationship list")
        return []
    
    # Build Cypher query to find relationships between the provided nodes
    query = """
    MATCH (n)-[r]->(m)
    WHERE elementId(n) IN $node_ids AND elementId(m) IN $node_ids
    RETURN r
    """
    
    driver = None
    try:
        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
        )
        
        driver.verify_connectivity()
        
        logger.info(f"Fetching relationships between {len(node_ids)} nodes")
        
        with driver.session() as session:
            result = session.run(query, node_ids=node_ids)
            
            records = []
            for record in result:
                records.append(dict(record))
            
            logger.info(f"Found {len(records)} relationships between nodes")
            return records
            
    except ServiceUnavailable as e:
        logger.error(f"Neo4j connection failed: {e}")
        raise RuntimeError(f"Unable to connect to Neo4j database: {str(e)}") from e
    
    except Neo4jError as e:
        logger.error(f"Neo4j query execution failed: {e}")
        raise RuntimeError(f"Query execution error: {str(e)}") from e
    
    except Exception as e:
        logger.error(f"Unexpected error fetching relationships: {e}")
        raise RuntimeError(f"Unexpected error: {str(e)}") from e
    
    finally:
        if driver:
            driver.close()


def expand_node_query(
    node_id: str,
    direction: str = "both",
    relationship_types: List[str] = None,
    limit: int = None,
    offset: int = 0,
    exclude_node_ids: List[str] = None
) -> Dict[str, Any]:
    """Execute a query to expand a node and return connected nodes and relationships.
    
    This function retrieves all nodes connected to the specified node, optionally
    filtering by relationship direction and types, with pagination support.
    
    Args:
        node_id: Element ID of the node to expand
        direction: Direction to follow relationships ('incoming', 'outgoing', or 'both')
        relationship_types: Optional list of relationship types to filter by
        limit: Maximum number of connected nodes to return
        offset: Number of results to skip (for pagination)
        exclude_node_ids: Optional list of node IDs to exclude (already loaded)
        
    Returns:
        Dictionary containing:
            - nodes: List of connected node records
            - relationships: List of relationship records
            - total: Total count of connected nodes (before pagination)
            
    Raises:
        RuntimeError: If Neo4j execution fails
        ValueError: If node_id is invalid or node not found
        
    Examples:
        >>> result = expand_node_query("123", direction="outgoing", limit=10)
        >>> len(result['nodes']) <= 10
        True
    """
    if not settings.NEO4J_ENABLED:
        raise RuntimeError("Neo4j is not enabled. Set NEO4J_ENABLED=true in .env")
    
    # Use configured default if limit not provided
    if limit is None:
        limit = settings.GRAPH_UI_MAX_NODES_TO_EXPAND

    logger.info(
        "[GRAPH-DEBUG][expand.query] params "
        f"node_id={node_id} direction={direction} limit={limit} offset={offset} "
        f"relationship_types_count={len(relationship_types or [])} "
        f"exclude_node_ids_count={len(exclude_node_ids or [])}"
    )
    
    # Build Cypher query based on direction
    relationship_filter = ""
    if relationship_types:
        # Build type filter like [:WORKS_ON|KNOWS|MANAGES]
        type_list = "|".join(relationship_types)
        relationship_filter = f":{type_list}"
    
    # Build exclusion filter for conditional node return
    # IMPORTANT: We exclude nodes but NOT relationships
    # This ensures relationships to already-loaded nodes are still returned
    exclude_ids_param = exclude_node_ids if exclude_node_ids else []
    
    # Build query based on direction
    if direction == "incoming":
        # Incoming: other nodes point TO this node
        # First collect limited unique nodes, then get ALL their relationships
        query = f"""
        MATCH (m)-[r{relationship_filter}]->(n)
        WHERE elementId(n) = $node_id 
        AND NOT elementId(m) IN $exclude_node_ids
        WITH DISTINCT m
        ORDER BY elementId(m)
        SKIP $offset
        LIMIT $limit
        MATCH (m)-[r{relationship_filter}]->(n)
        WHERE elementId(n) = $node_id
        RETURN m, r
        """
        count_query = f"""
        MATCH (m)-[r{relationship_filter}]->(n)
        WHERE elementId(n) = $node_id
        AND NOT elementId(m) IN $exclude_node_ids
        RETURN count(DISTINCT m) as total
        """
        
        # Query for relationships to already-loaded nodes
        relationships_only_query = f"""
        MATCH (m)-[r{relationship_filter}]->(n)
        WHERE elementId(n) = $node_id 
        AND elementId(m) IN $exclude_node_ids
        RETURN null as m, r
        """
        
    elif direction == "outgoing":
        # Outgoing: this node points TO other nodes
        # First collect limited unique nodes, then get ALL their relationships
        query = f"""
        MATCH (n)-[r{relationship_filter}]->(m)
        WHERE elementId(n) = $node_id
        AND NOT elementId(m) IN $exclude_node_ids
        WITH DISTINCT m
        ORDER BY elementId(m)
        SKIP $offset
        LIMIT $limit
        MATCH (n)-[r{relationship_filter}]->(m)
        WHERE elementId(n) = $node_id
        RETURN m, r
        """
        count_query = f"""
        MATCH (n)-[r{relationship_filter}]->(m)
        WHERE elementId(n) = $node_id
        AND NOT elementId(m) IN $exclude_node_ids
        RETURN count(DISTINCT m) as total
        """
        
        # Query for relationships to already-loaded nodes
        relationships_only_query = f"""
        MATCH (n)-[r{relationship_filter}]->(m)
        WHERE elementId(n) = $node_id 
        AND elementId(m) IN $exclude_node_ids
        RETURN null as m, r
        """
        
    else:  # both
        # Both directions: use undirected pattern to get nodes from both directions
        # First collect limited unique nodes, then get ALL their relationships
        query = f"""
        MATCH (m)-[r{relationship_filter}]-(n)
        WHERE elementId(n) = $node_id
        AND NOT elementId(m) IN $exclude_node_ids
        WITH DISTINCT m
        ORDER BY elementId(m)
        SKIP $offset
        LIMIT $limit
        MATCH (m)-[r{relationship_filter}]-(n)
        WHERE elementId(n) = $node_id
        RETURN m, r
        """
        count_query = f"""
        MATCH (m)-[r{relationship_filter}]-(n)
        WHERE elementId(n) = $node_id
        AND NOT elementId(m) IN $exclude_node_ids
        RETURN count(DISTINCT m) as total
        """
        
        # Query for relationships to already-loaded nodes (no limit on relationships)
        relationships_only_query = f"""
        MATCH (m)-[r{relationship_filter}]-(n)
        WHERE elementId(n) = $node_id 
        AND elementId(m) IN $exclude_node_ids
        RETURN null as m, r
        """
    
    # Create Neo4j driver
    driver = None
    try:
        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
        )
        
        # Verify connectivity
        driver.verify_connectivity()
        
        # Execute count query first to get total

        with driver.session() as session:
            # Get total count of unique nodes
            count_result = session.run(
                count_query,
                node_id=node_id,
                exclude_node_ids=exclude_ids_param
            )
            count_record = count_result.single()
            total = count_record["total"] if count_record else 0
            
            # Execute main query (new nodes + their relationships)
            result = session.run(
                query,
                node_id=node_id,
                limit=limit,
                offset=offset,
                exclude_node_ids=exclude_ids_param,
                timeout=settings.NEO4J_QUERY_TIMEOUT
            )
            
            # Convert to list of dictionaries
            records = [dict(record) for record in result]
            
            # Execute relationships-only query (relationships to already-loaded nodes)
            # Only run if there are excluded nodes
            rel_only_records = []
            if exclude_node_ids:
                rel_only_result = session.run(
                    relationships_only_query,
                    node_id=node_id,
                    exclude_node_ids=exclude_ids_param,
                    timeout=settings.NEO4J_QUERY_TIMEOUT
                )
                rel_only_records = [dict(record) for record in rel_only_result]
                # Merge with main results
                records.extend(rel_only_records)
            
            logger.info(
                "[GRAPH-DEBUG][expand.query] executed "
                f"records={len(records)} rel_only_records={len(rel_only_records)} total={total}"
            )
            
            return {
                "records": records,
                "total": total
            }
            
    except ServiceUnavailable as e:
        logger.error(f"Neo4j connection failed: {e}")
        raise RuntimeError(f"Unable to connect to Neo4j database: {str(e)}") from e
    
    except Neo4jError as e:
        logger.error(f"Neo4j expansion query failed: {e}")
        error_msg = str(e)
        
        # Check if node doesn't exist
        if "not found" in error_msg.lower():
            raise ValueError(f"Node with ID '{node_id}' not found") from e
        
        raise RuntimeError(f"Query execution error: {error_msg}") from e
    
    except Exception as e:
        logger.error(f"Unexpected error executing expansion query: {e}")
        raise RuntimeError(f"Unexpected error: {str(e)}") from e
    
    finally:
        if driver:
            driver.close()

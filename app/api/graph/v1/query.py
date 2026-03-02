"""Query layer for Neo4j graph database operations."""

import re
from typing import Any, Dict, List
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.settings import settings
from app.common.logger import logger


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


def execute_cypher_query(query: str, timeout: int = 30) -> List[Dict[str, Any]]:
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
            result = session.run(query, timeout=timeout)
            
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


def expand_node_query(
    node_id: str,
    direction: str = "both",
    relationship_types: List[str] = None,
    limit: int = 50,
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
    
    # Build Cypher query based on direction
    relationship_filter = ""
    if relationship_types:
        # Build type filter like [:WORKS_ON|KNOWS|MANAGES]
        type_list = "|".join(relationship_types)
        relationship_filter = f":{type_list}"
    
    # Build exclusion filter
    exclusion_clause = ""
    if exclude_node_ids:
        # Convert to comma-separated string for Cypher
        exclusion_list = ", ".join([f"'{nid}'" for nid in exclude_node_ids])
        exclusion_clause = f"AND NOT elementId(m) IN [{exclusion_list}]"
    
    # Build query based on direction
    if direction == "incoming":
        # Incoming: other nodes point TO this node
        query = f"""
        MATCH (m)-[r{relationship_filter}]->(n)
        WHERE elementId(n) = $node_id {exclusion_clause}
        RETURN m, r
        ORDER BY elementId(m)
        SKIP $offset
        LIMIT $limit
        """
        count_query = f"""
        MATCH (m)-[r{relationship_filter}]->(n)
        WHERE elementId(n) = $node_id {exclusion_clause}
        RETURN count(DISTINCT m) as total
        """
        
    elif direction == "outgoing":
        # Outgoing: this node points TO other nodes
        query = f"""
        MATCH (n)-[r{relationship_filter}]->(m)
        WHERE elementId(n) = $node_id {exclusion_clause}
        RETURN m, r
        ORDER BY elementId(m)
        SKIP $offset
        LIMIT $limit
        """
        count_query = f"""
        MATCH (n)-[r{relationship_filter}]->(m)
        WHERE elementId(n) = $node_id {exclusion_clause}
        RETURN count(DISTINCT m) as total
        """
        
    else:  # both
        # Both directions: UNION of incoming and outgoing
        query = f"""
        MATCH (m)-[r{relationship_filter}]->(n)
        WHERE elementId(n) = $node_id {exclusion_clause}
        RETURN m, r
        UNION
        MATCH (n)-[r{relationship_filter}]->(m)
        WHERE elementId(n) = $node_id {exclusion_clause}
        RETURN m, r
        ORDER BY elementId(m)
        SKIP $offset
        LIMIT $limit
        """
        count_query = f"""
        MATCH (m)-[r{relationship_filter}]->(n)
        WHERE elementId(n) = $node_id {exclusion_clause}
        RETURN count(DISTINCT m) as c1
        UNION
        MATCH (n)-[r{relationship_filter}]->(m)
        WHERE elementId(n) = $node_id {exclusion_clause}
        RETURN count(DISTINCT m) as c1
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
            # Get total count
            if direction == "both":
                # For UNION, sum the counts
                count_result = session.run(
                    count_query,
                    node_id=node_id
                )
                total = sum([record["c1"] for record in count_result])
            else:
                count_result = session.run(
                    count_query,
                    node_id=node_id
                )
                count_record = count_result.single()
                total = count_record["total"] if count_record else 0
            
            # Execute main query
            result = session.run(
                query,
                node_id=node_id,
                limit=limit,
                offset=offset,
                timeout=settings.NEO4J_QUERY_TIMEOUT
            )
            
            # Convert to list of dictionaries
            records = [dict(record) for record in result]
            
            logger.info(f"Node expansion query executed. Returned {len(records)} records, total={total}")
            
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

"""Data transformation utilities for graph visualization

Functions for converting between Neo4j format and Cytoscape format,
and parsing error responses from the backend API.
"""

from app.common.node_size import apply_node_size 
from app.settings import settings


def _compact_node_label(label_value):
    """Create a compact node label for in-node rendering.

    Keeps labels short enough to stay visually contained in node shapes.
    """
    max_chars = max(4, int(settings.GRAPH_UI_MAX_NODE_LABEL_CHARS))
    text = str(label_value) if label_value is not None else ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def neo4j_to_cytoscape(graph_response):
    """Transform Neo4j graph response to Cytoscape elements format
    
    Args:
        graph_response (dict): Graph response from backend API containing:
            - nodes: List of node objects with id, labels, properties
            - relationships: List of relationship objects with id, type, startNode, endNode, properties
    
    Returns:
        list: List of Cytoscape elements (nodes and edges)
    """
    elements = []
    
    # Transform nodes
    for node in graph_response.get("nodes", []):
        node_label = node.get("labels", ["Node"])[0] if node.get("labels") else "Node"
        display_name = (
            node.get("properties", {}).get("name") or 
            node.get("properties", {}).get("title") or 
            node.get("properties", {}).get("key") or 
            node_label
        )
        compact_label = _compact_node_label(display_name)

        # Neo4j element id is used as Cytoscape node id so edges (which reference element_id) connect correctly.
        # The wba_id is stored separately for spotlight matching and display in the properties panel.
        neo4j_element_id = node['elementId']
        wba_id = node['wba_id']

        cyto_node_data = {
            **node.get('properties', {}),
            'id': neo4j_element_id,   # Must match edge source/target (Neo4j element_id)
            'wba_id': wba_id,  # Canonical WBA node identifier for display and spotlight matching
            'label': display_name,
            'displayLabel': compact_label,
            'nodeType': node_label,
            'elementType': 'node'
        }

        cyto_node = {
            'group': 'nodes',
            'data': cyto_node_data
        }
        apply_node_size(cyto_node)
        elements.append(cyto_node)

    # Transform relationships
    for rel in graph_response.get("relationships", []):
        # Skip relationships flagged as hidden from the graph UI (e.g. auto-generated reverse edges).
        # The REST API still returns these; the filter applies to the UI render path only.
        if not rel.get('properties', {}).get('_display_in_graph', True):
            continue
        # Use Neo4j element ids for endpoints
        source_id = rel.get('startNode')
        target_id = rel.get('endNode')
        cyto_edge = {
            'group': 'edges',
            'data': {
                **rel.get('properties', {}),
                'id': rel['id'],
                'source': source_id,
                'target': target_id,
                'label': rel['type'],
                'relType': rel['type'],
                'elementType': 'edge'
            }
        }
        elements.append(cyto_edge)

    return elements


def parse_error_response(error_data, status_code):
    """Parse backend error response and provide user-friendly messages with helpful links
    
    Args:
        error_data (dict): Error response from backend API
        status_code (int): HTTP status code
    
    Returns:
        tuple: (message, hint, doc_link, alert_type)
    """
    # Extract error details
    error_type = error_data.get("detail", {}).get("error", "Unknown error")
    error_message = error_data.get("detail", {}).get("message", "")
    
    # Neo4j Cypher documentation base URL
    CYPHER_DOCS = "https://neo4j.com/docs/cypher-manual/current/"
    
    # Parse and categorize errors
    if status_code == 400:
        # Validation errors
        if "write operation" in error_message.lower() or "validation failed" in error_type.lower():
            return (
                "🚫 Write operations are not allowed",
                "Only read-only queries (MATCH, RETURN, WITH, etc.) are permitted for security reasons. Remove CREATE, MERGE, DELETE, SET, or similar keywords from your query.",
                f"{CYPHER_DOCS}clauses/match/",
                "danger"
            )
        elif "syntax error" in error_message.lower():
            # Extract the actual syntax error message
            return (
                "❌ Cypher Syntax Error",
                f"Your query has a syntax error: {error_message}. Check for missing parentheses, keywords, or commas.",
                f"{CYPHER_DOCS}syntax/",
                "danger"
            )
        else:
            return (
                "⚠️ Query Validation Error",
                error_message or "Your query did not pass validation. Check the query syntax and try again.",
                f"{CYPHER_DOCS}introduction/",
                "warning"
            )
    
    elif status_code == 500:
        # Server/execution errors
        if "unable to connect" in error_message.lower() or "connection" in error_message.lower():
            return (
                "🔌 Unable to Connect to Neo4j",
                f"Cannot establish connection to Neo4j database. Please ensure Neo4j is running at {settings.NEO4J_URI} and the credentials are correct.",
                "https://neo4j.com/docs/operations-manual/current/installation/",
                "danger"
            )
        elif "timeout" in error_message.lower():
            return (
                "⏱️ Query Timeout",
                "The query took too long to execute. Try simplifying your query or adding a LIMIT clause (e.g., LIMIT 100) to reduce the result set size.",
                f"{CYPHER_DOCS}clauses/limit/",
                "warning"
            )
        elif "syntax error" in error_message.lower():
            return (
                "❌ Cypher Syntax Error",
                f"{error_message}. Common issues: missing RETURN clause, unmatched parentheses, or invalid property access.",
                f"{CYPHER_DOCS}syntax/",
                "danger"
            )
        elif "not enabled" in error_message.lower():
            return (
                "⚙️ Neo4j Not Enabled",
                "Neo4j integration is not enabled in the application configuration. Contact your administrator.",
                None,
                "warning"
            )
        else:
            return (
                "💥 Query Execution Failed",
                f"{error_message or 'An error occurred while executing your query. Check the query syntax and Neo4j connection.'}",
                f"{CYPHER_DOCS}introduction/",
                "danger"
            )
    
    elif status_code == 503:
        # Service unavailable
        return (
            "🚧 Service Unavailable",
            "The Neo4j service is currently unavailable. Please try again later or contact your administrator.",
            None,
            "warning"
        )
    
    else:
        # Other errors
        return (
            "⚠️ Unexpected Error",
            error_message or "An unexpected error occurred. Please try again or contact support if the issue persists.",
            None,
            "danger"
        )

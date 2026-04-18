"""FastAPI router for Graph API v1 - Cypher query execution endpoints."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import ValidationError

from app.analytics.collaboration.config import CollaborationNetworkConfig
from app.common.logger import logger
from .model import (
    CollaborationNetworkResponse, 
    CypherQueryRequest, 
    GraphResponse, 
    NodeExpansionRequest, 
    NodeExpansionResponse
    )
from . import service

router = APIRouter(prefix="/graph", tags=["graph"])


@router.post("/query", response_model=GraphResponse)
async def execute_query(request: CypherQueryRequest):
    """
    Execute a Cypher query against Neo4j and return graph or tabular results.
    
    This endpoint accepts read-only Cypher queries (MATCH, RETURN, etc.) and
    returns either graph data (nodes/relationships) or tabular data depending
    on the query type.
    
    **Security**: Only read-only queries are allowed. Write operations 
    (CREATE, MERGE, DELETE, SET, REMOVE, etc.) are rejected with 400 error.
    
    **Examples**:
    - Graph query: `MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 25`
    - Tabular query: `MATCH (n) RETURN count(n) as nodeCount`
    - Properties query: `MATCH (p:Person) RETURN p.name, p.email LIMIT 10`
    
    Args:
        request: CypherQueryRequest with the query string to execute
        
    Returns:
        GraphResponse with nodes/relationships (if graph query) or 
        raw results (if tabular query)
        
    Raises:
        HTTPException 400: If query validation fails (write operations detected)
        HTTPException 500: If Neo4j execution fails (connection, syntax errors)
    """
    try:
        logger.info(f"Received query request: {request.query[:100]}...")
        response = service.execute_and_format_query(request.query)
        logger.info(f"Query executed successfully. isGraph={response.isGraph}, "
                   f"nodes={len(response.nodes)}, rels={len(response.relationships)}, "
                   f"resultCount={response.resultCount}")
        return response
        
    except ValueError as e:
        # Validation errors: invalid query format, write operations, etc.
        logger.warning(f"Query validation error: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Query validation failed",
                "message": str(e),
                "query": request.query[:200]  # Truncate for safety
            }
        ) from e

    except RuntimeError as e:
        # Execution errors: Neo4j connection, query execution, timeouts
        logger.error(f"Query execution error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Query execution failed",
                "message": str(e),
                "hint": "Check Neo4j connection and query syntax"
            }
        ) from e

    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error executing query: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "An unexpected error occurred while processing your query"
            }
        ) from e


@router.post("/expand", response_model=NodeExpansionResponse)
async def expand_node(request: NodeExpansionRequest):
    """
    Expand a node to retrieve connected neighbors (nodes and relationships).
    
    This endpoint allows progressive graph exploration by expanding a single
    node to show its connected neighbors. Supports:
    - Direction filtering (incoming, outgoing, or both)
    - Relationship type filtering
    - Pagination (limit and offset)
    - Deduplication (exclude already loaded nodes)
    
    **Use Cases**:
    - Click a node to see what it connects to
    - Progressive graph drilling and exploration
    - Load large graphs incrementally
    
    **Examples**:
    - Expand both directions: `{"node_id": "123", "direction": "both", "limit": 50}`
    - Expand with filter: `{"node_id": "123", "relationship_types": ["WORKS_ON"], "limit": 25}`
    - Paginate results: `{"node_id": "123", "limit": 50, "offset": 50}`
    
    Args:
        request: NodeExpansionRequest with node_id, direction, filters, and pagination
        
    Returns:
        NodeExpansionResponse with connected nodes, relationships, and pagination metadata
        
    Raises:
        HTTPException 400: If node_id is invalid or parameters are malformed
        HTTPException 404: If node not found
        HTTPException 500: If Neo4j execution fails
    """
    try:
        logger.info(f"Expanding node {request.node_id} with direction={request.direction}, "
                   f"limit={request.limit}, offset={request.offset}")
        
        response = service.expand_node(
            node_id=request.node_id,
            direction=request.direction,
            relationship_types=request.relationship_types,
            limit=request.limit,
            offset=request.offset,
            exclude_node_ids=request.exclude_node_ids
        )
        
        # Log expansion results
        logger.info(f"Node expanded successfully. nodes={len(response.nodes)}, "
                   f"relationships={len(response.relationships)}, "
                   f"total={getattr(response.pagination, 'total', 0)}, "
                   f"has_more={getattr(response.pagination, 'has_more', False)}")
        
        return response
        
    except ValueError as e:
        # Node not found or invalid parameters
        logger.warning(f"Node expansion validation error: {e}")
        
        # Check if it's a "not found" error
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "Node not found",
                    "message": str(e),
                    "node_id": request.node_id
                }
            ) from e
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid request",
                    "message": str(e),
                    "node_id": request.node_id
                }
            ) from e
        
    except RuntimeError as e:
        # Neo4j execution errors
        logger.error(f"Node expansion execution error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Expansion failed",
                "message": str(e),
                "hint": "Check Neo4j connection and query syntax"
            }
        ) from e
        
    except Exception as e:
        # Unexpected errors
        logger.error(f"Unexpected error expanding node: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "An unexpected error occurred while expanding the node"
            }
        ) from e


@router.get("/collaboration-network", response_model=CollaborationNetworkResponse)
async def get_collaboration_network(
    layers: str | None = Query(default=None, description="Comma-separated collaboration layers"),
    lookback_days: int = Query(default=90, ge=1, le=365),
    min_pair_score: float = Query(default=1.0, ge=0),
    top_n_edges_per_node: int = Query(default=0, ge=0, le=200),
    ensure_min_connection: bool = Query(default=True),
    exclude_bots: bool = Query(default=True),
    exclude_suffixes: str | None = Query(default=None, description="Comma-separated file suffixes to ignore"),
    w_reporter_assignee: float = Query(default=2.0, ge=0),
    w_pr_reviews: float = Query(default=3.0, ge=0),
    w_shared_file_commits: float = Query(default=5.0, ge=0),
    w_sprint_coworkers: float = Query(default=2.0, ge=0),
    w_explicit_review_requests: float = Query(default=2.0, ge=0),
    w_epic_overlap: float = Query(default=1.0, ge=0),
):
    """
    Build and return a collaboration network with Louvain community detection.

    This endpoint runs the 6-scenario collaboration score Cypher query (last 90 days),
    feeds the results through NetworkX + python-louvain community detection, and
    returns Cytoscape-ready elements enriched with:
    - **community** (int): Louvain community ID — maps to a colour class in the stylesheet
    - **hub_score** (float): Weighted degree — maps to node size in the stylesheet
    - **weight** (float): Collaboration score on edges — maps to line thickness

    Also returns summary statistics (nodes, pairs, communities, modularity score) for
    the UI banner or debugging.

    Returns:
        CollaborationNetworkResponse with elements and summary stats

    Raises:
        HTTPException 503: If Neo4j is not enabled
        HTTPException 404: If query returns no collaboration data
        HTTPException 500: If Neo4j execution or community detection fails
    """
    try:
        logger.info("Collaboration network request received.")
        config = CollaborationNetworkConfig.from_query_values(
            {
                "layers": layers,
                "lookback_days": lookback_days,
                "min_pair_score": min_pair_score,
                "top_n_edges_per_node": top_n_edges_per_node,
                "ensure_min_connection": ensure_min_connection,
                "exclude_bots": exclude_bots,
                "exclude_suffixes": exclude_suffixes,
                "w_reporter_assignee": w_reporter_assignee,
                "w_pr_reviews": w_pr_reviews,
                "w_shared_file_commits": w_shared_file_commits,
                "w_sprint_coworkers": w_sprint_coworkers,
                "w_explicit_review_requests": w_explicit_review_requests,
                "w_epic_overlap": w_epic_overlap,
            }
        )
        response = service.get_collaboration_network(config=config)
        logger.info(
            f"Collaboration network built: people={response.num_people}, "
            f"pairs={response.num_pairs}, communities={response.num_communities}, "
            f"modularity={response.modularity}"
        )
        return response

    except ValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Invalid collaboration configuration",
                "message": str(e),
            },
        ) from e

    except ValueError as e:
        if "No collaboration data" not in str(e) and "returned no data" not in str(e):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Invalid collaboration configuration",
                    "message": str(e),
                },
            ) from e
        raise HTTPException(
            status_code=404,
            detail={
                "error": "No collaboration data",
                "message": str(e),
                "hint": "Check that the 90-day window contains activity in Neo4j.",
            },
        ) from e

    except RuntimeError as e:
        logger.error(f"Collaboration network execution error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Execution failed",
                "message": str(e),
                "hint": "Check Neo4j connection and NEO4J_ENABLED setting.",
            },
        ) from e

    except Exception as e:
        logger.error(f"Unexpected error building collaboration network: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal server error",
                "message": "An unexpected error occurred while building the collaboration network.",
            },
        ) from e


@router.get("/health")
async def health_check():
    """
    Health check endpoint to verify Neo4j connectivity.
    
    Returns:
        dict: Status information including Neo4j connection state
    """
    from app.settings import settings
    
    if not settings.NEO4J_ENABLED:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unavailable",
                "message": "Neo4j is not enabled in configuration"
            }
        )
    
    # Try to execute a simple query to verify connectivity
    try:
        test_query = "RETURN 1 as test"
        response = service.execute_and_format_query(test_query)
        
        return {
            "status": "healthy",
            "neo4j": "connected",
            "message": "Graph API is operational"
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "neo4j": "disconnected",
                "message": str(e)
            }
        ) from e

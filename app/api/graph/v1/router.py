"""FastAPI router for Graph API v1 - Cypher query execution endpoints."""

from fastapi import APIRouter, HTTPException

from app.common.logger import logger
from .model import CypherQueryRequest, GraphResponse
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

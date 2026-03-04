"""Pytest tests for Graph API router endpoints.

These tests verify the FastAPI router endpoints work correctly,
including request/response handling, error cases, and serialization.

Tests assume Neo4j server is running and accessible.
Run with: pytest tests/test_graph_router.py -v
"""

import pytest
import httpx

from app.settings import settings


BASE_URL = "http://localhost:8000"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not settings.NEO4J_ENABLED,
    reason="Neo4j is not enabled (NEO4J_ENABLED=false)"
)
class TestGraphRouterEndpoints:
    """Integration tests for Graph API router endpoints."""
    
    async def test_health_check_endpoint(self):
        """Test GET /api/v1/graph/health returns healthy status."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.get("/api/v1/graph/health")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "healthy"
            assert data["neo4j"] == "connected"
            assert "message" in data
    
    async def test_query_endpoint_nodes_only(self):
        """Test POST /api/v1/graph/query with node-only query."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": "MATCH (n) RETURN n LIMIT 5"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify response structure
            assert "nodes" in data
            assert "relationships" in data
            assert "rawResults" in data
            assert "isGraph" in data
            assert "resultCount" in data
            
            # Should be graph data
            assert data["isGraph"] is True
            assert isinstance(data["nodes"], list)
            assert len(data["nodes"]) <= 5
            assert isinstance(data["relationships"], list)
            assert data["rawResults"] == []

            # If implicit relationships are returned, they should connect returned nodes
            if data["relationships"]:
                node_ids = {node["id"] for node in data["nodes"]}
                for rel in data["relationships"]:
                    assert rel["startNode"] in node_ids
                    assert rel["endNode"] in node_ids
            
            # Verify node structure if results exist
            if data["nodes"]:
                node = data["nodes"][0]
                assert "id" in node
                assert "labels" in node
                assert "properties" in node
                assert isinstance(node["labels"], list)
                assert isinstance(node["properties"], dict)
    
    async def test_query_endpoint_with_relationships(self):
        """Test POST /api/v1/graph/query with relationship query."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 3"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["isGraph"] is True
            assert isinstance(data["nodes"], list)
            assert isinstance(data["relationships"], list)
            
            # If relationships exist, verify structure
            if data["relationships"]:
                rel = data["relationships"][0]
                assert "id" in rel
                assert "type" in rel
                assert "startNode" in rel
                assert "endNode" in rel
                assert "properties" in rel
                
                # Verify start and end nodes exist in nodes list
                node_ids = [node["id"] for node in data["nodes"]]
                assert rel["startNode"] in node_ids
                assert rel["endNode"] in node_ids
    
    async def test_query_endpoint_tabular_data(self):
        """Test POST /api/v1/graph/query with aggregation query."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": "MATCH (n) RETURN count(n) as nodeCount"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Should be tabular data
            assert data["isGraph"] is False
            assert data["nodes"] == []
            assert data["relationships"] == []
            assert len(data["rawResults"]) == 1
            
            # Verify result structure
            result = data["rawResults"][0]
            assert "nodeCount" in result
            assert isinstance(result["nodeCount"], int)
            assert result["nodeCount"] >= 0
    
    async def test_query_endpoint_properties_query(self):
        """Test query returning specific node properties."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={
                    "query": """
                    MATCH (n)
                    WHERE n.name IS NOT NULL
                    RETURN n.name as name, labels(n) as labels
                    LIMIT 3
                    """
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Properties query returns tabular data
            assert data["isGraph"] is False
            
            if data["rawResults"]:
                result = data["rawResults"][0]
                assert "name" in result
                assert "labels" in result
    
    async def test_query_endpoint_empty_results(self):
        """Test query that returns no results."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": "MATCH (n:NonExistentLabel999) RETURN n"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["nodes"] == []
            assert data["relationships"] == []
            assert data["resultCount"] == 0
    
    async def test_query_endpoint_datetime_serialization(self):
        """Test that Neo4j DateTime properties are properly serialized."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": "MATCH (n) RETURN n LIMIT 5"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Should successfully serialize without errors
            # DateTime values should be strings in ISO format
            if data["nodes"]:
                for node in data["nodes"]:
                    for key, value in node["properties"].items():
                        # All values should be JSON-serializable (str, int, float, bool, list, dict, None)
                        assert isinstance(value, (str, int, float, bool, list, dict, type(None)))


@pytest.mark.asyncio
class TestGraphRouterValidation:
    """Tests for query validation and error handling."""
    
    async def test_reject_create_query(self):
        """Test that CREATE queries are rejected with 400 error."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": "CREATE (n:Test {name: 'test'}) RETURN n"}
            )
            
            assert response.status_code == 400
            data = response.json()
            
            assert "detail" in data
            detail = data["detail"]
            assert "error" in detail
            assert "validation" in detail["error"].lower()
            assert "message" in detail
            assert "write" in detail["message"].lower()
    
    async def test_reject_delete_query(self):
        """Test that DELETE queries are rejected."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": "MATCH (n:Test) DELETE n"}
            )
            
            assert response.status_code == 400
            data = response.json()
            assert "write" in data["detail"]["message"].lower() or "validation" in data["detail"]["error"].lower()
    
    async def test_reject_merge_query(self):
        """Test that MERGE queries are rejected."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": "MERGE (n:Person {name: 'Alice'}) RETURN n"}
            )
            
            assert response.status_code == 400
            data = response.json()
            assert "validation" in data["detail"]["error"].lower()
    
    async def test_reject_set_query(self):
        """Test that SET queries are rejected."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": "MATCH (n) SET n.property = 'value' RETURN n"}
            )
            
            assert response.status_code == 400
    
    async def test_reject_empty_query(self):
        """Test that empty queries are rejected."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": ""}
            )
            
            # Should be rejected by Pydantic validation
            assert response.status_code == 422  # Unprocessable Entity
    
    async def test_reject_whitespace_only_query(self):
        """Test that whitespace-only queries are rejected."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": "   \n\t   "}
            )
            
            # Should be rejected by Pydantic validation
            assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.skipif(
    not settings.NEO4J_ENABLED,
    reason="Neo4j is not enabled"
)
class TestGraphRouterErrorHandling:
    """Tests for error handling in router endpoints."""
    
    async def test_syntax_error_handling(self):
        """Test that Cypher syntax errors return error with helpful message."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": "MATCH (n) RETURN INVALID_FUNCTION(n)"}
            )
            
            # Syntax/function errors can return 400 (validation) or 500 (execution)
            assert response.status_code in [400, 500]
            data = response.json()
            
            assert "detail" in data
            detail = data["detail"]
            assert "error" in detail
            assert "message" in detail
    
    async def test_missing_query_field(self):
        """Test request without query field."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={}
            )
            
            # Pydantic validation error
            assert response.status_code == 422
    
    async def test_invalid_json_payload(self):
        """Test request with invalid JSON."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                content="not valid json",
                headers={"Content-Type": "application/json"}
            )
            
            assert response.status_code == 422
    
    async def test_query_too_long(self):
        """Test query exceeding max length."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            # Create a query longer than 10000 characters
            long_query = "MATCH (n) RETURN n " + "// padding " * 2000
            
            response = await client.post(
                "/api/v1/graph/query",
                json={"query": long_query}
            )
            
            # Should be rejected by Pydantic validation
            assert response.status_code == 422


@pytest.mark.asyncio
class TestGraphRouterHealthCheckEdgeCases:
    """Tests for health check endpoint edge cases."""
    
    async def test_health_check_when_neo4j_disabled(self, monkeypatch):
        """Test health check when Neo4j is disabled."""
        # This test would require mocking settings, skip if Neo4j is enabled
        if settings.NEO4J_ENABLED:
            pytest.skip("Neo4j is enabled, cannot test disabled state")
        
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.get("/api/v1/graph/health")
            
            assert response.status_code == 503
            data = response.json()
            assert "detail" in data
            assert "unavailable" in data["detail"]["status"].lower()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not settings.NEO4J_ENABLED,
    reason="Neo4j is not enabled"
)
class TestGraphRouterComplexQueries:
    """Tests for complex query scenarios."""
    
    async def test_query_with_where_clause(self):
        """Test query with WHERE clause."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={
                    "query": """
                    MATCH (n)
                    WHERE n.name IS NOT NULL
                    RETURN n
                    LIMIT 5
                    """
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["isGraph"] is True
    
    async def test_query_with_optional_match(self):
        """Test query with OPTIONAL MATCH."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={
                    "query": """
                    MATCH (n)
                    OPTIONAL MATCH (n)-[r]->(m)
                    RETURN n, r, m
                    LIMIT 5
                    """
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "isGraph" in data
    
    async def test_query_with_order_by(self):
        """Test query with ORDER BY clause."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={
                    "query": """
                    MATCH (n)
                    WHERE n.name IS NOT NULL
                    RETURN n.name as name
                    ORDER BY n.name
                    LIMIT 5
                    """
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["isGraph"] is False  # Property query returns tabular
    
    async def test_query_with_multiple_return_values(self):
        """Test query returning multiple scalar values."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v1/graph/query",
                json={
                    "query": """
                    MATCH (n)
                    RETURN count(n) as total, 
                           collect(DISTINCT labels(n)) as labelsList
                    """
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["isGraph"] is False
            
            if data["rawResults"]:
                result = data["rawResults"][0]
                assert "total" in result
                assert "labelsList" in result

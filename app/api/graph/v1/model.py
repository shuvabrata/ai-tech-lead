"""Pydantic models for Graph API v1 - Cypher query execution and graph data."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class CypherQueryRequest(BaseModel):
    """Request model for executing a Cypher query."""
    
    query: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Cypher query to execute against Neo4j",
        examples=["MATCH (n) RETURN n LIMIT 25"]
    )
    
    @field_validator('query')
    @classmethod
    def validate_query_not_empty(cls, v: str) -> str:
        """Ensure query is not just whitespace."""
        if not v or not v.strip():
            raise ValueError("Query cannot be empty or whitespace only")
        return v.strip()


class GraphNode(BaseModel):
    """Model representing a Neo4j node."""
    
    id: str = Field(..., description="Unique identifier for the node")
    labels: List[str] = Field(default_factory=list, description="Node labels/types")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Node properties")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "123",
                "labels": ["Person", "Employee"],
                "properties": {"name": "John Doe", "email": "john@example.com"}
            }
        }


class GraphRelationship(BaseModel):
    """Model representing a Neo4j relationship/edge."""
    
    id: str = Field(..., description="Unique identifier for the relationship")
    type: str = Field(..., description="Relationship type")
    startNode: str = Field(..., description="ID of the source node")
    endNode: str = Field(..., description="ID of the target node")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Relationship properties")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "456",
                "type": "WORKS_ON",
                "startNode": "123",
                "endNode": "789",
                "properties": {"role": "Developer", "since": "2024-01-01"}
            }
        }


class GraphResponse(BaseModel):
    """Response model for graph query execution."""
    
    nodes: List[GraphNode] = Field(
        default_factory=list,
        description="List of nodes returned by the query"
    )
    relationships: List[GraphRelationship] = Field(
        default_factory=list,
        description="List of relationships returned by the query"
    )
    rawResults: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Raw query results (for non-graph queries)"
    )
    isGraph: bool = Field(
        ...,
        description="True if results contain nodes/relationships, False for tabular data"
    )
    resultCount: Optional[int] = Field(
        None,
        description="Total number of results returned"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "nodes": [
                    {
                        "id": "123",
                        "labels": ["Person"],
                        "properties": {"name": "Alice"}
                    }
                ],
                "relationships": [
                    {
                        "id": "456",
                        "type": "KNOWS",
                        "startNode": "123",
                        "endNode": "789",
                        "properties": {}
                    }
                ],
                "rawResults": [],
                "isGraph": True,
                "resultCount": 2
            }
        }


class GraphErrorResponse(BaseModel):
    """Error response model for graph query failures."""
    
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    query: Optional[str] = Field(None, description="The query that caused the error")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Query validation failed",
                "detail": "Write operations are not allowed. Query contains CREATE statement.",
                "query": "CREATE (n:Test) RETURN n"
            }
        }

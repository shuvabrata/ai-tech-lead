"""Pydantic models for Graph API v1 - Cypher query execution and graph data."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.settings import settings


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
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "123",
                "labels": ["Person", "Employee"],
                "properties": {"name": "John Doe", "email": "john@example.com"}
            }
        }
    )


class GraphRelationship(BaseModel):
    """Model representing a Neo4j relationship/edge."""
    
    id: str = Field(..., description="Unique identifier for the relationship")
    type: str = Field(..., description="Relationship type")
    startNode: str = Field(..., description="ID of the source node")
    endNode: str = Field(..., description="ID of the target node")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Relationship properties")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "456",
                "type": "WORKS_ON",
                "startNode": "123",
                "endNode": "789",
                "properties": {"role": "Developer", "since": "2024-01-01"}
            }
        }
    )


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
    
    model_config = ConfigDict(
        json_schema_extra={
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
    )


class GraphErrorResponse(BaseModel):
    """Error response model for graph query failures."""
    
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    query: Optional[str] = Field(None, description="The query that caused the error")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "Query validation failed",
                "detail": "Write operations are not allowed. Query contains CREATE statement.",
                "query": "CREATE (n:Test) RETURN n"
            }
        }
    )


class NodeExpansionRequest(BaseModel):
    """Request model for expanding a node to show connected neighbors."""
    
    node_id: str = Field(
        ...,
        description="ID of the node to expand"
    )
    direction: str = Field(
        default="both",
        description="Direction of relationships to follow: 'incoming', 'outgoing', or 'both'",
        examples=["both", "incoming", "outgoing"]
    )
    relationship_types: Optional[List[str]] = Field(
        default=None,
        description="Filter by specific relationship types. If None, all types are included."
    )
    limit: int = Field(
        default=settings.GRAPH_UI_MAX_NODES_TO_EXPAND,
        ge=1,
        le=500,
        description="Maximum number of connected nodes to return (pagination)"
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Offset for pagination (skip first N results)"
    )
    exclude_node_ids: Optional[List[str]] = Field(
        default=None,
        description="List of node IDs to exclude from results (already loaded nodes)"
    )
    
    @field_validator('direction')
    @classmethod
    def validate_direction(cls, v: str) -> str:
        """Ensure direction is one of the valid values."""
        valid_directions = ["incoming", "outgoing", "both"]
        if v.lower() not in valid_directions:
            raise ValueError(f"Direction must be one of {valid_directions}, got '{v}'")
        return v.lower()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "node_id": "123",
                "direction": "both",
                "relationship_types": ["WORKS_ON", "KNOWS"],
                "limit": 50,
                "offset": 0,
                "exclude_node_ids": ["456", "789"]
            }
        }
    )


class CollaborationNetworkResponse(BaseModel):
    """Response model for the collaboration network endpoint.

    Instead of raw Neo4j nodes/relationships, this returns Cytoscape-ready
    element dicts (produced by the community detection pipeline) plus
    summary statistics useful for the UI banner.
    """

    elements: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Cytoscape element dicts (nodes + edges) with community and hub_score attributes",
    )
    num_people: int = Field(..., description="Number of Person nodes in the network")
    num_pairs: int = Field(..., description="Number of collaboration edges")
    num_communities: int = Field(..., description="Number of Louvain communities detected")
    modularity: float = Field(..., description="Louvain modularity score (0-1, >0.3 is meaningful)")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Applied collaboration configuration (layers, weights, filters)",
    )


class PaginationMeta(BaseModel):
    """Pagination metadata for expansion results."""
    
    total: int = Field(..., description="Total number of connected nodes (before pagination)")
    limit: int = Field(..., description="Number of results per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether there are more results available")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 150,
                "limit": 50,
                "offset": 0,
                "has_more": True
            }
        }
    )


class NodeExpansionResponse(BaseModel):
    """Response model for node expansion."""
    
    nodes: List[GraphNode] = Field(
        default_factory=list,
        description="List of newly discovered nodes"
    )
    relationships: List[GraphRelationship] = Field(
        default_factory=list,
        description="List of relationships connecting to the expanded node"
    )
    expanded_node_id: str = Field(
        ...,
        description="ID of the node that was expanded"
    )
    pagination: PaginationMeta = Field(
        ...,
        description="Pagination metadata"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "nodes": [
                    {
                        "id": "789",
                        "labels": ["Project"],
                        "properties": {"name": "AI Platform"}
                    }
                ],
                "relationships": [
                    {
                        "id": "456",
                        "type": "WORKS_ON",
                        "startNode": "123",
                        "endNode": "789",
                        "properties": {"role": "Developer"}
                    }
                ],
                "expanded_node_id": "123",
                "pagination": {
                    "total": 5,
                    "limit": 50,
                    "offset": 0,
                    "has_more": False
                }
            }
        }
    )


class NodePropertyFilter(BaseModel):
    """Server-side node property filter definition."""

    label: str = Field(..., min_length=1, description="Node label to filter")
    property: str = Field(..., min_length=1, description="Property name to filter")
    operator: Literal["=", "!=", ">", "<", ">=", "<=", "CONTAINS", "STARTS WITH", "IN"] = Field(
        ...,
        description="Filter operator",
    )
    value: Any = Field(..., description="Comparison value")


class RelationshipPropertyFilter(BaseModel):
    """Server-side relationship property filter definition."""

    type: str = Field(..., min_length=1, description="Relationship type")
    property: str = Field(..., min_length=1, description="Relationship property name")
    operator: Literal["=", "!=", ">", "<", ">=", "<=", "CONTAINS", "STARTS WITH", "IN"] = Field(
        ...,
        description="Filter operator",
    )
    value: Any = Field(..., description="Comparison value")


class DateRangeFilter(BaseModel):
    """Date range filter for nodes or relationships."""

    scope: Literal["node", "relationship"] = Field(..., description="Filter scope")
    label: Optional[str] = Field(None, description="Node label (required for node scope)")
    type: Optional[str] = Field(None, description="Relationship type (required for relationship scope)")
    property: str = Field(..., min_length=1, description="Date/datetime property name")
    from_value: Optional[str] = Field(None, alias="from", description="Inclusive ISO lower bound")
    to: Optional[str] = Field(None, description="Inclusive ISO upper bound")

    @field_validator("label")
    @classmethod
    def validate_label_for_node_scope(cls, value: Optional[str], info) -> Optional[str]:
        """Require label when scope is node."""
        if info.data.get("scope") == "node" and not value:
            raise ValueError("'label' is required when scope='node'")
        return value

    @field_validator("type")
    @classmethod
    def validate_type_for_relationship_scope(cls, value: Optional[str], info) -> Optional[str]:
        """Require relationship type when scope is relationship."""
        if info.data.get("scope") == "relationship" and not value:
            raise ValueError("'type' is required when scope='relationship'")
        return value


class FilterResultOptions(BaseModel):
    """Output shaping options for filtered graph results."""

    limitNodes: int = Field(default=1000, ge=1, le=20000)
    limitRelationships: int = Field(default=5000, ge=1, le=50000)
    includeImplicitRelationships: bool = Field(default=True)


class GraphFilterRequest(BaseModel):
    """Request model for server-side graph filtering."""

    baseQuery: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Read-only Cypher query that defines the source graph scope",
    )
    mode: Literal["database"] = Field(default="database")
    nodeTypeFilters: List[str] = Field(default_factory=list)
    relationshipTypeFilters: List[str] = Field(default_factory=list)
    nodePropertyFilters: List[NodePropertyFilter] = Field(default_factory=list)
    relationshipPropertyFilters: List[RelationshipPropertyFilter] = Field(default_factory=list)
    dateRangeFilters: List[DateRangeFilter] = Field(default_factory=list)
    resultOptions: FilterResultOptions = Field(default_factory=FilterResultOptions)

    @field_validator("baseQuery")
    @classmethod
    def validate_base_query_not_empty(cls, value: str) -> str:
        """Ensure base query is not whitespace only."""
        if not value or not value.strip():
            raise ValueError("baseQuery cannot be empty or whitespace only")
        return value.strip()


class GraphFilterExecutionMetadata(BaseModel):
    """Execution metadata for filtered graph responses."""

    mode: str = Field(..., description="Execution mode used")
    baseResultCounts: Dict[str, int] = Field(default_factory=dict)
    filteredResultCounts: Dict[str, int] = Field(default_factory=dict)
    truncated: bool = Field(default=False)
    warnings: List[str] = Field(default_factory=list)


class GraphFilterResponse(GraphResponse):
    """Response model for server-side filtered graph endpoint."""

    metadata: GraphFilterExecutionMetadata


class GraphFilterPropertyMetadata(BaseModel):
    """Merged metadata for one node/relationship property."""

    type: Optional[str] = Field(None, description="Property primitive type hint")
    operators: List[str] = Field(default_factory=list, description="Supported operators")
    discovered: bool = Field(default=False, description="True when observed in live discovery")
    serverFilterable: bool = Field(default=False, description="True when supported for server-side filtering")
    localFilterable: bool = Field(default=False, description="True when available for local filtering")
    indexed: bool = Field(default=False, description="True when backend marks property as indexed")


class GraphFilterMetadataDiscovery(BaseModel):
    """Live discovery metadata from the current graph scope."""

    nodeLabels: List[str] = Field(default_factory=list)
    relationshipTypes: List[str] = Field(default_factory=list)
    nodePropertiesByLabel: Dict[str, Dict[str, str]] = Field(default_factory=dict)
    relationshipPropertiesByType: Dict[str, Dict[str, str]] = Field(default_factory=dict)


class GraphFilterMetadataResponse(BaseModel):
    """Response model for graph filter metadata/introspection endpoint."""

    sourceQueryApplied: bool = Field(
        default=False,
        description="True when live discovery was generated from the provided base query",
    )
    discovered: GraphFilterMetadataDiscovery = Field(default_factory=GraphFilterMetadataDiscovery)
    registry: Dict[str, Dict[str, Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Backend-owned registry metadata for server filterability",
    )
    mergedNodeProperties: Dict[str, Dict[str, GraphFilterPropertyMetadata]] = Field(default_factory=dict)
    mergedRelationshipProperties: Dict[str, Dict[str, GraphFilterPropertyMetadata]] = Field(default_factory=dict)

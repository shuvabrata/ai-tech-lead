"""Pydantic models for Search API v1."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Query parameters for the search endpoint."""

    q: Optional[str] = Field(default=None, description="Free-text query.")
    entity_type: Optional[str] = Field(
        default=None,
        description="Filter to a specific entity type (e.g. Issue, PullRequest).",
    )
    source: Optional[str] = Field(
        default=None,
        description="Filter to a specific source (github, jira).",
    )
    status: Optional[str] = Field(
        default=None,
        description="Filter by status (categorical exact match).",
    )
    priority: Optional[str] = Field(
        default=None,
        description="Filter by priority (categorical exact match).",
    )
    date_from: Optional[datetime] = Field(
        default=None,
        description="Filter event_time >= this value (ISO 8601).",
    )
    date_to: Optional[datetime] = Field(
        default=None,
        description="Filter event_time <= this value (ISO 8601).",
    )
    page: int = Field(default=1, ge=1, description="Page number, 1-based.")
    page_size: int = Field(
        default=20, ge=1, le=100, description="Results per page. Max 100."
    )
    full: bool = Field(
        default=False,
        description="If true, include all stored attributes in each result.",
    )


class SearchResult(BaseModel):
    """A single search result."""

    wba_id: str = Field(..., description="WBA canonical key (identical to Neo4j node id).")
    score: Optional[float] = Field(default=None, description="Relevance score from Elasticsearch.")
    url: Optional[str] = Field(default=None, description="Entity URL.")
    event_time: Optional[str] = Field(default=None, description="ISO 8601 event timestamp.")
    highlight: Optional[str] = Field(
        default=None,
        description="Best-matching fragment with <em> tags around matched terms.",
    )
    attributes: Optional[Dict[str, Any]] = Field(
        default=None,
        description="All stored document fields when full=true. Flat ES document shape.",
    )


class SearchResponse(BaseModel):
    """Paginated search response."""

    total: int = Field(..., description="Total number of matching documents.")
    page: int = Field(..., description="Current page number (1-based).")
    page_size: int = Field(..., description="Number of results per page.")
    results: List[SearchResult] = Field(default_factory=list, description="Search results.")

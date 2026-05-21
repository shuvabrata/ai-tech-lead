"""FastAPI router for Search API v1 — GET /api/v1/search."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from common.logger import logger
from .model import SearchRequest, SearchResponse
from . import service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: Optional[str] = Query(default=None, description="Free-text query."),
    entity_type: Optional[str] = Query(
        default=None,
        description="Filter to a specific entity type (e.g. Issue, PullRequest).",
    ),
    source: Optional[str] = Query(
        default=None,
        description="Filter to a specific source (github, jira).",
    ),
    status: Optional[str] = Query(
        default=None,
        description="Filter by status (categorical exact match).",
    ),
    priority: Optional[str] = Query(
        default=None,
        description="Filter by priority (categorical exact match).",
    ),
    date_from: Optional[datetime] = Query(
        default=None,
        description="Filter event_time >= this value (ISO 8601).",
    ),
    date_to: Optional[datetime] = Query(
        default=None,
        description="Filter event_time <= this value (ISO 8601).",
    ),
    page: int = Query(default=1, ge=1, description="Page number, 1-based."),
    page_size: int = Query(default=20, ge=1, le=100, description="Results per page. Max 100."),
    full: bool = Query(
        default=False,
        description="If true, include all stored attributes in each result.",
    ),
) -> SearchResponse:
    """Search across all indexed entities.

    When ``q`` is absent, returns all documents sorted by ``event_time`` desc.
    Categorical filters (``entity_type``, ``source``, ``status``, ``priority``) and
    date range filters can be combined freely with or without a free-text query.
    """
    request = SearchRequest(
        q=q,
        entity_type=entity_type,
        source=source,
        status=status,
        priority=priority,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
        full=full,
    )

    logger.info(
        f"[Search] request q={q!r} entity_type={entity_type} source={source} "
        f"status={status} priority={priority} page={page} page_size={page_size} full={full}"
    )

    try:
        response = service.search(request)
    except Exception as exc:
        logger.exception(f"[Search] Unhandled error during search: {exc}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Search failed", "message": str(exc)},
        ) from exc

    logger.info(f"[Search] response total={response.total} returned={len(response.results)}")
    return response

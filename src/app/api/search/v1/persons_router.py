"""FastAPI router for Person autocomplete — GET /api/v1/search/persons.

Purpose-built for the catalog parameter autocomplete widget.  Returns a slim
list of Person suggestions (wba_id, name, email, source) sourced from the
existing Elasticsearch search service.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from common.logger import logger
from app.settings import settings
from .model import SearchRequest
from . import service


router = APIRouter(prefix="/search/persons", tags=["search"])


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class PersonSuggestion(BaseModel):
    """A single Person suggestion for the autocomplete dropdown."""

    wba_id: str
    name: str
    email: Optional[str] = None
    source: str
    login: Optional[str] = None


class PersonSuggestResponse(BaseModel):
    """Response envelope for the persons autocomplete endpoint."""

    results: List[PersonSuggestion]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_name(attrs: dict) -> str:
    """Extract the best display name from an ES Person document."""
    return (
        attrs.get("full_name")
        or attrs.get("name")
        or attrs.get("login")
        or attrs.get("wba_id", "Unknown")
    )


def _build_suggestion(result) -> PersonSuggestion | None:
    """Convert a SearchResult (with full attributes) to a PersonSuggestion."""
    attrs = result.attributes or {}
    name = _extract_name(attrs)
    source = attrs.get("source", "")
    if not source:
        # Derive source from the wba_id prefix (e.g. "github::Person::alice" → "github")
        parts = result.wba_id.split("::")
        source = parts[0] if parts else "unknown"
    return PersonSuggestion(
        wba_id=result.wba_id,
        name=name,
        email=attrs.get("email") or None,
        source=source,
        login=attrs.get("login") or None,
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("", response_model=PersonSuggestResponse)
async def search_persons(
    q: str = Query(..., min_length=3, description="Search term (min 3 characters)."),
    page_size: int = Query(
        default=10, ge=1, le=20, description="Max suggestions to return. Default 10, max 20."
    ),
) -> PersonSuggestResponse:
    """Autocomplete endpoint for Person entities.

    Returns a slim list of Person suggestions matching the free-text query *q*.
    Filters to ``entity_type=Person`` automatically.  Requires at least 3
    characters to avoid trivial queries.

    Typical use: catalog parameter pickers for person-to-person queries.
    """
    if not settings.ELASTICSEARCH_ENABLED:
        logger.debug("[PersonSearch] Elasticsearch disabled — returning empty suggestions")
        return PersonSuggestResponse(results=[])

    request = SearchRequest(
        q=q,
        entity_type="Person",
        page=1,
        page_size=page_size,
        full=True,  # Need attributes for name/email/source extraction
    )

    logger.info("[PersonSearch] q=%r page_size=%d", q, page_size)

    try:
        response = service.search(request)
    except Exception as exc:
        logger.exception("[PersonSearch] Search failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "Person search failed", "message": str(exc)},
        ) from exc

    suggestions: List[PersonSuggestion] = []
    for result in response.results:
        suggestion = _build_suggestion(result)
        if suggestion:
            suggestions.append(suggestion)

    logger.info("[PersonSearch] q=%r returned=%d", q, len(suggestions))
    return PersonSuggestResponse(results=suggestions)

"""Service layer for Search API v1 — Elasticsearch query construction and execution."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from elasticsearch import Elasticsearch, NotFoundError
from elasticsearch.exceptions import BadRequestError

from app.settings import settings
from common.logger import logger
from .model import SearchRequest, SearchResponse, SearchResult

# ---------------------------------------------------------------------------
# Multi-match field list with boost weights (spec section 3.3)
# ---------------------------------------------------------------------------
_SEARCH_FIELDS = [
    "full_name^5",
    "login^4",
    "email^4",
    "key^4",
    "summary^3",
    "title^3",
    "message^2",
    "description^2",
    "name^2",
    "project_name^2",
    "path^2",
    "entity_type^1",
    "source^1",
    "id^1",
    "branch_name^1",
]

# Highlight settings (spec section 3.3)
_HIGHLIGHT_FRAGMENT_SIZE = 150
_HIGHLIGHT_NUMBER_OF_FRAGMENTS = 1


def _build_client() -> Elasticsearch:
    """Build an Elasticsearch client from application settings."""
    if settings.ELASTIC_PASSWORD:
        return Elasticsearch(
            settings.ELASTICSEARCH_URL,
            basic_auth=("elastic", settings.ELASTIC_PASSWORD),
        )
    return Elasticsearch(settings.ELASTICSEARCH_URL)


def _derive_index(source: Optional[str], entity_type: Optional[str]) -> str:
    """Return the target index or alias for a search request.

    Uses the ``wba_all`` alias when no filters narrow the source/entity_type.
    Otherwise derives the specific index name so ES targets only the relevant
    shard.
    """
    if source and entity_type:
        return f"{source}_{entity_type.lower()}_index"
    if source:
        # Fan out across all indexes for this source via a pattern match.
        return f"{source}_*_index"
    if entity_type:
        # entity_type without source — query the alias with a filter (caller adds filter).
        return "wba_all"
    return "wba_all"


def _build_query_body(request: SearchRequest) -> Dict[str, Any]:
    """Build the full Elasticsearch request body for *request*."""
    must: List[Dict[str, Any]] = []
    filters: List[Dict[str, Any]] = []

    # --- Free-text ---
    if request.q:
        must.append({
            "multi_match": {
                "query": request.q,
                "fields": _SEARCH_FIELDS,
                "type": "best_fields",
            }
        })

    # --- Categorical filters ---
    if request.entity_type:
        filters.append({"term": {"entity_type": request.entity_type}})
    if request.source:
        filters.append({"term": {"source": request.source}})
    if request.status:
        filters.append({"term": {"status": request.status}})
    if request.priority:
        filters.append({"term": {"priority": request.priority}})

    # --- Date range filter ---
    date_range: Dict[str, str] = {}
    if request.date_from:
        date_range["gte"] = request.date_from.isoformat()
    if request.date_to:
        date_range["lte"] = request.date_to.isoformat()
    if date_range:
        filters.append({"range": {"event_time": date_range}})

    # --- Bool query ---
    if must:
        bool_clause: Dict[str, Any] = {"must": must}
    else:
        bool_clause = {"must": [{"match_all": {}}]}

    if filters:
        bool_clause["filter"] = filters

    # --- Sort (relevance when q present, event_time desc otherwise) ---
    sort: List[Any] = (
        ["_score"] if request.q else [{"event_time": {"order": "desc"}}]
    )

    # --- Pagination ---
    # ES default max_result_window is 10 000.  Cap the offset so we never
    # exceed it — any page beyond the window simply returns no results.
    _ES_MAX_RESULT_WINDOW = 10_000
    from_offset = min((request.page - 1) * request.page_size, _ES_MAX_RESULT_WINDOW)

    body: Dict[str, Any] = {
        "query": {"bool": bool_clause},
        "sort": sort,
        "from": from_offset,
        "size": request.page_size,
        "highlight": {
            "number_of_fragments": _HIGHLIGHT_NUMBER_OF_FRAGMENTS,
            "fragment_size": _HIGHLIGHT_FRAGMENT_SIZE,
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
            "fields": {"*": {}},
        },
    }

    return body


def _extract_highlight(raw_highlight: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return the best highlight fragment from the raw ES highlight map."""
    if not raw_highlight:
        return None
    # Take the first fragment from the first field that has highlights.
    for fragments in raw_highlight.values():
        if fragments:
            return fragments[0]
    return None


def _hit_to_result(hit: Dict[str, Any], full: bool) -> SearchResult:
    """Convert a raw Elasticsearch hit dict into a ``SearchResult``."""
    source: Dict[str, Any] = hit.get("_source", {})
    wba_id: str = source.get("wba_id") or hit.get("_id", "")
    highlight = _extract_highlight(hit.get("highlight"))

    result = SearchResult(
        wba_id=wba_id,
        score=hit.get("_score"),
        url=source.get("url"),
        event_time=source.get("event_time"),
        highlight=highlight,
    )

    if full:
        result.attributes = source

    return result


def search_in_graph(request: SearchRequest, graph_wba_ids: list[str]) -> SearchResponse:
    """Execute a search scoped to the specific wba_ids currently loaded in the graph.

    Unlike ``search()``, this function constrains the ES query to only the
    documents whose ``wba_id`` is in *graph_wba_ids*.  This ensures that:

    * Every loaded node is a candidate, regardless of how common the query term
      is across the full corpus (eliminates the top-N clipping problem).
    * The result ``size`` is always ``len(graph_wba_ids)`` — all matches are
      returned in a single request without pagination.

    Returns an empty response when Elasticsearch is disabled, *graph_wba_ids*
    is empty, or the index does not exist.

    Args:
        request:        A ``SearchRequest`` whose ``q`` is used for scoring.
                        ``page``, ``page_size``, and filter params are ignored —
                        the graph scope supersedes them.
        graph_wba_ids:  The list of ``wba_id`` values for all nodes currently
                        rendered in the graph.
    """
    if not graph_wba_ids:
        return SearchResponse(total=0, page=1, page_size=0, results=[])

    if not settings.ELASTICSEARCH_ENABLED:
        logger.debug("[Spotlight] Elasticsearch is disabled — returning empty response")
        return SearchResponse(total=0, page=1, page_size=0, results=[])

    client = _build_client()
    body = _build_query_body(request)

    # Override pagination — return all graph nodes in one shot.
    body["from"] = 0
    body["size"] = len(graph_wba_ids)

    # Constrain to the wba_ids currently in the graph.
    bool_clause = body["query"]["bool"]
    filters: List[Dict[str, Any]] = list(bool_clause.get("filter", []))
    filters.append({"terms": {"wba_id": graph_wba_ids}})
    bool_clause["filter"] = filters

    try:
        response = client.search(index="wba_all", body=body)
    except NotFoundError:
        logger.warning("[Spotlight] wba_all alias not found")
        return SearchResponse(total=0, page=1, page_size=0, results=[])
    except BadRequestError as exc:
        logger.warning("[Spotlight] Bad request from Elasticsearch: %s", exc)
        return SearchResponse(total=0, page=1, page_size=0, results=[])
    except Exception as exc:
        logger.exception("[Spotlight] Elasticsearch query failed: %s", exc)
        raise

    hits = response.get("hits", {})
    total_value = hits.get("total", {})
    total = total_value.get("value", 0) if isinstance(total_value, dict) else int(total_value)
    results: List[SearchResult] = [
        _hit_to_result(hit, False) for hit in hits.get("hits", [])
    ]

    return SearchResponse(total=total, page=1, page_size=len(graph_wba_ids), results=results)


def search(request: SearchRequest) -> SearchResponse:
    """Execute a search against Elasticsearch and return a ``SearchResponse``.

    Returns an empty response (total=0) when Elasticsearch is disabled or
    when the target index does not exist.
    """
    if not settings.ELASTICSEARCH_ENABLED:
        logger.debug("[Search] Elasticsearch is disabled — returning empty response")
        return SearchResponse(total=0, page=request.page, page_size=request.page_size, results=[])

    client = _build_client()
    index = _derive_index(request.source, request.entity_type)
    body = _build_query_body(request)

    try:
        response = client.search(index=index, body=body)
    except NotFoundError:
        logger.warning(f"[Search] Index not found: {index}")
        return SearchResponse(total=0, page=request.page, page_size=request.page_size, results=[])
    except BadRequestError as exc:
        logger.warning(f"[Search] Bad request from Elasticsearch (offset={from_offset}): {exc}")
        return SearchResponse(total=0, page=request.page, page_size=request.page_size, results=[])
    except Exception as exc:
        logger.exception(f"[Search] Elasticsearch query failed: {exc}")
        raise

    hits = response.get("hits", {})
    total_value = hits.get("total", {})
    total = total_value.get("value", 0) if isinstance(total_value, dict) else int(total_value)

    results: List[SearchResult] = [
        _hit_to_result(hit, request.full) for hit in hits.get("hits", [])
    ]

    return SearchResponse(
        total=total,
        page=request.page,
        page_size=request.page_size,
        results=results,
    )

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from connectors.producers.confluence.fetch_spaces import fetch_spaces
from connectors.producers.confluence.fetch_cql_results import fetch_cql_results
from connectors.producers.confluence.fetch_content_likes import fetch_content_likes
from connectors.producers.confluence.fetch_page_body import fetch_page_body
from connectors.producers.confluence.fetch_page_comments import fetch_page_comments
from connectors.producers.confluence.fetch_user_details import fetch_user_details
from connectors.producers.confluence.parse_body_for_relations import parse_body_for_relations
from connectors.producers.confluence.confluence_settings import get_max_results_per_page

def _normalize_space_key(key: str) -> str:
    return key.strip().upper()

def _build_recent_content_cql(
    since_date: datetime,
    include_spaces: Optional[Sequence[str]] = None,
    exclude_spaces: Optional[Sequence[str]] = None,
) -> str:
    date_str = since_date.strftime("%Y-%m-%d %H:%M")
    clauses = [f'(type=page OR type=blogpost)', f'lastModified >= "{date_str}"']

    include = [
        _normalize_space_key(space)
        for space in (include_spaces or [])
        if space and space.strip()
    ]
    exclude = [
        _normalize_space_key(space)
        for space in (exclude_spaces or [])
        if space and space.strip()
    ]

    if include:
        clauses.append(
            "space in (" + ", ".join(f'"{space}"' for space in include) + ")"
        )
    if exclude:
        clauses.append(
            "space not in (" + ", ".join(f'"{space}"' for space in exclude) + ")"
        )

    return " AND ".join(clauses) + " ORDER BY lastModified DESC"

async def get_spaces(confluence) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(fetch_spaces, confluence)

async def get_recent_content(
    confluence,
    since_date: datetime,
    limit: Optional[int] = None,
    include_spaces: Optional[Sequence[str]] = None,
    exclude_spaces: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    limit = limit if limit is not None else get_max_results_per_page()
    cql = _build_recent_content_cql(since_date, include_spaces, exclude_spaces)
    return await asyncio.to_thread(fetch_cql_results, confluence, cql, limit)

async def process_content_body(confluence, content_id: str) -> Tuple[Set[str], Set[str]]:
    body = await asyncio.to_thread(fetch_page_body, confluence, content_id)
    return await asyncio.to_thread(parse_body_for_relations, body)

async def get_comments(confluence, content_id: str, content_type: str = "page") -> List[Dict[str, Any]]:
    return await asyncio.to_thread(fetch_page_comments, confluence, content_id, content_type)

async def get_likes(confluence, content_id: str, content_type: str = "page") -> List[Dict[str, Any]]:
    return await asyncio.to_thread(fetch_content_likes, confluence, content_id, content_type)

async def get_user_details_async(confluence, account_id: str) -> Dict[str, Any]:
    return await asyncio.to_thread(fetch_user_details, confluence, account_id)

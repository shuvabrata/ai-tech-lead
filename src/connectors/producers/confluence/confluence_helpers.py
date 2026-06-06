import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from common.logger import logger
from connectors.producers.confluence.fetch_spaces import fetch_spaces
from connectors.producers.confluence.fetch_cql_results import fetch_cql_results
from connectors.producers.confluence.fetch_content_likes import fetch_content_likes
from connectors.producers.confluence.fetch_page_comments import fetch_page_comments
from connectors.producers.confluence.fetch_user_details import fetch_user_details

def _normalize_space_key(key: str) -> str:
    return key.strip().upper()

def _build_recent_content_cql(
    since_date: datetime,
    include_spaces: Optional[Sequence[str]] = None,
    exclude_spaces: Optional[Sequence[str]] = None,
) -> str:
    date_str = since_date.strftime("%Y-%m-%d %H:%M")
    clauses = ['(type=page OR type=blogpost)', f'lastModified >= "{date_str}"']

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

    # Sort by id ASC (stable immutable field) instead of lastModified DESC.
    # Confluence Cloud uses offset-based CQL pagination; sorting by a mutable
    # field like lastModified causes pages to shift position between batches
    # when other pages are modified during the scan — leading to duplicates and
    # silently skipped pages. id ASC is stable for the full duration of the scan.
    return " AND ".join(clauses) + " ORDER BY id ASC"

async def get_spaces(confluence) -> List[Dict[str, Any]]:
    logger.debug("Dispatching Confluence space fetch to worker thread")
    spaces = await asyncio.to_thread(fetch_spaces, confluence)
    logger.info("Helper fetched %d spaces from Confluence", len(spaces))
    return spaces

async def get_recent_content(
    confluence,
    since_date: datetime,
    include_spaces: Optional[Sequence[str]] = None,
    exclude_spaces: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    cql = _build_recent_content_cql(since_date, include_spaces, exclude_spaces)
    logger.debug("Dispatching recent content fetch to worker thread with CQL=%s", cql)
    results = await asyncio.to_thread(fetch_cql_results, confluence, cql)
    logger.info("Helper fetched %d recently changed content items", len(results))
    return results

async def get_comments(confluence, content_id: str, content_type: str = "page") -> List[Dict[str, Any]]:
    logger.debug(
        "Dispatching comment fetch to worker thread for content_type=%s content_id=%s",
        content_type,
        content_id,
    )
    comments = await asyncio.to_thread(fetch_page_comments, confluence, content_id, content_type)
    logger.info(
        "Helper fetched %d comments for content_type=%s content_id=%s",
        len(comments),
        content_type,
        content_id,
    )
    return comments

async def get_likes(confluence, content_id: str, content_type: str = "page") -> List[Dict[str, Any]]:
    logger.debug(
        "Dispatching like fetch to worker thread for content_type=%s content_id=%s",
        content_type,
        content_id,
    )
    likes = await asyncio.to_thread(fetch_content_likes, confluence, content_id, content_type)
    logger.info(
        "Helper fetched %d likes for content_type=%s content_id=%s",
        len(likes),
        content_type,
        content_id,
    )
    return likes

async def get_user_details_async(confluence, account_id: str) -> Dict[str, Any]:
    logger.debug("Dispatching user detail fetch to worker thread for account_id=%s", account_id)
    user_details = await asyncio.to_thread(fetch_user_details, confluence, account_id)
    logger.info(
        "Helper fetched user details for account_id=%s (found=%s)",
        account_id,
        bool(user_details),
    )
    return user_details

from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

from atlassian import Confluence
from common.logger import logger


def _next_cursor(next_link: str) -> str | None:
    parsed = urlparse(next_link)
    cursor_values = parse_qs(parsed.query).get("cursor", [])
    return cursor_values[0] if cursor_values else None


def fetch_content_likes(
    confluence: Confluence,
    content_id: str,
    content_type: str = "page",
) -> List[Dict[str, Any]]:
    """Fetch the current users who like a page or blogpost."""
    content_type = (content_type or "page").lower()
    if content_type not in {"page", "blogpost"}:
        return []

    page_size = 25

    collection = "pages" if content_type == "page" else "blogposts"
    path = f"/api/v2/{collection}/{content_id}/likes/users"
    results: List[Dict[str, Any]] = []
    cursor: str | None = None

    logger.debug(f"Fetching likes for {content_type} with ID: {content_id} using page size {page_size}")

    while True:
        params = {"limit": page_size}
        if cursor:
            params["cursor"] = cursor

        logger.debug(f"Calling Confluence API: {path} with params: {params}")
        response = confluence.get(path, params=params)
        page_results = response.get("results", [])
        results.extend(page_results)
        
        logger.debug(f"Retrieved {len(page_results)} likes in this page. Total so far: {len(results)}")

        next_link = response.get("_links", {}).get("next")
        if not next_link:
            logger.debug(f"No next link found. Finished fetching likes for {content_id}")
            break

        cursor = _next_cursor(next_link)
        if not cursor:
            logger.debug(f"Next link found but no cursor. Finished fetching likes for {content_id}")
            break
    
    logger.info(f"Total likes fetched for {content_type} with ID {content_id}: {len(results)}")
    return results

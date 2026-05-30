from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from atlassian import Confluence

from connectors.producers.confluence.confluence_settings import get_max_results_per_page


def _next_cursor(next_link: str) -> str | None:
    parsed = urlparse(next_link)
    cursor_values = parse_qs(parsed.query).get("cursor", [])
    return cursor_values[0] if cursor_values else None


def fetch_content_likes(
    confluence: Confluence,
    content_id: str,
    content_type: str = "page",
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch the current users who like a page or blogpost."""
    content_type = (content_type or "page").lower()
    if content_type not in {"page", "blogpost"}:
        return []

    limit = limit if limit is not None else get_max_results_per_page()

    collection = "pages" if content_type == "page" else "blogposts"
    path = f"/api/v2/{collection}/{content_id}/likes/users"
    results: List[Dict[str, Any]] = []
    cursor: str | None = None

    while True:
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor

        response = confluence.get(path, params=params)
        results.extend(response.get("results", []))

        next_link = response.get("_links", {}).get("next")
        if not next_link:
            break

        cursor = _next_cursor(next_link)
        if not cursor:
            break

    return results

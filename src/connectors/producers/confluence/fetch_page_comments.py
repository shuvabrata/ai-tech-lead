from typing import Any, Dict, List
from atlassian import Confluence
from common.logger import logger

def fetch_page_comments(confluence: Confluence, page_id: str, content_type: str = "page") -> List[Dict[str, Any]]:
    """Fetch comments for a page/blogpost."""
    logger.debug("Fetching comments for %s content_id=%s", content_type, page_id)
    try:
        response = confluence.get_page_comments(page_id, expand='body.storage,history')
        results = response.get('results', [])
        logger.debug(
            "Fetched %d comments for %s content_id=%s",
            len(results),
            content_type,
            page_id,
        )
        return results
    except Exception as exc:
        logger.warning(
            "Failed to fetch comments for %s content_id=%s: %s",
            content_type,
            page_id,
            exc,
        )
        return []

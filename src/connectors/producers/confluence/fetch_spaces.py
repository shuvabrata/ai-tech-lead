from typing import Any, Dict, List
from atlassian import Confluence
from common.logger import logger
from connectors.producers.github.retry_with_backoff import retry_with_backoff

def fetch_spaces(confluence: Confluence) -> List[Dict[str, Any]]:
    """Fetch all spaces from Confluence using pagination."""
    page_limit = 100
    start = 0
    all_spaces: List[Dict[str, Any]] = []

    logger.info("Starting to fetch all spaces from Confluence")

    while True:
        logger.debug(f"Fetching spaces with start={start} and limit={page_limit}")
        # Retry rate-limit (HTTP 429) and transient network errors with
        # exponential backoff so a momentary connectivity loss does not abort
        # the space fetch.
        spaces_response = retry_with_backoff(
            lambda: confluence.get_all_spaces(start=start, limit=page_limit)
        )
        results = spaces_response.get('results', [])
        fetched_count = len(results)
        all_spaces.extend(results)

        logger.debug(f"Fetched {fetched_count} spaces in current page")

        if fetched_count < page_limit:
            break
        
        start += page_limit

    logger.info(f"Finished fetching spaces. Total spaces fetched: {len(all_spaces)}")
    return all_spaces

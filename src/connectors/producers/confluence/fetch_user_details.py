from typing import Any, Dict
from atlassian import Confluence
from common.logger import logger
from connectors.producers.github.retry_with_backoff import retry_with_backoff

def fetch_user_details(confluence: Confluence, account_id: str) -> Dict[str, Any]:
    """Fetch user details from Confluence REST API."""
    logger.info("Fetching user details for account_id=%s", account_id)
    try:
        # Retry rate-limit (HTTP 429) and transient network errors with
        # exponential backoff so a momentary connectivity loss does not drop
        # a user's details.
        response = retry_with_backoff(
            lambda: confluence.get(f"/rest/api/user?accountId={account_id}")
        )
        logger.debug("Fetched user details for account_id=%s", account_id)
        return response
    except Exception as exc:
        logger.warning("Failed to fetch user details for account_id=%s: %s", account_id, exc)
        return {}

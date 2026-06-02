from atlassian import Confluence
from common.logger import logger

def fetch_page_body(confluence: Confluence, page_id: str) -> str:
    """Fetch the storage format body of a page/blogpost."""
    logger.debug("Fetching page body for page_id=%s", page_id)
    page = confluence.get_page_by_id(page_id, expand='body.storage')
    body = page.get('body', {}).get('storage', {}).get('value', '')
    logger.debug("Fetched page body for page_id=%s (length=%d)", page_id, len(body))
    return body

from typing import Any
from atlassian import Confluence

def fetch_page_body(confluence: Confluence, page_id: str) -> str:
    """Fetch the storage format body of a page/blogpost."""
    print(f"  [Network] Fetching body for page ID: {page_id}")
    page = confluence.get_page_by_id(page_id, expand='body.storage')
    return page.get('body', {}).get('storage', {}).get('value', '')

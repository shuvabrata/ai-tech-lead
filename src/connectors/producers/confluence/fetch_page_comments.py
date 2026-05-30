from typing import Any, Dict, List
from atlassian import Confluence

def fetch_page_comments(confluence: Confluence, page_id: str) -> List[Dict[str, Any]]:
    """Fetch comments for a page/blogpost."""
    print(f"  [Network] Fetching comments for page ID: {page_id}")
    try:
        response = confluence.get_page_comments(page_id, expand='body.storage,history')
        return response.get('results', [])
    except Exception as e:
        print(f"    ❌ Failed to fetch comments: {e}")
        return []

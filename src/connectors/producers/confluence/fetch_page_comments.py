from typing import Any, Dict, List
from atlassian import Confluence

def fetch_page_comments(confluence: Confluence, page_id: str, content_type: str = "page") -> List[Dict[str, Any]]:
    """Fetch comments for a page/blogpost."""
    try:
        response = confluence.get_page_comments(page_id, expand='body.storage,history')
        return response.get('results', [])
    except Exception as e:
        return []

from typing import Any, Dict
from atlassian import Confluence

def fetch_user_details(confluence: Confluence, account_id: str) -> Dict[str, Any]:
    """Fetch user details from Confluence REST API."""
    try:
        response = confluence.get(f"/rest/api/user?accountId={account_id}")
        return response
    except Exception as e:
        return {}

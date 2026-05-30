from typing import Any, Dict
from atlassian import Confluence

def fetch_user_details(confluence: Confluence, account_id: str) -> Dict[str, Any]:
    """Fetch user details from Confluence REST API."""
    print(f"  [Network] Fetching user details for account: {account_id}")
    try:
        response = confluence.get(f"/rest/api/user?accountId={account_id}")
        return response
    except Exception as e:
        print(f"    ❌ Failed to fetch user details: {e}")
        return {}

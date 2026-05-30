from typing import Any, Dict, List
from atlassian import Confluence

def fetch_spaces(confluence: Confluence, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch spaces from Confluence."""
    print(f"  [Network] Fetching spaces (limit={limit})...")
    spaces_response = confluence.get_all_spaces(start=0, limit=limit)
    return spaces_response.get('results', [])

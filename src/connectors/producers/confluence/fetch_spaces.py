from typing import Any, Dict, List, Optional
from atlassian import Confluence

from connectors.producers.confluence.confluence_settings import get_max_results_per_page


def fetch_spaces(confluence: Confluence, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch spaces from Confluence."""
    limit = limit if limit is not None else get_max_results_per_page()
    spaces_response = confluence.get_all_spaces(start=0, limit=limit)
    return spaces_response.get('results', [])

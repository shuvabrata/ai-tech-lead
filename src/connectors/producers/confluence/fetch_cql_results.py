from typing import Any, Dict, List, Optional
from atlassian import Confluence

from connectors.producers.confluence.confluence_settings import get_max_results_per_page


def fetch_cql_results(confluence: Confluence, cql: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch results using Confluence Query Language (CQL)."""
    limit = limit if limit is not None else get_max_results_per_page()
    response = confluence.cql(
        cql,
        limit=limit,
        expand="content.version,content.history,content.space,content.ancestors",
    )
    return response.get('results', [])

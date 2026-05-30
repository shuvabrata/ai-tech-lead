from typing import Any, Dict, List
from atlassian import Confluence

def fetch_cql_results(confluence: Confluence, cql: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch results using Confluence Query Language (CQL)."""
    print(f"  [Network] Executing CQL: {cql}")
    response = confluence.cql(cql, limit=limit, expand="content.version,content.history")
    return response.get('results', [])

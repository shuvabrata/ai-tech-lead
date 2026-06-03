from typing import Any, Dict, List
from atlassian import Confluence
from common.logger import logger


def fetch_cql_results(confluence: Confluence, cql: str) -> List[Dict[str, Any]]:
    """Fetch results using Confluence Query Language (CQL)."""
    all_results = []
    start = 0
    page_size = 25

    logger.info(f"Starting CQL query: {cql}")
    while True:
        response = confluence.cql(
            cql,
            start=start,
            limit=page_size,
            expand="content.version,content.history,content.space,content.ancestors",
        )
        results = response.get('results', [])
        if not results:
            break
        
        logger.debug(f"Fetched {len(results)} results for CQL: {cql} (start={start})")
        all_results.extend(results)

        # If the number of results returned is less than the page size, we've reached the end
        if len(results) < page_size:
            break
            
        start += page_size

    logger.info(f"Fetched {len(all_results)} results for CQL: {cql}")
    return all_results

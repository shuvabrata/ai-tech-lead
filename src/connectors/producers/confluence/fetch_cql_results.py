from typing import Any, Dict, List
from atlassian import Confluence
from common.logger import logger


def fetch_cql_results(confluence: Confluence, cql: str) -> List[Dict[str, Any]]:
    """Fetch results using Confluence Query Language (CQL)."""
    all_results = []
    start = 0
    page_size = 25
    total_size: int | None = None

    logger.info(f"Starting CQL query: {cql}")
    while True:
        response = confluence.cql(
            cql,
            start=start,
            limit=page_size,
            expand="content.version,content.history,content.space,content.ancestors",
        )

        # Capture the authoritative total on the first response.
        # Confluence Cloud can keep returning results past the real total when
        # paginating by offset alone (the len < page_size guard is unreliable).
        if total_size is None:
            total_size = int(response.get("totalSize", 0))
            logger.info(f"CQL total_size={total_size} for query: {cql}")
            if total_size == 0:
                break

        results = response.get('results', [])
        if not results:
            break

        logger.debug(f"Fetched {len(results)} results for CQL: {cql} (start={start})")
        all_results.extend(results)

        start += len(results)
        if start >= total_size:
            break

    logger.info(f"Fetched {len(all_results)} results for CQL: {cql}")
    return all_results

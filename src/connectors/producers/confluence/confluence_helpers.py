import asyncio
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

from connectors.producers.confluence.fetch_spaces import fetch_spaces
from connectors.producers.confluence.fetch_cql_results import fetch_cql_results
from connectors.producers.confluence.fetch_page_body import fetch_page_body
from connectors.producers.confluence.fetch_page_comments import fetch_page_comments
from connectors.producers.confluence.fetch_user_details import fetch_user_details
from connectors.producers.confluence.parse_body_for_relations import parse_body_for_relations

async def get_spaces(confluence, limit: int = 50) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(fetch_spaces, confluence, limit)

async def get_recent_content(confluence, since_date: datetime, limit: int = 10) -> List[Dict[str, Any]]:
    date_str = since_date.strftime("%Y-%m-%d")
    cql = f'(type=page OR type=blogpost) AND lastModified >= "{date_str}" ORDER BY lastModified DESC'
    return await asyncio.to_thread(fetch_cql_results, confluence, cql, limit)

async def process_content_body(confluence, content_id: str) -> Tuple[Set[str], Set[str]]:
    body = await asyncio.to_thread(fetch_page_body, confluence, content_id)
    return await asyncio.to_thread(parse_body_for_relations, body)

async def get_comments(confluence, content_id: str) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(fetch_page_comments, confluence, content_id)

async def get_user_details_async(confluence, account_id: str) -> Dict[str, Any]:
    return await asyncio.to_thread(fetch_user_details, confluence, account_id)

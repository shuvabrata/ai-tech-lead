from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Set

from common.activity_signal.models import ActivitySignal
from common.logger import logger

from connectors.producers.fetch_github import fetch_pull_requests_direct, resolve_prs_since_date
from connectors.producers.github.process_single_pr import process_single_pr


async def process_prs(
    repo: Any,
    repo_data: Dict[str, Any],
    repo_owner: str,
    full_name: str,
    last_synced_at: Optional[datetime],
    published: Dict[str, int],
    seen_commits: Set[str],
    published_persons: Set[str],
    pub_callback: Callable[[Optional[ActivitySignal]], Awaitable[None]],
) -> None:
    """Fetch pull requests for *repo* and publish PullRequest and related signals."""
    pr_since = resolve_prs_since_date(last_synced_at)
    logger.info("Fetching pull requests for '%s'...", full_name)
    prs_raw = await asyncio.to_thread(fetch_pull_requests_direct, repo)

    for pr in prs_raw:
        try:
            should_stop = await process_single_pr(
                pr,
                pr_since,
                repo=repo,
                repo_data=repo_data,
                repo_owner=repo_owner,
                seen_commits=seen_commits,
                published_persons=published_persons,
                _pub=pub_callback,
            )
            if should_stop:
                break
        except Exception as exc:
            logger.warning("PR skipped: %s", exc)

    logger.info("PRs done (%d) for '%s'", published.get("PullRequest", 0), full_name)

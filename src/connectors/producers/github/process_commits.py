from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from common.logger import logger

from common.activity_signal.models import ActivitySignal
from connectors.producers.fetch_github import fetch_commits, resolve_commits_since_date
from connectors.producers.github.process_single_commit import process_single_commit


async def process_commits(
    repo: Any,
    repo_owner: str,
    full_name: str,
    last_synced_at: Optional[datetime],
    published: Dict[str, int],
    pub_callback: Callable[[Optional[ActivitySignal]], Awaitable[None]],
) -> tuple[set[str], set[str]]:
    """Fetch and process commits for a repo.

    Returns:
        (seen_commits, published_persons) — both sets are populated during processing
        and consumed by downstream processors (e.g. process_prs, process_teams).
    """
    since = resolve_commits_since_date(last_synced_at)
    logger.info("Fetching commits for '%s' since %s...", full_name, since.date())
    commits_raw = await asyncio.to_thread(fetch_commits, repo, since)
    logger.info(f"Number of commits fetched for {full_name} = {len(commits_raw)}")

    published_persons: set[str] = set()
    seen_commits: set[str] = set()

    semaphore = asyncio.Semaphore(3)  # Capped concurrency to prevent API rate limits

    if commits_raw:
        await asyncio.gather(*(
            process_single_commit(
                commit=c,
                semaphore=semaphore,
                repo=repo,
                repo_owner=repo_owner,
                published_persons=published_persons,
                seen_commits=seen_commits,
                pub_callback=pub_callback,
            )
            for c in commits_raw
        ))

    logger.info("Commits done (%d) for '%s'", published.get("Commit", 0), full_name)
    return seen_commits, published_persons

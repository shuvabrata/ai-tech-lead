from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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
            pr_updated = getattr(pr, "updated_at", None)
            logger.debug(f"PR # {pr.number} updated at {pr_updated} (since={pr_since})")
            if pr_updated and pr_updated.replace(tzinfo=timezone.utc) < pr_since:
                logger.debug("PR #%s skipped (updated before since=%s)", pr.number, pr_since.date())
                # Since PRs are processed newest-first, we can stop the entire loop
                # once we hit a PR older than our cutoff, saving massive API pagination!
                logger.info(
                    "Stopping PR fetch loop for '%s' since remaining PRs will be older than %s",
                    full_name,
                    pr_since.date(),
                )
                break

            await process_single_pr(
                pr,
                repo=repo,
                repo_data=repo_data,
                repo_owner=repo_owner,
                seen_commits=seen_commits,
                published_persons=published_persons,
                _pub=pub_callback,
            )
        except Exception as exc:
            logger.warning("PR skipped: %s", exc)

    logger.info("PRs done (%d) for '%s'", published.get("PullRequest", 0), full_name)

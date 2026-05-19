from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

from common.logger import logger

from common.activity_signal.models import ActivitySignal
from connectors.producers.fetch_github import fetch_branches
from connectors.producers.map_github import map_branch
from connectors.producers.github.build_branch_signal import build_branch_signal


async def process_branches(
    repo: Any,
    repo_owner: str,
    repo_data: Dict[str, Any],
    full_name: str,
    published: Dict[str, int],
    pub_callback: Callable[[Optional[ActivitySignal]], Awaitable[None]],
) -> Optional[Dict[str, Any]]:
    """Fetch and process branches for a repo.

    Returns:
        The default branch data dict, or None if the default branch was not found.
    """
    default_branch = repo.default_branch or "main"
    logger.info("Fetching branches for '%s'...", full_name)
    branches_raw = await asyncio.to_thread(fetch_branches, repo)
    branch_map: Dict[str, Dict[str, Any]] = {}  # branch_name -> branch_data

    branch_semaphore = asyncio.Semaphore(3)

    async def process_single_branch(branch: Any) -> None:
        async with branch_semaphore:
            try:
                b_data = await asyncio.to_thread(map_branch, repo.name, default_branch, branch, repo_owner)
                branch_map[b_data["name"]] = b_data
                logger.debug("Branch '%s' mapped (is_default=%s)", b_data["name"], b_data.get("is_default"))
                b_sig = build_branch_signal(b_data, repo_data)
                await pub_callback(b_sig)
            except Exception as exc:
                logger.warning("Branch '%s' skipped: %s", getattr(branch, "name", "?"), exc)

    if branches_raw:
        await asyncio.gather(*(process_single_branch(b) for b in branches_raw))

    logger.info("Branches done (%d) for '%s'", published.get("Branch", 0), full_name)
    return branch_map.get(default_branch)

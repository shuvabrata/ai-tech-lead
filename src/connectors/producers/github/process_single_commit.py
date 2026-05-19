from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

from common.logger import logger

from common.activity_signal.models import ActivitySignal
from connectors.producers.map_github import fetch_github_user, map_commit
from connectors.producers.github.build_commit_signal import build_commit_signal
from connectors.producers.github.build_person_signal import build_person_signal


async def process_single_commit(
    commit: Any,
    semaphore: asyncio.Semaphore,
    repo: Any,
    repo_owner: str,
    default_branch_data: Optional[Dict[str, Any]],
    published_persons: set[str],
    seen_commits: set[str],
    pub_callback: Callable[[Optional[ActivitySignal]], Awaitable[None]],
) -> None:
    """Process a single commit: emit Person and Commit ActivitySignals."""
    async with semaphore:
        try:
            # Isolate blocking PyGithub lazy-loads in a background thread.
            # fetch_github_user handles both NamedUser (triggers GET /users/{login})
            # and GitAuthor (reads git metadata directly).
            def extract_data() -> tuple[Dict[str, Any], Dict[str, Any]]:
                a_data = fetch_github_user(commit.author or commit.commit.author)
                c_data = map_commit(repo.name, commit, repo_owner)
                return a_data, c_data

            author_data, commit_data = await asyncio.to_thread(extract_data)

            # Back on the async event loop (thread-safe updates)
            login = author_data.get("login") or author_data.get("name", "unknown")
            if login not in published_persons:
                published_persons.add(login)
                logger.debug(
                    "[person:commit_author] login=%r  name=%r  email=%r  sha=%s",
                    login,
                    author_data.get("name"),
                    author_data.get("email"),
                    commit_data.get("sha", "?")[:8],
                )
                await pub_callback(build_person_signal(author_data))

            sha_short = commit_data.get("sha", "?")[:8]
            seen_commits.add(commit_data.get("sha"))
            logger.debug("Commit %s by '%s' processed", sha_short, login)

            await pub_callback(build_commit_signal(commit_data, author_data, default_branch_data))

        except Exception as exc:
            logger.warning("Commit skipped: %s", exc)

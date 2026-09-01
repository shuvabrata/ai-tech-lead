from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

from common.logger import logger

from common.activity_signal.models import ActivitySignal
from connectors.producers.github.map_github import fetch_github_user, map_commit, map_commit_files
from connectors.producers.github.build_commit_signal import build_commit_signal
from connectors.producers.github.build_file_signal import build_file_signal
from connectors.producers.github.build_person_signal import build_person_signal
from connectors.producers.github.retry_with_backoff import (
    WbaRetryTimeoutError,
    retry_with_backoff,
)


def _extract_commit_data(
    commit: Any,
    repo: Any,
    repo_owner: str,
) -> tuple[Dict[str, Any], Dict[str, Any], list[Dict[str, Any]]]:
    """Extract author, commit, and file data for a single commit.

    All three steps touch lazy PyGithub attributes that trigger network calls
    on access (``fetch_github_user`` → GET /users/{login}, ``map_commit`` →
    commit.stats, ``commit.files``). This helper is designed to be wrapped in
    ``retry_with_backoff`` so a transient network blip retries the whole unit
    instead of dropping the commit.
    """
    a_data = fetch_github_user(commit.author or commit.commit.author)
    c_data = map_commit(repo.name, commit, repo_owner)
    files = list(commit.files)
    f_data = map_commit_files(files)
    return a_data, c_data, f_data


async def process_single_commit(
    commit: Any,
    semaphore: asyncio.Semaphore,
    repo: Any,
    repo_owner: str,
    published_persons: set[str],
    seen_commits: set[str],
    pub_callback: Callable[[Optional[ActivitySignal]], Awaitable[None]],
) -> None:
    """Process a single commit: emit Person, Commit, and File ActivitySignals."""
    async with semaphore:
        try:
            # Isolate blocking PyGithub lazy-loads in a background thread.
            # fetch_github_user handles both NamedUser (triggers GET /users/{login})
            # and GitAuthor (reads git metadata directly).
            #
            # The whole extract_data body is wrapped in retry_with_backoff so
            # ALL lazy PyGithub loads for this commit (author, commit.stats via
            # map_commit, and commit.files) retry as a single unit. Previously
            # only commit.files was wrapped; commit.stats (accessed inside
            # map_commit) was NOT, so a transient network blip there dropped
            # the entire commit with no retry.
            def extract_data() -> tuple[Dict[str, Any], Dict[str, Any], list[Dict[str, Any]]]:
                return retry_with_backoff(
                    lambda: _extract_commit_data(commit, repo, repo_owner)
                )

            author_data, commit_data, file_data_list = await asyncio.to_thread(extract_data)

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

            branch_name = repo.default_branch or "main" # this does not cause a new API call since it's already loaded in the repo object
            await pub_callback(build_commit_signal(commit_data, author_data, repo_name=repo.name, branch_name=branch_name))

            # Emit one File signal per file changed in this commit
            repo_data = {"name": repo.name, "owner": repo_owner}
            logger.info("Commit %s touches %d file(s)", sha_short, len(file_data_list))
            for file_data in file_data_list:
                await pub_callback(build_file_signal(file_data, commit_data, repo_data))

        except WbaRetryTimeoutError:
            # A retry-budget exhaustion means the repo is incomplete — propagate
            # so the config-level handler skips this repo's cursor and retries
            # it on the next scan.
            raise
        except Exception as exc:
            logger.warning(
                "Commit skipped: type=%s exception=%r sha=%s",
                type(exc).__name__,
                exc,
                getattr(commit, "sha", "?")[:12],
                exc_info=False,
            )

"""Pure fetch functions for the GitHub connector.

All GitHub API I/O is isolated here. Functions return raw PyGithub objects or
plain lists so that callers (process_* orchestrators and handlers) are decoupled
from the API surface. Every call goes through ``retry_with_backoff`` for rate-limit
resilience.

Phase 3: These utilities replace inline API calls in the legacy ``process_*`` and
``new_*_handler`` modules. Phase 4 producers will import from this module to reuse
the same fetch logic without touching the database.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from github import GithubException

from connectors.commons.logger import logger
from connectors.modules.github.retry_with_backoff import retry_with_backoff


# ---------------------------------------------------------------------------
# Repository-level fetchers
# ---------------------------------------------------------------------------


def fetch_repo_topics(repo: Any) -> List[str]:
    """Fetch the topic list for a repository.

    Args:
        repo: PyGithub Repository object.

    Returns:
        List of topic strings (may be empty).
    """
    return retry_with_backoff(repo.get_topics)


# ---------------------------------------------------------------------------
# Branch fetchers
# ---------------------------------------------------------------------------


def fetch_branches(repo: Any) -> List[Any]:
    """Fetch all branches for a repository.

    Args:
        repo: PyGithub Repository object.

    Returns:
        List of PyGithub Branch objects.
    """
    return retry_with_backoff(lambda: list(repo.get_branches()))


# ---------------------------------------------------------------------------
# Commit fetchers
# ---------------------------------------------------------------------------


def fetch_commits(repo: Any, since_date: datetime) -> List[Any]:
    """Fetch commits on the default branch since *since_date*.

    Args:
        repo: PyGithub Repository object.
        since_date: Fetch commits updated at or after this datetime.

    Returns:
        List of PyGithub Commit objects (full pagination resolved).
    """
    return retry_with_backoff(
        lambda: list(repo.get_commits(sha=repo.default_branch, since=since_date))
    )


def fetch_commit_files(commit: Any) -> List[Any]:
    """Fetch the file list for a single commit.

    Args:
        commit: PyGithub Commit object.

    Returns:
        List of PyGithub File objects.
    """
    return retry_with_backoff(lambda: list(commit.files))


# ---------------------------------------------------------------------------
# Pull request fetchers
# ---------------------------------------------------------------------------


def fetch_pull_requests_search(
    github_obj: Any,
    repo_full_name: str,
    since_date: datetime,
) -> List[Any]:
    """Fetch closed PRs via the GitHub Search API and convert to PR objects.

    Uses the Search API which is more efficient for incremental syncs but is
    subject to a separate rate limit (30 requests/min for authenticated users).

    Args:
        github_obj: Authenticated PyGithub ``Github`` client instance.
        repo_full_name: Repository full name (e.g. ``"owner/repo"``).
        since_date: Lower bound for ``updated_at`` filtering.

    Returns:
        List of PyGithub PullRequest objects (issues converted via
        ``as_pull_request()``).
    """
    query = (
        f"repo:{repo_full_name} is:pr is:closed"
        f" updated:>={since_date.date()}"
    )

    def _search() -> List[Any]:
        try:
            return list(github_obj.search_issues(query=query, sort="updated", order="desc"))
        except GithubException as exc:
            logger.warning(f"    GitHub Search API error: {exc}")
            return []

    raw_issues = retry_with_backoff(_search)

    converted: List[Any] = []
    for index, issue in enumerate(raw_issues, start=1):
        logger.debug(
            f"[fetch_pull_requests_search] Issue {index}: "
            f"pull_request={bool(issue.pull_request)} number={getattr(issue, 'number', None)}"
        )
        if issue.pull_request:
            converted.append(issue.as_pull_request())

    return converted


def fetch_pull_requests_direct(repo_obj: Any) -> List[Any]:
    """Fetch closed PRs directly from the repository endpoint.

    Args:
        repo_obj: PyGithub Repository object.

    Returns:
        List of PyGithub PullRequest objects.
    """
    return retry_with_backoff(
        lambda: list(repo_obj.get_pulls(state="closed", sort="updated", direction="desc"))
    )


def fetch_pr_reviews(pr: Any) -> List[Any]:
    """Fetch all review objects for a pull request.

    Args:
        pr: PyGithub PullRequest object.

    Returns:
        List of PyGithub PullRequestReview objects.
    """
    return retry_with_backoff(lambda: list(pr.get_reviews()))


def fetch_pr_commits(pr: Any) -> List[Any]:
    """Fetch all commit objects associated with a pull request.

    Args:
        pr: PyGithub PullRequest object.

    Returns:
        List of PyGithub Commit objects.
    """
    return retry_with_backoff(lambda: list(pr.get_commits()))


def fetch_external_branch_details(head_ref: Any) -> Optional[dict]:
    """Fetch last-commit details for an external (fork) branch.

    Returns ``None`` when the fork repo has been deleted. Returns a dict with
    ``sha``, ``timestamp``, and ``is_protected`` when the branch is accessible.

    Args:
        head_ref: PyGithub ``PullRequestPart`` (``pr.head``).

    Returns:
        Dict with branch details, or ``None`` if the fork is gone.
    """
    if head_ref.repo is None:
        return None

    fork_repo = head_ref.repo
    branch_name = head_ref.ref

    try:
        fork_branch = retry_with_backoff(lambda: fork_repo.get_branch(branch_name))
        last_commit = fork_branch.commit
        return {
            "sha": last_commit.sha,
            "timestamp": (
                last_commit.commit.author.date.isoformat()
                if last_commit.commit.author.date
                else datetime.now().isoformat()
            ),
            "is_protected": fork_branch.protected,
        }
    except Exception as exc:  # branch may have been deleted from the fork
        logger.debug(f"  Could not fetch fork branch '{branch_name}': {exc}")
        sha = head_ref.sha if hasattr(head_ref, "sha") else "unknown"
        return {
            "sha": sha,
            "timestamp": datetime.now().isoformat(),
            "is_protected": False,
        }


# ---------------------------------------------------------------------------
# Sync-window helpers (thin wrappers kept here for co-location with fetchers)
# ---------------------------------------------------------------------------


def resolve_commits_since_date(last_synced_at: Optional[datetime]) -> datetime:
    """Return the *since* date to use when fetching commits.

    Args:
        last_synced_at: Last successful sync timestamp, or ``None`` for first run.

    Returns:
        ``last_synced_at`` for incremental syncs; a rolling window based on the
        ``COMMIT_DAYS_LIMIT`` env var (default 60 days) for first-time syncs.
    """
    if last_synced_at:
        return last_synced_at
    commit_days_limit = int(os.getenv("COMMIT_DAYS_LIMIT", "60"))
    return datetime.now() - timedelta(days=commit_days_limit)


def resolve_prs_since_date(last_synced_at: Optional[datetime]) -> datetime:
    """Return the *since* date to use when fetching pull requests.

    Args:
        last_synced_at: Last successful sync timestamp, or ``None`` for first run.

    Returns:
        ``last_synced_at`` (UTC-aware) for incremental syncs; a rolling window
        based on the ``PULL_REQUEST_DAYS_LIMIT`` env var (default 60 days) for
        first-time syncs.
    """
    if last_synced_at:
        return last_synced_at if last_synced_at.tzinfo else last_synced_at.replace(tzinfo=timezone.utc)
    pr_days_limit = int(os.getenv("PULL_REQUEST_DAYS_LIMIT", "60"))
    return datetime.now(timezone.utc) - timedelta(days=pr_days_limit)

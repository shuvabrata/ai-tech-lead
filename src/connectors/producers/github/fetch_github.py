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
from typing import Any, Iterable, List, Optional

from github import GithubException

from common.logger import logger
from connectors.producers.github.retry_with_backoff import (
    WbaRetryTimeoutError,
    retry_with_backoff,
)


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
    # Materialize inside the retry: repo.get_topics() returns a lazy
    # PaginatedList whose network I/O happens on iteration, so the retry must
    # wrap the list(). Note get_topics is a method — call it with ().
    return retry_with_backoff(lambda: list(repo.get_topics()))


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
    branch_sha = repo.default_branch or "main"

    def _get_commits() -> List[Any]:
        try:
            return list(repo.get_commits(sha=branch_sha, since=since_date))
        except GithubException as exc:
            if exc.status == 409:
                logger.info("Repository '%s' is empty, skipping commits.", getattr(repo, "full_name", "?"))
                return []
            raise

    commits = retry_with_backoff(_get_commits)
    logger.debug(
        "[fetch_commits] repo=%s branch=%s since=%s fetched=%d commits",
        getattr(repo, "full_name", "?"),
        branch_sha,
        since_date.date(),
        len(commits),
    )
    return commits


def fetch_commit_files(commit: Any) -> List[Any]:
    """Fetch the file list for a single commit.

    Args:
        commit: PyGithub Commit object.

    Returns:
        List of PyGithub File objects.
    """
    files = retry_with_backoff(lambda: list(commit.files))
    logger.debug(
        "[fetch_commit_files] sha=%s fetched=%d files",
        getattr(commit, "sha", "?")[:12],
        len(files),
    )
    return files


def fetch_commit_comments(commit: Any) -> List[Any]:
    """Fetch all comments on a specific commit.

    Args:
        commit: PyGithub Commit object.

    Returns:
        List of PyGithub CommitComment objects.
    """
    return retry_with_backoff(lambda: list(commit.get_comments()))


# ---------------------------------------------------------------------------
# Pull request fetchers
# ---------------------------------------------------------------------------


def fetch_pull_requests_search(
    github_obj: Any,
    repo_full_name: str,
    since_date: datetime,
) -> List[Any]:
    """Fetch all PRs (open + closed) via the GitHub Search API and convert to PR objects.

    Uses the Search API which is more efficient for incremental syncs but is
    subject to a separate rate limit (30 req/min for authenticated users).

    Args:
        github_obj: Authenticated PyGithub ``Github`` client instance.
        repo_full_name: Repository full name (e.g. ``"owner/repo"``).
        since_date: Lower bound for ``updated_at`` filtering.

    Returns:
        List of PyGithub PullRequest objects (issues converted via
        ``as_pull_request()``).
    """
    # Unlike the direct endpoint, the Search API DOES support an ``updated:>=``
    # filter, so we can fetch open and closed PRs in a single query. The Search
    # API sorts by ``updated`` regardless of state, so the caller's early-break
    # on the ``updated_at`` cutoff remains correct across both state groups.
    query = (
        f"repo:{repo_full_name} is:pr"
        f" updated:>={since_date.date()}"
    )

    def _search_and_convert() -> List[Any]:
        # search_issues returns partially-loaded Issue objects. Accessing
        # .pull_request on each triggers a lazy GET /repos/{owner}/{repo}/issues/{number}
        # API call per issue. Both the search and the per-issue lazy loads are
        # inside the enclosing retry_with_backoff, so a transient network blip or
        # rate-limit error during either retries instead of being swallowed to [].
        raw = list(github_obj.search_issues(query=query, sort="updated", order="desc"))
        converted: List[Any] = []
        for idx, issue in enumerate(raw, start=1):
            logger.debug(
                f"[fetch_pull_requests_search] Issue {idx}: "
                f"pull_request={bool(issue.pull_request)} number={getattr(issue, 'number', None)}"
            )
            if issue.pull_request:
                converted.append(issue.as_pull_request())
        logger.debug(
            "[fetch_pull_requests_search] repo=%s since=%s raw_issues=%d converted_prs=%d",
            repo_full_name,
            since_date.date(),
            len(raw),
            len(converted),
        )
        return converted

    return retry_with_backoff(_search_and_convert)


def fetch_pull_requests_direct(repo_obj: Any) -> Iterable[Any]:
    """Fetch all PRs (open + closed) directly from the repository endpoint.

    Args:
        repo_obj: PyGithub Repository object.

    Returns:
        Iterable of PyGithub PullRequest objects, globally sorted by
        ``updated_at`` descending (open and closed merged together).
    """
    # The call repo_obj.get_pulls (from PyGithub) does NOT support a date filter directly.
    # The get_pulls method only supports filtering by state, sort, direction, base branch, and head branch.
    # It does NOT accept updated_at or created_at filters.
    # See: https://pygithub.readthedocs.io/en/latest/github_objects/Repository.html#github.Repository.Repository.get_pulls
    #
    # WHY WE FETCH OPEN AND CLOSED PRs AS TWO SEPARATE CALLS (CRITICAL):
    #
    # We want to capture ALL pull requests — both open (mutable, still receiving
    # commits/reviews/labels) and closed/merged (terminal, immutable). However,
    # GitHub's /pulls endpoint does NOT return a single, globally
    # updated_at-sorted list when you pass state="all". Instead, it always
    # returns OPEN PRs FIRST, followed by CLOSED PRs, IRRESPECTIVE of the
    # `sort`/`direction` parameters. The sort only applies WITHIN each state
    # group.
    #
    # This matters because the caller (process_prs.py) relies on the returned
    # PRs being ordered newest-first by `updated_at` so it can `break` out of
    # its processing loop as soon as it hits a PR older than the sync cutoff
    # (an optimization that avoids paginating through the entire history).
    #
    # If we merely concatenated the two calls, the list would be:
    #   [open PRs sorted by updated desc] + [closed PRs sorted by updated desc]
    # The loop would encounter an OLD open PR (e.g. a long-lived PR last updated
    # months ago) and `break` early — silently skipping ALL newer closed PRs
    # that appear later in the list. That would be silent data loss.
    #
    # So we issue two separate calls — one for open, one for closed — each
    # independently sorted by updated desc, and then MERGE-SORT the combined
    # list globally by `updated_at` descending. This final global sort is what
    # guarantees the caller's early-break stays correct across both state
    # groups and no PRs are skipped.
    open_prs = retry_with_backoff(
        lambda: list(repo_obj.get_pulls(state="open", sort="updated", direction="desc"))
    )
    closed_prs = retry_with_backoff(
        lambda: list(repo_obj.get_pulls(state="closed", sort="updated", direction="desc"))
    )
    combined = open_prs + closed_prs

    def _updated_key(pr: Any) -> datetime:
        updated: Optional[datetime] = getattr(pr, "updated_at", None)
        if updated is not None:
            return updated
        return datetime(1, 1, 1, tzinfo=timezone.utc)

    combined.sort(key=_updated_key, reverse=True)
    return combined


def fetch_pr_reviews(pr: Any) -> List[Any]:
    """Fetch all review objects for a pull request.

    Args:
        pr: PyGithub PullRequest object.

    Returns:
        List of PyGithub PullRequestReview objects.
    """
    return retry_with_backoff(lambda: list(pr.get_reviews()))


def fetch_pr_issue_comments(pr: Any) -> List[Any]:
    """Fetch all issue comments (PR-level) for a pull request.

    Args:
        pr: PyGithub PullRequest object.

    Returns:
        List of PyGithub IssueComment objects.
    """
    return retry_with_backoff(lambda: list(pr.get_issue_comments()))


def fetch_pr_review_comments(pr: Any) -> List[Any]:
    """Fetch all review comments (file/line-level) for a pull request.

    Args:
        pr: PyGithub PullRequest object.

    Returns:
        List of PyGithub PullRequestComment objects.
    """
    return retry_with_backoff(lambda: list(pr.get_review_comments()))


def fetch_pr_commits(pr: Any) -> List[Any]:
    """Fetch all commit objects associated with a pull request.

    Args:
        pr: PyGithub PullRequest object.

    Returns:
        List of PyGithub Commit objects.
    """
    return retry_with_backoff(lambda: list(pr.get_commits()))


# ---------------------------------------------------------------------------
# Issue fetchers
# ---------------------------------------------------------------------------


def fetch_issues(
    github_obj: Any,
    repo_full_name: str,
    since_date: datetime,
) -> List[Any]:
    """Fetch issues via the GitHub Search API and filter out pull requests.

    Uses the Search API which supports the ``updated:>=`` filter for incremental
    syncs.  Subject to a separate rate limit (30 requests/min for authenticated
    users).

    Args:
        github_obj: Authenticated PyGithub ``Github`` client instance.
        repo_full_name: Repository full name (e.g. ``"owner/repo"``).
        since_date: Lower bound for ``updated_at`` filtering.

    Returns:
        List of PyGithub Issue objects (PRs excluded).
    """
    query = (
        f"repo:{repo_full_name} is:issue"
        f" updated:>={since_date.date()}"
    )

    logger.info("Fetching issues for '%s' since %s ...", repo_full_name, since_date.date())

    def _search_and_filter() -> List[Any]:
        # search_issues returns partially-loaded Issue objects. Accessing
        # .pull_request on each triggers a lazy GET /repos/{owner}/{repo}/issues/{number}
        # API call per issue. Both the search and the per-issue lazy loads are
        # inside the enclosing retry_with_backoff, so a transient network blip or
        # rate-limit error during either retries instead of being swallowed to [].
        raw = list(github_obj.search_issues(query=query, sort="updated", order="desc"))
        filtered: List[Any] = []
        for idx, issue in enumerate(raw, start=1):
            # Accessing .pull_request triggers a lazy GET — inside retry scope.
            is_pr = bool(getattr(issue, "pull_request", None))
            logger.debug(
                "Issue #%d: pull_request=%s, state=%s",
                getattr(issue, "number", "?"),
                is_pr,
                getattr(issue, "state", "?"),
            )
            if not is_pr:
                filtered.append(issue)
        logger.info("Found %d total issues (filtered %d PRs) for '%s'", len(filtered), len(raw) - len(filtered), repo_full_name)
        return filtered

    return retry_with_backoff(_search_and_filter)


def fetch_issues_direct(repo_obj: Any, since_date: Optional[datetime] = None) -> Iterable[Any]:
    """Fetch all issues directly from the repository endpoint.

    Fallback for first sync or when the Search API fails.  The ``get_issues``
    method supports a ``since`` filter (ISO 8601) that limits results to issues
    last updated at or after that time. When ``since_date`` is provided, only
    issues updated within the incremental window are returned — matching the
    Search API's ``updated:>=`` filter so both code paths produce consistent
    counts.

    Args:
        repo_obj: PyGithub Repository object.
        since_date: Optional lower bound for ``updated_at`` filtering. When
            ``None``, all issues are returned (full sync).

    Returns:
        Iterable of PyGithub Issue objects (PRs excluded).
    """
    full_name = getattr(repo_obj, "full_name", "?")
    if since_date is not None:
        logger.info(
            "Fetching issues directly for '%s' since %s (fallback)...",
            full_name,
            since_date.date(),
        )
    else:
        logger.info("Fetching issues directly for '%s' (fallback, full sync)...", full_name)

    # Materialize inside the retry: get_issues returns a lazy PaginatedList
    # whose network I/O happens on iteration, so the retry must wrap the list().
    # The `since` param mirrors the Search API's updated:>= filter so both
    # implementations apply the same incremental window.
    raw = retry_with_backoff(
        lambda: list(
            repo_obj.get_issues(
                state="all",
                sort="updated",
                direction="desc",
                since=since_date.isoformat() if since_date else None,
            )
        )
    )

    filtered = [issue for issue in raw if not getattr(issue, "pull_request", None)]
    logger.info("Found %d issues (direct) for '%s'", len(filtered), full_name)
    return filtered


def fetch_issue_comments(issue: Any) -> List[Any]:
    """Fetch all comments on a specific issue.

    Args:
        issue: PyGithub Issue object.

    Returns:
        List of PyGithub IssueComment objects.
    """
    issue_number = getattr(issue, "number", "?")
    logger.debug("Fetching comments for issue #%s ...", issue_number)
    comments = retry_with_backoff(lambda: list(issue.get_comments()))
    logger.debug("Fetched %d comments for issue #%s", len(comments), issue_number)
    return comments


def fetch_repo_teams(repo: Any) -> List[Any]:
    """Fetch all teams with access to *repo*.

    Args:
        repo: PyGithub Repository object.

    Returns:
        List of PyGithub Team objects.  Returns an empty list when the
        repository belongs to a personal account (no org teams) or when
        the caller lacks the required permissions.
    """
    try:
        return retry_with_backoff(lambda: list(repo.get_teams()))
    except WbaRetryTimeoutError as exc:
        # CRITICAL: retry budget exhausted. Returning [] here would silently
        # drop ALL teams for this repo AND advance the sync cursor (the caller
        # sees an empty list as success). Re-raise so the config-level handler
        # skips this repo without advancing the cursor.
        logger.debug(
            "fetch_repo_teams: WbaRetryTimeoutError for '%s' after %.0fs — re-raising "
            "so repo is skipped without cursor advance: %s",
            getattr(repo, "full_name", "?"),
            exc.timeout,
            exc,
        )
        raise
    except Exception as exc:
        logger.debug(
            "fetch_repo_teams: could not fetch teams for '%s' type=%s: %s",
            getattr(repo, "full_name", "?"),
            type(exc).__name__,
            exc,
        )
        return []


def fetch_repo_collaborators(repo: Any) -> List[Any]:
    """Fetch user collaborators with access to *repo*.

    Args:
        repo: PyGithub Repository object.

    Returns:
        List of collaborator user objects (type == "User"). Returns an empty
        list on permission/API failures.
    """
    try:
        collaborators = retry_with_backoff(lambda: list(repo.get_collaborators()))
        return [collab for collab in collaborators if getattr(collab, "type", None) == "User"]
    except WbaRetryTimeoutError as exc:
        # CRITICAL: retry budget exhausted. Returning [] here would silently
        # drop ALL collaborators for this repo AND advance the sync cursor.
        # Re-raise so the config-level handler skips this repo without
        # advancing the cursor.
        logger.debug(
            "fetch_repo_collaborators: WbaRetryTimeoutError for '%s' after %.0fs — "
            "re-raising so repo is skipped without cursor advance: %s",
            getattr(repo, "full_name", "?"),
            exc.timeout,
            exc,
        )
        raise
    except Exception as exc:
        logger.debug(
            "fetch_repo_collaborators: could not fetch collaborators for '%s' type=%s: %s",
            getattr(repo, "full_name", "?"),
            type(exc).__name__,
            exc,
        )
        return []


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


def resolve_issues_since_date(last_synced_at: Optional[datetime]) -> datetime:
    """Return the *since* date to use when fetching issues.

    Args:
        last_synced_at: Last successful sync timestamp, or ``None`` for first run.

    Returns:
        ``last_synced_at`` (UTC-aware) for incremental syncs; a rolling window
        based on the ``ISSUE_DAYS_LIMIT`` env var (default 60 days) for
        first-time syncs.
    """
    if last_synced_at:
        resolved = last_synced_at if last_synced_at.tzinfo else last_synced_at.replace(tzinfo=timezone.utc)
        logger.info("Issues incremental sync: using cursor %s", resolved.isoformat())
        return resolved
    issue_days_limit = int(os.getenv("ISSUE_DAYS_LIMIT", "60"))
    resolved = datetime.now(timezone.utc) - timedelta(days=issue_days_limit)
    logger.info("Issues first sync: using %d-day lookback window (since %s)", issue_days_limit, resolved.date())
    return resolved

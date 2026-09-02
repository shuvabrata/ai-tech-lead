"""Unit tests for GitHub issue fetch functions (Phase 1).

Tests cover:
- ``fetch_issues`` — Search API query construction, PR filtering, pagination.
- ``fetch_issues_direct`` — direct repository endpoint, ``since`` param, PR filtering.
- ``fetch_issue_comments`` — comment retrieval.
- ``resolve_issues_since_date`` — cursor resolution and lookback window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest
from github import GithubException

from connectors.producers.github.fetch_github import (
    fetch_issue_comments,
    fetch_issues,
    fetch_issues_direct,
    resolve_issues_since_date,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(number: int, *, is_pr: bool = False, state: str = "open") -> MagicMock:
    """Build a mock PyGithub Issue object."""
    issue = MagicMock()
    issue.number = number
    issue.state = state
    issue.pull_request = MagicMock() if is_pr else None
    return issue


def _make_comment(comment_id: int, body: str = "comment body") -> MagicMock:
    """Build a mock PyGithub IssueComment object."""
    comment = MagicMock()
    comment.id = comment_id
    comment.body = body
    comment.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    comment.updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    comment.user = MagicMock()
    comment.user.login = f"user{comment_id}"
    return comment


# ---------------------------------------------------------------------------
# fetch_issues — Search API
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fetch_issues_returns_only_non_pr_issues():
    """Issues with ``pull_request`` set should be filtered out."""
    issues = [
        _make_issue(1, is_pr=False, state="open"),
        _make_issue(2, is_pr=True, state="closed"),
        _make_issue(3, is_pr=False, state="closed"),
    ]

    github_obj = MagicMock()
    github_obj.search_issues.return_value = issues

    result = fetch_issues(github_obj, "owner/repo", datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert len(result) == 2
    assert result[0].number == 1
    assert result[1].number == 3


@pytest.mark.unit
def test_fetch_issues_search_query_contains_is_issue_filter():
    """The Search API query must include ``is:issue`` to exclude PRs."""
    github_obj = MagicMock()
    github_obj.search_issues.return_value = []

    fetch_issues(github_obj, "owner/repo", datetime(2026, 1, 1, tzinfo=timezone.utc))

    call_args = github_obj.search_issues.call_args
    query = call_args.kwargs.get("query") or call_args.args[0]
    assert "is:issue" in query
    assert "repo:owner/repo" in query


@pytest.mark.unit
def test_fetch_issues_search_query_contains_updated_filter():
    """The Search API query must include ``updated:>=`` for incremental sync."""
    github_obj = MagicMock()
    github_obj.search_issues.return_value = []

    since = datetime(2026, 6, 15, tzinfo=timezone.utc)
    fetch_issues(github_obj, "owner/repo", since)

    call_args = github_obj.search_issues.call_args
    query = call_args.kwargs.get("query") or call_args.args[0]
    assert "updated:>=2026-06-15" in query


@pytest.mark.unit
def test_fetch_issues_search_query_sort_and_order():
    """Issues should be sorted by ``updated`` descending."""
    github_obj = MagicMock()
    github_obj.search_issues.return_value = []

    fetch_issues(github_obj, "owner/repo", datetime(2026, 1, 1, tzinfo=timezone.utc))

    call_args = github_obj.search_issues.call_args
    assert call_args.kwargs.get("sort") == "updated"
    assert call_args.kwargs.get("order") == "desc"


@pytest.mark.unit
def test_fetch_issues_propagates_non_retryable_search_error():
    """A non-retryable Search failure (e.g. 404) propagates — never converted to [].

    Returning [] here would silently advance the sync cursor and drop the repo's
    issues. Non-retryable errors must surface to the caller. Mirror the passthrough
    patch used by the retryable test to keep the test deterministic.
    """
    github_obj = MagicMock()
    github_obj.search_issues.side_effect = GithubException(status=404, data={}, headers={})

    with patch(
        "connectors.producers.github.fetch_github.retry_with_backoff",
        side_effect=lambda fn: fn(),
    ):
        with pytest.raises(GithubException):
            fetch_issues(github_obj, "owner/repo", datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.mark.unit
def test_fetch_issues_returns_empty_list_when_no_issues():
    """When the repo has no issues, return an empty list."""
    github_obj = MagicMock()
    github_obj.search_issues.return_value = []

    result = fetch_issues(github_obj, "owner/repo", datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert result == []


@pytest.mark.unit
def test_fetch_issues_all_returned_issues_are_non_pr():
    """No issue in the result should have ``pull_request`` set."""
    issues = [
        _make_issue(10, is_pr=False),
        _make_issue(11, is_pr=False),
        _make_issue(12, is_pr=False),
    ]

    github_obj = MagicMock()
    github_obj.search_issues.return_value = issues

    result = fetch_issues(github_obj, "owner/repo", datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert all(not getattr(i, "pull_request", None) for i in result)


@pytest.mark.unit
def test_fetch_issues_propagates_retryable_rate_limit_error():
    """A retryable Search failure (rate limit) must NOT be swallowed to [].

    PyGithub raises ``RateLimitExceededException`` (a ``GithubException``
    subclass) whose message contains "API rate limit exceeded". That is
    exactly what ``_is_rate_limit`` classifies as retryable, so the inner
    ``except GithubException: return []`` in ``fetch_issues`` must not
    intercept it. Instead the error must propagate to ``retry_with_backoff``.

    To make the test deterministic without a real 1-hour retry budget, we
    patch ``retry_with_backoff`` with a passthrough that simply invokes the
    wrapped function once (no retry loop). The wrapped function should raise
    the ``GithubException`` out to the caller rather than return [].
    """
    github_obj = MagicMock()
    github_obj.search_issues.side_effect = GithubException(
        status=403, data={"message": "API rate limit exceeded"}, headers={}
    )

    with patch(
        "connectors.producers.github.fetch_github.retry_with_backoff",
        side_effect=lambda fn: fn(),
    ):
        with pytest.raises(GithubException):
            fetch_issues(github_obj, "owner/repo", datetime(2026, 1, 1, tzinfo=timezone.utc))


# ---------------------------------------------------------------------------
# fetch_issues_direct — direct repository endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fetch_issues_direct_returns_only_non_pr_issues():
    """The direct fetch should also filter out PRs."""
    issues = [
        _make_issue(1, is_pr=False),
        _make_issue(2, is_pr=True),
        _make_issue(3, is_pr=False),
    ]

    repo_obj = MagicMock()
    repo_obj.full_name = "owner/repo"
    repo_obj.get_issues.return_value = issues

    result = list(fetch_issues_direct(repo_obj))

    assert len(result) == 2
    assert result[0].number == 1
    assert result[1].number == 3


@pytest.mark.unit
def test_fetch_issues_direct_uses_state_all():
    """The direct fetch should use ``state="all"``."""
    repo_obj = MagicMock()
    repo_obj.full_name = "owner/repo"
    repo_obj.get_issues.return_value = []

    list(fetch_issues_direct(repo_obj))

    call_args = repo_obj.get_issues.call_args
    assert call_args.kwargs.get("state") == "all"
    assert call_args.kwargs.get("sort") == "updated"
    assert call_args.kwargs.get("direction") == "desc"


@pytest.mark.unit
def test_fetch_issues_direct_passes_since_when_provided():
    """When ``since_date`` is provided, it should be passed to ``get_issues``."""
    repo_obj = MagicMock()
    repo_obj.full_name = "owner/repo"
    repo_obj.get_issues.return_value = []

    since = datetime(2026, 6, 15, tzinfo=timezone.utc)
    list(fetch_issues_direct(repo_obj, since_date=since))

    call_args = repo_obj.get_issues.call_args
    assert call_args.kwargs.get("since") == since.isoformat()


@pytest.mark.unit
def test_fetch_issues_direct_omits_since_when_not_provided():
    """When ``since_date`` is None, ``since`` should not be passed to ``get_issues``."""
    repo_obj = MagicMock()
    repo_obj.full_name = "owner/repo"
    repo_obj.get_issues.return_value = []

    list(fetch_issues_direct(repo_obj, since_date=None))

    call_args = repo_obj.get_issues.call_args
    assert call_args.kwargs.get("since") is None


@pytest.mark.unit
def test_fetch_issues_direct_returns_empty_when_no_issues():
    """When the repo has no issues, return an empty list."""
    repo_obj = MagicMock()
    repo_obj.full_name = "owner/repo"
    repo_obj.get_issues.return_value = []

    result = list(fetch_issues_direct(repo_obj))

    assert result == []


# ---------------------------------------------------------------------------
# fetch_issue_comments
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fetch_issue_comments_returns_comments():
    """``fetch_issue_comments`` should return the list from ``issue.get_comments()``."""
    comments = [_make_comment(1), _make_comment(2), _make_comment(3)]

    issue = MagicMock()
    issue.number = 42
    issue.get_comments.return_value = comments

    result = fetch_issue_comments(issue)

    assert len(result) == 3
    assert result[0].id == 1
    assert result[1].id == 2
    assert result[2].id == 3


@pytest.mark.unit
def test_fetch_issue_comments_returns_empty_when_no_comments():
    """When an issue has no comments, return an empty list."""
    issue = MagicMock()
    issue.number = 42
    issue.get_comments.return_value = []

    result = fetch_issue_comments(issue)

    assert result == []


@pytest.mark.unit
def test_fetch_issue_comments_calls_get_comments():
    """``fetch_issue_comments`` should call ``issue.get_comments()`` exactly once."""
    issue = MagicMock()
    issue.number = 42
    issue.get_comments.return_value = []

    fetch_issue_comments(issue)

    issue.get_comments.assert_called_once()


# ---------------------------------------------------------------------------
# resolve_issues_since_date
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_issues_since_date_returns_cursor_when_provided():
    """When ``last_synced_at`` is provided, return it (UTC-aware)."""
    cursor = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    result = resolve_issues_since_date(cursor)
    assert result == cursor


@pytest.mark.unit
def test_resolve_issues_since_date_makes_naive_cursor_utc_aware():
    """When ``last_synced_at`` is naive, attach UTC timezone."""
    cursor = datetime(2026, 6, 15, 12, 0, 0)
    result = resolve_issues_since_date(cursor)
    assert result.tzinfo == timezone.utc
    assert result.replace(tzinfo=None) == cursor


@pytest.mark.unit
def test_resolve_issues_since_date_uses_lookback_window_on_first_sync():
    """When ``last_synced_at`` is None, use the ``ISSUE_DAYS_LIMIT`` runtime setting."""
    with patch(
        "connectors.producers.daemon_common.runtime_cache"
    ) as mock_cache:
        mock_cache.get_int.return_value = 30
        result = resolve_issues_since_date(None)
    now = datetime.now(timezone.utc)
    # Should be roughly 30 days ago (allow a small delta for test execution time)
    delta = now - result
    assert timedelta(days=29) < delta < timedelta(days=31)


@pytest.mark.unit
def test_resolve_issues_since_date_defaults_to_60_days():
    """When the runtime cache is unavailable, default to 60 days."""
    with patch(
        "connectors.producers.daemon_common.runtime_cache"
    ) as mock_cache:
        mock_cache.get_int.side_effect = RuntimeError("cache unavailable")
        result = resolve_issues_since_date(None)
    now = datetime.now(timezone.utc)
    delta = now - result
    assert timedelta(days=59) < delta < timedelta(days=61)


@pytest.mark.unit
def test_resolve_issues_since_date_first_sync_is_utc_aware():
    """The first-sync lookback date should be UTC-aware."""
    with patch(
        "connectors.producers.daemon_common.runtime_cache"
    ) as mock_cache:
        mock_cache.get_int.return_value = 10
        result = resolve_issues_since_date(None)
    assert result.tzinfo == timezone.utc

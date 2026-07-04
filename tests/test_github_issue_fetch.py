"""Unit tests for GitHub issue fetch functions (Phase 1).

Tests cover:
- ``fetch_issues`` — Search API query construction, PR filtering, pagination.
- ``fetch_issues_direct`` — fallback path, PR filtering.
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
def test_fetch_issues_returns_empty_list_on_search_api_error():
    """When the Search API raises a GithubException, return an empty list."""
    github_obj = MagicMock()
    github_obj.search_issues.side_effect = GithubException(status=403, data={}, headers={})

    result = fetch_issues(github_obj, "owner/repo", datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert result == []


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


# ---------------------------------------------------------------------------
# fetch_issues_direct — fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fetch_issues_direct_returns_only_non_pr_issues():
    """The direct fallback should also filter out PRs."""
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
    """The direct fallback should fetch issues with ``state="all"``."""
    repo_obj = MagicMock()
    repo_obj.full_name = "owner/repo"
    repo_obj.get_issues.return_value = []

    list(fetch_issues_direct(repo_obj))

    call_args = repo_obj.get_issues.call_args
    assert call_args.kwargs.get("state") == "all"
    assert call_args.kwargs.get("sort") == "updated"
    assert call_args.kwargs.get("direction") == "desc"


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
def test_resolve_issues_since_date_uses_lookback_window_on_first_sync(monkeypatch):
    """When ``last_synced_at`` is None, use the ``ISSUE_DAYS_LIMIT`` env var."""
    monkeypatch.setenv("ISSUE_DAYS_LIMIT", "30")
    result = resolve_issues_since_date(None)
    now = datetime.now(timezone.utc)
    # Should be roughly 30 days ago (allow a small delta for test execution time)
    delta = now - result
    assert timedelta(days=29) < delta < timedelta(days=31)


@pytest.mark.unit
def test_resolve_issues_since_date_defaults_to_60_days(monkeypatch):
    """When ``ISSUE_DAYS_LIMIT`` is not set, default to 60 days."""
    monkeypatch.delenv("ISSUE_DAYS_LIMIT", raising=False)
    result = resolve_issues_since_date(None)
    now = datetime.now(timezone.utc)
    delta = now - result
    assert timedelta(days=59) < delta < timedelta(days=61)


@pytest.mark.unit
def test_resolve_issues_since_date_first_sync_is_utc_aware(monkeypatch):
    """The first-sync lookback date should be UTC-aware."""
    monkeypatch.setenv("ISSUE_DAYS_LIMIT", "10")
    result = resolve_issues_since_date(None)
    assert result.tzinfo == timezone.utc

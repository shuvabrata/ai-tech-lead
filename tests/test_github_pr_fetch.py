"""Unit tests for GitHub pull request fetch functions.

Focus: the ordering contract between ``fetch_pull_requests_direct`` and its
caller ``process_prs.process_prs``, which relies on PRs being returned in
globally ``updated_at``-descending order so it can ``break`` early.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from connectors.producers.github.fetch_github import fetch_pull_requests_direct


def _make_pr(number: int, updated_at: datetime) -> MagicMock:
    """Build a mock PyGithub PullRequest object."""
    pr = MagicMock()
    pr.number = number
    pr.updated_at = updated_at
    return pr


@pytest.mark.unit
def test_fetch_pull_requests_direct_queries_both_states():
    """Both ``open`` and ``closed`` states must be queried."""
    repo_obj = MagicMock()
    repo_obj.full_name = "owner/repo"
    repo_obj.get_pulls.side_effect = lambda state, **kwargs: []

    list(fetch_pull_requests_direct(repo_obj))

    states = {call.kwargs.get("state") for call in repo_obj.get_pulls.call_args_list}
    assert states == {"open", "closed"}


@pytest.mark.unit
def test_fetch_pull_requests_direct_returns_globally_sorted_by_updated_desc():
    """Open and closed PRs must merge into one ``updated_at``-desc list.

    Regression for silent data loss: the caller (``process_prs``) breaks on the
    first PR older than the sync cutoff. If open PRs are returned first
    regardless of age, a stale open PR causes recently-merged closed PRs to be
    skipped. The correct result orders the recently-updated closed PR BEFORE the
    stale open PR.
    """
    old_open = _make_pr(1, datetime(2020, 1, 1, tzinfo=timezone.utc))
    recent_closed = _make_pr(2, datetime(2026, 6, 1, tzinfo=timezone.utc))

    repo_obj = MagicMock()
    repo_obj.full_name = "owner/repo"

    def get_pulls(state, **kwargs):
        return [old_open] if state == "open" else [recent_closed]

    repo_obj.get_pulls.side_effect = get_pulls

    result = list(fetch_pull_requests_direct(repo_obj))

    assert [pr.number for pr in result] == [2, 1]
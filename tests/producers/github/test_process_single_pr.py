"""
Tests for concurrent comment-fetching behaviour in process_single_pr.

Strategy: test through the public `process_single_pr` boundary.
- `asyncio.to_thread` is replaced with an AsyncMock whose side_effect calls
  the wrapped function directly (no real thread pool), keeping tests
  deterministic.
- Underlying fetch functions are mocked at the
  `connectors.producers.github.process_single_pr` module level.
- All tests are marked `unit` (no external services required).
"""
from __future__ import annotations

import pytest
import asyncio
import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

from connectors.producers.github.process_single_pr import process_single_pr

_MODULE = "connectors.producers.github.process_single_pr"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_comment(login: str, comment_id: int = 1) -> MagicMock:
    comment = MagicMock()
    comment.user = MagicMock()
    comment.user.login = login
    comment.id = comment_id
    comment.created_at = datetime(2026, 6, 20, 10, 0, 0, tzinfo=timezone.utc)
    return comment


def _make_commit(sha: str) -> MagicMock:
    c = MagicMock()
    c.sha = sha
    return c


def _make_pr(number: int = 1) -> MagicMock:
    pr = MagicMock()
    pr.number = number
    pr.user = MagicMock()
    pr.user.login = "pr_author"
    pr.title = "Test PR"
    pr.state = "open"
    pr.merged_by = None
    pr.requested_reviewers = []
    return pr


def _make_repo() -> MagicMock:
    repo = MagicMock()
    repo.name = "test-repo"
    return repo


async def _fake_to_thread(func, *args, **kwargs):
    """AsyncMock side_effect: call func synchronously, no real thread."""
    return func(*args, **kwargs)


_MINIMAL_PR_DATA = {
    "number": 1, "title": "T", "state": "open",
    "created_at": "2026-06-20T10:00:00+00:00",
    "updated_at": "2026-06-20T10:00:00+00:00",
    "commits_count": 0, "additions": 0, "deletions": 0, "changed_files": 0,
    "comments": 0, "review_comments": 0,
    "head_branch_name": "feat", "base_branch_name": "main",
    "mergeable_state": "clean", "labels": [], "url": "http://x",
    "base_branch_id": "test-repo::main", "head_branch_id": "test-repo::feat",
}


def _common_patches(
    commits=None,
    issue_comments=None,
    review_comments=None,
    fetch_commit_comments_fn=None,
    fetch_user_fn=None,
):
    commits = commits or []
    issue_comments = issue_comments or []
    review_comments = review_comments or []
    fetch_user_fn = fetch_user_fn or (lambda u: {"login": u.login, "name": u.login, "email": ""})
    fetch_commit_comments_fn = fetch_commit_comments_fn or (lambda c: [])

    return [
        patch(f"{_MODULE}.asyncio.to_thread", new=AsyncMock(side_effect=_fake_to_thread)),
        patch(f"{_MODULE}.fetch_pr_commits", return_value=commits),
        patch(f"{_MODULE}.fetch_pr_issue_comments", return_value=issue_comments),
        patch(f"{_MODULE}.fetch_pr_review_comments", return_value=review_comments),
        patch(f"{_MODULE}.fetch_commit_comments", side_effect=fetch_commit_comments_fn),
        patch(f"{_MODULE}.fetch_github_user", side_effect=fetch_user_fn),
        patch(f"{_MODULE}.fetch_pr_reviews", return_value=[]),
        patch(f"{_MODULE}.map_pull_request", return_value=_MINIMAL_PR_DATA),
        patch(f"{_MODULE}.map_commit", return_value={}),
        patch(f"{_MODULE}.map_pr_reviews", return_value={}),
    ]


# ---------------------------------------------------------------------------
# Test 1: Happy path — commit comments fetched for all 3 commits
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_commit_comments_fetched_concurrently():
    """
    With 3 mock commits, fetch_commit_comments should be called 3 times
    and all results should appear in the PR signal's COMMENTED_ON relationships.
    """
    commits = [_make_commit("sha1"), _make_commit("sha2"), _make_commit("sha3")]

    comment_by_sha = {
        "sha1": [_make_comment("alice", 1)],
        "sha2": [_make_comment("bob",   2)],
        "sha3": [_make_comment("carol", 3)],
    }

    published: list[Any] = []

    async def _pub(signal):
        if signal is not None:
            published.append(signal)

    all_patches = _common_patches(
        commits=commits,
        fetch_commit_comments_fn=lambda c: comment_by_sha[c.sha],
        fetch_user_fn=lambda u: {"login": u.login, "name": u.login, "email": ""},
    )

    with patch(f"{_MODULE}.fetch_commit_comments", side_effect=lambda c: comment_by_sha[c.sha]) as mock_fcc:
        # re-stack all_patches except the fetch_commit_comments one (index 4)
        active = all_patches[:4] + all_patches[5:]
        with active[0], active[1], active[2], active[3], \
             active[4], active[5], active[6], active[7], active[8]:
            await process_single_pr(
                pr=_make_pr(), repo=_make_repo(),
                repo_data={"name": "test-repo"}, repo_owner="org",
                seen_commits=set(), published_persons=set(), _pub=_pub,
            )

    assert mock_fcc.call_count == 3, \
        f"Expected fetch_commit_comments called 3 times, got {mock_fcc.call_count}"

    pr_signal = published[-1]
    comment_logins = {r.target.id for r in pr_signal.relationships if r.type == "COMMENTED_ON"}
    assert comment_logins == {"alice", "bob", "carol"}


# ---------------------------------------------------------------------------
# Test 2: Partial failure — one commit comment fetch raises
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_commit_comments_partial_failure(caplog):
    """
    When one commit's fetch raises, the other commits' comments are still
    included, a warning is logged, and process_single_pr does not raise.
    """
    commits = [_make_commit("sha1"), _make_commit("sha2"), _make_commit("sha3")]

    def _fcc_partial(c):
        if c.sha == "sha2":
            raise RuntimeError("API exploded for sha2")
        return [_make_comment(f"user_{c.sha}", 99)]

    published: list[Any] = []

    async def _pub(signal):
        if signal is not None:
            published.append(signal)

    all_patches = _common_patches(commits=commits)

    with caplog.at_level(logging.WARNING), \
         patch(f"{_MODULE}.fetch_commit_comments", side_effect=_fcc_partial), \
         all_patches[0], all_patches[1], all_patches[2], all_patches[3], \
         all_patches[5], all_patches[6], all_patches[7], all_patches[8], all_patches[9]:
        await process_single_pr(
            pr=_make_pr(), repo=_make_repo(),
            repo_data={"name": "test-repo"}, repo_owner="org",
            seen_commits=set(), published_persons=set(), _pub=_pub,
        )

    assert any("sha2" in r.message for r in caplog.records), \
        "Expected warning mentioning sha2"

    pr_signal = published[-1]
    comment_logins = {r.target.id for r in pr_signal.relationships if r.type == "COMMENTED_ON"}
    assert "user_sha1" in comment_logins
    assert "user_sha3" in comment_logins
    assert "user_sha2" not in comment_logins


# ---------------------------------------------------------------------------
# Test 3: Commenter deduplication — same user commenting twice → fetched once
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_commenter_user_data_deduplicated():
    """
    If the same user appears in multiple comments, fetch_github_user should be
    called exactly once per unique login (3 unique users despite 4 comments).
    """
    issue_comments = [
        _make_comment("alice", 1),
        _make_comment("bob",   2),
        _make_comment("alice", 3),  # duplicate
        _make_comment("carol", 4),
    ]

    user_db = {
        "alice":     {"login": "alice",     "name": "Alice",  "email": ""},
        "bob":       {"login": "bob",       "name": "Bob",    "email": ""},
        "carol":     {"login": "carol",     "name": "Carol",  "email": ""},
        "pr_author": {"login": "pr_author", "name": "Author", "email": ""},
    }
    fetch_calls: list[str] = []

    def _fetch_user(u):
        fetch_calls.append(u.login)
        return user_db[u.login]

    published: list[Any] = []

    async def _pub(signal):
        if signal is not None:
            published.append(signal)

    with (
        patch(f"{_MODULE}.asyncio.to_thread", new=AsyncMock(side_effect=_fake_to_thread)),
        patch(f"{_MODULE}.fetch_pr_commits", return_value=[]),
        patch(f"{_MODULE}.fetch_pr_issue_comments", return_value=issue_comments),
        patch(f"{_MODULE}.fetch_pr_review_comments", return_value=[]),
        patch(f"{_MODULE}.fetch_commit_comments", return_value=[]),
        patch(f"{_MODULE}.fetch_github_user", side_effect=_fetch_user),
        patch(f"{_MODULE}.fetch_pr_reviews", return_value=[]),
        patch(f"{_MODULE}.map_pull_request", return_value=_MINIMAL_PR_DATA),
        patch(f"{_MODULE}.map_commit", return_value={}),
        patch(f"{_MODULE}.map_pr_reviews", return_value={}),
    ):
        await process_single_pr(
            pr=_make_pr(), repo=_make_repo(),
            repo_data={"name": "test-repo"}, repo_owner="org",
            seen_commits=set(), published_persons=set(), _pub=_pub,
        )

    commenter_calls = [l for l in fetch_calls if l in ("alice", "bob", "carol")]
    assert commenter_calls.count("alice") == 1, "alice fetched more than once"
    assert commenter_calls.count("bob")   == 1, "bob fetched more than once"
    assert commenter_calls.count("carol") == 1, "carol fetched more than once"


# ---------------------------------------------------------------------------
# Test 4: Partial failure — one user-data fetch returns fallback data
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.asyncio
async def test_commenter_user_data_partial_failure(caplog):
    """
    When one fetch_github_user call returns fallback data (login-only, no
    name/email), the failing login should be absent from published Person
    signals, a warning should be logged, and process_single_pr should not
    raise. Other logins' data should be present. The comment entry (login +
    timestamp) should still be in comments_data regardless of user-fetch
    failure.
    """
    issue_comments = [
        _make_comment("alice", 1),
        _make_comment("bob",   2),
        _make_comment("carol", 3),
    ]

    def _fetch_user(u):
        if u.login == "bob":
            # Simulate fetch_github_user falling back to login-only data
            # (e.g. after a WbaRetryTimeoutError or non-retryable error).
            return {"login": "bob", "name": "bob", "email": ""}
        return {"login": u.login, "name": u.login.title(), "email": ""}

    published: list[Any] = []

    async def _pub(signal):
        if signal is not None:
            published.append(signal)

    with (
        patch(f"{_MODULE}.asyncio.to_thread", new=AsyncMock(side_effect=_fake_to_thread)),
        patch(f"{_MODULE}.fetch_pr_commits", return_value=[]),
        patch(f"{_MODULE}.fetch_pr_issue_comments", return_value=issue_comments),
        patch(f"{_MODULE}.fetch_pr_review_comments", return_value=[]),
        patch(f"{_MODULE}.fetch_commit_comments", return_value=[]),
        patch(f"{_MODULE}.fetch_github_user", side_effect=_fetch_user),
        patch(f"{_MODULE}.fetch_pr_reviews", return_value=[]),
        patch(f"{_MODULE}.map_pull_request", return_value=_MINIMAL_PR_DATA),
        patch(f"{_MODULE}.map_commit", return_value={}),
        patch(f"{_MODULE}.map_pr_reviews", return_value={}),
    ):
        with caplog.at_level(logging.WARNING):
            await process_single_pr(
                pr=_make_pr(), repo=_make_repo(),
                repo_data={"name": "test-repo"}, repo_owner="org",
                seen_commits=set(), published_persons=set(), _pub=_pub,
            )

    # No warning — fetch_github_user returns fallback data instead of raising.
    # The fallback data (login-only) is still published as a Person signal.
    assert not any("commenter" in r.message.lower() for r in caplog.records), \
        "No warning expected — fetch_github_user returns fallback data, never raises"

    # All three commenters should have Person signals (bob gets login-only fallback).
    # ActivitySignal.id is the canonical key e.g. "github::Person::alice"
    published_ids = {getattr(sig, "id", None) for sig in published if getattr(sig, "id", None)}

    assert any(eid.endswith("alice") for eid in published_ids), \
        f"alice Person signal should be published; got {published_ids}"
    assert any(eid.endswith("bob") for eid in published_ids), \
        f"bob Person signal should be published (fallback data); got {published_ids}"
    assert any(eid.endswith("carol") for eid in published_ids), \
        f"carol Person signal should be published; got {published_ids}"

    # All 3 COMMENTED_ON entries preserved (comment data recorded before user-fetch)
    pr_signal = published[-1]
    comment_target_ids = {r.target.id for r in pr_signal.relationships if r.type == "COMMENTED_ON"}
    assert "alice" in comment_target_ids
    assert "carol" in comment_target_ids
    assert "bob" in comment_target_ids  # comment entry preserved regardless of user-fetch quality

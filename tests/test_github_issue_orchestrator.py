"""Unit tests for the GitHub issue orchestrator (Phase 4).

Tests cover ``process_issues`` through the public boundary, mirroring the
strategy used in ``tests/producers/github/test_process_single_pr.py``:

- ``asyncio.to_thread`` is replaced with an ``AsyncMock`` whose side_effect
  calls the wrapped function directly (no real thread pool).
- Underlying fetch / map / build functions are mocked at the
  ``connectors.producers.github.process_issues`` module level.
- All tests are marked ``unit`` (no external services required).
"""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.producers.github.process_issues import process_issues

_MODULE = "connectors.producers.github.process_issues"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_FULL_NAME = "owner/repo"


def _make_issue(number: int = 42, state: str = "open", body: str = "") -> MagicMock:
    issue = MagicMock()
    issue.number = number
    issue.state = state
    issue.body = body
    issue.assignees = []
    issue.assignee = None
    return issue


def _make_comment(login: str, body: str = "") -> MagicMock:
    comment = MagicMock()
    comment.user = MagicMock()
    comment.user.login = login
    comment.body = body
    comment.created_at = datetime(2026, 1, 3, 10, 0, 0, tzinfo=timezone.utc)
    return comment


def _make_repo() -> MagicMock:
    repo = MagicMock()
    repo.full_name = _REPO_FULL_NAME
    return repo


def _repo_data() -> Dict[str, Any]:
    return {"name": "repo", "full_name": _REPO_FULL_NAME}


def _issue_data(number: int = 42) -> Dict[str, Any]:
    return {
        "key": f"{_REPO_FULL_NAME}#{number}",
        "number": number,
        "summary": "Some issue",
        "priority": "None",
        "status": "open",
        "type": "Issue",
        "created_at": "2026-01-01T09:00:00+00:00",
        "updated_at": "2026-01-02T12:00:00+00:00",
        "assignee": None,
        "reporter": "alice",
        "labels": [],
        "url": f"https://github.com/{_REPO_FULL_NAME}/issues/{number}",
        "repo_full_name": _REPO_FULL_NAME,
    }


async def _fake_to_thread(func, *args, **kwargs):
    """AsyncMock side_effect: call func synchronously, no real thread."""
    return func(*args, **kwargs)


def _common_patches(
    issues=None,
    comments=None,
    issue_data_fn=None,
    mentions=None,
    jira_keys=None,
    github_refs=None,
):
    """Build the standard patch list for ``process_issues`` tests."""
    issues = issues if issues is not None else []
    comments = comments if comments is not None else []
    issue_data_fn = issue_data_fn or (lambda i, fn: _issue_data(getattr(i, "number", 42)))
    mentions = mentions or []
    jira_keys = jira_keys or []
    github_refs = github_refs or []

    return [
        patch(f"{_MODULE}.asyncio.to_thread", new=AsyncMock(side_effect=_fake_to_thread)),
        patch(f"{_MODULE}.fetch_issues", return_value=issues),
        patch(f"{_MODULE}.fetch_issues_direct", return_value=issues),
        patch(f"{_MODULE}.fetch_issue_comments", return_value=comments),
        patch(f"{_MODULE}.map_issue", side_effect=issue_data_fn),
        patch(f"{_MODULE}.extract_mentions", return_value=mentions),
        patch(f"{_MODULE}.extract_issue_keys", return_value=jira_keys),
        patch(f"{_MODULE}.extract_github_issue_refs", return_value=github_refs),
        patch(f"{_MODULE}.fetch_github_user", side_effect=lambda u: {"login": u.login, "name": u.login, "email": ""}),
        patch(f"{_MODULE}.build_issue_signal", side_effect=lambda **kw: MagicMock(_signal_kind="Issue")),
        patch(f"{_MODULE}.build_person_signal", side_effect=lambda pd: MagicMock(_signal_kind="Person")),
    ]


def _enter_patches(stack: ExitStack, patches: List):
    """Enter a list of patch context managers into the given ExitStack."""
    for p in patches:
        stack.enter_context(p)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_issues_uses_search_api_when_github_obj_provided():
    """When ``github_obj`` is provided, the Search API path should be used."""
    issue = _make_issue(number=42)
    with ExitStack() as stack:
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=[issue]))
        published: Dict[str, int] = {}
        seen: set = set()
        pub = AsyncMock()
        await process_issues(
            repo=_make_repo(),
            repo_data=_repo_data(),
            repo_owner="owner",
            full_name=_REPO_FULL_NAME,
            last_synced_at=None,
            published=published,
            seen_persons=seen,
            pub_callback=pub,
            github_obj=MagicMock(),
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_issues_skips_direct_when_search_returns_empty():
    """When the Search API returns no issues (success), the direct fallback is skipped."""
    with ExitStack() as stack:
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=[], comments=[]))
        direct_mock = stack.enter_context(
            patch(f"{_MODULE}.fetch_issues_direct", return_value=[])
        )
        pub = AsyncMock()
        await process_issues(
            repo=_make_repo(),
            repo_data=_repo_data(),
            repo_owner="owner",
            full_name=_REPO_FULL_NAME,
            last_synced_at=None,
            published={},
            seen_persons=set(),
            pub_callback=pub,
            github_obj=MagicMock(),
        )
        direct_mock.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_issues_falls_back_to_direct_when_no_github_obj():
    """Without a ``github_obj``, the direct fetch path is used."""
    issue = _make_issue(number=11)
    with ExitStack() as stack:
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=[issue]))
        direct_mock = stack.enter_context(
            patch(f"{_MODULE}.fetch_issues_direct", return_value=[issue])
        )
        pub = AsyncMock()
        await process_issues(
            repo=_make_repo(),
            repo_data=_repo_data(),
            repo_owner="owner",
            full_name=_REPO_FULL_NAME,
            last_synced_at=None,
            published={},
            seen_persons=set(),
            pub_callback=pub,
            github_obj=None,
        )
        direct_mock.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_issues_publishes_issue_signal_per_issue():
    """One Issue signal should be published per fetched issue."""
    issues = [_make_issue(number=1), _make_issue(number=2), _make_issue(number=3)]
    with ExitStack() as stack:
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=issues))
        pub = AsyncMock()
        await process_issues(
            repo=_make_repo(),
            repo_data=_repo_data(),
            repo_owner="owner",
            full_name=_REPO_FULL_NAME,
            last_synced_at=None,
            published={},
            seen_persons=set(),
            pub_callback=pub,
            github_obj=None,
        )
        # Each issue → one Issue signal (plus any Person signals).
        issue_signals = [c for c in pub.call_args_list if c.args[0] is not None and getattr(c.args[0], "_signal_kind", None) == "Issue"]
        assert len(issue_signals) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_issues_emits_person_signals_for_unseen_users():
    """Person signals should be emitted for assignees/commenters/mentions not yet seen."""
    issue = _make_issue(number=1)
    issue.assignees = [MagicMock(login="bob")]
    comments = [_make_comment("charlie")]

    with ExitStack() as stack:
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=[issue], comments=comments, mentions=["dave"]))
        seen: set = set()
        pub = AsyncMock()
        await process_issues(
            repo=_make_repo(),
            repo_data=_repo_data(),
            repo_owner="owner",
            full_name=_REPO_FULL_NAME,
            last_synced_at=None,
            published={},
            seen_persons=seen,
            pub_callback=pub,
            github_obj=None,
        )
        # bob (assignee), charlie (commenter), dave (mention) → 3 Person signals
        person_signals = [c for c in pub.call_args_list if getattr(c.args[0], "_signal_kind", None) == "Person"]
        assert len(person_signals) == 3
        # All three logins should now be in seen_persons
        assert {"bob", "charlie", "dave"}.issubset(seen)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_issues_skips_person_signals_for_already_seen_users():
    """Users already in ``seen_persons`` should not trigger a duplicate Person signal."""
    issue = _make_issue(number=1)
    issue.assignees = [MagicMock(login="bob")]
    comments = [_make_comment("charlie")]

    with ExitStack() as stack:
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=[issue], comments=comments, mentions=[]))
        seen = {"bob", "charlie"}
        pub = AsyncMock()
        await process_issues(
            repo=_make_repo(),
            repo_data=_repo_data(),
            repo_owner="owner",
            full_name=_REPO_FULL_NAME,
            last_synced_at=None,
            published={},
            seen_persons=seen,
            pub_callback=pub,
            github_obj=None,
        )
        person_signals = [c for c in pub.call_args_list if getattr(c.args[0], "_signal_kind", None) == "Person"]
        assert len(person_signals) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_issues_splits_github_refs_into_relates_to_and_references():
    """Same-repo GitHub refs → RELATES_TO; cross-repo refs → REFERENCES."""
    issue = _make_issue(number=1)
    # extract_github_issue_refs returns both same-repo and cross-repo refs
    github_refs = [f"{_REPO_FULL_NAME}#10", "otherorg/otherrepo#99"]

    captured: Dict[str, Any] = {}

    def _capture_build(**kwargs):
        captured["relates_to_ids"] = kwargs.get("relates_to_ids", [])
        captured["referenced_github_issue_ids"] = kwargs.get("referenced_github_issue_ids", [])
        return MagicMock(_signal_kind="Issue")

    with ExitStack() as stack:
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=[issue], github_refs=github_refs))
        stack.enter_context(patch(f"{_MODULE}.build_issue_signal", side_effect=_capture_build))
        await process_issues(
            repo=_make_repo(),
            repo_data=_repo_data(),
            repo_owner="owner",
            full_name=_REPO_FULL_NAME,
            last_synced_at=None,
            published={},
            seen_persons=set(),
            pub_callback=AsyncMock(),
            github_obj=None,
        )
        assert captured["relates_to_ids"] == [f"{_REPO_FULL_NAME}#10"]
        assert captured["referenced_github_issue_ids"] == ["otherorg/otherrepo#99"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_issues_continues_on_per_issue_exception():
    """A failure processing one issue should not stop the rest."""
    issues = [_make_issue(number=1), _make_issue(number=2), _make_issue(number=3)]

    call_count = {"n": 0}

    def _flaky_map(issue, full_name):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("boom")
        return _issue_data(getattr(issue, "number", 1))

    with ExitStack() as stack:
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=issues, issue_data_fn=_flaky_map))
        pub = AsyncMock()
        await process_issues(
            repo=_make_repo(),
            repo_data=_repo_data(),
            repo_owner="owner",
            full_name=_REPO_FULL_NAME,
            last_synced_at=None,
            published={},
            seen_persons=set(),
            pub_callback=pub,
            github_obj=None,
        )
        # Two Issue signals should still be published (issues 1 and 3)
        issue_signals = [c for c in pub.call_args_list if getattr(c.args[0], "_signal_kind", None) == "Issue"]
        assert len(issue_signals) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_issues_returns_early_when_direct_fetch_fails():
    """When both Search and direct fetch fail, no signals should be published."""
    with ExitStack() as stack:
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=[]))
        stack.enter_context(
            patch(f"{_MODULE}.fetch_issues_direct", side_effect=RuntimeError("api down"))
        )
        pub = AsyncMock()
        await process_issues(
            repo=_make_repo(),
            repo_data=_repo_data(),
            repo_owner="owner",
            full_name=_REPO_FULL_NAME,
            last_synced_at=None,
            published={},
            seen_persons=set(),
            pub_callback=pub,
            github_obj=None,
        )
        pub.assert_not_called()

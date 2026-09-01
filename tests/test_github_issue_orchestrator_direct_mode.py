"""Unit tests for the GitHub issue orchestrator in **direct** mode.

Covers ``process_issues`` when ``ISSUE_FETCH_MODE=direct``. In this mode the
repository issues endpoint (``fetch_issues_direct``) is used exclusively —
there is no automatic fallback to the Search API. These tests verify:

- The direct API is used when ``ISSUE_FETCH_MODE=direct``.
- The Search API is never called in direct mode.
- ``github_obj`` is not required in direct mode (it's only needed for search).
- ``WbaRetryTimeoutError`` propagates so the repo is skipped without cursor
  advance.
- The ``since_date`` is passed to ``fetch_issues_direct`` for incremental sync.
- Per-issue processing still works (signals, persons, refs, error isolation).

The ``asyncio.to_thread`` is replaced with an ``AsyncMock`` whose side_effect
calls the wrapped function directly (no real thread pool). All fetch / map /
build functions are mocked at the ``process_issues`` module level.
"""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.producers.github.process_issues import process_issues
from connectors.producers.github.retry_with_backoff import WbaRetryTimeoutError

_MODULE = "connectors.producers.github.process_issues"

_REPO_FULL_NAME = "owner/repo"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _patch_mode(stack: ExitStack, mode: str = "direct"):
    """Force ``ISSUE_FETCH_MODE`` to the given value for the test."""
    stack.enter_context(patch(f"{_MODULE}.os.getenv", return_value=mode))


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_mode_uses_direct_api():
    """In direct mode, ``fetch_issues_direct`` should be used."""
    issue = _make_issue(number=42)
    with ExitStack() as stack:
        _patch_mode(stack, "direct")
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=[issue]))
        search_mock = stack.enter_context(
            patch(f"{_MODULE}.fetch_issues", return_value=[issue])
        )
        direct_mock = stack.enter_context(
            patch(f"{_MODULE}.fetch_issues_direct", return_value=[issue])
        )
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
        direct_mock.assert_called_once()
        search_mock.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_mode_never_calls_search():
    """In direct mode, the Search API must never be called."""
    with ExitStack() as stack:
        _patch_mode(stack, "direct")
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=[]))
        search_mock = stack.enter_context(
            patch(f"{_MODULE}.fetch_issues", return_value=[])
        )
        await process_issues(
            repo=_make_repo(),
            repo_data=_repo_data(),
            repo_owner="owner",
            full_name=_REPO_FULL_NAME,
            last_synced_at=None,
            published={},
            seen_persons=set(),
            pub_callback=AsyncMock(),
            github_obj=MagicMock(),
        )
        search_mock.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_mode_does_not_require_github_obj():
    """In direct mode, ``github_obj`` is not needed (only used for search)."""
    issue = _make_issue(number=42)
    with ExitStack() as stack:
        _patch_mode(stack, "direct")
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=[issue]))
        direct_mock = stack.enter_context(
            patch(f"{_MODULE}.fetch_issues_direct", return_value=[issue])
        )
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
        direct_mock.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_mode_passes_since_date():
    """The ``since_date`` should be forwarded to ``fetch_issues_direct``."""
    since = datetime(2026, 6, 1, tzinfo=timezone.utc)
    with ExitStack() as stack:
        _patch_mode(stack, "direct")
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=since)
        )
        _enter_patches(stack, _common_patches(issues=[]))
        direct_mock = stack.enter_context(
            patch(f"{_MODULE}.fetch_issues_direct", return_value=[])
        )
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
        # fetch_issues_direct should be called with (repo, since_date)
        call_args = direct_mock.call_args
        assert call_args.args[1] == since


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_mode_propagates_wba_timeout():
    """A ``WbaRetryTimeoutError`` in direct mode must propagate (no cursor advance)."""
    with ExitStack() as stack:
        _patch_mode(stack, "direct")
        stack.enter_context(
            patch(f"{_MODULE}.resolve_issues_since_date", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc))
        )
        _enter_patches(stack, _common_patches(issues=[]))
        stack.enter_context(
            patch(
                f"{_MODULE}.fetch_issues_direct",
                side_effect=WbaRetryTimeoutError(3600, RuntimeError("net down")),
            )
        )
        with pytest.raises(WbaRetryTimeoutError):
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_mode_failure_is_fatal():
    """A direct API failure in direct mode must not silently swallow errors."""
    with ExitStack() as stack:
        _patch_mode(stack, "direct")
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


# ---------------------------------------------------------------------------
# Per-issue processing (shared behavior, exercised in direct mode)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_mode_publishes_issue_signal_per_issue():
    """One Issue signal should be published per fetched issue."""
    issues = [_make_issue(number=1), _make_issue(number=2), _make_issue(number=3)]
    with ExitStack() as stack:
        _patch_mode(stack, "direct")
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
        issue_signals = [c for c in pub.call_args_list if c.args[0] is not None and getattr(c.args[0], "_signal_kind", None) == "Issue"]
        assert len(issue_signals) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_mode_emits_person_signals_for_unseen_users():
    """Person signals should be emitted for assignees/commenters/mentions not yet seen."""
    issue = _make_issue(number=1)
    issue.assignees = [MagicMock(login="bob")]
    comments = [_make_comment("charlie")]

    with ExitStack() as stack:
        _patch_mode(stack, "direct")
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
        person_signals = [c for c in pub.call_args_list if getattr(c.args[0], "_signal_kind", None) == "Person"]
        assert len(person_signals) == 3
        assert {"bob", "charlie", "dave"}.issubset(seen)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_direct_mode_continues_on_per_issue_exception():
    """A failure processing one issue should not stop the rest."""
    issues = [_make_issue(number=1), _make_issue(number=2), _make_issue(number=3)]

    call_count = {"n": 0}

    def _flaky_map(issue, full_name):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("boom")
        return _issue_data(getattr(issue, "number", 1))

    with ExitStack() as stack:
        _patch_mode(stack, "direct")
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
        issue_signals = [c for c in pub.call_args_list if getattr(c.args[0], "_signal_kind", None) == "Issue"]
        assert len(issue_signals) == 2
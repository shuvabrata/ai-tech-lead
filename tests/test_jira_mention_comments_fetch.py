"""Integration tests for Plan 018 Phase 1 — Jira comments and @mentions.

These tests connect to a **real Jira instance** and validate the Phase 1
fetch + map layer against live data.  They are designed to work on any Jira
instance — they find the first entity with comments/mentions rather than
depending on specific issue keys.

**Architecture:**
    These tests call the FastAPI app **in-process** via ``httpx.ASGITransport``
    (no running server needed).  Jira credentials are fetched from the API
    server's ``GET /api/v1/connectors/jira/configs?include_secrets=true``
    endpoint — no ``.config.json`` file access.

**Self-discovering:**
    The test suite calls the API to check whether a Jira connector is
    configured and enabled.  If no enabled config exists, every test is
    skipped automatically.  No environment variable or marker is needed.

**Prerequisites:**
    - At least one Jira config item stored in the database (via the Settings UI
      or API) with ``enabled=true`` and valid credentials.
    - The database must be accessible (PostgreSQL running).

**Run:**
    pytest -m integration tests/test_jira_mention_comments_fetch.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
import pytest

from app.main import app
from connectors.producers.jira.fetch_jira import (
    fetch_comments,
    fetch_epics,
    fetch_initiatives,
    fetch_issues,
    resolve_jql_date_field,
)
from connectors.producers.jira.jira_config import create_jira_connection
from connectors.producers.jira.map_jira import (
    extract_mentions_from_adf,
    extract_mentions_from_texts,
)

# ---------------------------------------------------------------------------
# Module-level skip gate — every test inherits this
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# API helpers — call the FastAPI app in-process via ASGI transport
# ---------------------------------------------------------------------------


async def _api_get(path: str, **params: Any) -> httpx.Response:
    """Issue a GET against the in-process FastAPI app."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.get(path, params=params)


async def _fetch_jira_config() -> Optional[Dict[str, Any]]:
    """Return the first enabled Jira config item from the API, or skip.

    Calls ``GET /api/v1/connectors/jira/configs?include_secrets=true`` to
    retrieve decrypted credentials.  If the API is unreachable, the database
    is empty, or no config is enabled, the entire test suite is skipped.
    """
    try:
        resp = await _api_get(
            "/api/v1/connectors/jira/configs", include_secrets="true"
        )
    except Exception as exc:
        pytest.skip(
            f"Could not reach Jira configs API — is PostgreSQL running? ({exc})"
        )
    if resp.status_code != 200:
        pytest.skip(
            f"Jira configs endpoint returned {resp.status_code} — "
            "is the database running and populated?"
        )
    items: List[Dict[str, Any]] = resp.json()
    if not items:
        pytest.skip("No Jira config items in the database")
    enabled = [item for item in items if item.get("enabled", False)]
    if not enabled:
        pytest.skip("No enabled Jira config items in the database")
    return enabled[0]


# ---------------------------------------------------------------------------
# Module-level Jira connection cache — authenticate once, reuse across tests
# ---------------------------------------------------------------------------

_jira: Any = None


def _get_jira() -> Any:
    """Return the cached Jira connection, authenticating on first call.

    All tests share the same connection so we don't exhaust the DB pool
    by creating a new ASGI transport + session per test.
    """
    global _jira
    if _jira is not None:
        return _jira

    import asyncio

    async def _connect_once() -> Any:
        config = await _fetch_jira_config()
        return create_jira_connection({"account": [config]})

    _jira = asyncio.run(_connect_once())
    return _jira


def _find_first_with_comments(
    jira: Any, issues: List[Dict[str, Any]]
) -> Dict[str, Any] | None:
    """Scan *issues* until one with ≥1 comment is found; return its raw dict.

    Returns ``None`` when no issue in the list has comments.
    """
    for raw in issues:
        key = raw.get("key", "?")
        comments = fetch_comments(jira, key, max_results=5)
        if comments:
            return raw
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResolveJqlDateFieldLive:
    """``resolve_jql_date_field`` produces JQL that the real instance accepts."""

    def test_first_run_jql_is_accepted(self) -> None:
        """First-run JQL (``created >=``) must return results from the API."""
        jira = _get_jira()
        field, date_str = resolve_jql_date_field(365, None)
        assert field == "created"
        results = fetch_issues(jira, lookback_days=365, max_results_per_page=5)
        assert isinstance(results, list), "fetch_issues must return a list"

    def test_incremental_jql_is_accepted(self) -> None:
        """Incremental JQL (``updated >=``) must be accepted by the API."""
        jira = _get_jira()
        cursor = datetime.now(timezone.utc) - timedelta(days=30)
        field, date_str = resolve_jql_date_field(365, cursor)
        assert field == "updated"
        assert date_str.startswith('"') and date_str.endswith('"'), (
            f"Incremental date must be quoted for JQL, got: {date_str!r}"
        )
        results = fetch_issues(
            jira, lookback_days=365, max_results_per_page=5, last_synced_at=cursor
        )
        assert isinstance(results, list), "fetch_issues (incremental) must return a list"


class TestFetchCommentsLive:
    """``fetch_comments`` returns real data from the Jira REST API."""

    def test_fetch_comments_on_issue_with_comments(self) -> None:
        """Find the first Issue with ≥1 comment and verify the response shape."""
        jira = _get_jira()
        issues = fetch_issues(jira, lookback_days=365, max_results_per_page=50)
        if not issues:
            pytest.skip("No issues found in the Jira instance")

        target = _find_first_with_comments(jira, issues)
        if target is None:
            pytest.skip("No Jira Issue with comments found — nothing to validate")

        key = target["key"]
        comments = fetch_comments(jira, key)
        assert len(comments) >= 1, f"Issue {key} should have ≥1 comment"
        first = comments[0]
        assert "id" in first, "Comment must have an 'id' field"
        assert "author" in first, "Comment must have an 'author' field"
        assert "created" in first, "Comment must have a 'created' field"
        author = first.get("author") or {}
        assert "accountId" in author, (
            f"Comment author must have accountId; got keys={list(author.keys())}"
        )

    def test_fetch_comments_on_initiative_with_comments(self) -> None:
        """Find the first Initiative with ≥1 comment and verify the response."""
        jira = _get_jira()
        initiatives = fetch_initiatives(
            jira, lookback_days=365, max_results_per_page=50
        )
        if not initiatives:
            pytest.skip("No initiatives found in the Jira instance")

        target = _find_first_with_comments(jira, initiatives)
        if target is None:
            pytest.skip("No Jira Initiative with comments found — nothing to validate")

        key = target["key"]
        comments = fetch_comments(jira, key)
        assert len(comments) >= 1, f"Initiative {key} should have ≥1 comment"
        assert "author" in comments[0], "Comment must have an 'author' field"


class TestExtractMentionsLive:
    """``extract_mentions_from_texts`` works on real ADF content."""

    def test_extract_mentions_from_issue_with_mentions(self) -> None:
        """Find the first Issue with an @mention and verify extraction."""
        jira = _get_jira()
        issues = fetch_issues(jira, lookback_days=365, max_results_per_page=50)
        if not issues:
            pytest.skip("No issues found in the Jira instance")

        found_mention = False
        for raw in issues:
            key = raw.get("key", "?")
            comments = fetch_comments(jira, key, max_results=50)
            if not comments:
                continue

            description = raw.get("fields", {}).get("description")
            body_docs = [c.get("body") for c in comments if c.get("body")]
            mentions = extract_mentions_from_texts(description, body_docs)

            if mentions:
                found_mention = True
                for m in mentions:
                    assert isinstance(m, str) and len(m) > 0, (
                        f"Mention must be a non-empty string, got {m!r} "
                        f"on issue {key}"
                    )
                if body_docs:
                    adf_result = extract_mentions_from_adf(body_docs[0])
                    assert isinstance(adf_result, list), (
                        "extract_mentions_from_adf must return a list"
                    )
                break

        if not found_mention:
            pytest.skip(
                "No Jira Issue with @mentions found — "
                "add a comment with an @mention to any issue and re-run"
            )

    def test_extract_mentions_from_initiative_with_mentions(self) -> None:
        """Find the first Initiative with an @mention and verify extraction."""
        jira = _get_jira()
        initiatives = fetch_initiatives(
            jira, lookback_days=365, max_results_per_page=50
        )
        if not initiatives:
            pytest.skip("No initiatives found in the Jira instance")

        found_mention = False
        for raw in initiatives:
            key = raw.get("key", "?")
            comments = fetch_comments(jira, key, max_results=50)
            if not comments:
                continue

            description = raw.get("fields", {}).get("description")
            body_docs = [c.get("body") for c in comments if c.get("body")]
            mentions = extract_mentions_from_texts(description, body_docs)

            if mentions:
                found_mention = True
                for m in mentions:
                    assert isinstance(m, str) and len(m) > 0, (
                        f"Mention must be a non-empty string, got {m!r} "
                        f"on initiative {key}"
                    )
                break

        if not found_mention:
            pytest.skip(
                "No Jira Initiative with @mentions found — "
                "add a comment with an @mention to any initiative and re-run"
            )


class TestFetchFunctionsWithLastSyncedAt:
    """``fetch_*`` functions accept ``last_synced_at`` and return results."""

    def test_fetch_issues_with_last_synced_at(self) -> None:
        """``fetch_issues(last_synced_at=...)`` must not raise."""
        jira = _get_jira()
        cursor = datetime.now(timezone.utc) - timedelta(days=30)
        results = fetch_issues(
            jira, lookback_days=365, max_results_per_page=5, last_synced_at=cursor
        )
        assert isinstance(results, list)

    def test_fetch_epics_with_last_synced_at(self) -> None:
        """``fetch_epics(last_synced_at=...)`` must not raise."""
        jira = _get_jira()
        cursor = datetime.now(timezone.utc) - timedelta(days=30)
        results = fetch_epics(
            jira, lookback_days=365, max_results_per_page=5, last_synced_at=cursor
        )
        assert isinstance(results, list)

    def test_fetch_initiatives_with_last_synced_at(self) -> None:
        """``fetch_initiatives(last_synced_at=...)`` must not raise."""
        jira = _get_jira()
        cursor = datetime.now(timezone.utc) - timedelta(days=30)
        results = fetch_initiatives(
            jira, lookback_days=365, max_results_per_page=5, last_synced_at=cursor
        )
        assert isinstance(results, list)
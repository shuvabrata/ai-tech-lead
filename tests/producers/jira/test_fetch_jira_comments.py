"""Unit tests for Jira comment fetching and JQL date-resolution logic.

Tests ``src/connectors/producers/jira/fetch_jira.py``:

- ``fetch_comments`` — paginates the Jira comment endpoint via ``startAt``.
- ``resolve_jql_date_field`` — picks ``created`` + lookback on first run and
  ``updated`` + cursor on incremental runs.
- The ``last_synced_at`` parameter threading through ``fetch_initiatives``,
  ``fetch_epics``, and ``fetch_issues``.
"""

from datetime import datetime, timedelta, timezone
from unittest import mock
from unittest.mock import Mock

import pytest

from connectors.producers.jira import fetch_jira
from connectors.producers.jira.fetch_jira import (
    fetch_comments,
    fetch_epics,
    fetch_initiatives,
    fetch_issues,
    resolve_jql_date_field,
)
from connectors.producers.github.retry_with_backoff import WbaRetryTimeoutError


# ---------------------------------------------------------------------------
# fetch_comments
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchComments:
    def test_fetch_comments_returns_list(self):
        """Happy path: comments are aggregated from the API response."""
        mock_jira = Mock()
        mock_jira.get.return_value = {
            "comments": [
                {
                    "id": "10001",
                    "author": {"accountId": "alice", "displayName": "Alice"},
                    "body": {"type": "doc"},
                    "created": "2024-03-01T10:00:00.000+0000",
                    "updated": "2024-03-01T10:00:00.000+0000",
                },
                {
                    "id": "10002",
                    "author": {"accountId": "bob", "displayName": "Bob"},
                    "body": {"type": "doc"},
                    "created": "2024-03-02T10:00:00.000+0000",
                    "updated": "2024-03-02T10:00:00.000+0000",
                },
            ],
            "total": 2,
        }

        result = fetch_comments(mock_jira, "PROJ-1")

        assert len(result) == 2
        assert result[0]["author"]["accountId"] == "alice"
        assert result[1]["author"]["accountId"] == "bob"
        mock_jira.get.assert_called_once_with(
            "rest/api/3/issue/PROJ-1/comment",
            params={"startAt": 0, "maxResults": 100},
        )

    def test_fetch_comments_empty(self):
        """Issue with no comments returns an empty list."""
        mock_jira = Mock()
        mock_jira.get.return_value = {"comments": [], "total": 0}

        result = fetch_comments(mock_jira, "PROJ-2")

        assert result == []

    def test_fetch_comments_api_error(self):
        """API error returns an empty list and does not raise."""
        mock_jira = Mock()
        mock_jira.get.side_effect = Exception("Boom")

        result = fetch_comments(mock_jira, "PROJ-3")

        assert result == []

    def test_fetch_comments_pagination(self):
        """Multiple pages are aggregated correctly via startAt."""
        mock_jira = Mock()
        page_one = {
            "comments": [
                {"id": "1", "author": {"accountId": "a"}},
                {"id": "2", "author": {"accountId": "b"}},
            ],
            "total": 3,
        }
        page_two = {
            "comments": [{"id": "3", "author": {"accountId": "c"}}],
            "total": 3,
        }
        # Return page_two only on the second call (startAt > 0).
        def _fake_get(path, params=None):  # noqa: ANN001
            if params and params.get("startAt", 0) > 0:
                return page_two
            return page_one

        mock_jira.get.side_effect = _fake_get

        result = fetch_comments(mock_jira, "PROJ-4")

        assert len(result) == 3
        assert [c["id"] for c in result] == ["1", "2", "3"]

    def test_fetch_comments_retries_on_429(self):
        """A 429 response is retried with backoff, recovering the comments.

        The atlassian ``HTTPError`` carries its response on the instance; the
        retry helper detects ``status_code == 429`` even when the body does
        NOT contain the words "rate limit" (common for Jira). After the
        retries succeed, the comments must not be dropped.
        """
        mock_jira = Mock()
        ok_response = {
            "comments": [
                {"id": "1", "author": {"accountId": "alice"}},
            ],
            "total": 1,
        }
        # Explicit calls: 2 failures then success (gradually succeed).
        calls = [_http_429(), _http_429(), ok_response]
        mock_jira.get.side_effect = calls

        with mock.patch("time.sleep"):
            result = fetch_comments(mock_jira, "PROJ-5")

        assert len(result) == 1
        assert result[0]["id"] == "1"
        # The success path finalised after retrying the two 429s.
        assert mock_jira.get.call_count == 3

    def test_fetch_comments_gives_up_after_timeout(self):
        """A persistent 429 exhausts the retry deadline and raises WbaRetryTimeoutError.

        The retry-budget exhaustion is a distinct signal that propagates so the
        config-level handler can skip this account's cursor and retry it on the
        next scan (rather than silently dropping the comments).
        """
        mock_jira = Mock()
        # A callable side_effect raises every time (persistent 429).
        def _always_429(*a, **k):  # noqa: ANN001
            raise _http_429()
        mock_jira.get.side_effect = _always_429

        # A tiny timeout forces immediate exhaustion; time.sleep is mocked so
        # the loop terminates deterministically instead of waiting the full
        # 1-hour default deadline.
        with mock.patch("time.sleep"), pytest.raises(WbaRetryTimeoutError):
            fetch_comments(mock_jira, "PROJ-6", retry_timeout=0)

    def test_fetch_comments_non_rate_limit_rethrows_to_empty(self):
        """A 404 (non-rate-limit) is NOT retried — falls through to []."""
        mock_jira = Mock()
        import requests
        mock_jira.get.side_effect = requests.HTTPError("not found")

        with mock.patch("time.sleep"):
            result = fetch_comments(mock_jira, "PROJ-7")

        assert mock_jira.get.call_count == 1
        assert result == []


def _http_429(*args, **kwargs):
    """Return an atlassian-style HTTPError whose response carries 429.

    Mirrors ``raise HTTPError(error_msg, response=response)`` in the
    atlassian client: the status code is available on the instance via
    ``e.response.status_code``, and the body text is intentionally generic
    (no "rate limit" wording) — exactly the Jira case the fix targets.
    Args/kwargs are accepted so the same factory can serve as a
    ``side_effect`` (called with path + params).
    """
    import requests
    response = Mock()
    response.status_code = 429
    # Generic error body — must still be detected as rate limiting.
    response.json.return_value = {"errorMessages": ["Too many requests"]}
    return requests.HTTPError("Too many requests", response=response)


# ---------------------------------------------------------------------------
# resolve_jql_date_field
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveJqlDateField:
    """Test the JQL date-field resolution for first vs incremental runs."""

    def test_resolve_jql_date_field_first_run(self):
        """No cursor → uses 'created' with the lookback cutoff."""
        field, date_str = resolve_jql_date_field(90, None)
        assert field == "created"
        assert date_str == fetch_jira.resolve_lookback_cutoff(90)

    def test_resolve_jql_date_field_incremental(self):
        """Cursor present → uses 'updated' with a quoted cursor timestamp."""
        cursor = datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc)
        field, date_str = resolve_jql_date_field(90, cursor)
        assert field == "updated"
        assert date_str == '"2026-08-01 10:30"'

    def test_resolve_jql_date_field_incremental_overlap(self):
        """A sync cursor is used directly without adjustment."""
        cursor = datetime(2026, 8, 22, 4, 7, tzinfo=timezone.utc)
        field, date_str = resolve_jql_date_field(90, cursor)
        assert field == "updated"
        assert date_str == '"2026-08-22 04:07"'


# ---------------------------------------------------------------------------
# last_synced_at threading into fetch functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchJqlWithLastSyncedAt:
    """Verify each fetch function uses the sync-cursor-based JQL."""

    def test_fetch_initiatives_uses_updated_on_incremental(self):
        mock_jira = Mock()
        mock_jira.enhanced_jql.return_value = {"issues": [], "nextPageToken": None}
        cursor = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
        fetch_initiatives(mock_jira, lookback_days=90, last_synced_at=cursor)
        jql = mock_jira.enhanced_jql.call_args.kwargs["jql"]
        assert 'updated >= "2026-08-01 09:00"' in jql

    def test_fetch_epics_uses_updated_on_incremental(self):
        mock_jira = Mock()
        mock_jira.enhanced_jql.return_value = {"issues": [], "nextPageToken": None}
        cursor = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
        fetch_epics(mock_jira, lookback_days=30, last_synced_at=cursor)
        jql = mock_jira.enhanced_jql.call_args.kwargs["jql"]
        assert 'updated >= "2026-08-01 09:00"' in jql

    def test_fetch_issues_uses_created_on_first_run(self):
        mock_jira = Mock()
        mock_jira.enhanced_jql.return_value = {"issues": [], "nextPageToken": None}
        fetch_issues(mock_jira, lookback_days=60)
        jql = mock_jira.enhanced_jql.call_args.kwargs["jql"]
        assert "created >=" in jql
        assert "updated" not in jql
"""Unit tests for Jira comment fetching and JQL date-resolution logic.

Tests ``src/connectors/producers/jira/fetch_jira.py``:

- ``fetch_comments`` — paginates the Jira comment endpoint via ``startAt``.
- ``resolve_jql_date_field`` — picks ``created`` + lookback on first run and
  ``updated`` + cursor on incremental runs.
- The ``last_synced_at`` parameter threading through ``fetch_initiatives``,
  ``fetch_epics``, and ``fetch_issues``.
"""

from datetime import datetime, timedelta, timezone
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
        assert "updated >= \"2026-08-01 09:00\"" in jql

    def test_fetch_epics_uses_updated_on_incremental(self):
        mock_jira = Mock()
        mock_jira.enhanced_jql.return_value = {"issues": [], "nextPageToken": None}
        cursor = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
        fetch_epics(mock_jira, lookback_days=30, last_synced_at=cursor)
        jql = mock_jira.enhanced_jql.call_args.kwargs["jql"]
        assert "updated >= \"2026-08-01 09:00\"" in jql

    def test_fetch_issues_uses_created_on_first_run(self):
        mock_jira = Mock()
        mock_jira.enhanced_jql.return_value = {"issues": [], "nextPageToken": None}
        fetch_issues(mock_jira, lookback_days=60)
        jql = mock_jira.enhanced_jql.call_args.kwargs["jql"]
        assert "created >=" in jql
        assert "updated" not in jql
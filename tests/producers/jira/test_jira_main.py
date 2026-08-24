import pytest
from unittest.mock import patch, Mock
import os
import requests
import time

from connectors.producers.jira.main import load_config_from_server

# --- Tests for load_config_from_server ---

@patch('connectors.producers.jira.jira_config.requests.get')
def test_load_config_from_server_success(mock_get, monkeypatch):
    """
    Test successful configuration loading from the server for Jira.
    """
    monkeypatch.setenv("API_SERVER", "http://mock-server:8000")
    
    # Mock the API response
    mock_api_response = [
        {
            "id": 1,
            "url": "https://test.atlassian.net",
            "email": "test@example.com",
            "api_token": "token123"
        }
    ]
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_api_response
    mock_get.return_value = mock_response

    # Call the function
    config = load_config_from_server()

    # Assertions
    expected_config = {
        "account": [
            {
                "id": 1,
                "url": "https://test.atlassian.net",
                "email": "test@example.com",
                "api_token": "token123"
            }
        ]
    }
    assert config == expected_config
    
    # Verify requests.get was called correctly
    mock_get.assert_called_once_with(
        "http://mock-server:8000/api/v1/connectors/jira/configs",
        params={'include_secrets': 'true'},
        timeout=10
    )

@patch('connectors.producers.jira.jira_config.requests.get')
def test_load_config_from_server_http_error(mock_get, monkeypatch):
    """
    Test handling of an HTTP error from the server for Jira.
    """
    monkeypatch.setenv("API_SERVER", "http://mock-server:8000")
    
    # Mock a failed API response
    mock_get.side_effect = requests.exceptions.HTTPError("404 Not Found")

    # Assert that the correct exception is raised
    with pytest.raises(requests.exceptions.HTTPError):
        load_config_from_server()

# --- New tests for main() config logic ---

def setup_downstream_mocks(mock_jira_conn, mock_driver):
    """Helper to set up mocks for calls made after config loading."""
    mock_jira_conn.return_value.myself.return_value = {"displayName": "test"}
    # Mock fetch functions to return empty lists to prevent further processing
    mock_jira_conn.return_value.get.return_value = {'values': [], 'total': 0}
    mock_jira_conn.return_value.enhanced_jql.return_value = {'issues': []}

    mock_driver_instance = mock_driver.return_value
    mock_driver_instance.verify_connectivity.return_value = None
    mock_session = mock_driver_instance.session.return_value
    mock_session.__enter__.return_value = mock_session
    mock_session.__exit__.return_value = None


# ═══════════════════════════════════════════════════════════════════════════
#  test_connection — connectivity check
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestJiraTestConnection:
    """Tests for ``test_connection()`` in ``jira.main``."""

    @patch.dict(os.environ, {"TEST_ITEM_ID": ""}, clear=True)
    @pytest.mark.asyncio
    async def test_jira_test_connection_success(self):
        """Valid credentials → returns (True, "Authenticated as ...")."""
        mock_jira = Mock()
        mock_jira.myself.return_value = {"displayName": "Alice Dev", "emailAddress": "alice@example.com"}

        with (
            patch("connectors.producers.jira.main.load_config_from_file") as mock_load,
            patch("connectors.producers.jira.main.create_jira_connection", return_value=mock_jira),
        ):
            mock_load.return_value = {
                "account": [
                    {"url": "https://test.atlassian.net", "email": "a@b.com", "api_token": "tok", "enabled": True},
                ]
            }
            from connectors.producers.jira.main import test_connection
            success, message = await test_connection()

        assert success is True
        assert "Authenticated as Alice Dev" in message

    @patch.dict(os.environ, {"TEST_ITEM_ID": ""}, clear=True)
    @pytest.mark.asyncio
    async def test_jira_test_connection_failure(self):
        """Invalid credentials → returns (False, "Jira auth failed ...")."""
        with (
            patch("connectors.producers.jira.main.load_config_from_file") as mock_load,
            patch("connectors.producers.jira.main.create_jira_connection") as mock_create,
        ):
            mock_load.return_value = {
                "account": [
                    {"url": "https://test.atlassian.net", "email": "a@b.com", "api_token": "bad_tok", "enabled": True},
                ]
            }
            mock_create.side_effect = Exception("Invalid credentials")
            from connectors.producers.jira.main import test_connection
            success, message = await test_connection()

        assert success is False
        assert "Jira auth failed" in message

    @patch.dict(os.environ, {"TEST_ITEM_ID": "7"}, clear=True)
    @pytest.mark.asyncio
    async def test_jira_test_connection_with_item_id(self):
        """Filters to specific item_id, tests only that one."""
        mock_jira = Mock()
        mock_jira.myself.return_value = {"displayName": "Filtered User"}

        with (
            patch("connectors.producers.jira.main.load_config_from_file") as mock_load,
            patch("connectors.producers.jira.main.create_jira_connection", return_value=mock_jira),
        ):
            mock_load.return_value = {
                "account": [
                    {"id": 7, "url": "https://test.atlassian.net", "email": "a@b.com", "api_token": "tok", "enabled": True},
                ]
            }
            from connectors.producers.jira.main import test_connection
            success, message = await test_connection()

        assert success is True
        assert "Filtered User" in message

    @patch.dict(os.environ, {"TEST_ITEM_ID": "999"}, clear=True)
    @pytest.mark.asyncio
    async def test_jira_test_connection_item_id_not_found(self):
        """Unknown item_id → returns (False, "No Jira account config found ...")."""
        with patch("connectors.producers.jira.main.load_config_from_file") as mock_load:
            mock_load.return_value = {
                "account": [
                    {"id": 1, "url": "https://test.atlassian.net", "email": "a@b.com", "api_token": "tok", "enabled": True},
                ]
            }
            from connectors.producers.jira.main import test_connection
            success, message = await test_connection()

        assert success is False
        assert "No Jira account config found with id=999" in message

    @patch.dict(os.environ, {"TEST_ITEM_ID": ""}, clear=True)
    @pytest.mark.asyncio
    async def test_jira_test_connection_no_enabled_configs(self):
        """No enabled accounts → returns (False, "No enabled Jira account configurations to test")."""
        with patch("connectors.producers.jira.main.load_config_from_file") as mock_load:
            mock_load.return_value = {"account": []}
            from connectors.producers.jira.main import test_connection
            success, message = await test_connection()

        assert success is False
        assert "No enabled Jira account configurations" in message


@pytest.mark.unit
class TestJiraGetTestItemId:
    """Tests for ``_get_test_item_id()`` in ``jira.main``."""

    def test_test_item_id_env_var(self):
        """``TEST_ITEM_ID`` env var parsed correctly."""
        with patch.dict(os.environ, {"TEST_ITEM_ID": "42"}, clear=True):
            from connectors.producers.jira.main import _get_test_item_id
            assert _get_test_item_id() == 42

    def test_test_item_id_env_var_missing(self):
        """No env var → returns None."""
        with patch.dict(os.environ, {}, clear=True):
            from connectors.producers.jira.main import _get_test_item_id
            assert _get_test_item_id() is None


# ═══════════════════════════════════════════════════════════════════════════
#  _process_entities — bounded concurrency for per-entity comment fetching
#  (plan 022)
# ═══════════════════════════════════════════════════════════════════════════


def _issue_raw(account_id: str) -> dict:
    """A single Jira issue entity with an assignee and no comments."""
    return {
        "id": account_id,
        "key": f"PROJ-{account_id}",
        "fields": {
            "description": None,
            "assignee": {
                "accountId": f"a-{account_id}",
                "displayName": f"Assignee {account_id}",
            },
            "reporter": {
                "accountId": f"r-{account_id}",
                "displayName": f"Reporter {account_id}",
            },
            "project": {"key": "PROJ"},
        },
    }


_FETCH_LATENCY = 0.3  # seconds per mocked comment fetch


def _slow_fetch_comments(jira, jira_issue_id):
    """Stand-in for ``fetch_comments`` with a fixed latency.

    Returns a single comment authored by ``jira_issue_id``. The sleep makes
    concurrent processing observable in wall-clock time, mirroring a real
    Jira API round-trip.
    """
    time.sleep(_FETCH_LATENCY)
    return [
        {
            "author": {
                "accountId": jira_issue_id,
                "displayName": f"User {jira_issue_id}",
            },
            "created": "2024-06-01T10:00:00.000+0000",
            "body": {"type": "doc", "content": []},
        }
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_issue_comment_fetch_sequential_by_default(monkeypatch):
    """Default (concurrency=1) fetches comments sequentially.

    Three entities each sleeping ``_FETCH_LATENCY`` must take at least
    ``2 * _FETCH_LATENCY`` (i.e. they did NOT overlap). A broken
    implementation that always parallelized would complete in ~1× latency and
    fail this assertion.
    """
    elapsed = await _run_comment_fetch_scenario(monkeypatch, concurrency=1)
    assert elapsed >= 2 * _FETCH_LATENCY, (
        f"expected sequential fetch (>= {2 * _FETCH_LATENCY}s) but comment "
        f"fetches overlapped ({elapsed:.2f}s)"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_issue_comment_fetch_parallel_with_concurrency(monkeypatch):
    """With ``JIRA_COMMENT_FETCH_CONCURRENCY=3``, fetches overlap.

    Three entities each sleeping ``_FETCH_LATENCY`` must complete in well
    under ``2 * _FETCH_LATENCY`` — impossible if fetches ran sequentially.
    """
    elapsed = await _run_comment_fetch_scenario(monkeypatch, concurrency=3)
    assert elapsed < 2 * _FETCH_LATENCY, (
        f"expected parallel fetch ({elapsed:.2f}s < "
        f"{2 * _FETCH_LATENCY}s) but comment fetches did not overlap"
    )


async def _run_comment_fetch_scenario(monkeypatch, concurrency: int) -> float:
    """Run ``publish_signals`` over 3 issues and return elapsed wall-clock time."""
    monkeypatch.setattr(
        "connectors.producers.jira.main._JIRA_COMMENT_FETCH_CONCURRENCY", concurrency
    )
    monkeypatch.setattr(
        "connectors.producers.jira.main._JIRA_FETCH_COMMENTS", True
    )
    monkeypatch.setattr(
        "connectors.producers.jira.main.fetch_comments", _slow_fetch_comments
    )
    monkeypatch.setattr(
        "connectors.producers.jira.main.fetch_projects", lambda *a, **k: []
    )
    monkeypatch.setattr(
        "connectors.producers.jira.main.fetch_initiatives", lambda *a, **k: []
    )
    monkeypatch.setattr(
        "connectors.producers.jira.main.fetch_epics", lambda *a, **k: []
    )
    monkeypatch.setattr(
        "connectors.producers.jira.main.fetch_issues", lambda *a, **k: [
            _issue_raw(acct) for acct in ("u1", "u2", "u3")
        ]
    )
    monkeypatch.setattr(
        "connectors.producers.jira.main.fetch_sprints_by_ids", lambda *a, **k: []
    )

    from connectors.producers.jira.main import publish_signals

    published: list = []
    class _FakePublisher:
        async def publish(self, sig):
            published.append(sig)

    start = time.monotonic()
    await publish_signals(
        _FakePublisher(),   # type: ignore[arg-type]
        jira=object(),
        jira_base_url="https://jira.example.com",
        lookback_days=30,
        max_results_per_page=100,
    )
    elapsed = time.monotonic() - start

    # Each of the 3 issues is still published regardless of concurrency.
    issue_signals = [s for s in published if s.entity_type == "Issue"]
    assert len(issue_signals) == 3

    return elapsed



import pytest
from unittest.mock import patch, Mock
import os
import requests

from connectors.producers.github.github_config import load_config_from_server

# --- Tests for load_config_from_server (converted to pytest style) ---

@patch('connectors.producers.github.github_config.requests.get')
def test_load_config_from_server_success(mock_get, monkeypatch):
    """
    Test successful configuration loading from the server.
    """
    monkeypatch.setenv("API_SERVER", "http://mock-server:8000")
    
    # Mock the API response
    mock_api_response = [
        {
            "id": 1,
            "url": "https://github.com/test/repo1",
            "access_token": "token123",
            "branch_name_patterns": ["main"],
            "extraction_sources": ["branch"]
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
        "repos": [
            {
                "id": 1,
                "enabled": True,
                "url": "https://github.com/test/repo1",
                "access_token": "token123",
                "branch_name_patterns": ["main"],
                "extraction_sources": ["branch"],
                "search_filters": {}
            }
        ]
    }
    assert config == expected_config
    
    # Verify requests.get was called correctly
    mock_get.assert_called_once_with(
        "http://mock-server:8000/api/v1/connectors/github/configs",
        params={'include_secrets': 'true'},
        timeout=10
    )

@patch('connectors.producers.github.github_config.requests.get')
def test_load_config_from_server_http_error(mock_get, monkeypatch):
    """
    Test handling of an HTTP error from the server.
    """
    monkeypatch.setenv("API_SERVER", "http://mock-server:8000")
    
    # Mock a failed API response
    mock_get.side_effect = requests.exceptions.HTTPError("404 Not Found")

    # Assert that the correct exception is raised
    with pytest.raises(requests.exceptions.HTTPError):
        load_config_from_server()


# ═══════════════════════════════════════════════════════════════════════════
#  test_connection — connectivity check
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestGitHubTestConnection:
    """Tests for ``test_connection()`` in ``github.main``."""

    @patch.dict(os.environ, {"TEST_ITEM_ID": ""}, clear=True)
    @pytest.mark.asyncio
    async def test_github_test_connection_success(self):
        """Valid token → returns (True, "Authenticated as ...")."""
        mock_user = Mock()
        mock_user.login = "testuser"

        with patch("connectors.producers.github.main.Github") as mock_github:
            mock_github.return_value.get_user.return_value = mock_user
            from connectors.producers.github.main import test_connection
            success, message = await test_connection()

        assert success is True
        assert "Authenticated as testuser" in message

    @patch.dict(os.environ, {"TEST_ITEM_ID": ""}, clear=True)
    @pytest.mark.asyncio
    async def test_github_test_connection_failure(self):
        """Invalid token → returns (False, "GitHub auth failed ...")."""
        with patch("connectors.producers.github.main.Github") as mock_github:
            mock_github.return_value.get_user.side_effect = Exception("Bad credentials")
            from connectors.producers.github.main import test_connection
            success, message = await test_connection()

        assert success is False
        assert "GitHub auth failed" in message

    @patch.dict(os.environ, {"TEST_ITEM_ID": "42"}, clear=True)
    @pytest.mark.asyncio
    async def test_github_test_connection_with_item_id(self):
        """Filters to specific item_id, tests only that one."""
        mock_user = Mock()
        mock_user.login = "filtereduser"

        with (
            patch("connectors.producers.github.main.load_config_from_file") as mock_load,
            patch("connectors.producers.github.main.Github") as mock_github,
        ):
            mock_load.return_value = {
                "repos": [
                    {"id": 42, "url": "https://github.com/owner/repo", "access_token": "tok", "enabled": True},
                ]
            }
            mock_github.return_value.get_user.return_value = mock_user
            from connectors.producers.github.main import test_connection
            success, message = await test_connection()

        assert success is True
        assert "filtereduser" in message

    @patch.dict(os.environ, {"TEST_ITEM_ID": "999"}, clear=True)
    @pytest.mark.asyncio
    async def test_github_test_connection_item_id_not_found(self):
        """Unknown item_id → returns (False, "No repository config found ...")."""
        with patch("connectors.producers.github.main.load_config_from_file") as mock_load:
            mock_load.return_value = {
                "repos": [
                    {"id": 1, "url": "https://github.com/owner/repo", "access_token": "tok", "enabled": True},
                ]
            }
            from connectors.producers.github.main import test_connection
            success, message = await test_connection()

        assert success is False
        assert "No repository config found with id=999" in message

    @patch.dict(os.environ, {"TEST_ITEM_ID": ""}, clear=True)
    @pytest.mark.asyncio
    async def test_github_test_connection_no_enabled_configs(self):
        """No enabled repos → returns (False, "No enabled repository configurations to test")."""
        with patch("connectors.producers.github.main.load_config_from_file") as mock_load:
            mock_load.return_value = {"repos": []}
            from connectors.producers.github.main import test_connection
            success, message = await test_connection()

        assert success is False
        assert "No enabled repository configurations" in message


@pytest.mark.unit
class TestGitHubGetTestItemId:
    """Tests for ``_get_test_item_id()`` in ``github.main``."""

    def test_test_item_id_env_var(self):
        """``TEST_ITEM_ID`` env var parsed correctly."""
        with patch.dict(os.environ, {"TEST_ITEM_ID": "42"}, clear=True):
            from connectors.producers.github.main import _get_test_item_id
            assert _get_test_item_id() == 42

    def test_test_item_id_env_var_missing(self):
        """No env var → returns None."""
        with patch.dict(os.environ, {}, clear=True):
            from connectors.producers.github.main import _get_test_item_id
            assert _get_test_item_id() is None


"""Unit tests for the runtime settings REST snapshot client.

Tests that ``fetch_runtime_snapshot`` correctly parses API responses,
falls back to defaults when the API is unreachable, and logs appropriate
warnings.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from common.runtime_settings import RuntimeConfig
from common.runtime_settings.client import fetch_runtime_snapshot

pytestmark = [pytest.mark.unit]


# ── Helpers ────────────────────────────────────────────────────────────


def _valid_payload(**overrides: object) -> dict[str, object]:
    """Return a valid runtime-snapshot payload with optional overrides."""
    payload: dict[str, object] = {
        "HTTP_REQUEST_TIMEOUT": 60,
        "NEO4J_QUERY_TIMEOUT": 10,
        "GRAPH_UI_MAX_NODES_TO_EXPAND": 20,
        "GRAPH_UI_MAX_NODE_LABEL_CHARS": 10,
        "CONNECTOR_SCAN_POLL_INTERVAL": 5000,
        "RECENT_ACTIONS_LIMIT": 5,
        "TIMEZONE": "UTC",
        "UI_DATETIME_FORMAT": "%b %d, %Y %I:%M %p",
        "UI_DATE_FORMAT": "%b %d, %Y",
        "AUGMENTATION_HISTORY_TURNS": 5,
        "ES_CHAIN_MAX_RESULTS": 5,
        "MAX_MCP_ITERATIONS": 3,
        "FF_NEO4J_USE_PROVIDER_PIPELINE": False,
        # ── AI / LLM ──────────────────────────────────────────────
        "LLM_PROVIDER": "openai",
        "LLM_MODEL": "gpt-5",
        "MAX_TOKENS": 16000,
        "GITHUB_MCP_ENABLED": False,
        "ATLASSIAN_MCP_ENABLED": False,
        # ── System ────────────────────────────────────────────────
        "NEO4J_ENABLED": False,
        # ── Connectors ────────────────────────────────────────────
        "COMMIT_DAYS_LIMIT": 60,
        "PULL_REQUEST_DAYS_LIMIT": 60,
        "IDENTITY_REFRESH_DAYS": 7,
        "MAX_TEAM_SIZE": 100,
        "JIRA_LOOKBACK_DAYS": 90,
        "JIRA_MAX_RESULTS_PER_PAGE": 100,
        "CONFLUENCE_LOOKBACK_DAYS": 60,
        "JIRA_EPIC_TEAM_FIELD": "Team",
        "JIRA_ISSUE_TEAM_FIELD": "Team",
        "JIRA_EPIC_START_DATE_FIELD": "created",
        "JIRA_EPIC_DUE_DATE_FIELD": "duedate",
        "API_SERVER": "http://app:8000/",
        "CONFIGURATION_SOURCE": "SERVER",
        # ── Logging ───────────────────────────────────────────────
        "LOG_LEVEL": "INFO",
        "LOG_FORMAT": "JSON",
        "ENABLE_FILE_LOGGING": False,
        "LOG_DIR": "logs",
        "LOG_SIGNAL_DUMPS": False,
    }
    payload.update(overrides)
    return payload


# ── Tests ──────────────────────────────────────────────────────────────


class TestFetchRuntimeSnapshot:
    """Verify ``fetch_runtime_snapshot`` behaviour."""

    def test_parses_valid_response(self) -> None:
        """A valid API response is parsed into a ``RuntimeConfig``."""
        with patch("common.runtime_settings.client.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                ok=True,
                json=lambda: _valid_payload(HTTP_REQUEST_TIMEOUT=90),
            )

            config = fetch_runtime_snapshot("http://app:8000")

        assert isinstance(config, RuntimeConfig)
        assert config.HTTP_REQUEST_TIMEOUT == 90
        assert config.TIMEZONE == "UTC"

    def test_uses_provided_timeout(self) -> None:
        """The *timeout* parameter is passed to ``requests.get``."""
        with patch("common.runtime_settings.client.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, ok=True, json=lambda: _valid_payload()
            )

            fetch_runtime_snapshot("http://app:8000", timeout=5)

        mock_get.assert_called_once()
        _call_kwargs = mock_get.call_args[1]
        assert _call_kwargs.get("timeout") == 5

    def test_strips_trailing_slash(self) -> None:
        """Trailing slashes on *api_base_url* are stripped."""
        with patch("common.runtime_settings.client.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, ok=True, json=lambda: _valid_payload()
            )

            fetch_runtime_snapshot("http://app:8000/")

        mock_get.assert_called_once_with(
            "http://app:8000/api/v1/settings/runtime-snapshot", timeout=10
        )

    def test_falls_back_on_connection_error(self) -> None:
        """A connection error falls back to defaults and logs a warning."""
        with patch("common.runtime_settings.client.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError(
                "Connection refused"
            )

            with patch("common.runtime_settings.client.logger.warning") as mock_warn:
                config = fetch_runtime_snapshot("http://app:8000")

        assert isinstance(config, RuntimeConfig)
        # All defaults.
        assert config.HTTP_REQUEST_TIMEOUT == 60
        assert config.TIMEZONE == "UTC"
        mock_warn.assert_called_once()

    def test_falls_back_on_timeout(self) -> None:
        """A timeout falls back to defaults and logs a warning."""
        with patch("common.runtime_settings.client.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout("Timed out")

            with patch("common.runtime_settings.client.logger.warning") as mock_warn:
                config = fetch_runtime_snapshot("http://app:8000")

        assert isinstance(config, RuntimeConfig)
        assert config.HTTP_REQUEST_TIMEOUT == 60
        mock_warn.assert_called_once()

    def test_falls_back_on_http_error(self) -> None:
        """A non-200 status falls back to defaults and logs a warning."""
        with patch("common.runtime_settings.client.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=503,
                ok=False,
                raise_for_status=MagicMock(
                    side_effect=requests.exceptions.HTTPError("503 Service Unavailable")
                ),
            )

            with patch("common.runtime_settings.client.logger.warning") as mock_warn:
                config = fetch_runtime_snapshot("http://app:8000")

        assert isinstance(config, RuntimeConfig)
        assert config.HTTP_REQUEST_TIMEOUT == 60
        mock_warn.assert_called_once()

    def test_falls_back_on_invalid_json(self) -> None:
        """Invalid JSON response falls back to defaults and logs a warning."""
        with patch("common.runtime_settings.client.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                ok=True,
                json=MagicMock(side_effect=ValueError("Invalid JSON")),
            )

            with patch("common.runtime_settings.client.logger.warning") as mock_warn:
                config = fetch_runtime_snapshot("http://app:8000")

        assert isinstance(config, RuntimeConfig)
        assert config.HTTP_REQUEST_TIMEOUT == 60
        mock_warn.assert_called_once()

    def test_falls_back_on_validation_error(self) -> None:
        """Response with invalid field values falls back to defaults."""
        with patch("common.runtime_settings.client.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                ok=True,
                json=lambda: _valid_payload(HTTP_REQUEST_TIMEOUT=-1),
            )

            with patch("common.runtime_settings.client.logger.warning") as mock_warn:
                config = fetch_runtime_snapshot("http://app:8000")

        assert isinstance(config, RuntimeConfig)
        assert config.HTTP_REQUEST_TIMEOUT == 60  # default
        mock_warn.assert_called_once()
"""Unit tests for MCP connector test-connection functionality.

Tests cover:
  - ``test_mcp_connection()`` in ``tool_executor.py`` — routing and error handling
  - ``test_connector()`` in ``service.py`` — DB status update and message formatting
  - ``handle_mcp_test_connection`` callback — API interaction and alert rendering
  - ``_render_top_action_bar`` — MCP Test Connection button visibility
  - ``_test_result_message`` — message formatting for each status
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests
from dash import no_update

from app.api.connectors.v1.registry import CONNECTOR_REGISTRY
from app.dash_app.pages.connectors.layout import _render_top_action_bar


pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════════════════════════════
#  test_mcp_connection() — tool_executor
# ═══════════════════════════════════════════════════════════════════════════


class TestMcpConnectionToolExecutor:
    """Tests for ``test_mcp_connection()`` in ``tool_executor.py``."""

    def test_github_mcp_routes_to_github_manager(self):
        """``github_mcp`` builds the GitHub manager and calls test_connection."""
        from app.ai_agent.mcp_integration.tool_executor import test_mcp_connection

        with patch(
            "app.ai_agent.mcp_integration.tool_executor._build_github_manager"
        ) as mock_build:
            mock_manager = MagicMock()
            mock_manager.test_connection.return_value = {
                "server": "github",
                "status": "connected",
                "connected": True,
                "tool_count": 5,
                "error": None,
            }
            mock_build.return_value = mock_manager

            result = test_mcp_connection("github_mcp")

        assert result["server"] == "github"
        assert result["connected"] is True
        assert result["tool_count"] == 5
        mock_manager.test_connection.assert_called_once()

    def test_atlassian_mcp_routes_to_atlassian_manager(self):
        """``atlassian_mcp`` builds the Atlassian manager and calls test_connection."""
        from app.ai_agent.mcp_integration.tool_executor import test_mcp_connection

        with patch(
            "app.ai_agent.mcp_integration.tool_executor._build_atlassian_manager"
        ) as mock_build:
            mock_manager = MagicMock()
            mock_manager.test_connection.return_value = {
                "server": "atlassian",
                "status": "connected",
                "connected": True,
                "tool_count": 12,
                "error": None,
            }
            mock_build.return_value = mock_manager

            result = test_mcp_connection("atlassian_mcp")

        assert result["server"] == "atlassian"
        assert result["connected"] is True
        assert result["tool_count"] == 12
        mock_manager.test_connection.assert_called_once()

    def test_unknown_connector_type_raises_value_error(self):
        """Non-MCP connector types raise ValueError."""
        from app.ai_agent.mcp_integration.tool_executor import test_mcp_connection

        with pytest.raises(ValueError, match="Not an MCP connector type"):
            test_mcp_connection("github")

    def test_empty_toolset_result(self):
        """Empty tool list returns connected=False with empty_toolset status."""
        from app.ai_agent.mcp_integration.tool_executor import test_mcp_connection

        with patch(
            "app.ai_agent.mcp_integration.tool_executor._build_github_manager"
        ) as mock_build:
            mock_manager = MagicMock()
            mock_manager.test_connection.return_value = {
                "server": "github",
                "status": "empty_toolset",
                "connected": False,
                "tool_count": 0,
                "error": "server returned 0 tools — token may lack scopes",
            }
            mock_build.return_value = mock_manager

            result = test_mcp_connection("github_mcp")

        assert result["connected"] is False
        assert result["tool_count"] == 0
        assert "token may lack scopes" in result["error"]

    def test_unavailable_result(self):
        """Connection failure returns connected=False with error."""
        from app.ai_agent.mcp_integration.tool_executor import test_mcp_connection

        with patch(
            "app.ai_agent.mcp_integration.tool_executor._build_github_manager"
        ) as mock_build:
            mock_manager = MagicMock()
            mock_manager.test_connection.return_value = {
                "server": "github",
                "status": "unavailable",
                "connected": False,
                "tool_count": None,
                "error": "Connection refused",
            }
            mock_build.return_value = mock_manager

            result = test_mcp_connection("github_mcp")

        assert result["connected"] is False
        assert result["tool_count"] is None
        assert result["error"] == "Connection refused"


# ═══════════════════════════════════════════════════════════════════════════
#  _test_result_message — service helper
# ═══════════════════════════════════════════════════════════════════════════


class TestResultMessage:
    """Tests for ``_test_result_message()`` in ``service.py``."""

    def test_connected_message(self):
        """Connected status shows tool count."""
        from app.api.connectors.v1.service import _test_result_message

        msg = _test_result_message("atlassian_mcp", "connected", 12, None)
        assert "connected" in msg.lower()
        assert "12 tools" in msg

    def test_empty_toolset_message(self):
        """Empty toolset status shows scope guidance."""
        from app.api.connectors.v1.service import _test_result_message

        msg = _test_result_message("atlassian_mcp", "empty_toolset", 0, "server returned 0 tools")
        assert "0 tools" in msg
        assert "scopes" in msg.lower()

    def test_disabled_message(self):
        """Disabled status shows disabled message."""
        from app.api.connectors.v1.service import _test_result_message

        msg = _test_result_message("github_mcp", "disabled", None, "github_mcp_disabled")
        assert "disabled" in msg.lower()

    def test_unavailable_message(self):
        """Unavailable status shows the error."""
        from app.api.connectors.v1.service import _test_result_message

        msg = _test_result_message("github_mcp", "unavailable", None, "Connection refused")
        assert "failed" in msg.lower()
        assert "Connection refused" in msg

    def test_unknown_status_fallback(self):
        """Unknown status still produces a non-empty message."""
        from app.api.connectors.v1.service import _test_result_message

        msg = _test_result_message("github_mcp", "bogus", None, "something")
        assert len(msg) > 0
        assert "failed" in msg.lower()


# ═══════════════════════════════════════════════════════════════════════════
#  handle_mcp_test_connection — callback
# ═══════════════════════════════════════════════════════════════════════════


class TestMcpTestConnectionCallback:
    """Tests for the ``handle_mcp_test_connection`` callback."""

    def test_successful_test_shows_green_alert(self):
        """A successful test renders a success alert with the message."""
        from app.dash_app.pages.connectors.callbacks import handle_mcp_test_connection

        with (
            patch("app.dash_app.pages.connectors.callbacks.callback_context") as mock_ctx,
            patch("app.dash_app.pages.connectors.callbacks.requests.post") as mock_post,
        ):
            mock_ctx.triggered = [
                {
                    "prop_id": '.{"type":"connector-mcp-test","connector_type":"atlassian_mcp"}.n_clicks',
                    "value": 1,
                    "type": "",
                    "index": "",
                }
            ]
            mock_ctx.triggered_id = {"type": "connector-mcp-test", "connector_type": "atlassian_mcp"}
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                "success": True,
                "message": "Atlassian MCP Server connected — 12 tools available",
                "server": "atlassian",
                "tool_count": 12,
            }
            mock_post.return_value = mock_response

            result = handle_mcp_test_connection([1])

        assert result is not None
        assert "Atlassian MCP Server connected" in str(result)
        assert "12 tools" in str(result)
        mock_post.assert_called_once()
        call_args = mock_post.call_args[0]
        assert "/api/v1/connectors/atlassian_mcp/test" in call_args[0]

    def test_failed_test_shows_red_alert(self):
        """A failed test renders a danger alert with the error message."""
        from app.dash_app.pages.connectors.callbacks import handle_mcp_test_connection

        with (
            patch("app.dash_app.pages.connectors.callbacks.callback_context") as mock_ctx,
            patch("app.dash_app.pages.connectors.callbacks.requests.post") as mock_post,
        ):
            mock_ctx.triggered = [
                {
                    "prop_id": '.{"type":"connector-mcp-test","connector_type":"github_mcp"}.n_clicks',
                    "value": 1,
                    "type": "",
                    "index": "",
                }
            ]
            mock_ctx.triggered_id = {"type": "connector-mcp-test", "connector_type": "github_mcp"}
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                "success": False,
                "message": "GitHub MCP Server connection failed: Connection refused",
                "server": "github",
                "tool_count": None,
            }
            mock_post.return_value = mock_response

            result = handle_mcp_test_connection([1])

        assert result is not None
        assert "Connection refused" in str(result)

    def test_request_exception_shows_danger_alert(self):
        """A network error renders a danger alert."""
        from app.dash_app.pages.connectors.callbacks import handle_mcp_test_connection

        with (
            patch("app.dash_app.pages.connectors.callbacks.callback_context") as mock_ctx,
            patch("app.dash_app.pages.connectors.callbacks.requests.post") as mock_post,
        ):
            mock_ctx.triggered = [
                {
                    "prop_id": '.{"type":"connector-mcp-test","connector_type":"atlassian_mcp"}.n_clicks',
                    "value": 1,
                    "type": "",
                    "index": "",
                }
            ]
            mock_ctx.triggered_id = {"type": "connector-mcp-test", "connector_type": "atlassian_mcp"}
            mock_post.side_effect = requests.exceptions.ConnectionError("Network error")

            result = handle_mcp_test_connection([1])

        assert result is not None
        assert "Test failed" in str(result)
        assert "Network error" in str(result)

    def test_no_trigger_returns_no_update(self):
        """No trigger → returns no_update."""
        from app.dash_app.pages.connectors.callbacks import handle_mcp_test_connection

        with patch("app.dash_app.pages.connectors.callbacks.callback_context") as mock_ctx:
            mock_ctx.triggered = []
            result = handle_mcp_test_connection([None])

        assert result is no_update


# ═══════════════════════════════════════════════════════════════════════════
#  _render_top_action_bar — MCP Test Connection button
# ═══════════════════════════════════════════════════════════════════════════


class TestMcpButtonInActionBar:
    """Tests for the MCP Test Connection button in the top action bar."""

    def _collect_ids(self, component):
        """Collect all Dash component IDs from a component tree."""
        ids = set()
        component_id = getattr(component, "id", None)
        if component_id:
            if isinstance(component_id, dict):
                ids.add(tuple(sorted(component_id.items())))
            else:
                ids.add(component_id)
        children = getattr(component, "children", None)
        if children is None:
            return ids
        if not isinstance(children, list):
            children = [children]
        for child in children:
            ids.update(self._collect_ids(child))
        return ids

    def _flatten_text(self, component):
        """Flatten a Dash component tree to text."""
        if isinstance(component, (str, int, float)):
            return str(component)
        parts = []
        children = getattr(component, "children", None)
        if children is None:
            return ""
        if not isinstance(children, list):
            children = [children]
        for child in children:
            parts.append(self._flatten_text(child))
        return " ".join(parts)

    def test_mcp_test_button_visible_for_atlassian_mcp(self):
        """Atlassian MCP detail page has a Test Connection button."""
        meta = CONNECTOR_REGISTRY["atlassian_mcp"]
        bar = _render_top_action_bar("atlassian_mcp", meta)
        ids = self._collect_ids(bar)
        expected = (("connector_type", "atlassian_mcp"), ("type", "connector-mcp-test"))
        assert expected in ids
        text = self._flatten_text(bar)
        assert "Test Connection" in text

    def test_mcp_test_button_not_visible_for_producer_connectors(self):
        """Producer connectors (GitHub, Jira) do NOT have the MCP Test Connection button."""
        meta = CONNECTOR_REGISTRY["github"]
        bar = _render_top_action_bar("github", meta)
        ids = self._collect_ids(bar)
        assert not any("connector-mcp-test" in str(i) for i in ids)

    def test_mcp_test_button_not_visible_for_non_mcp_non_producer(self):
        """Slack etc. do NOT have the MCP Test Connection button."""
        meta = CONNECTOR_REGISTRY["slack"]
        bar = _render_top_action_bar("slack", meta)
        ids = self._collect_ids(bar)
        assert not any("connector-mcp-test" in str(i) for i in ids)

    def test_delete_button_still_present_for_mcp(self):
        """Delete Configuration button is still present for MCP connectors."""
        meta = CONNECTOR_REGISTRY["atlassian_mcp"]
        bar = _render_top_action_bar("atlassian_mcp", meta)
        ids = self._collect_ids(bar)
        expected = (("connector_type", "atlassian_mcp"), ("type", "connector-delete"))
        assert expected in ids
        text = self._flatten_text(bar)
        assert "Delete Configuration" in text


# ═══════════════════════════════════════════════════════════════════════════
#  TestConnectionResponse model
# ═══════════════════════════════════════════════════════════════════════════


class TestConnectionResponseModel:
    """Tests for the ``TestConnectionResponse`` Pydantic model."""

    def test_valid_response(self):
        """A valid response can be constructed with all fields."""
        from app.api.connectors.v1.model import TestConnectionResponse

        resp = TestConnectionResponse(
            success=True,
            message="Atlassian MCP Server connected — 12 tools available",
            server="atlassian",
            tool_count=12,
        )
        assert resp.success is True
        assert resp.tool_count == 12

    def test_tool_count_optional(self):
        """tool_count is optional (None for failed tests)."""
        from app.api.connectors.v1.model import TestConnectionResponse

        resp = TestConnectionResponse(
            success=False,
            message="Connection failed",
            server="github",
        )
        assert resp.tool_count is None
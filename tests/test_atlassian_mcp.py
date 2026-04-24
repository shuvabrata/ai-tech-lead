"""Dedicated unit tests for Atlassian MCP client manager behavior."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.ai_agent.mcp_integration.client_manager import AtlassianMCPClientManager


pytestmark = pytest.mark.unit


def _manager(enabled: bool = True, token: str = "ATATT_example_validish_token_123456") -> AtlassianMCPClientManager:
    return AtlassianMCPClientManager(
        atlassian_server_url="https://mcp.atlassian.com/v1/mcp",
        atlassian_token=token,
        atlassian_enabled=enabled,
        request_timeout_seconds=20,
    )


def test_check_connection_returns_disabled_when_flag_off():
    manager = _manager(enabled=False)

    result = manager.check_connection()

    assert result["status"] == "disabled"
    assert result["connected"] is False
    assert result["error"] == "atlassian_mcp_disabled"


def test_check_connection_returns_unavailable_when_run_sync_fails():
    manager = _manager(enabled=True)

    with patch.object(manager, "_run_sync", side_effect=RuntimeError("network down")):
        result = manager.check_connection()

    assert result["status"] == "unavailable"
    assert result["connected"] is False
    assert "network down" in result["error"]


def test_list_tools_returns_empty_when_unavailable():
    manager = _manager(enabled=True)

    with patch.object(manager, "_run_sync", side_effect=RuntimeError("timeout")):
        tools = manager.list_tools()

    assert tools == []


def test_call_tool_returns_tool_error_envelope_when_unavailable():
    manager = _manager(enabled=True)

    with patch.object(manager, "_run_sync", side_effect=RuntimeError("upstream unavailable")):
        result = manager.call_tool("getTeamworkGraphContext", {"objectType": "JIRA_ISSUE"})

    assert result["status"] == "unavailable"
    assert result["tool_name"] == "getTeamworkGraphContext"
    assert result["result"] is None
    assert "upstream unavailable" in result["error"]


def test_has_plausible_token_validation():
    manager = _manager(enabled=True)

    assert manager._has_plausible_token("ATATT_example_validish_token_123456") is True
    assert manager._has_plausible_token("") is False
    assert manager._has_plausible_token("invalid") is False

"""MCP tool discovery and execution facade for the chat pipeline."""

from __future__ import annotations

from typing import Any

from app.ai_agent.mcp_integration.client_manager import MCPClientManager
from app.settings import settings


def _build_manager() -> MCPClientManager:
    """Create a manager instance from application settings."""
    return MCPClientManager(
        github_server_url=settings.GITHUB_MCP_SERVER_URL,
        github_token=settings.GITHUB_MCP_TOKEN,
        github_enabled=settings.GITHUB_MCP_ENABLED,
        request_timeout_seconds=settings.HTTP_REQUEST_TIMEOUT,
    )


def list_available_tools() -> list[dict[str, Any]]:
    """List normalized tools from enabled MCP backends."""
    return _build_manager().list_tools()


def execute_tool_call(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute one MCP tool call through the configured manager."""
    return _build_manager().call_tool(tool_name=tool_name, arguments=arguments)
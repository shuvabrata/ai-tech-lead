"""MCP tool discovery and execution facade for the chat pipeline."""

from __future__ import annotations

from typing import Any

from app.ai_agent.mcp_integration.client_manager import AtlassianMCPClientManager, GithubMCPClientManager
from app.settings import settings

GITHUB_TOOL_PREFIX = "github__"
ATLASSIAN_TOOL_PREFIX = "atlassian__"


def _build_github_manager() -> GithubMCPClientManager:
    """Create a GitHub manager instance from application settings."""
    return GithubMCPClientManager(
        github_server_url=settings.GITHUB_MCP_SERVER_URL,
        github_token=settings.GITHUB_MCP_TOKEN,
        github_enabled=settings.GITHUB_MCP_ENABLED,
        request_timeout_seconds=settings.HTTP_REQUEST_TIMEOUT,
    )


def _build_atlassian_manager() -> AtlassianMCPClientManager:
    """Create an Atlassian manager instance from application settings."""
    return AtlassianMCPClientManager(
        atlassian_server_url=settings.ATLASSIAN_MCP_SERVER_URL,
        atlassian_token=settings.ATLASSIAN_MCP_TOKEN,
        atlassian_enabled=settings.ATLASSIAN_MCP_ENABLED,
        request_timeout_seconds=settings.HTTP_REQUEST_TIMEOUT,
    )


def _namespace_tools(tools: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    """Prefix tool names so multi-backend tool discovery avoids collisions."""
    namespaced_tools: list[dict[str, Any]] = []

    for tool in tools:
        if tool.get("type") != "function":
            continue

        function = dict(tool.get("function") or {})
        name = function.get("name")
        if not name:
            continue

        function["name"] = f"{prefix}{name}"
        namespaced_tools.append({"type": "function", "function": function})

    return namespaced_tools


def list_available_tools() -> list[dict[str, Any]]:
    """List normalized tools from enabled MCP backends with namespaced names."""
    tools: list[dict[str, Any]] = []

    if settings.GITHUB_MCP_ENABLED:
        github_tools = _build_github_manager().list_tools()
        tools.extend(_namespace_tools(github_tools, GITHUB_TOOL_PREFIX))

    if settings.ATLASSIAN_MCP_ENABLED:
        atlassian_tools = _build_atlassian_manager().list_tools()
        tools.extend(_namespace_tools(atlassian_tools, ATLASSIAN_TOOL_PREFIX))

    return tools


def execute_tool_call(tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute one MCP tool call by routing namespace-prefixed names to the backend."""
    safe_args = arguments or {}

    if tool_name.startswith(GITHUB_TOOL_PREFIX):
        bare_name = tool_name.removeprefix(GITHUB_TOOL_PREFIX)
        return _build_github_manager().call_tool(tool_name=bare_name, arguments=safe_args)

    if tool_name.startswith(ATLASSIAN_TOOL_PREFIX):
        bare_name = tool_name.removeprefix(ATLASSIAN_TOOL_PREFIX)
        return _build_atlassian_manager().call_tool(tool_name=bare_name, arguments=safe_args)

    return {
        "tool_name": tool_name,
        "arguments": safe_args,
        "result": None,
        "status": "error",
        "error": "unknown_tool_namespace",
    }
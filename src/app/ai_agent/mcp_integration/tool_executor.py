"""MCP tool discovery and execution facade for the chat pipeline."""

from __future__ import annotations

from typing import Any

from app.ai_agent.mcp_integration.atlassian_config_loader import load_atlassian_mcp_config
from app.ai_agent.mcp_integration.client_manager import AtlassianMCPClientManager, GithubMCPClientManager
from app.runtime_settings import runtime_settings
from app.settings import settings
from common.logger import logger

GITHUB_TOOL_PREFIX = "github__"
ATLASSIAN_TOOL_PREFIX = "atlassian__"


def _mask_token_for_log(token: str) -> str:
    """Return a redaction marker for a secret for safe DEBUG logging."""
    if not token:
        return "<empty>"
    return "<redacted>"


def _build_github_manager() -> GithubMCPClientManager:
    """Create a GitHub manager instance from application settings."""
    logger.debug(
        "[github_mcp] Building manager: enabled=%s server_url=%r token_set=%s token=%s timeout=%ds",
        settings.GITHUB_MCP_ENABLED,
        settings.GITHUB_MCP_SERVER_URL,
        bool(settings.GITHUB_MCP_TOKEN),
        _mask_token_for_log(settings.GITHUB_MCP_TOKEN),
        runtime_settings.get_int("HTTP_REQUEST_TIMEOUT"),
    )
    return GithubMCPClientManager(
        github_server_url=settings.GITHUB_MCP_SERVER_URL,
        github_token=settings.GITHUB_MCP_TOKEN,
        github_enabled=settings.GITHUB_MCP_ENABLED,
        request_timeout_seconds=runtime_settings.get_int("HTTP_REQUEST_TIMEOUT"),
    )


def _build_atlassian_manager() -> AtlassianMCPClientManager:
    """Create an Atlassian manager, preferring DB-backed config with env fallback.

    Calls ``load_atlassian_mcp_config()`` first.  When the DB returns a config
    record that record becomes the authoritative source for ``enabled``,
    ``server_url``, and ``token``.  If the DB is unavailable or the record is
    absent the function falls back to the ``ATLASSIAN_MCP_*`` env-var settings.
    """
    db_config = None
    try:
        db_config = load_atlassian_mcp_config()
    except Exception:  # noqa: BLE001 – loader error must not crash the manager build
        pass
    if db_config is not None:
        return AtlassianMCPClientManager(
            atlassian_server_url=db_config["server_url"],
            atlassian_token=db_config["token"],
            atlassian_enabled=db_config["enabled"],
            request_timeout_seconds=runtime_settings.get_int("HTTP_REQUEST_TIMEOUT"),
        )
    # DB config absent or unavailable — fall back to env settings.
    return AtlassianMCPClientManager(
        atlassian_server_url=settings.ATLASSIAN_MCP_SERVER_URL,
        atlassian_token=settings.ATLASSIAN_MCP_TOKEN,
        atlassian_enabled=settings.ATLASSIAN_MCP_ENABLED,
        request_timeout_seconds=runtime_settings.get_int("HTTP_REQUEST_TIMEOUT"),
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

    # Atlassian: DB config is checked first inside _build_atlassian_manager.
    # The manager's own atlassian_enabled flag controls whether tools are returned,
    # so no early env check is needed here.
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


def test_mcp_connection(connector_type: str) -> dict[str, Any]:
    """Test MCP connectivity for a connector by listing tools.

    This is the public entry point for the connectors API ``/test`` endpoint.
    It builds the appropriate MCP client manager, opens a session, and calls
    ``list_tools()`` to verify the connection is useful to the application.

    Args:
        connector_type: One of ``"atlassian_mcp"`` or ``"github_mcp"``.

    Returns:
        A dict with keys ``server``, ``status``, ``connected``, ``tool_count``,
        and ``error``.

    Raises:
        ValueError: If ``connector_type`` is not a recognised MCP connector.
    """
    if connector_type == "github_mcp":
        result = _build_github_manager().test_connection()
    elif connector_type == "atlassian_mcp":
        result = _build_atlassian_manager().test_connection()
    else:
        raise ValueError(f"Not an MCP connector type: {connector_type}")

    logger.debug(
        "[%s] Test connection result: status=%s connected=%s tool_count=%s server=%s error=%r",
        connector_type,
        result.get("status"),
        result.get("connected"),
        result.get("tool_count"),
        result.get("server"),
        result.get("error"),
    )
    return result
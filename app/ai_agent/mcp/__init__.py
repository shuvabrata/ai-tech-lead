"""MCP package for AI agent integrations.

This package provides MCP client and tool execution primitives.
Runtime wiring is intentionally deferred to later phases.
"""

from app.ai_agent.mcp.client_manager import MCPClientManager
from app.ai_agent.mcp.tool_executor import execute_tool_call, list_available_tools

__all__ = ["MCPClientManager", "list_available_tools", "execute_tool_call"]
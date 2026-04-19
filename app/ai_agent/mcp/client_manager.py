"""MCP client manager placeholders.

Concrete SSE transport behavior will be implemented in a later phase.
"""

from dataclasses import dataclass


@dataclass
class MCPClientManager:
    """Placeholder manager for MCP server client lifecycle."""

    github_server_url: str
    jira_server_url: str

    def list_tools(self) -> list[dict]:
        """Return available tools from configured MCP servers.

        Placeholder implementation to establish module shape.
        """
        return []

    def call_tool(self, tool_name: str, arguments: dict | None = None) -> dict:
        """Execute a tool call on configured MCP servers.

        Placeholder implementation to establish module shape.
        """
        return {
            "tool_name": tool_name,
            "arguments": arguments or {},
            "result": None,
            "status": "not_implemented",
        }
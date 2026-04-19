"""MCP tool execution placeholders.

Concrete tool discovery and execution will be implemented in a later phase.
"""


def list_available_tools() -> list[dict]:
    """List available MCP tools.

    Placeholder implementation to establish module shape.
    """
    return []


def execute_tool_call(tool_name: str, arguments: dict | None = None) -> dict:
    """Execute an MCP tool call.

    Placeholder implementation to establish module shape.
    """
    return {
        "tool_name": tool_name,
        "arguments": arguments or {},
        "result": None,
        "status": "not_implemented",
    }
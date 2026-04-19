"""MCP client manager for GitHub MCP server access.

This module keeps a synchronous surface while using the async MCP SDK internally.
"""

from __future__ import annotations

import asyncio
from queue import Queue
from threading import Thread
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable, Coroutine

import anyio
import httpx
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _default_function_schema() -> dict[str, Any]:
    """Provide a minimal JSON schema fallback when server schema is missing."""
    return {"type": "object", "properties": {}}


@dataclass
class MCPClientManager:
    """Manage GitHub MCP client lifecycle, tool discovery, and tool execution."""

    github_server_url: str
    github_token: str = ""
    github_enabled: bool = False
    request_timeout_seconds: int = 20

    def _run_sync(self, async_fn: Callable[..., Coroutine[Any, Any, Any]], *args: Any) -> Any:
        """Run async MCP operations while preserving a synchronous API surface."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return anyio.run(async_fn, *args)

        # If called from an async context, execute in a dedicated worker thread.
        result_queue: Queue[tuple[bool, Any]] = Queue(maxsize=1)

        def _runner() -> None:
            try:
                result_queue.put((True, anyio.run(async_fn, *args)))
            except Exception as exc:  # noqa: BLE001 - propagate to caller below
                result_queue.put((False, exc))

        worker = Thread(target=_runner, daemon=True)
        worker.start()
        ok, value = result_queue.get()
        worker.join()
        if ok:
            return value
        raise value

    async def _with_github_session(self, operation: Callable[[ClientSession], Coroutine[Any, Any, Any]]) -> Any:
        """Open an MCP session to GitHub and run one operation safely."""
        headers: dict[str, str] = {}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        timeout = httpx.Timeout(self.request_timeout_seconds)
        async with httpx.AsyncClient(headers=headers, timeout=timeout) as http_client:
            async with streamable_http_client(self.github_server_url, http_client=http_client) as (
                read_stream,
                write_stream,
                _,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    return await operation(session)

    def _normalize_tool(self, raw_tool: Any) -> dict[str, Any]:
        """Normalize MCP tool metadata into provider-expected function schema format."""
        input_schema = getattr(raw_tool, "inputSchema", None) or _default_function_schema()
        return {
            "type": "function",
            "function": {
                "name": getattr(raw_tool, "name", ""),
                "description": getattr(raw_tool, "description", "") or "",
                "parameters": input_schema,
            },
        }

    @staticmethod
    def _serialize_content_item(item: Any) -> dict[str, Any]:
        """Serialize MCP content union to plain dict for downstream consumers."""
        if hasattr(item, "model_dump"):
            return item.model_dump()
        return {"value": str(item)}

    def check_connection(self) -> dict[str, Any]:
        """Verify GitHub MCP connectivity and return a structured status payload."""
        if not self.github_enabled:
            return {
                "server": "github",
                "status": "disabled",
                "connected": False,
                "error": "github_mcp_disabled",
            }

        async def _check(session: ClientSession) -> dict[str, Any]:
            _ = session
            return {"server": "github", "status": "connected", "connected": True}

        try:
            return self._run_sync(self._with_github_session, _check)
        except Exception as exc:  # noqa: BLE001 - return structured errors to caller
            return {
                "server": "github",
                "status": "unavailable",
                "connected": False,
                "error": str(exc),
            }

    def list_tools(self) -> list[dict[str, Any]]:
        """Return normalized tools from the GitHub MCP server.

        Returns an empty list when MCP is disabled or unavailable.
        """
        if not self.github_enabled:
            return []

        async def _list(session: ClientSession) -> list[dict[str, Any]]:
            result = await session.list_tools()
            return [self._normalize_tool(tool) for tool in result.tools]

        try:
            return self._run_sync(self._with_github_session, _list)
        except Exception:
            return []

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute one GitHub MCP tool and return a stable, structured result payload."""
        safe_args = arguments or {}

        if not self.github_enabled:
            return {
                "tool_name": tool_name,
                "arguments": safe_args,
                "result": None,
                "status": "disabled",
                "error": "github_mcp_disabled",
            }

        async def _call(session: ClientSession) -> dict[str, Any]:
            result = await session.call_tool(
                name=tool_name,
                arguments=safe_args,
                read_timeout_seconds=timedelta(seconds=self.request_timeout_seconds),
            )
            return {
                "tool_name": tool_name,
                "arguments": safe_args,
                "result": {
                    "content": [self._serialize_content_item(item) for item in result.content],
                    "structured_content": result.structuredContent,
                    "is_error": bool(result.isError),
                },
                "status": "tool_error" if result.isError else "success",
            }

        try:
            return self._run_sync(self._with_github_session, _call)
        except Exception as exc:  # noqa: BLE001 - return structured errors to caller
            return {
                "tool_name": tool_name,
                "arguments": safe_args,
                "result": None,
                "status": "unavailable",
                "error": str(exc),
            }
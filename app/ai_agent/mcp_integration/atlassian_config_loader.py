"""DB-backed Atlassian MCP config loader for the MCP runtime.

Fetches and decrypts the atlassian_mcp connector config from PostgreSQL and
returns it in the shape expected by the MCP client managers.  Falls back to
``None`` when the record is absent or any database / decryption error occurs,
allowing the caller to apply an env-based fallback.
"""

from __future__ import annotations

import asyncio
import logging
from queue import Queue
from threading import Thread
from typing import Any, Optional

import anyio

from app.db.session import ASYNC_SESSION_LOCAL

logger = logging.getLogger(__name__)


def _run_async_sync(async_fn: Any, *args: Any) -> Any:
    """Run an async callable synchronously, safe to call from any thread context.

    Mirrors the pattern used in ``_MCPClientBase._run_sync`` so that the
    loader can be called from synchronous code even when an event loop is
    already running (e.g. inside a FastAPI request handler).
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running event loop — start one directly.
        return anyio.run(async_fn, *args)

    # Already inside an async context: execute in a dedicated worker thread to
    # avoid nesting event loops.
    result_queue: Queue[tuple[bool, Any]] = Queue(maxsize=1)

    def _runner() -> None:
        try:
            result_queue.put((True, anyio.run(async_fn, *args)))
        except Exception as exc:  # noqa: BLE001
            result_queue.put((False, exc))

    worker = Thread(target=_runner, daemon=True)
    worker.start()
    ok, value = result_queue.get()
    worker.join()
    if ok:
        return value
    raise value


def load_atlassian_mcp_config() -> Optional[dict[str, Any]]:
    """Return Atlassian MCP runtime config loaded from the connectors database.

    The returned dict has three keys:

    - ``enabled``: bool
    - ``server_url``: str (may be empty string when not set)
    - ``token``: str decrypted plaintext (may be empty string when not set)

    Returns ``None`` when the connector record is absent, the ``atlassian_mcp``
    type is not registered, or any database / decryption error occurs.  The
    caller should fall back to env-based settings in that case.
    """
    # Imported here to avoid a circular-import risk at module load time.
    # tool_executor → atlassian_config_loader → service creates no cycle since
    # service does not import from the ai_agent tree.
    from app.api.connectors.v1.service import get_connector  # pylint: disable=import-outside-toplevel

    async def _fetch() -> Optional[dict[str, Any]]:
        async with ASYNC_SESSION_LOCAL() as session:
            try:
                connector = await get_connector(session, "atlassian_mcp", include_secrets=True)
            except ValueError:
                return None
            config = connector.get("config") or {}
            if not isinstance(config, dict):
                return None
            return {
                "enabled": bool(config.get("enabled", False)),
                "server_url": config.get("server_url") or "",
                "token": config.get("token") or "",
            }

    try:
        return _run_async_sync(_fetch)
    except Exception:  # noqa: BLE001
        logger.debug(
            "Failed to load Atlassian MCP config from DB; will use env fallback",
            exc_info=True,
        )
        return None

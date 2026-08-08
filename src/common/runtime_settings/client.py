"""REST snapshot client for non-app processes.

Provides ``fetch_runtime_snapshot()`` so that producer daemons, signal
consumers, and CLI utilities can retrieve the effective runtime settings
from the app API without importing ``src.app`` or requiring a DB connection.

If the API is unreachable the module falls back to env/default values
(``RuntimeConfig`` defaults) and logs a warning — this is essential for
CLI utilities that may run outside Docker Compose but still reuse shared
code.
"""

from __future__ import annotations

from typing import Any

import requests

from common.logger import logger
from common.runtime_settings.config import RuntimeConfig

# ── Public API ─────────────────────────────────────────────────────────


def fetch_runtime_snapshot(
    api_base_url: str,
    timeout: int = 10,
) -> RuntimeConfig:
    """Fetch the effective runtime settings snapshot from the app API.

    Calls ``GET <api_base_url>/api/v1/settings/runtime-snapshot`` and
    returns a validated ``RuntimeConfig`` instance.

    If the API is unreachable (connection error, timeout, non-200 status)
    the function logs a **WARNING** and falls back to plain
    ``RuntimeConfig()`` with all-defaults (env / code defaults).

    Args:
        api_base_url: Base URL of the running app, e.g. ``http://app:8000``.
        timeout: HTTP request timeout in seconds.

    Returns:
        A ``RuntimeConfig`` instance populated from the API snapshot, or
        all-defaults if the API is unreachable.
    """
    url = f"{api_base_url.rstrip('/')}/api/v1/settings/runtime-snapshot"

    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        config = RuntimeConfig(**data)
        logger.info("Fetched runtime settings snapshot from %s", url)
        return config
    except requests.exceptions.RequestException as exc:
        logger.warning(
            "Runtime settings API unreachable at %s — "
            "falling back to env/default values. Reason: %s",
            url,
            exc,
        )
    except (ValueError, TypeError, RuntimeError) as exc:
        # Covers Pydantic validation errors and unexpected response shapes.
        logger.warning(
            "Runtime settings API returned invalid data from %s — "
            "falling back to env/default values. Reason: %s",
            url,
            exc,
        )

    return RuntimeConfig()
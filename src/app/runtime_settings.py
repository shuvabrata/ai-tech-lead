"""App-specific wiring for the runtime settings system.

Initialises the shared ``RuntimeConfigCache`` from the app's ``Settings``
singleton and DB on startup, and exports a module-level ``runtime_settings``
instance that call sites can import.

Usage::

    from app.runtime_settings import runtime_settings

    timeout = runtime_settings.get_int("HTTP_REQUEST_TIMEOUT")
"""

from __future__ import annotations

from app.settings import settings as app_settings
from common.runtime_settings import RuntimeConfig, RuntimeConfigCache

# Module-level cache — seeded from the Settings singleton (which reads env
# vars) so that env-configured values are available immediately.  DB
# overrides will be loaded on top during startup (Phase 5).
_runtime_settings: RuntimeConfigCache = RuntimeConfigCache()


def _build_initial_config() -> RuntimeConfig:
    """Build a RuntimeConfig from the current app Settings singleton."""
    return RuntimeConfig(
        HTTP_REQUEST_TIMEOUT=app_settings.HTTP_REQUEST_TIMEOUT,
        NEO4J_QUERY_TIMEOUT=app_settings.NEO4J_QUERY_TIMEOUT,
        GRAPH_UI_MAX_NODES_TO_EXPAND=app_settings.GRAPH_UI_MAX_NODES_TO_EXPAND,
        GRAPH_UI_MAX_NODE_LABEL_CHARS=app_settings.GRAPH_UI_MAX_NODE_LABEL_CHARS,
        CONNECTOR_SCAN_POLL_INTERVAL=app_settings.CONNECTOR_SCAN_POLL_INTERVAL,
        RECENT_ACTIONS_LIMIT=app_settings.RECENT_ACTIONS_LIMIT,
        TIMEZONE=app_settings.TIMEZONE,
        UI_DATETIME_FORMAT=app_settings.UI_DATETIME_FORMAT,
        UI_DATE_FORMAT=app_settings.UI_DATE_FORMAT,
        AUGMENTATION_HISTORY_TURNS=app_settings.AUGMENTATION_HISTORY_TURNS,
        ES_CHAIN_MAX_RESULTS=app_settings.ES_CHAIN_MAX_RESULTS,
        MAX_MCP_ITERATIONS=app_settings.MAX_MCP_ITERATIONS,
        FF_NEO4J_USE_PROVIDER_PIPELINE=app_settings.FF_NEO4J_USE_PROVIDER_PIPELINE,
    )


# Seed the cache from the Settings singleton so env-configured values are
# available immediately at import time.
_runtime_settings.refresh(_build_initial_config())

# Public alias — all call sites import ``runtime_settings``.
runtime_settings = _runtime_settings


def get_effective_config() -> RuntimeConfig:
    """Return the current effective ``RuntimeConfig`` (defaults only for now).

    In Phase 5 this will also load DB overrides at startup.
    """
    return runtime_settings.current()
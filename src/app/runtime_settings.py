"""App-specific wiring for the runtime settings system.

Initialises the shared ``RuntimeConfigCache`` from the app's ``Settings``
singleton and DB on startup, and exports a module-level ``runtime_settings``
instance that call sites can import.

Usage::

    from app.runtime_settings import runtime_settings

    timeout = runtime_settings.get_int("HTTP_REQUEST_TIMEOUT")

    # On startup, also load DB overrides:
    from app.runtime_settings import load_db_overrides_from_session
    async with ASYNC_SESSION_LOCAL() as db:
        await load_db_overrides_from_session(db)
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.settings import settings as app_settings
from common.logger import logger
from common.runtime_settings import RuntimeConfig, RuntimeConfigCache

# Module-level cache — seeded from the Settings singleton (which reads env
# vars) so that env-configured values are available immediately.  DB
# overrides will be loaded on top during startup.
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
        # ── AI / LLM ──────────────────────────────────────────────────
        LLM_PROVIDER=app_settings.LLM_PROVIDER,
        LLM_MODEL=app_settings.LLM_MODEL,
        MAX_TOKENS=app_settings.MAX_TOKENS,
        GITHUB_MCP_ENABLED=app_settings.GITHUB_MCP_ENABLED,
        ATLASSIAN_MCP_ENABLED=app_settings.ATLASSIAN_MCP_ENABLED,
        # ── System ────────────────────────────────────────────────────
        NEO4J_ENABLED=app_settings.NEO4J_ENABLED,
        # ── Connectors ────────────────────────────────────────────────
        COMMIT_DAYS_LIMIT=app_settings.COMMIT_DAYS_LIMIT,
        PULL_REQUEST_DAYS_LIMIT=app_settings.PULL_REQUEST_DAYS_LIMIT,
        IDENTITY_REFRESH_DAYS=app_settings.IDENTITY_REFRESH_DAYS,
        MAX_TEAM_SIZE=app_settings.MAX_TEAM_SIZE,
        JIRA_LOOKBACK_DAYS=app_settings.JIRA_LOOKBACK_DAYS,
        JIRA_MAX_RESULTS_PER_PAGE=app_settings.JIRA_MAX_RESULTS_PER_PAGE,
        CONFLUENCE_LOOKBACK_DAYS=app_settings.CONFLUENCE_LOOKBACK_DAYS,
        JIRA_EPIC_TEAM_FIELD=app_settings.JIRA_EPIC_TEAM_FIELD,
        JIRA_ISSUE_TEAM_FIELD=app_settings.JIRA_ISSUE_TEAM_FIELD,
        JIRA_EPIC_START_DATE_FIELD=app_settings.JIRA_EPIC_START_DATE_FIELD,
        JIRA_EPIC_DUE_DATE_FIELD=app_settings.JIRA_EPIC_DUE_DATE_FIELD,
        API_SERVER=app_settings.API_SERVER,
        CONFIGURATION_SOURCE=app_settings.CONFIGURATION_SOURCE,
        # ── Logging ───────────────────────────────────────────────────
        LOG_LEVEL=app_settings.LOG_LEVEL,
        LOG_FORMAT=app_settings.LOG_FORMAT,
        ENABLE_FILE_LOGGING=app_settings.ENABLE_FILE_LOGGING,
        LOG_DIR=app_settings.LOG_DIR,
        LOG_SIGNAL_DUMPS=app_settings.LOG_SIGNAL_DUMPS,
    )


# Seed the cache from the Settings singleton so env-configured values are
# available immediately at import time.
_runtime_settings.refresh(_build_initial_config())

# Public alias — all call sites import ``runtime_settings``.
runtime_settings = _runtime_settings


def get_effective_config() -> RuntimeConfig:
    """Return the current effective ``RuntimeConfig``."""
    return runtime_settings.current()


async def load_db_overrides_from_session(db: AsyncSession) -> None:
    """Query the DB and refresh the runtime settings cache with DB overrides.

    Builds an effective ``RuntimeConfig`` from DB overrides + env + defaults,
    then atomically replaces the current snapshot.

    Call this during startup, or from the RabbitMQ event listener callback.
    """
    # Imported here (not at module level) to avoid any circular-dependency
    # concerns at import time.
    # pylint: disable=import-outside-toplevel
    from app.api.settings.v1 import query as qry
    from app.api.settings.v1.service import _resolve_effective_config

    rows = await qry.get_all_settings(db)
    config = _resolve_effective_config(rows)
    _runtime_settings.refresh(config)

    logger.info(
        "Runtime settings cache refreshed from DB (%d settings)",
        len(rows),
    )
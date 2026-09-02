"""Pydantic models for the settings API.

Defines request/response schemas for the ``/api/v1/settings/`` endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SettingResponse(BaseModel):
    """Source-aware response for a single setting row."""

    key: str
    value: Any = None
    effective_value: Any
    source: str  # "db" | "env" | "default"
    value_type: str
    category: str | None = None
    description: str | None = None
    apply_mode: str
    importance: str = "optional"  # "recommended" | "optional"
    is_sensitive: bool = False
    is_configured: bool = True
    updated_at: datetime | None = None
    propagation_warning: str | None = None

    model_config = ConfigDict(from_attributes=True)


class BulkUpdateRequest(BaseModel):
    """Request body for bulk-updating multiple settings."""

    updates: dict[str, Any]
    expected_updated_at: datetime | None = None


class SingleUpdateRequest(BaseModel):
    """Request body for updating a single setting."""

    value: Any
    expected_updated_at: datetime | None = None


class SingleResetRequest(BaseModel):
    """Request body for resetting a single setting."""

    expected_updated_at: datetime | None = None


class BulkResetRequest(BaseModel):
    """Request body for resetting all settings."""

    expected_updated_at: datetime | None = None


class BulkUpdateResponse(BaseModel):
    """Response after a successful bulk update."""

    updated: dict[str, Any]
    propagation_warning: str | None = None


class ConflictResponse(BaseModel):
    """Response body for a 409 conflict."""

    detail: str
    conflicting_keys: list[str]
    current_values: dict[str, Any]


class RuntimeSnapshotResponse(BaseModel):
    """Effective RuntimeConfig used by non-app processes."""

    HTTP_REQUEST_TIMEOUT: int
    NEO4J_QUERY_TIMEOUT: int
    GRAPH_UI_MAX_NODES_TO_EXPAND: int
    GRAPH_UI_MAX_NODE_LABEL_CHARS: int
    CONNECTOR_SCAN_POLL_INTERVAL: int
    RECENT_ACTIONS_LIMIT: int
    RETRY_BUDGET_SECONDS: int = 3600
    RETRY_BACKOFF_CAP_SECONDS: int = 30
    RETRY_BASE_DELAY_SECONDS: int = 1
    TIMEZONE: str
    UI_DATETIME_FORMAT: str
    UI_DATE_FORMAT: str
    AUGMENTATION_HISTORY_TURNS: int
    ES_CHAIN_MAX_RESULTS: int
    MAX_MCP_ITERATIONS: int
    FF_NEO4J_USE_PROVIDER_PIPELINE: bool
    # ── AI / LLM ──────────────────────────────────────────────────────
    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "gpt-5"
    MAX_TOKENS: int = 16000
    GITHUB_MCP_ENABLED: bool = False
    ATLASSIAN_MCP_ENABLED: bool = False
    # ── System ────────────────────────────────────────────────────────
    NEO4J_ENABLED: bool = False
    # ── Connectors ────────────────────────────────────────────────────
    COMMIT_DAYS_LIMIT: int = 60
    PULL_REQUEST_DAYS_LIMIT: int = 60
    ISSUE_DAYS_LIMIT: int = 60
    IDENTITY_REFRESH_DAYS: int = 7
    MAX_TEAM_SIZE: int = 100
    JIRA_LOOKBACK_DAYS: int = 90
    JIRA_MAX_RESULTS_PER_PAGE: int = 100
    CONFLUENCE_LOOKBACK_DAYS: int = 60
    JIRA_EPIC_TEAM_FIELD: str = "Team"
    JIRA_ISSUE_TEAM_FIELD: str = "Team"
    JIRA_EPIC_START_DATE_FIELD: str = "created"
    JIRA_EPIC_DUE_DATE_FIELD: str = "duedate"
    API_SERVER: str = "http://app:8000/"
    CONFIGURATION_SOURCE: str = "SERVER"
    # ── Logging ───────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "JSON"
    ENABLE_FILE_LOGGING: bool = False
    LOG_DIR: str = "logs"
    LOG_SIGNAL_DUMPS: bool = False

    model_config = ConfigDict(from_attributes=True)
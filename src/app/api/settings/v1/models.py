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
    is_sensitive: bool = False
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class BulkUpdateRequest(BaseModel):
    """Request body for bulk-updating multiple settings."""

    updates: dict[str, Any]
    expected_updated_at: datetime | None = None


class SingleUpdateRequest(BaseModel):
    """Request body for updating a single setting."""

    value: Any
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
    TIMEZONE: str
    UI_DATETIME_FORMAT: str
    UI_DATE_FORMAT: str
    AUGMENTATION_HISTORY_TURNS: int
    ES_CHAIN_MAX_RESULTS: int
    MAX_MCP_ITERATIONS: int
    FF_NEO4J_USE_PROVIDER_PIPELINE: bool

    model_config = ConfigDict(from_attributes=True)
"""Pydantic model for the runtime-configurable subset of application settings.

``RuntimeConfig`` is a pure data + validation layer that lives in shared code
(``src/common/``) so both app and non-app processes can import it without
pulling in ``src.app`` or requiring a database connection.

The defaults here mirror the hardcoded defaults in ``src/app/settings.py``.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, StrictBool, field_validator


class RuntimeConfig(BaseModel):
    """Effective runtime-configurable application settings.

    All fields have defaults matching :class:`app.settings.Settings` so that
    the model can be used standalone (e.g. in producer processes) without
    an env file or DB connection.
    """

    # ── Network ──────────────────────────────────────────────────────────
    HTTP_REQUEST_TIMEOUT: int = Field(default=60, ge=1)
    NEO4J_QUERY_TIMEOUT: int = Field(default=10, ge=1)

    # ── Graph ────────────────────────────────────────────────────────────
    GRAPH_UI_MAX_NODES_TO_EXPAND: int = Field(default=20, ge=1)
    GRAPH_UI_MAX_NODE_LABEL_CHARS: int = Field(default=10, ge=4)

    # ── Connectors ───────────────────────────────────────────────────────
    CONNECTOR_SCAN_POLL_INTERVAL: int = Field(default=5000, ge=500)
    RECENT_ACTIONS_LIMIT: int = Field(default=5, ge=1, le=50)

    # ── UI ───────────────────────────────────────────────────────────────
    TIMEZONE: str = "UTC"
    UI_DATETIME_FORMAT: str = "%b %d, %Y %I:%M %p"
    UI_DATE_FORMAT: str = "%b %d, %Y"

    # ── AI / Augmentation ────────────────────────────────────────────────
    AUGMENTATION_HISTORY_TURNS: int = Field(default=5, ge=0)
    ES_CHAIN_MAX_RESULTS: int = Field(default=5, ge=1)
    MAX_MCP_ITERATIONS: int = Field(default=3, ge=1)

    # ── Feature Flags ────────────────────────────────────────────────────
    FF_NEO4J_USE_PROVIDER_PIPELINE: StrictBool = False

    @field_validator("TIMEZONE")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Validate that *value* is a valid IANA timezone name."""
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid timezone: {value}") from exc
        return value
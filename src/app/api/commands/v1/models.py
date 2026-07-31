"""Pydantic models for the commands API.

Defines request/response schemas for the ``/api/v1/commands/`` endpoints.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CreateCommandRequest(BaseModel):
    """Request body for creating a new scan command."""

    command_type: str
    target: str
    parameters: dict[str, Any] | None = None


class CommandStatusUpdateRequest(BaseModel):
    """Request body for updating a command's status (used by producers via PATCH)."""

    status: str
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_summary: dict[str, Any] | None = None


class CommandResponse(BaseModel):
    """Response model for a single command."""

    command_id: uuid.UUID
    command_type: str
    target: str
    parameters: dict[str, Any] | None = None
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    result_summary: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class CommandListResponse(BaseModel):
    """Response model for a paginated list of commands."""

    commands: list[CommandResponse]
    total: int
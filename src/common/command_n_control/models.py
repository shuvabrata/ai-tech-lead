"""Pydantic models for the command-and-control bus.

Defines the ``CommandEnvelope`` (outbound command) and ``CommandStatusUpdate``
(inbound status callback) models shared by the app and all producers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CommandEnvelope(BaseModel):
    """A command message published to the ``command_n_control`` exchange.

    Attributes:
        command_id: Unique UUID identifying this command instance.
        command_type: The command verb, e.g. ``"scan"``.
        target: Container name, e.g. ``"github-producer"``, or ``"*"`` for
            broadcast to all known containers.
        parameters: Optional free-form key/value pairs scoped to the command.
        issued_at: UTC timestamp from the issuer.
    """

    command_id: uuid.UUID
    command_type: str
    target: str
    parameters: dict[str, Any] | None = None
    issued_at: datetime


# Valid status values in the command lifecycle.
CommandStatusValue = Literal[
    "accepted",
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
]


class CommandStatusUpdate(BaseModel):
    """Status update sent by a producer back to the app via HTTP PATCH.

    Attributes:
        status: The new status value.
        error_message: Human-readable error detail (required when status is
            ``"failed"``, optional otherwise).
        started_at: When the command started executing (set on ``"running"``).
        completed_at: When the command finished (set on ``"completed"`` or
            ``"failed"``).
        result_summary: Optional structured result metadata, e.g.
            ``{"signals_published": 42}``.
    """

    status: CommandStatusValue
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_summary: dict[str, Any] | None = Field(default=None, alias="result_summary")

    model_config = {"populate_by_name": True}
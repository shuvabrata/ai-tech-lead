"""SQLAlchemy model for the command_status table.

Tracks the lifecycle of every command sent via the command_n_control exchange.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class CommandStatus(Base):
    """Tracks the lifecycle of every command sent via the command_n_control exchange.

    Written by the app's API layer (``/api/v1/commands/``) when a command is
    created.  Updated by producer daemons via HTTP PATCH
    ``/api/v1/commands/{command_id}/status``.

    Status lifecycle::

        pending → accepted → queued → running → completed
                                               → failed
    """

    __tablename__ = "command_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    command_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, index=True
    )
    command_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False  # pylint: disable=not-callable
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
"""Business logic for the commands API.

Handles command creation (with RabbitMQ publishing), retrieval, listing,
and status updates from producer daemons.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from common.command_n_control.models import CommandEnvelope
from common.command_n_control.publisher import CommandPublisher
from common.logger import logger
from app.api.connectors.v1.registry import CONNECTOR_REGISTRY
from app.db.models.command_status import CommandStatus
from app.settings import settings

# Valid status lifecycle transitions.
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"accepted", "failed"},
    "accepted": {"running", "failed", "cancelled"},
    "running": {"completed", "failed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


def _validate_state_transition(current: str, new: str) -> None:
    """Raise ``ValueError`` if the transition is not allowed.

    Same-state transitions are always allowed (idempotent — useful when
    multiple processes race to set ``running``).  Terminal states have no
    outgoing transitions, including same-state.
    """
    if current == new:
        return  # same state is always valid (idempotent)
    allowed = _VALID_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise ValueError(
            f"Invalid status transition: '{current}' → '{new}'. "
            f"Allowed transitions from '{current}': {sorted(allowed) or '(terminal)'}"
        )


def _is_producer_target(target: str) -> bool:
    """Check if a target matches a known producer container name."""
    for entry in CONNECTOR_REGISTRY.values():
        if entry.get("producer_container") == target:
            return True
    return False


async def create_and_publish_command(
    request: Any,  # CreateCommandRequest
    db: AsyncSession,
) -> CommandStatus:
    """Create a command record, publish to RabbitMQ, and return the result.

    1. Validates target (must be a known producer container or ``"*"``).
    2. Inserts a row in ``command_status`` with status ``"pending"``.
    3. Publishes a ``CommandEnvelope`` to the ``command_n_control`` exchange.
    4. On success, updates status to ``"accepted"``; on failure, sets to
       ``"failed"`` with an error message.
    """
    # Validate target.
    if request.target != "*" and not _is_producer_target(request.target):
        raise ValueError(f"Unknown target: '{request.target}'. Must be a known producer container or '*'.")

    command_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Insert the command record.
    cmd = CommandStatus(
        command_id=command_id,
        command_type=request.command_type,
        target=request.target,
        parameters=request.parameters,
        status="pending",
        created_at=now,
    )
    db.add(cmd)
    await db.flush()  # Get the ID assigned, but don't commit yet.

    # Build the command envelope.
    envelope = CommandEnvelope(
        command_id=command_id,
        command_type=request.command_type,
        target=request.target,
        parameters=request.parameters,
        issued_at=now,
    )

    # Publish to RabbitMQ.
    try:
        async with CommandPublisher(
            settings.RABBITMQ_URL,
            known_targets=[
                str(entry["producer_container"]) for entry in CONNECTOR_REGISTRY.values()
                if entry.get("producer_container")
            ],
        ) as pub:
            await pub.publish(envelope)
        cmd.status = "accepted"
        logger.info("Command published command_id=%s target=%s", command_id, request.target)
    except Exception as exc:
        logger.error("Failed to publish command command_id=%s: %s", command_id, exc, exc_info=True)
        cmd.status = "failed"
        cmd.error_message = "Failed to publish to RabbitMQ"

    await db.commit()
    await db.refresh(cmd)
    return cmd


async def get_command(command_id: uuid.UUID, db: AsyncSession) -> CommandStatus | None:
    """Fetch a single command by its ``command_id``."""
    stmt = select(CommandStatus).where(CommandStatus.command_id == command_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_commands(
    db: AsyncSession,
    status: str | None = None,
    target: str | None = None,
    command_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[CommandStatus], int]:
    """List commands with optional filters and pagination.

    Returns a tuple of ``(commands, total_count)``.
    """
    base_query = select(CommandStatus)
    count_query = select(sa_func.count(CommandStatus.id))  # pylint: disable=not-callable

    if status is not None:
        base_query = base_query.where(CommandStatus.status == status)
        count_query = count_query.where(CommandStatus.status == status)
    if target is not None:
        base_query = base_query.where(CommandStatus.target == target)
        count_query = count_query.where(CommandStatus.target == target)
    if command_type is not None:
        base_query = base_query.where(CommandStatus.command_type == command_type)
        count_query = count_query.where(CommandStatus.command_type == command_type)

    # Get total count.
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Fetch paginated results, newest first.
    base_query = base_query.order_by(CommandStatus.created_at.desc())
    base_query = base_query.offset(offset).limit(limit)
    result = await db.execute(base_query)
    commands = list(result.scalars().all())

    return commands, total


async def update_command_status(
    command_id: uuid.UUID,
    status_update: Any,  # CommandStatusUpdateRequest
    db: AsyncSession,
) -> CommandStatus:
    """Update the status of a command.

    Validates the state transition before applying changes.
    """
    cmd = await get_command(command_id, db)
    if cmd is None:
        raise ValueError(f"Command not found: command_id={command_id}")

    _validate_state_transition(cmd.status, status_update.status)

    cmd.status = status_update.status
    if status_update.error_message is not None:
        cmd.error_message = status_update.error_message
    if status_update.started_at is not None:
        cmd.started_at = status_update.started_at
    if status_update.completed_at is not None:
        cmd.completed_at = status_update.completed_at
    if status_update.result_summary is not None:
        cmd.result_summary = status_update.result_summary

    await db.commit()
    await db.refresh(cmd)
    return cmd
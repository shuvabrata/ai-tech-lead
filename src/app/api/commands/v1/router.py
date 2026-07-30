"""FastAPI router for the command-and-control API.

Endpoints:
- ``POST /commands/``  — Create and publish a new command.
- ``GET /commands/``   — List commands with optional filters.
- ``GET /commands/{command_id}`` — Get a single command.
- ``PATCH /commands/{command_id}/status`` — Update command status (producer callback).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db
from . import service
from .models import (
    CommandListResponse,
    CommandResponse,
    CommandStatusUpdateRequest,
    CreateCommandRequest,
)

router = APIRouter(prefix="/commands", tags=["commands"])


@router.post("/", response_model=CommandResponse, status_code=201)
async def create_command(
    payload: CreateCommandRequest,
    db: AsyncSession = Depends(get_async_db),
) -> CommandResponse:
    """Create and publish a new scan command."""
    try:
        cmd = await service.create_and_publish_command(payload, db)
        return CommandResponse.model_validate(cmd)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/", response_model=CommandListResponse)
async def list_commands(
    status: str | None = Query(None, description="Filter by status"),
    target: str | None = Query(None, description="Filter by target container"),
    command_type: str | None = Query(None, description="Filter by command type"),
    limit: int = Query(20, ge=1, le=100, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: AsyncSession = Depends(get_async_db),
) -> CommandListResponse:
    """List commands with optional filters and pagination."""
    commands, total = await service.list_commands(
        db, status=status, target=target, command_type=command_type,
        limit=limit, offset=offset,
    )
    return CommandListResponse(
        commands=[CommandResponse.model_validate(cmd) for cmd in commands],
        total=total,
    )


@router.get("/{command_id}", response_model=CommandResponse)
async def get_command(
    command_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
) -> CommandResponse:
    """Get a single command by its UUID."""
    cmd = await service.get_command(command_id, db)
    if cmd is None:
        raise HTTPException(status_code=404, detail="Command not found")
    return CommandResponse.model_validate(cmd)


@router.patch("/{command_id}/status", response_model=CommandResponse)
async def patch_command_status(
    command_id: uuid.UUID,
    payload: CommandStatusUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
) -> CommandResponse:
    """Update the status of a command (producer callback)."""
    try:
        cmd = await service.update_command_status(command_id, payload, db)
        return CommandResponse.model_validate(cmd)
    except ValueError as exc:
        detail = str(exc)
        status_code = 422 if "transition" in detail.lower() else 404
        raise HTTPException(status_code=status_code, detail=detail) from exc
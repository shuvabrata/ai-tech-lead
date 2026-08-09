"""FastAPI router for the settings API.

Endpoints:
- ``GET /settings`` — List all settings with source-aware metadata.
- ``PATCH /settings`` — Bulk update (primary write path).
- ``PATCH /settings/{key}`` — Single-key update.
- ``POST /settings/reset`` — Bulk reset all overrides to ``NULL``.
- ``POST /settings/{key}/reset`` — Reset one key to ``NULL``.
- ``GET /settings/runtime-snapshot`` — Effective ``RuntimeConfig`` for non-app processes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.settings.v1.models import BulkUpdateRequest, BulkUpdateResponse
from app.api.settings.v1.models import BulkResetRequest
from app.api.settings.v1.models import ConflictResponse
from app.api.settings.v1.models import RuntimeSnapshotResponse
from app.api.settings.v1.models import SettingResponse, SingleUpdateRequest
from app.api.settings.v1.models import SingleResetRequest
from app.api.settings.v1 import service as settings_service
from app.api.settings.v1.service import ConflictError
from app.db.session import get_async_db

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/", response_model=list[SettingResponse])
async def get_settings(
    db: AsyncSession = Depends(get_async_db),
) -> list[SettingResponse]:
    """List all settings with source-aware metadata."""
    rows = await settings_service.get_all_settings(db)
    return [SettingResponse(**row) for row in rows]


@router.get("/runtime-snapshot", response_model=RuntimeSnapshotResponse)
async def get_runtime_snapshot(
    db: AsyncSession = Depends(get_async_db),
) -> RuntimeSnapshotResponse:
    """Return the effective ``RuntimeConfig`` (used by non-app processes)."""
    config = await settings_service.get_runtime_snapshot(db)
    return RuntimeSnapshotResponse(**config.model_dump())


@router.patch("/", response_model=BulkUpdateResponse)
async def bulk_update_settings(
    payload: BulkUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
) -> BulkUpdateResponse:
    """Bulk-update settings (primary write path)."""
    try:
        result = await settings_service.bulk_update(
            db, payload.updates, expected_updated_at=payload.expected_updated_at
        )
        return BulkUpdateResponse(**result)
    except ConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=ConflictResponse(
                detail=str(exc),
                conflicting_keys=exc.conflicting_keys,
                current_values=exc.current_values,
            ).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


@router.patch("/{key}", response_model=SettingResponse)
async def update_single_setting(
    key: str,
    payload: SingleUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
) -> SettingResponse:
    """Update a single setting by key."""
    try:
        result = await settings_service.update_single(
            db, key, payload.value, expected_updated_at=payload.expected_updated_at
        )
        return SettingResponse(**result)
    except ConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=ConflictResponse(
                detail=str(exc),
                conflicting_keys=exc.conflicting_keys,
                current_values=exc.current_values,
            ).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


@router.post("/reset", response_model=list[SettingResponse])
async def reset_all_settings(
    body: BulkResetRequest,
    db: AsyncSession = Depends(get_async_db),
) -> list[SettingResponse]:
    """Reset all settings to their env/default values."""
    try:
        rows = await settings_service.reset_all(
            db, expected_updated_at=body.expected_updated_at
        )
        return [SettingResponse(**row) for row in rows]
    except ConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=ConflictResponse(
                detail=str(exc),
                conflicting_keys=exc.conflicting_keys,
                current_values=exc.current_values,
            ).model_dump(),
        ) from exc


@router.post("/{key}/reset", response_model=SettingResponse)
async def reset_single_setting(
    key: str,
    body: SingleResetRequest,
    db: AsyncSession = Depends(get_async_db),
) -> SettingResponse:
    """Reset a single setting to its env/default value."""
    try:
        result = await settings_service.reset_single(
            db, key, expected_updated_at=body.expected_updated_at
        )
        return SettingResponse(**result)
    except ConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=ConflictResponse(
                detail=str(exc),
                conflicting_keys=exc.conflicting_keys,
                current_values=exc.current_values,
            ).model_dump(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
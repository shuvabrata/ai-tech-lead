"""FastAPI router for the graph-themes API.

Endpoints:
- ``GET /graph-themes/`` — List all themes.
- ``POST /graph-themes/`` — Create a user theme.
- ``GET /graph-themes/effective?base_theme=`` — Merged effective tokens.
- ``GET /graph-themes/{id}`` — Fetch one theme.
- ``PATCH /graph-themes/{id}`` — Update a user theme (builtin → 409).
- ``DELETE /graph-themes/{id}`` — Delete a user theme (builtin → 409).
- ``POST /graph-themes/{id}/set-default`` — Make a theme the default for its base mode.
- ``POST /graph-themes/{id}/clone`` — Copy-on-write a theme (builtin → new user row).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.graph_themes.v1 import service as themes_service
from app.api.graph_themes.v1.models import (
    CloneResponse,
    EffectiveThemeResponse,
    GraphThemeCreate,
    GraphThemeResponse,
    GraphThemeUpdate,
    SetDefaultResponse,
)
from app.api.graph_themes.v1.service import (
    BuiltinImmutableError,
    DefaultThemeError,
    DuplicateNameError,
    InvalidBaseThemeError,
    ThemeNotFoundError,
)
from app.db.session import get_async_db

router = APIRouter(prefix="/graph-themes", tags=["graph-themes"])


def _not_found(exc: ThemeNotFoundError) -> HTTPException:
    """Build a 404 from a :class:`ThemeNotFoundError`."""
    return HTTPException(status_code=404, detail=str(exc))


def _conflict(detail: str) -> HTTPException:
    """Build a 409 conflict response."""
    return HTTPException(status_code=409, detail=detail)


@router.get("/", response_model=list[GraphThemeResponse])
async def list_graph_themes(
    db: AsyncSession = Depends(get_async_db),
) -> list[GraphThemeResponse]:
    """List all themes (builtin + user)."""
    themes = await themes_service.list_themes(db)
    return [GraphThemeResponse.model_validate(t) for t in themes]


@router.post("/", response_model=GraphThemeResponse, status_code=201)
async def create_graph_theme(
    payload: GraphThemeCreate,
    db: AsyncSession = Depends(get_async_db),
) -> GraphThemeResponse:
    """Create a user theme (never a default)."""
    try:
        theme = await themes_service.create_theme(db, payload)
    except DuplicateNameError as exc:
        raise _conflict(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GraphThemeResponse.model_validate(theme)


@router.get("/effective", response_model=EffectiveThemeResponse)
async def effective_graph_theme(
    base_theme: str = Query(..., description="Base mode: executive-light | executive-dark"),
    db: AsyncSession = Depends(get_async_db),
) -> EffectiveThemeResponse:
    """Return the merged effective tokens (base ⊕ default-theme overrides)."""
    try:
        merged = await themes_service.get_effective_theme(db, base_theme)
    except InvalidBaseThemeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EffectiveThemeResponse.model_validate(merged)


@router.get("/{theme_id}", response_model=GraphThemeResponse)
async def get_graph_theme(
    theme_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> GraphThemeResponse:
    """Fetch a single theme."""
    try:
        theme = await themes_service.get_theme(db, theme_id)
    except ThemeNotFoundError as exc:
        raise _not_found(exc) from exc
    return GraphThemeResponse.model_validate(theme)


@router.patch("/{theme_id}", response_model=GraphThemeResponse)
async def update_graph_theme(
    theme_id: int,
    payload: GraphThemeUpdate,
    db: AsyncSession = Depends(get_async_db),
) -> GraphThemeResponse:
    """Update a user theme. Builtin themes are immutable (409)."""
    try:
        theme = await themes_service.update_theme(db, theme_id, payload)
    except ThemeNotFoundError as exc:
        raise _not_found(exc) from exc
    except BuiltinImmutableError as exc:
        raise _conflict(str(exc)) from exc
    except DuplicateNameError as exc:
        raise _conflict(str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return GraphThemeResponse.model_validate(theme)


@router.delete("/{theme_id}", status_code=204)
async def delete_graph_theme(
    theme_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """Delete a user theme. Builtin themes are immutable (409)."""
    try:
        await themes_service.delete_theme(db, theme_id)
    except ThemeNotFoundError as exc:
        raise _not_found(exc) from exc
    except BuiltinImmutableError as exc:
        raise _conflict(str(exc)) from exc
    except DefaultThemeError as exc:
        raise _conflict(str(exc)) from exc


@router.post("/{theme_id}/set-default", response_model=SetDefaultResponse)
async def set_default_graph_theme(
    theme_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> SetDefaultResponse:
    """Make the theme the default for its base mode (transactional swap)."""
    try:
        theme = await themes_service.set_default(db, theme_id)
    except ThemeNotFoundError as exc:
        raise _not_found(exc) from exc
    return SetDefaultResponse.model_validate(theme)


@router.post("/{theme_id}/clone", response_model=CloneResponse, status_code=201)
async def clone_graph_theme(
    theme_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> CloneResponse:
    """Copy-on-write a theme (builtin or user) into a new user row."""
    try:
        theme = await themes_service.clone_theme(db, theme_id)
    except ThemeNotFoundError as exc:
        raise _not_found(exc) from exc
    except DuplicateNameError as exc:
        raise _conflict(str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CloneResponse.model_validate(theme)
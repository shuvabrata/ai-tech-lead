"""Database access layer for the graph-themes API.

Provides async query functions for reading/writing ``graph_themes`` rows.
Write helpers keep the returned rows attached to the given ``AsyncSession``
so the caller can manage the transaction boundary (commit/rollback).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.graph_theme import GraphTheme


async def list_themes(db: AsyncSession) -> list[GraphTheme]:
    """Return all themes ordered by base mode, then name."""
    stmt = (
        select(GraphTheme)
        .order_by(GraphTheme.base_theme, GraphTheme.name)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_theme_by_id(db: AsyncSession, theme_id: int) -> GraphTheme | None:
    """Fetch a single theme by primary key."""
    stmt = select(GraphTheme).where(GraphTheme.id == theme_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_default_for_base_theme(
    db: AsyncSession, base_theme: str
) -> GraphTheme | None:
    """Return the default theme for a base mode, or ``None`` if unset.

    The partial unique index on ``(base_theme) WHERE is_default`` guarantees
    at most one row for any given base mode.
    """
    stmt = select(GraphTheme).where(
        GraphTheme.base_theme == base_theme,
        GraphTheme.is_default.is_(True),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def add_theme(db: AsyncSession, theme: GraphTheme) -> GraphTheme:
    """Persist a new theme row and refresh it."""
    db.add(theme)
    await db.flush()
    await db.refresh(theme)
    return theme


async def touch_theme(db: AsyncSession, theme: GraphTheme) -> GraphTheme:
    """Mark ``updated_at`` and refresh the row.

    Caller is expected to have mutated ``theme`` before calling; the refresh
    pulls the DB-generated ``updated_at`` back onto the instance.
    """
    theme.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(theme)
    return theme


async def delete_theme(db: AsyncSession, theme: GraphTheme) -> None:
    """Remove a theme row."""
    await db.delete(theme)
    await db.flush()
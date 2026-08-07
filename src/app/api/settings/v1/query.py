"""Database access layer for the settings API.

Provides async query functions for reading and writing
``application_settings`` rows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.application_settings import ApplicationSettings


async def check_conflicts(
    db: AsyncSession,
    keys: list[str],
    expected_updated_at: datetime | None,
) -> dict[str, dict[str, Any]]:
    """Check if any of the given *keys* have been updated since *expected_updated_at*.

    Returns a dict of ``{key: {"value": ..., "updated_at": ...}}`` for rows
    whose ``updated_at`` differs from the expected timestamp.  Returns an
    empty dict if there are no conflicts (or if *expected_updated_at* is
    ``None``, meaning no check was requested).
    """
    if expected_updated_at is None:
        return {}

    stmt = select(ApplicationSettings).where(ApplicationSettings.key.in_(keys))
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    conflicts: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.updated_at and row.updated_at > expected_updated_at:
            conflicts[row.key] = {
                "value": row.value,
                "updated_at": row.updated_at.isoformat(),
            }
    return conflicts


async def get_all_settings(db: AsyncSession) -> list[ApplicationSettings]:
    """Return all catalog rows ordered by key."""
    stmt = select(ApplicationSettings).order_by(ApplicationSettings.key)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_setting_by_key(
    db: AsyncSession, key: str
) -> ApplicationSettings | None:
    """Fetch a single catalog row by key."""
    stmt = select(ApplicationSettings).where(ApplicationSettings.key == key)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_setting_value(
    db: AsyncSession, key: str, value: Any
) -> ApplicationSettings | None:
    """Set the DB override *value* for a setting and return the updated row."""
    row = await get_setting_by_key(db, key)
    if row is None:
        return None
    row.value = value
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


async def reset_setting_value(
    db: AsyncSession, key: str
) -> ApplicationSettings | None:
    """Clear the DB override (set ``value = NULL``) for a setting."""
    row = await get_setting_by_key(db, key)
    if row is None:
        return None
    row.value = None
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


async def bulk_update_values(
    db: AsyncSession, updates: dict[str, Any]
) -> list[ApplicationSettings]:
    """Persist multiple setting overrides in a single transaction.

    Returns the refreshed rows for all updated keys.
    """
    now = datetime.now(timezone.utc)
    keys = list(updates.keys())
    stmt = select(ApplicationSettings).where(ApplicationSettings.key.in_(keys))
    result = await db.execute(stmt)
    rows = {r.key: r for r in result.scalars().all()}

    for key, value in updates.items():
        if key in rows:
            rows[key].value = value
            rows[key].updated_at = now

    await db.commit()
    # Refresh all updated rows.
    for row in rows.values():
        await db.refresh(row)
    return list(rows.values())


async def reset_all_values(db: AsyncSession) -> list[ApplicationSettings]:
    """Clear all DB overrides (set ``value = NULL`` on all rows).

    Returns the refreshed rows.
    """
    now = datetime.now(timezone.utc)
    stmt = select(ApplicationSettings)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    for row in rows:
        row.value = None
        row.updated_at = now
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows
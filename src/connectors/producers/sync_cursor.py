"""Sync cursor utility for ActivitySignal producers.

Uses asyncpg directly to avoid importing src/app/ FastAPI dependencies.
The producer_sync_state table schema is managed by Alembic via
``src/app/db/models/producer_sync_state.py``.

Usage::

    from connectors.producers.sync_cursor import get_sync_cursor, set_sync_cursor

    last = await get_sync_cursor("github", "org/repo")   # None on first run
    await set_sync_cursor("github", "org/repo", datetime.now(timezone.utc))
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import asyncpg


def _get_db_url() -> str:
    """Return a plain asyncpg-compatible postgres:// URL from DATABASE_URL env."""
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def get_sync_cursor(source: str, resource_id: str) -> Optional[datetime]:
    """Return the last successfully synced timestamp, or *None* on first run.

    Args:
        source:      Producer identifier, e.g. ``"github"`` or ``"jira"``.
        resource_id: Resource key, e.g. a repo full name or Jira project key.

    Returns:
        A timezone-aware :class:`datetime` in UTC, or ``None`` if no record exists.
    """
    conn = await asyncpg.connect(_get_db_url())
    try:
        row = await conn.fetchrow(
            "SELECT last_synced_at FROM producer_sync_state"
            " WHERE source=$1 AND resource_id=$2",
            source,
            resource_id,
        )
        if row is None:
            return None
        ts: datetime = row["last_synced_at"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    finally:
        await conn.close()


async def set_sync_cursor(
    source: str, resource_id: str, last_synced_at: datetime
) -> None:
    """Upsert the sync cursor for *source* / *resource_id*.

    Args:
        source:         Producer identifier.
        resource_id:    Resource key.
        last_synced_at: Timestamp to record (should be timezone-aware UTC).
    """
    conn = await asyncpg.connect(_get_db_url())
    try:
        await conn.execute(
            """
            INSERT INTO producer_sync_state (source, resource_id, last_synced_at)
            VALUES ($1, $2, $3)
            ON CONFLICT (source, resource_id)
            DO UPDATE SET last_synced_at = EXCLUDED.last_synced_at
            """,
            source,
            resource_id,
            last_synced_at,
        )
    finally:
        await conn.close()

"""Query layer for YAML-backed catalog metadata."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.db.models.catalog_metadata import CatalogMetadata
from app.query_catalog import (
    CatalogNamespace,
    CatalogQuery,
    load_catalog,
    load_namespaces,
)


def list_catalog_queries() -> list[CatalogQuery]:
    """Return all normalized catalog queries."""
    return load_catalog()


def list_catalog_namespaces() -> list[CatalogNamespace]:
    """Return catalog namespaces in display order."""
    return load_namespaces()


async def list_catalog_metadata(
    db: AsyncSession, *, is_favourite: bool | None = None
) -> list[CatalogMetadata]:
    """Return catalog metadata rows, optionally filtered by favourite state."""
    stmt = select(CatalogMetadata).order_by(CatalogMetadata.catalog_id)
    if is_favourite is not None:
        stmt = stmt.where(CatalogMetadata.is_favourite.is_(is_favourite))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_catalog_metadata(
    db: AsyncSession, catalog_id: str
) -> CatalogMetadata | None:
    """Fetch a single catalog metadata row by ``catalog_id``."""
    stmt = select(CatalogMetadata).where(
        CatalogMetadata.catalog_id == catalog_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def upsert_catalog_metadata(
    db: AsyncSession, catalog_id: str, is_favourite: bool
) -> CatalogMetadata:
    """Upsert a catalog metadata row (idempotent).

    Uses ``INSERT ... ON CONFLICT (catalog_id) DO UPDATE`` so repeated writes
    never create duplicate rows. The caller manages the transaction boundary
    (commit/rollback); the returned row is refreshed so the DB-generated
    ``updated_at`` is populated.
    """
    stmt = (
        pg_insert(CatalogMetadata)
        .values(catalog_id=catalog_id, is_favourite=is_favourite)
        .on_conflict_do_update(
            index_elements=[CatalogMetadata.catalog_id],
            set_={
                "is_favourite": is_favourite,
                "updated_at": func.now(),  # pylint: disable=not-callable
            },
        )
        .returning(CatalogMetadata)
    )
    result = await db.execute(stmt)
    row = result.scalar_one()
    await db.refresh(row)
    return row

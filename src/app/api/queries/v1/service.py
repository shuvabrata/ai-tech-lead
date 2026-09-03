"""Service layer for Query Catalog API v1."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.catalog_metadata import CatalogMetadata
from app.query_catalog import (
    CatalogLoadError,
    CatalogNamespace,
    CatalogQuery,
    get_catalog_query as loader_get_catalog_query,
)

from . import query


class CatalogQueryNotFoundError(ValueError):
    """Raised when a ``catalog_id`` does not exist in the YAML catalog."""


def list_namespaces() -> list[CatalogNamespace]:
    """List catalog namespaces in configured order."""
    return query.list_catalog_namespaces()


def list_catalog_queries(
    *,
    namespace: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    view: str | None = None,
) -> list[CatalogQuery]:
    """List catalog queries with optional filtering."""
    queries = query.list_catalog_queries()

    if namespace:
        normalized_namespace = namespace.strip().lower()
        queries = [
            catalog_query
            for catalog_query in queries
            if catalog_query.namespace.directory.lower() == normalized_namespace
            or catalog_query.namespace.name.lower() == normalized_namespace
        ]

    if tag:
        normalized_tag = tag.strip().lower()
        queries = [
            catalog_query
            for catalog_query in queries
            if any(item.lower() == normalized_tag for item in catalog_query.tags)
        ]

    if view:
        queries = [
            catalog_query
            for catalog_query in queries
            if view in catalog_query.available_views
        ]

    if q:
        search_text = q.strip().lower()
        queries = [
            catalog_query
            for catalog_query in queries
            if _matches_search(catalog_query, search_text)
        ]

    return queries


def get_catalog_query(namespace: str, slug: str) -> CatalogQuery | None:
    """Get one catalog query by namespace directory and slug."""
    catalog_id = f"{namespace}/{slug}"
    for catalog_query in query.list_catalog_queries():
        if catalog_query.id == catalog_id:
            return catalog_query
    return None


def _matches_search(catalog_query: CatalogQuery, search_text: str) -> bool:
    haystack = " ".join(
        [
            catalog_query.id,
            catalog_query.name,
            catalog_query.description,
            catalog_query.summary or "",
            catalog_query.namespace.name,
            catalog_query.namespace.directory,
            " ".join(catalog_query.tags),
            catalog_query.owner or "",
            catalog_query.status or "",
        ]
    ).lower()
    return search_text in haystack


# ── Catalog metadata (favourites) ─────────────────────────────────────


def _require_catalog_query(catalog_id: str) -> None:
    """Raise :class:`CatalogQueryNotFoundError` if ``catalog_id`` is unknown.

    Validates the id against the YAML catalog so metadata can only be stored
    for queries that actually exist.
    """
    try:
        loader_get_catalog_query(catalog_id)
    except CatalogLoadError as exc:
        raise CatalogQueryNotFoundError(
            f"Catalog query not found: {catalog_id}"
        ) from exc


async def list_catalog_metadata(
    db: AsyncSession, *, is_favourite: bool | None = None
) -> list[CatalogMetadata]:
    """List catalog metadata rows, optionally filtered by favourite state."""
    return await query.list_catalog_metadata(db, is_favourite=is_favourite)


async def get_catalog_metadata(
    db: AsyncSession, catalog_id: str
) -> CatalogMetadata | None:
    """Fetch one catalog metadata row by ``catalog_id``."""
    return await query.get_catalog_metadata(db, catalog_id)


async def set_catalog_metadata(
    db: AsyncSession, catalog_id: str, is_favourite: bool
) -> CatalogMetadata:
    """Upsert a catalog metadata row, validating ``catalog_id`` first.

    Raises :class:`CatalogQueryNotFoundError` (→ 404) if ``catalog_id`` does
    not exist in the YAML catalog.
    """
    _require_catalog_query(catalog_id)
    row = await query.upsert_catalog_metadata(db, catalog_id, is_favourite)
    await db.commit()
    await db.refresh(row)
    return row

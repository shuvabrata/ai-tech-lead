"""Service layer for Query Catalog API v1."""

from . import query
from app.query_catalog import CatalogNamespace, CatalogQuery


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

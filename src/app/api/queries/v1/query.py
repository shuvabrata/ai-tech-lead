"""Query layer for YAML-backed catalog metadata."""

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

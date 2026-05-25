"""Pydantic models for Query Catalog API v1."""

from pydantic import BaseModel

from app.query_catalog import CatalogNamespace, CatalogQuery


class CatalogQueryListResponse(BaseModel):
    """Response wrapper for catalog query listings."""

    items: list[CatalogQuery]
    count: int


class CatalogNamespaceListResponse(BaseModel):
    """Response wrapper for catalog namespace listings."""

    items: list[CatalogNamespace]
    count: int

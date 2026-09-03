"""Pydantic models for Query Catalog API v1."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.query_catalog import CatalogNamespace, CatalogQuery


class CatalogQueryListResponse(BaseModel):
    """Response wrapper for catalog query listings."""

    items: list[CatalogQuery]
    count: int


class CatalogNamespaceListResponse(BaseModel):
    """Response wrapper for catalog namespace listings."""

    items: list[CatalogNamespace]
    count: int


class CatalogMetadataResponse(BaseModel):
    """Response body for a single catalog metadata row."""

    id: int
    catalog_id: str
    is_favourite: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CatalogMetadataListResponse(BaseModel):
    """Response wrapper for catalog metadata listings."""

    items: list[CatalogMetadataResponse]
    count: int


class CatalogMetadataPatch(BaseModel):
    """Request body for PUT /api/v1/queries/catalog-metadata/{catalog_id}.

    A generic partial patch — currently only ``is_favourite`` is supported.
    """

    is_favourite: bool = Field(description="Whether the catalog query is a favourite")

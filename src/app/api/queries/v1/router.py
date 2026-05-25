"""FastAPI router for YAML-backed query catalog metadata."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from . import service
from .model import CatalogNamespaceListResponse, CatalogQueryListResponse
from app.query_catalog import CatalogQuery

router = APIRouter(prefix="/queries", tags=["queries"])


@router.get("/catalog", response_model=CatalogQueryListResponse, response_model_exclude_none=True)
async def list_catalog_queries(
    namespace: str | None = Query(default=None, description="Filter by namespace name or directory"),
    tag: str | None = Query(default=None, description="Filter by exact tag"),
    q: str | None = Query(default=None, description="Search query names, descriptions, tags, and ids"),
    view: Literal["graph", "tabular"] | None = Query(default=None, description="Filter by available view"),
):
    """List normalized query catalog entries."""
    items = service.list_catalog_queries(namespace=namespace, tag=tag, q=q, view=view)
    return CatalogQueryListResponse(items=items, count=len(items))


@router.get("/catalog/namespaces", response_model=CatalogNamespaceListResponse)
async def list_catalog_namespaces():
    """List query catalog namespaces in display order."""
    items = service.list_namespaces()
    return CatalogNamespaceListResponse(items=items, count=len(items))


@router.get("/catalog/{namespace}/{slug}", response_model=CatalogQuery, response_model_exclude_none=True)
async def get_catalog_query(namespace: str, slug: str):
    """Get one normalized query catalog entry."""
    catalog_query = service.get_catalog_query(namespace=namespace, slug=slug)
    if catalog_query is None:
        raise HTTPException(status_code=404, detail="Catalog query not found")
    return catalog_query

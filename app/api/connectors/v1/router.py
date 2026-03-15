from typing import Any, Dict, List, Union

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db
from . import service
from .model import (
    ConnectorConfigUpdateRequest,
    ConnectorStatus,
    EmailConfigItemRequest,
    GithubConfigItemRequest,
    JiraConfigItemRequest,
    SlackConfigItemRequest,
    TeamsConfigItemRequest,
    ConfluenceConfigItemRequest,
    GoogleDocsConfigItemRequest,
    SharepointConfigItemRequest,
    TestConnectionResponse,
)


router = APIRouter(prefix="/connectors", tags=["connectors"])

ConfigItemRequest = Union[
    GithubConfigItemRequest,
    JiraConfigItemRequest,
    SlackConfigItemRequest,
    TeamsConfigItemRequest,
    ConfluenceConfigItemRequest,
    GoogleDocsConfigItemRequest,
    SharepointConfigItemRequest,
    EmailConfigItemRequest,
]


@router.get("/", response_model=List[ConnectorStatus])
async def list_connectors(db: AsyncSession = Depends(get_async_db)):
    return await service.list_connectors(db)


@router.get("/{connector_type}", response_model=ConnectorStatus)
async def get_connector(connector_type: str, db: AsyncSession = Depends(get_async_db)):
    try:
        return await service.get_connector(db, connector_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{connector_type}", response_model=ConnectorStatus)
async def update_connector_config(
    connector_type: str,
    payload: ConnectorConfigUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        return await service.update_connector_config(db, connector_type, payload.config)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{connector_type}/configs", response_model=List[Dict[str, Any]])
async def list_config_items(connector_type: str, db: AsyncSession = Depends(get_async_db)):
    try:
        return await service.list_config_items(db, connector_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{connector_type}/configs", response_model=Dict[str, Any])
async def create_config_item(
    connector_type: str,
    item: ConfigItemRequest,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        return await service.save_config_item(db, connector_type, item, item_id=None)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{connector_type}/configs/{item_id}", response_model=Dict[str, Any])
async def update_config_item(
    connector_type: str,
    item_id: int,
    item: ConfigItemRequest,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        return await service.save_config_item(db, connector_type, item, item_id=item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{connector_type}/configs/{item_id}")
async def delete_config_item(
    connector_type: str,
    item_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    try:
        await service.delete_config_item(db, connector_type, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/{connector_type}/test", response_model=TestConnectionResponse)
async def test_connection(connector_type: str, db: AsyncSession = Depends(get_async_db)):
    try:
        return await service.test_connection(db, connector_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{connector_type}")
async def delete_all_configs(
    connector_type: str, db: AsyncSession = Depends(get_async_db)
):
    try:
        await service.delete_all_configs(db, connector_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}

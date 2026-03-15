from datetime import datetime
from typing import Any, Dict, List, Optional, Type

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.connector import Connector
from app.db.models import connector_configs as config_models


CONFIG_MODEL_MAP: Dict[str, Type] = {
    "github": config_models.GithubConfig,
    "jira": config_models.JiraConfig,
    "slack": config_models.SlackConfig,
    "teams": config_models.TeamsConfig,
    "confluence": config_models.ConfluenceConfig,
    "google_docs": config_models.GoogleDocsConfig,
    "sharepoint": config_models.SharepointConfig,
    "email": config_models.EmailConfig,
}


async def get_all_connectors(db: AsyncSession) -> List[Connector]:
    result = await db.execute(select(Connector))
    return result.scalars().all()


async def get_connector(db: AsyncSession, connector_type: str) -> Optional[Connector]:
    result = await db.execute(
        select(Connector).where(Connector.connector_type == connector_type)
    )
    return result.scalars().first()


async def update_connector_config(
    db: AsyncSession, connector_type: str, config_dict: Optional[Dict[str, Any]]
) -> Optional[Connector]:
    connector = await get_connector(db, connector_type)
    if not connector:
        return None
    connector.config = config_dict
    await db.commit()
    await db.refresh(connector)
    return connector


_UNSET = object()


async def update_connector_status(
    db: AsyncSession,
    connector_type: str,
    status: str,
    last_tested_at: Any = _UNSET,
    error: Optional[str] = None,
) -> Optional[Connector]:
    connector = await get_connector(db, connector_type)
    if not connector:
        return None
    connector.status = status
    connector.last_test_error = error
    if last_tested_at is not _UNSET:
        connector.last_tested_at = last_tested_at
    await db.commit()
    await db.refresh(connector)
    return connector


async def get_configs(db: AsyncSession, connector_type: str) -> List[Any]:
    model = CONFIG_MODEL_MAP[connector_type]
    connector = await get_connector(db, connector_type)
    if not connector:
        return []
    result = await db.execute(select(model).where(model.connector_id == connector.id))
    return result.scalars().all()


async def upsert_config_item(
    db: AsyncSession,
    connector_type: str,
    item_id: Optional[int],
    data: Dict[str, Any],
) -> Optional[Any]:
    model = CONFIG_MODEL_MAP[connector_type]
    connector = await get_connector(db, connector_type)
    if not connector:
        return None

    if item_id is None:
        db_item = model(**data, connector_id=connector.id)
        db.add(db_item)
        await db.commit()
        await db.refresh(db_item)
        return db_item

    result = await db.execute(
        select(model).where(model.id == item_id, model.connector_id == connector.id)
    )
    db_item = result.scalars().first()
    if not db_item:
        return None

    for key, value in data.items():
        setattr(db_item, key, value)
    await db.commit()
    await db.refresh(db_item)
    return db_item


async def delete_config_item(
    db: AsyncSession, connector_type: str, item_id: int
) -> bool:
    model = CONFIG_MODEL_MAP[connector_type]
    connector = await get_connector(db, connector_type)
    if not connector:
        return False
    result = await db.execute(
        select(model).where(model.id == item_id, model.connector_id == connector.id)
    )
    db_item = result.scalars().first()
    if not db_item:
        return False
    await db.delete(db_item)
    await db.commit()
    return True


async def delete_all_configs(db: AsyncSession, connector_type: str) -> None:
    model = CONFIG_MODEL_MAP[connector_type]
    connector = await get_connector(db, connector_type)
    if not connector:
        return
    await db.execute(delete(model).where(model.connector_id == connector.id))
    await db.commit()

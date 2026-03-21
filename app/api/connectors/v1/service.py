from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.encryption import encrypt
from . import query
from .registry import CONNECTOR_REGISTRY


SENSITIVE_FIELDS: Dict[str, Dict[str, str]] = {
    "github": {"access_token": "encrypted_access_token"},
    "jira": {"api_token": "encrypted_api_token"},
    "email": {"password": "encrypted_password"},
}

REQUEST_FIELDS: Dict[str, List[str]] = {
    "github": ["url", "access_token", "branch_name_patterns", "extraction_sources"],
    "jira": ["url", "email", "api_token"],
    "slack": ["channel_id", "channel_name"],
    "teams": ["channel_id", "channel_name"],
    "confluence": ["space_key", "space_name"],
    "google_docs": ["drive_id", "drive_name"],
    "sharepoint": ["site_url"],
    "email": [
        "smtp_host",
        "smtp_port",
        "imap_host",
        "imap_port",
        "username",
        "use_tls",
        "password",
    ],
}

RESPONSE_FIELDS: Dict[str, List[str]] = {
    "github": ["id", "url", "access_token", "branch_name_patterns", "extraction_sources", "created_at", "updated_at"],
    "jira": ["id", "url", "email", "api_token", "created_at", "updated_at"],
    "slack": ["id", "channel_id", "channel_name", "created_at", "updated_at"],
    "teams": ["id", "channel_id", "channel_name", "created_at", "updated_at"],
    "confluence": ["id", "space_key", "space_name", "created_at", "updated_at"],
    "google_docs": ["id", "drive_id", "drive_name", "created_at", "updated_at"],
    "sharepoint": ["id", "site_url", "created_at", "updated_at"],
    "email": [
        "id",
        "smtp_host",
        "smtp_port",
        "imap_host",
        "imap_port",
        "username",
        "use_tls",
        "password",
        "created_at",
        "updated_at",
    ],
}


def _validate_connector_type(connector_type: str) -> Dict[str, str]:
    meta = CONNECTOR_REGISTRY.get(connector_type)
    if not meta:
        raise ValueError("Unknown connector_type")
    return meta


def _to_dict(item: Any) -> Dict[str, Any]:
    if hasattr(item, "dict"):
        return item.dict(exclude_unset=True)
    return dict(item)


def _mask(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return "********"


async def list_connectors(db: AsyncSession) -> List[Dict[str, Any]]:
    connectors = await query.get_all_connectors(db)
    results = []
    for connector in connectors:
        meta = CONNECTOR_REGISTRY.get(connector.connector_type)
        if not meta:
            continue
        results.append(
            {
                "connector_type": connector.connector_type,
                "display_name": meta["display_name"],
                "status": connector.status,
                "enabled": connector.enabled,
                "config": connector.config,
                "last_tested_at": connector.last_tested_at,
                "last_test_error": connector.last_test_error,
            }
        )
    return results


async def get_connector(db: AsyncSession, connector_type: str) -> Dict[str, Any]:
    meta = _validate_connector_type(connector_type)
    connector = await query.get_connector(db, connector_type)
    if not connector:
        raise ValueError("Connector not found")
    return {
        "connector_type": connector.connector_type,
        "display_name": meta["display_name"],
        "status": connector.status,
        "enabled": connector.enabled,
        "config": connector.config,
        "last_tested_at": connector.last_tested_at,
        "last_test_error": connector.last_test_error,
    }


async def update_connector_config(
    db: AsyncSession, connector_type: str, config: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    _validate_connector_type(connector_type)
    connector = await query.update_connector_config(db, connector_type, config)
    if not connector:
        raise ValueError("Connector not found")
    return await get_connector(db, connector_type)


async def list_config_items(db: AsyncSession, connector_type: str) -> List[Dict[str, Any]]:
    _validate_connector_type(connector_type)
    rows = await query.get_configs(db, connector_type)
    encrypted_map = SENSITIVE_FIELDS.get(connector_type, {})
    response_fields = RESPONSE_FIELDS[connector_type]

    results = []
    for row in rows:
        row_dict: Dict[str, Any] = {"id": row.id}
        for field in response_fields:
            if field == "id":
                continue
            encrypted_field = encrypted_map.get(field)
            if encrypted_field:
                row_dict[field] = _mask(getattr(row, encrypted_field))
            else:
                row_dict[field] = getattr(row, field)
        results.append(row_dict)
    return results


async def save_config_item(
    db: AsyncSession,
    connector_type: str,
    item: Any,
    item_id: Optional[int] = None,
) -> Dict[str, Any]:
    _validate_connector_type(connector_type)
    data = _to_dict(item)
    allowed_fields = set(REQUEST_FIELDS[connector_type])
    encrypted_map = SENSITIVE_FIELDS.get(connector_type, {})

    payload: Dict[str, Any] = {}
    for key, value in data.items():
        if key not in allowed_fields:
            continue
        encrypted_field = encrypted_map.get(key)
        if encrypted_field:
            if value in (None, ""):
                payload[encrypted_field] = None
            else:
                payload[encrypted_field] = encrypt(value)
        else:
            payload[key] = value

    saved = await query.upsert_config_item(db, connector_type, item_id, payload)
    if not saved:
        raise ValueError("Config item not found")

    # Convert saved row to response shape
    response_fields = RESPONSE_FIELDS[connector_type]
    row_dict: Dict[str, Any] = {"id": saved.id}
    for field in response_fields:
        if field == "id":
            continue
        encrypted_field = encrypted_map.get(field)
        if encrypted_field:
            row_dict[field] = _mask(getattr(saved, encrypted_field))
        else:
            row_dict[field] = getattr(saved, field)
    return row_dict


async def delete_config_item(db: AsyncSession, connector_type: str, item_id: int) -> None:
    _validate_connector_type(connector_type)
    deleted = await query.delete_config_item(db, connector_type, item_id)
    if not deleted:
        raise ValueError("Config item not found")


async def test_connection(db: AsyncSession, connector_type: str) -> Dict[str, Any]:
    _validate_connector_type(connector_type)
    now = datetime.now(timezone.utc)
    await query.update_connector_status(
        db,
        connector_type,
        status="connected",
        last_tested_at=now,
        error=None,
    )
    return {"success": True, "message": "Connection verified (stub)"}


async def delete_all_configs(db: AsyncSession, connector_type: str) -> None:
    _validate_connector_type(connector_type)
    await query.delete_all_configs(db, connector_type)
    await query.update_connector_status(
        db,
        connector_type,
        status="not_configured",
        last_tested_at=None,
        error=None,
    )

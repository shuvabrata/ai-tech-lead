from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.logger import logger
from app.common.encryption import decrypt, encrypt
from . import query
from .registry import CONNECTOR_REGISTRY


CONNECTOR_CONFIG_SENSITIVE_FIELDS: Dict[str, Dict[str, str]] = {
    "atlassian_mcp": {"token": "encrypted_token"},
}

CONNECTOR_CONFIG_ALLOWED_FIELDS: Dict[str, List[str]] = {
    "atlassian_mcp": ["enabled", "server_url", "token"],
}

SENSITIVE_FIELDS: Dict[str, Dict[str, str]] = {
    "github": {"access_token": "encrypted_access_token"},
    "jira": {"api_token": "encrypted_api_token"},
    "email": {"password": "encrypted_password"},
}

REQUEST_FIELDS: Dict[str, List[str]] = {
    "github": ["url", "access_token", "search_filters", "branch_name_patterns", "extraction_sources"],
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
    "github": [
        "id",
        "url",
        "access_token",
        "search_filters",
        "branch_name_patterns",
        "extraction_sources",
        "created_at",
        "updated_at",
    ],
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


def _normalize_connector_config(
    connector_type: str,
    config: Optional[Dict[str, Any]],
    include_secrets: bool = False,
) -> Optional[Dict[str, Any]]:
    if not isinstance(config, dict):
        return config

    encrypted_map = CONNECTOR_CONFIG_SENSITIVE_FIELDS.get(connector_type)
    if not encrypted_map:
        return config

    normalized: Dict[str, Any] = {}
    for key, value in config.items():
        if key in encrypted_map.values():
            continue
        normalized[key] = value

    for field, encrypted_field in encrypted_map.items():
        encrypted_value = config.get(encrypted_field)
        if include_secrets:
            normalized[field] = decrypt(encrypted_value) if encrypted_value else None
        else:
            normalized[field] = _mask(encrypted_value)

    return normalized


def _validate_atlassian_mcp_config(
    data: Dict[str, Any],
    existing_config: Optional[Dict[str, Any]],
) -> None:
    enabled = bool(data.get("enabled"))
    if not enabled:
        return

    server_url = data.get("server_url")
    if not isinstance(server_url, str) or not server_url.strip():
        msg = (
            "Server URL is required when Atlassian MCP is enabled. "
            "Use the Atlassian cloud endpoint: https://mcp.atlassian.com/v1/mcp"
        )
        logger.error("[atlassian_mcp] Validation failed: %s", msg)
        raise ValueError(msg)

    token = data.get("token")
    encrypted_token = data.get("encrypted_token")
    existing_encrypted_token = None
    if isinstance(existing_config, dict):
        existing_encrypted_token = existing_config.get("encrypted_token")
    has_any_secret = bool(token) or bool(encrypted_token) or bool(existing_encrypted_token)

    if not has_any_secret:
        msg = (
            "API token is required when Atlassian MCP is enabled. "
            "Generate a Rovo MCP scoped token at https://id.atlassian.com/manage-profile/security/api-tokens"
        )
        logger.error("[atlassian_mcp] Validation failed: %s", msg)
        raise ValueError(msg)


def _prepare_connector_config_for_storage(
    connector_type: str,
    config: Optional[Dict[str, Any]],
    existing_config: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if config is None:
        return None

    if connector_type != "atlassian_mcp":
        return config

    if not isinstance(config, dict):
        raise ValueError("Connector config must be an object")

    existing_dict = existing_config if isinstance(existing_config, dict) else {}
    allowed_fields = set(CONNECTOR_CONFIG_ALLOWED_FIELDS[connector_type])
    encrypted_map = CONNECTOR_CONFIG_SENSITIVE_FIELDS.get(connector_type, {})
    payload: Dict[str, Any] = {}

    for key, value in config.items():
        if key not in allowed_fields:
            continue

        encrypted_field = encrypted_map.get(key)
        if encrypted_field:
            if value in (None, ""):
                if existing_dict.get(encrypted_field):
                    payload[encrypted_field] = existing_dict.get(encrypted_field)
            else:
                payload[encrypted_field] = encrypt(value)
        else:
            payload[key] = value

    for encrypted_field in encrypted_map.values():
        if encrypted_field not in payload and existing_dict.get(encrypted_field):
            payload[encrypted_field] = existing_dict.get(encrypted_field)

    _validate_atlassian_mcp_config(payload, existing_dict)
    return payload


def _validate_github_item_payload(data: Dict[str, Any], item_id: Optional[int]) -> None:
    url = data.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("GitHub repository URL is required")

    access_token = data.get("access_token")
    if item_id is None and (not isinstance(access_token, str) or not access_token.strip()):
        raise ValueError("GitHub access_token is required")

    if "access_token" in data and isinstance(access_token, str) and not access_token.strip():
        raise ValueError("GitHub access_token cannot be empty")


def _validate_jira_item_payload(data: Dict[str, Any], item_id: Optional[int]) -> None:
    api_token = data.get("api_token")
    if item_id is None and (not isinstance(api_token, str) or not api_token.strip()):
        raise ValueError("Jira api_token is required")

    if "api_token" in data and isinstance(api_token, str) and not api_token.strip():
        raise ValueError("Jira api_token cannot be empty")


async def list_connectors(db: AsyncSession) -> List[Dict[str, Any]]:
    logger.debug("[list_connectors] Starting list_connectors")
    connectors = await query.get_all_connectors(db)
    logger.debug(f"[list_connectors] Retrieved {len(connectors)} connectors")
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
                "config": _normalize_connector_config(connector.connector_type, connector.config),
                "last_tested_at": connector.last_tested_at,
                "last_test_error": connector.last_test_error,
            }
        )
    logger.debug(f"[list_connectors] Returning {len(results)} normalized connectors")
    return results


async def get_connector(
    db: AsyncSession,
    connector_type: str,
    include_secrets: bool = False,
) -> Dict[str, Any]:
    # TODO: The 'include_secrets' flag is a temporary measure. This should be
    # replaced with a proper role-based access control check based on the
    # authenticated user's permissions. Exposing secrets via a query parameter is not secure.
    meta = _validate_connector_type(connector_type)
    connector = await query.get_connector(db, connector_type)
    if not connector:
        raise ValueError("Connector not found")
    return {
        "connector_type": connector.connector_type,
        "display_name": meta["display_name"],
        "status": connector.status,
        "enabled": connector.enabled,
        "config": _normalize_connector_config(
            connector.connector_type,
            connector.config,
            include_secrets=include_secrets,
        ),
        "last_tested_at": connector.last_tested_at,
        "last_test_error": connector.last_test_error,
    }


async def update_connector_config(
    db: AsyncSession, connector_type: str, config: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    _validate_connector_type(connector_type)
    existing_connector = await query.get_connector(db, connector_type)
    if not existing_connector:
        raise ValueError("Connector not found")
    prepared_config = _prepare_connector_config_for_storage(
        connector_type,
        config,
        existing_connector.config,
    )
    connector = await query.update_connector_config(db, connector_type, prepared_config)
    if not connector:
        raise ValueError("Connector not found")
    return await get_connector(db, connector_type)


async def clear_connector_config(
    db: AsyncSession, connector_type: str
) -> Dict[str, Any]:
    """Clear all stored connector-level config, including any encrypted secrets."""
    _validate_connector_type(connector_type)
    connector = await query.update_connector_config(db, connector_type, {})
    if not connector:
        raise ValueError("Connector not found")
    return await get_connector(db, connector_type)


async def list_config_items(
    db: AsyncSession, connector_type: str, include_secrets: bool = False
) -> List[Dict[str, Any]]:
    # TODO: The 'include_secrets' flag is a temporary measure. This should be
    # replaced with a proper role-based access control check based on the
    # authenticated user's permissions. Exposing secrets via a query parameter is not secure.
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
                encrypted_value = getattr(row, encrypted_field)
                if include_secrets:
                    row_dict[field] = decrypt(encrypted_value) if encrypted_value else None
                else:
                    row_dict[field] = _mask(encrypted_value)
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
    if connector_type == "github":
        _validate_github_item_payload(data, item_id)
    if connector_type == "jira":
        _validate_jira_item_payload(data, item_id)
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

    if connector_type == "atlassian_mcp":
        return await _test_atlassian_mcp_connection(db, now)

    if connector_type == "github_mcp":
        return await _test_github_mcp_connection(db, now)

    # Stub for connectors that do not yet have a real test implementation.
    await query.update_connector_status(
        db,
        connector_type,
        status="connected",
        last_tested_at=now,
        error=None,
    )
    return {"success": True, "message": "Connection verified (stub)"}


async def _test_atlassian_mcp_connection(db: AsyncSession, now: datetime) -> Dict[str, Any]:
    """Run a real Atlassian MCP connectivity check using DB-backed config."""
    from app.ai_agent.mcp_integration.client_manager import AtlassianMCPClientManager  # pylint: disable=import-outside-toplevel
    from app.settings import settings as _settings  # pylint: disable=import-outside-toplevel

    connector = await get_connector(db, "atlassian_mcp", include_secrets=True)
    config = connector.get("config") or {}

    db_server_url = config.get("server_url")
    db_token = config.get("token")
    db_enabled = config.get("enabled")

    resolved_server_url = db_server_url or _settings.ATLASSIAN_MCP_SERVER_URL
    resolved_token = db_token or _settings.ATLASSIAN_MCP_TOKEN
    resolved_enabled = bool(db_enabled if db_enabled is not None else _settings.ATLASSIAN_MCP_ENABLED)

    logger.debug(
        "[atlassian_mcp test] resolved: enabled=%r server_url=%r token_present=%r token_source=%s",
        resolved_enabled,
        resolved_server_url,
        bool(resolved_token),
        "db" if db_token else "env",
    )

    manager = AtlassianMCPClientManager(
        atlassian_server_url=resolved_server_url,
        atlassian_token=resolved_token,
        atlassian_enabled=resolved_enabled,
        request_timeout_seconds=_settings.HTTP_REQUEST_TIMEOUT,
    )
    result = manager.check_connection()
    logger.debug("[atlassian_mcp test] check_connection result=%r", result)
    connected = result.get("connected", False)
    error_msg = result.get("error") if not connected else None
    db_status = "connected" if connected else "error"
    await query.update_connector_status(
        db,
        "atlassian_mcp",
        status=db_status,
        last_tested_at=now,
        error=error_msg,
    )
    if connected:
        return {"success": True, "message": "Atlassian MCP connection verified"}
    return {"success": False, "message": error_msg or "Atlassian MCP connection failed"}


async def _test_github_mcp_connection(db: AsyncSession, now: datetime) -> Dict[str, Any]:
    """Run a GitHub MCP connectivity check using env-driven runtime config."""
    from app.ai_agent.mcp_integration.client_manager import GithubMCPClientManager  # pylint: disable=import-outside-toplevel
    from app.settings import settings as _settings  # pylint: disable=import-outside-toplevel

    manager = GithubMCPClientManager(
        github_server_url=_settings.GITHUB_MCP_SERVER_URL,
        github_token=_settings.GITHUB_MCP_TOKEN,
        github_enabled=_settings.GITHUB_MCP_ENABLED,
        request_timeout_seconds=_settings.HTTP_REQUEST_TIMEOUT,
    )
    result = manager.check_connection()
    connected = result.get("connected", False)
    error_msg = result.get("error") if not connected else None
    db_status = "connected" if connected else "error"
    await query.update_connector_status(
        db,
        "github_mcp",
        status=db_status,
        last_tested_at=now,
        error=error_msg,
    )
    if connected:
        return {"success": True, "message": "GitHub MCP connection verified"}
    return {"success": False, "message": error_msg or "GitHub MCP connection failed"}


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

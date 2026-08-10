"""Business logic for the settings API.

Handles resolving effective values (DB override → env → default), validating
candidate updates against ``RuntimeConfig``, and refreshing the local cache.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.settings.v1 import query as qry
from common.logger import logger
from common.runtime_settings import RuntimeConfig, RuntimeConfigCache
from common.runtime_settings.events import publish_settings_changed

# Module-level cache — initialised by ``src/app/runtime_settings.py`` on
# startup.  Tests can replace this with a fresh instance.
_runtime_cache: RuntimeConfigCache = RuntimeConfigCache()


def set_runtime_cache(cache: RuntimeConfigCache) -> None:
    """Replace the module-level cache (used during startup / tests)."""
    global _runtime_cache  # noqa: PLW0603
    _runtime_cache = cache


def get_runtime_cache() -> RuntimeConfigCache:
    """Return the current runtime cache instance."""
    return _runtime_cache


# ── RabbitMQ propagation support ────────────────────────────────────────


async def _publish_changed(keys: list[str]) -> str | None:
    """Publish a ``settings.changed`` event for the given keys.

    Returns a propagation warning string if the event could not be published
    (or no connection is available), or ``None`` on success.

    The DB commit has already succeeded and the local cache has already been
    refreshed by the caller before this is invoked, so a publish failure is
    non-fatal — settings are still saved and applied locally.
    """
    # Lazy import to avoid a circular dependency between this service module
    # and ``app.main`` (which imports this router's module).
    # pylint: disable=import-outside-toplevel
    from app.main import get_rabbitmq_connection

    connection = get_rabbitmq_connection()
    if connection is None:
        logger.warning(
            "No RabbitMQ connection available — settings.changed not published"
        )
        return (
            "Settings saved but change could not be propagated to "
            "other running processes."
        )

    success = await publish_settings_changed(keys, connection)
    if not success:
        return (
            "Settings saved but change could not be propagated to "
            "other running processes."
        )
    return None


# ── Exceptions ─────────────────────────────────────────────────────────


class ConflictError(ValueError):
    """Raised when a write would overwrite a change made by another session.

    Attributes:
        conflicting_keys: Keys that were modified since the caller loaded them.
        current_values: Current values of the conflicting keys.
    """

    def __init__(
        self,
        conflicting_keys: list[str],
        current_values: dict[str, Any],
    ) -> None:
        self.conflicting_keys = conflicting_keys
        self.current_values = current_values
        keys_str = ", ".join(sorted(conflicting_keys))
        super().__init__(
            f"Settings changed by another session: {keys_str}. "
            f"Reload and retry."
        )


# ── Source resolution ──────────────────────────────────────────────────


def _resolve_source(
    db_row_value: Any,
    setting_key: str,
) -> tuple[Any, str]:
    """Determine the effective value and source for a single setting.

    Precedence: DB override > env value > code default.

    If *setting_key* is not a field on ``RuntimeConfig`` (e.g. a sensitive
    bootstrap secret), the function returns the raw DB value or env string
    without type coercion, and falls back to ``None`` for the code default.
    """
    # 1. DB override
    if db_row_value is not None:
        return db_row_value, "db"

    # 2. Environment value — check os.environ so we can distinguish
    #    "env var set to default" from "no env var, using code default".
    env_raw = os.environ.get(setting_key)
    if env_raw is not None:
        # If the key is not in RuntimeConfig (e.g. a bootstrap secret),
        # return the raw string without type coercion.
        if setting_key not in RuntimeConfig.model_fields:
            return env_raw, "env"
        # Convert the raw string to the expected Python type.
        field = RuntimeConfig.model_fields[setting_key]
        if field.annotation is bool:
            return env_raw.lower() in ("1", "true", "yes"), "env"
        if field.annotation is int:
            return int(env_raw), "env"
        return env_raw, "env"

    # 3. Code default (from RuntimeConfig, or None for bootstrap-only keys)
    if setting_key not in RuntimeConfig.model_fields:
        return None, "default"
    default = RuntimeConfig.model_fields[setting_key].default
    return default, "default"


def _resolve_effective_config(db_rows: list[Any]) -> RuntimeConfig:
    """Build an effective ``RuntimeConfig`` from DB rows + env + defaults.

    Invalid persisted overrides are logged and ignored, falling back to
    env/default for that key.

    Sensitive rows (``is_sensitive=True``) are excluded from the effective
    config — they are bootstrap/secret values that should never be served
    by the runtime snapshot API.
    """
    overrides = {}
    for row in db_rows:
        if row.is_sensitive:
            continue
        value, _ = _resolve_source(row.value, row.key)
        if value is not None:
            overrides[row.key] = value
    try:
        return RuntimeConfig(**overrides)
    except ValidationError:
        # One or more overrides are stale/invalid.  Try each key
        # individually so valid overrides are kept.
        logger.warning(
            "Invalid persisted overrides detected; falling back per-key"
        )
        valid = {}
        for key, value in list(overrides.items()):
            try:
                RuntimeConfig(**{key: value})
                valid[key] = value
            except ValidationError:
                logger.warning(
                    "Ignoring invalid persisted override: %s=%r", key, value
                )
        return RuntimeConfig(**valid)


# ── Sensitive value masking ────────────────────────────────────────────


def _mask_value(value: Any) -> str | None:
    """Return a fully masked string for sensitive settings.

    The original value is completely replaced with ``"*******"`` so no
    information about length or content is leaked.

    Examples::

        "sk-abc123def456xyz789"     →  "*******"
        "ghp_abc123def456"          →  "*******"
        "amqp://user:pass@host:5672" →  "*******"
        "short"                     →  "*******"
        None                        →  None
    """
    if value is None:
        return None
    return "*******"


# ── Public API ─────────────────────────────────────────────────────────


async def get_all_settings(
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """Return source-aware setting rows for the UI."""
    rows = await qry.get_all_settings(db)
    result = []
    for row in rows:
        effective_value, source = _resolve_source(row.value, row.key)
        if row.is_sensitive:
            effective_value = _mask_value(effective_value)
        result.append({
            "key": row.key,
            "value": _mask_value(row.value) if row.is_sensitive else row.value,
            "effective_value": effective_value,
            "source": source,
            "value_type": row.value_type,
            "category": row.category,
            "description": row.description,
            "apply_mode": row.apply_mode,
            "is_sensitive": row.is_sensitive,
            "updated_at": row.updated_at,
        })
    return result


async def get_runtime_snapshot(db: AsyncSession) -> RuntimeConfig:
    """Build the effective ``RuntimeConfig`` from DB + env + defaults."""
    rows = await qry.get_all_settings(db)
    return _resolve_effective_config(rows)


async def bulk_update(
    db: AsyncSession,
    updates: dict[str, Any],
    expected_updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Validate and persist a bulk update.

    Returns the new effective values (key → value) and an optional
    propagation warning.

    Raises ``ValueError`` for unknown keys, ``ValidationError`` for invalid
    values, and ``ConflictError`` if any row changed since
    *expected_updated_at*.
    """
    # 1. Load catalog rows for requested keys.
    rows = await qry.get_all_settings(db)
    row_map = {r.key: r for r in rows}

    # 2. Reject unknown keys.
    unknown = [k for k in updates if k not in row_map]
    if unknown:
        raise ValueError(f"Unknown setting keys: {', '.join(sorted(unknown))}")

    # 2b. Optimistic concurrency check.
    conflicts = await qry.check_conflicts(
        db, list(updates.keys()), expected_updated_at
    )
    if conflicts:
        current_values = {k: v["value"] for k, v in conflicts.items()}
        raise ConflictError(list(conflicts.keys()), current_values)

    # 3. Build full candidate effective RuntimeConfig.
    #    Only include keys that are actual RuntimeConfig fields (skip
    #    sensitive bootstrap secrets like OPENAI_API_KEY).
    candidate_overrides = {
        r.key: r.value
        for r in rows
        if r.value is not None and r.key in RuntimeConfig.model_fields
    }
    candidate_overrides.update(updates)

    try:
        RuntimeConfig(**candidate_overrides)
    except ValidationError as exc:
        # Re-raise with a readable message.
        raise ValidationError.from_exception_data(
            "Invalid settings update",
            line_errors=exc.errors(),
        ) from exc

    # 4. Persist all changed values in one DB transaction.
    updated_rows = await qry.bulk_update_values(db, updates)

    # 5. Refresh local cache with the newly persisted values.
    refreshed_rows = await qry.get_all_settings(db)
    _runtime_cache.refresh(_resolve_effective_config(refreshed_rows))

    # 6. Publish RabbitMQ invalidation event (best-effort).
    propagation_warning = await _publish_changed(list(updates.keys()))

    # 7. Return effective values.
    return {
        "updated": {r.key: r.value for r in updated_rows},
        "propagation_warning": propagation_warning,
    }


async def update_single(
    db: AsyncSession,
    key: str,
    value: Any,
    expected_updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Validate and persist a single-key update.

    Returns the source-aware row dict.

    Raises ``ValueError`` for unknown keys, ``ValidationError`` for invalid
    values, and ``ConflictError`` if the row changed since
    *expected_updated_at*.
    """
    # 1. Load catalog row.
    row = await qry.get_setting_by_key(db, key)
    if row is None:
        raise ValueError(f"Unknown setting key: {key}")

    # 1b. Optimistic concurrency check.
    conflicts = await qry.check_conflicts(db, [key], expected_updated_at)
    if conflicts:
        current_values = {k: v["value"] for k, v in conflicts.items()}
        raise ConflictError(list(conflicts.keys()), current_values)

    # 2. Validate candidate value.
    all_rows = await qry.get_all_settings(db)
    candidate_overrides = {
        r.key: r.value
        for r in all_rows
        if r.value is not None and r.key in RuntimeConfig.model_fields
    }
    candidate_overrides[key] = value
    try:
        RuntimeConfig(**candidate_overrides)
    except ValidationError as exc:
        raise ValidationError.from_exception_data(
            "Invalid settings update",
            line_errors=exc.errors(),
        ) from exc

    # 3. Persist.
    updated = await qry.update_setting_value(db, key, value)
    if updated is None:
        raise ValueError(f"Unknown setting key: {key}")

    # 4. Refresh local cache.
    refreshed_rows = await qry.get_all_settings(db)
    _runtime_cache.refresh(_resolve_effective_config(refreshed_rows))

    # 5. Publish RabbitMQ invalidation event (best-effort).
    propagation_warning = await _publish_changed([key])

    # 6. Return source-aware response.
    effective_value, source = _resolve_source(updated.value, key)
    if updated.is_sensitive:
        effective_value = _mask_value(effective_value)
    return {
        "key": key,
        "value": _mask_value(updated.value) if updated.is_sensitive else updated.value,
        "effective_value": effective_value,
        "source": source,
        "value_type": updated.value_type,
        "category": updated.category,
        "description": updated.description,
        "apply_mode": updated.apply_mode,
        "is_sensitive": updated.is_sensitive,
        "updated_at": updated.updated_at,
        "propagation_warning": propagation_warning,
    }


async def reset_single(
    db: AsyncSession,
    key: str,
    expected_updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Reset a single setting to ``NULL`` (env/default falls through).

    Returns the source-aware row dict.

    Raises ``ConflictError`` if the row changed since
    *expected_updated_at*.
    """
    row = await qry.get_setting_by_key(db, key)
    if row is None:
        raise ValueError(f"Unknown setting key: {key}")

    # 1b. Optimistic concurrency check.
    conflicts = await qry.check_conflicts(db, [key], expected_updated_at)
    if conflicts:
        current_values = {k: v["value"] for k, v in conflicts.items()}
        raise ConflictError(list(conflicts.keys()), current_values)

    row = await qry.reset_setting_value(db, key)
    if row is None:
        raise ValueError(f"Unknown setting key: {key}")

    # Refresh local cache.
    all_rows = await qry.get_all_settings(db)
    _runtime_cache.refresh(_resolve_effective_config(all_rows))

    # Publish RabbitMQ invalidation event (best-effort).
    propagation_warning = await _publish_changed([key])

    effective_value, source = _resolve_source(None, key)
    if row.is_sensitive:
        effective_value = _mask_value(effective_value)
    return {
        "key": key,
        "value": None,
        "effective_value": effective_value,
        "source": source,
        "value_type": row.value_type,
        "category": row.category,
        "description": row.description,
        "apply_mode": row.apply_mode,
        "is_sensitive": row.is_sensitive,
        "updated_at": row.updated_at,
        "propagation_warning": propagation_warning,
    }


async def reset_all(
    db: AsyncSession,
    expected_updated_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Reset all settings to ``NULL`` (env/default falls through).

    Returns source-aware row dicts.

    Raises ``ConflictError`` if any row changed since
    *expected_updated_at*.
    """
    # 0. Optimistic concurrency check — check all keys.
    rows = await qry.get_all_settings(db)
    all_keys = [r.key for r in rows]
    conflicts = await qry.check_conflicts(db, all_keys, expected_updated_at)
    if conflicts:
        current_values = {k: v["value"] for k, v in conflicts.items()}
        raise ConflictError(list(conflicts.keys()), current_values)

    rows = await qry.reset_all_values(db)
    _runtime_cache.refresh(_resolve_effective_config(rows))

    # Publish RabbitMQ invalidation event (best-effort).
    reset_keys = [row.key for row in rows]
    propagation_warning = await _publish_changed(reset_keys)

    result = []
    for row in rows:
        effective_value, source = _resolve_source(None, row.key)
        if row.is_sensitive:
            effective_value = _mask_value(effective_value)
        result.append({
            "key": row.key,
            "value": None,
            "effective_value": effective_value,
            "source": source,
            "value_type": row.value_type,
            "category": row.category,
            "description": row.description,
            "apply_mode": row.apply_mode,
            "is_sensitive": row.is_sensitive,
            "updated_at": row.updated_at,
            "propagation_warning": propagation_warning,
        })
    return result
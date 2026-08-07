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
from app.settings import settings as app_settings
from common.logger import logger
from common.runtime_settings import RuntimeConfig, RuntimeConfigCache

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
    """
    # 1. DB override
    if db_row_value is not None:
        return db_row_value, "db"

    # 2. Environment value — check os.environ so we can distinguish
    #    "env var set to default" from "no env var, using code default".
    if setting_key in os.environ:
        return getattr(app_settings, setting_key), "env"

    # 3. Code default (from RuntimeConfig)
    default = RuntimeConfig.model_fields[setting_key].default
    return default, "default"


def _resolve_effective_config(db_rows: list[Any]) -> RuntimeConfig:
    """Build an effective ``RuntimeConfig`` from DB rows + env + defaults.

    Invalid persisted overrides are logged and ignored, falling back to
    env/default for that key.
    """
    overrides = {}
    for row in db_rows:
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


# ── Public API ─────────────────────────────────────────────────────────


async def get_all_settings(
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """Return source-aware setting rows for the UI."""
    rows = await qry.get_all_settings(db)
    result = []
    for row in rows:
        effective_value, source = _resolve_source(row.value, row.key)
        result.append({
            "key": row.key,
            "value": row.value,
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
    candidate_overrides = {r.key: r.value for r in rows if r.value is not None}
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

    # 6. Return effective values (propagation handled in Phase 5).
    return {
        "updated": {r.key: r.value for r in updated_rows},
        "propagation_warning": None,
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
    candidate_overrides = {r.key: r.value for r in all_rows if r.value is not None}
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

    # 5. Return source-aware response.
    effective_value, source = _resolve_source(updated.value, key)
    return {
        "key": key,
        "value": updated.value,
        "effective_value": effective_value,
        "source": source,
        "value_type": updated.value_type,
        "category": updated.category,
        "description": updated.description,
        "apply_mode": updated.apply_mode,
        "is_sensitive": updated.is_sensitive,
        "updated_at": updated.updated_at,
    }


async def reset_single(
    db: AsyncSession, key: str
) -> dict[str, Any]:
    """Reset a single setting to ``NULL`` (env/default falls through).

    Returns the source-aware row dict.
    """
    row = await qry.reset_setting_value(db, key)
    if row is None:
        raise ValueError(f"Unknown setting key: {key}")

    # Refresh local cache.
    all_rows = await qry.get_all_settings(db)
    _runtime_cache.refresh(_resolve_effective_config(all_rows))

    effective_value, source = _resolve_source(None, key)
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
    }


async def reset_all(
    db: AsyncSession,
) -> list[dict[str, Any]]:
    """Reset all settings to ``NULL`` (env/default falls through).

    Returns source-aware row dicts.
    """
    rows = await qry.reset_all_values(db)
    _runtime_cache.refresh(_resolve_effective_config(rows))

    result = []
    for row in rows:
        effective_value, source = _resolve_source(None, row.key)
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
        })
    return result
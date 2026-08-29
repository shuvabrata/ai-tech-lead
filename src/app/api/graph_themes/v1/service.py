"""Business logic for the graph-themes API.

Handles create/update/delete/clone/set-default with builtin immutability
guards and a transactional default swap, plus the server-side merge that
produces the effective theme (base tokens ⊕ DB overrides).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.graph_themes.v1 import query as qry
from app.api.graph_themes.v1.models import (
    GraphThemeCreate,
    GraphThemeUpdate,
    ThemeOverrides,
)
from app.common.graph_theme import merge_theme_overrides
from app.db.models.graph_theme import (
    SOURCE_BUILTIN,
    SOURCE_USER,
    VALID_BASE_THEMES,
    GraphTheme,
)
from app.dash_app.styles import get_theme_tokens
from common.logger import logger


class ThemeNotFoundError(ValueError):
    """Raised when a theme id does not exist."""


class BuiltinImmutableError(ValueError):
    """Raised when a write targets an immutable builtin theme.

    Builtin themes are seeded and immutable; editing one must go through an
    explicit clone (copy-on-write).
    """


class InvalidBaseThemeError(ValueError):
    """Raised when an unknown ``base_theme`` is requested."""


def _require_user_theme(theme: GraphTheme) -> None:
    """Raise if ``theme`` is an immutable builtin row."""
    if theme.source == SOURCE_BUILTIN:
        raise BuiltinImmutableError(
            f"Theme '{theme.name}' is a builtin and cannot be modified. "
            "Duplicate it first to create an editable copy."
        )


def _overrides_to_dict(overrides: ThemeOverrides) -> dict[str, Any]:
    """Convert a validated Pydantic override doc to the JSONB dict shape."""
    return overrides.model_dump(by_alias=True, exclude_none=True)


# ── Read ───────────────────────────────────────────────────────────────


async def list_themes(db: AsyncSession) -> list[GraphTheme]:
    """Return all themes."""
    return await qry.list_themes(db)


async def get_theme(db: AsyncSession, theme_id: int) -> GraphTheme:
    """Fetch one theme or raise :class:`ThemeNotFoundError`."""
    theme = await qry.get_theme_by_id(db, theme_id)
    if theme is None:
        raise ThemeNotFoundError(f"Graph theme {theme_id} not found.")
    return theme


# ── Write ──────────────────────────────────────────────────────────────


async def create_theme(
    db: AsyncSession, payload: GraphThemeCreate
) -> GraphTheme:
    """Create a new user theme."""
    theme = GraphTheme(
        name=payload.name,
        base_theme=payload.base_theme,
        is_default=False,
        overrides=_overrides_to_dict(payload.overrides),
        source=SOURCE_USER,
    )
    theme = await qry.add_theme(db, theme)
    await db.commit()
    await db.refresh(theme)
    logger.info(
        "Created graph theme '%s' (base=%s)", theme.name, theme.base_theme
    )
    return theme


async def update_theme(
    db: AsyncSession, theme_id: int, payload: GraphThemeUpdate
) -> GraphTheme:
    """Update a user theme (builtin → :class:`BuiltinImmutableError`)."""
    theme = await get_theme(db, theme_id)
    _require_user_theme(theme)

    if payload.name is not None:
        theme.name = payload.name
    if payload.base_theme is not None:
        theme.base_theme = payload.base_theme
    if payload.overrides is not None:
        theme.overrides = _overrides_to_dict(payload.overrides)

    theme = await qry.touch_theme(db, theme)
    await db.commit()
    await db.refresh(theme)
    logger.info("Updated graph theme '%s' (id=%s)", theme.name, theme.id)
    return theme


async def delete_theme(db: AsyncSession, theme_id: int) -> None:
    """Delete a user theme (builtin → :class:`BuiltinImmutableError`)."""
    theme = await get_theme(db, theme_id)
    _require_user_theme(theme)
    name = theme.name
    await qry.delete_theme(db, theme)
    await db.commit()
    logger.info("Deleted graph theme '%s' (id=%s)", name, theme_id)


async def clone_theme(db: AsyncSession, theme_id: int) -> GraphTheme:
    """Copy-on-write: create a new user row from an existing theme.

    Works for both builtin and user sources. The clone is never a default and
    is named ``<name> (copy)``.
    """
    source = await get_theme(db, theme_id)
    clone = GraphTheme(
        name=f"{source.name} (copy)",
        base_theme=source.base_theme,
        is_default=False,
        overrides=dict(source.overrides or {}),
        source=SOURCE_USER,
    )
    clone = await qry.add_theme(db, clone)
    await db.commit()
    await db.refresh(clone)
    logger.info(
        "Cloned graph theme '%s' → '%s' (id=%s)",
        source.name,
        clone.name,
        clone.id,
    )
    return clone


async def set_default(db: AsyncSession, theme_id: int) -> GraphTheme:
    """Make ``theme_id`` the default for its base mode (transactional swap).

    Clears any existing default for the same base mode, then sets the new one.
    The clear is flushed **before** the new default is set so the partial
    unique index ``uq_graph_themes_default_per_base`` never observes two
    defaults for the same base mode in a single statement batch (which would
    otherwise raise ``IntegrityError``).
    """
    theme = await get_theme(db, theme_id)

    current = await qry.get_default_for_base_theme(db, theme.base_theme)
    if current is not None and current.id != theme.id:
        current.is_default = False
        # Flush the clear in isolation so the index never sees two defaults.
        await db.flush()

    theme.is_default = True
    await db.flush()
    await db.commit()
    await db.refresh(theme)
    logger.info(
        "Set graph theme '%s' (id=%s) as default for %s",
        theme.name,
        theme.id,
        theme.base_theme,
    )
    return theme


# ── Effective theme ────────────────────────────────────────────────────


async def get_effective_theme(
    db: AsyncSession, base_theme: str
) -> dict[str, Any]:
    """Return the merged effective theme for a base mode.

    Resolution order:
      1. The default theme for ``base_theme`` (if any) provides overrides.
      2. Otherwise, the empty "Default" anchor (no overrides) is used.

    The base tokens come from the hardcoded ``THEME_TOKENS`` registry (the
    single source of truth); the DB overrides are merged on top.
    """
    if base_theme not in VALID_BASE_THEMES:
        raise InvalidBaseThemeError(
            f"Unknown base theme '{base_theme}'. "
            f"Allowed: {', '.join(VALID_BASE_THEMES)}."
        )

    base_tokens = get_theme_tokens(base_theme)
    default_theme = await qry.get_default_for_base_theme(db, base_theme)

    overrides: dict[str, Any] = {}
    if default_theme is not None:
        overrides = default_theme.overrides or {}

    merged = merge_theme_overrides(base_tokens, overrides)
    merged["base_theme"] = base_theme
    return merged
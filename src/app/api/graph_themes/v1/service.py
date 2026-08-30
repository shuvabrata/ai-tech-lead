"""Business logic for the graph-themes API.

Handles create/update/delete/clone/set-default with builtin immutability
guards and a transactional default swap, plus the server-side merge that
produces the effective theme (base tokens ⊕ DB overrides).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.graph_themes.v1 import query as qry
from app.api.graph_themes.v1.models import (
    GraphThemeCreate,
    GraphThemeUpdate,
    ThemeOverrides,
)
from app.common.graph_theme import effective_semantic_theme, merge_theme_overrides, parse_overrides
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


class DefaultThemeError(ValueError):
    """Raised when a write targets the current default theme.

    The default theme for a base mode cannot be deleted directly — the user
    must set another theme as default first, so the base mode never silently
    falls back to the hardcoded base palette.
    """


class InvalidBaseThemeError(ValueError):
    """Raised when an unknown ``base_theme`` is requested."""


class DuplicateNameError(ValueError):
    """Raised when a theme name already exists for the same base mode.

    Backed by the ``uq_graph_themes_name_base_theme`` unique constraint.
    """


def _require_user_theme(theme: GraphTheme) -> None:
    """Raise if ``theme`` is an immutable builtin row."""
    if theme.source == SOURCE_BUILTIN:
        raise BuiltinImmutableError(
            f"Theme '{theme.name}' is a builtin and cannot be modified. "
            "Duplicate it first to create an editable copy."
        )


def _require_not_default(theme: GraphTheme) -> None:
    """Raise if ``theme`` is the current default for its base mode."""
    if theme.is_default:
        raise DefaultThemeError(
            f"Theme '{theme.name}' is the default for its base mode and "
            "cannot be deleted. Set another theme as default first."
        )


def _overrides_to_dict(overrides: ThemeOverrides) -> dict[str, Any]:
    """Convert a validated Pydantic override doc to the JSONB dict shape."""
    return overrides.model_dump(by_alias=True, exclude_none=True)


def _snapshot_overrides(
    base_theme: str, overrides: ThemeOverrides
) -> dict[str, Any]:
    """Materialize a **full snapshot** of the effective theme for a user theme.

    Custom (user) themes are stored as complete snapshots so they are immune to
    future base-palette changes: every field — including the untyped ``default``
    node which has no editor card — is resolved to its effective value and
    frozen. This is the deliberate reversal of the "deltas only" principle,
    scoped to ``source == user`` rows (builtin themes remain sparse deltas that
    track the base palette).
    """
    effective = effective_semantic_theme(
        get_theme_tokens(base_theme), overrides
    )
    return {
        "nodes": effective["nodes"],
        "edges": effective["edges"],
        "global": effective["global"],
    }


def _snapshot_delta(
    base_theme: str, snapshot: dict[str, Any]
) -> dict[str, Any]:
    """Extract the user's intentional overrides from a full snapshot.

    A full snapshot is a complete document frozen to ``base_theme``'s palette,
    so re-snapshotting it verbatim against a *different* base is a no-op (every
    field is explicit and overrides the new base). To re-base a theme, we must
    first recover the user's deltas — the fields that differ from the pure
    ``base_theme`` palette — then re-snapshot those deltas against the new base.

    Returns a sparse override doc (only the fields that diverge from the base),
    suitable for :func:`parse_overrides` / :func:`_snapshot_overrides`.
    """
    base = effective_semantic_theme(get_theme_tokens(base_theme), {})
    delta: dict[str, Any] = {}

    nodes = snapshot.get("nodes", {})
    base_nodes = base.get("nodes", {})
    delta_nodes: dict[str, Any] = {}
    for node_type, props in nodes.items():
        base_props = base_nodes.get(node_type, {})
        changed = {
            key: value
            for key, value in props.items()
            if base_props.get(key) != value
        }
        if changed:
            delta_nodes[node_type] = changed
    if delta_nodes:
        delta["nodes"] = delta_nodes

    for section in ("edges", "global"):
        props = snapshot.get(section, {})
        base_props = base.get(section, {})
        changed = {
            key: value
            for key, value in props.items()
            if base_props.get(key) != value
        }
        if changed:
            delta[section] = changed

    return delta


def _raise_on_duplicate_name(exc: IntegrityError) -> None:
    """Translate a name-uniqueness IntegrityError into :class:`DuplicateNameError`.

    The ``uq_graph_themes_name_base_theme`` constraint enforces that ``name``
    is unique within a ``base_theme``. Other integrity errors are re-raised
    unchanged.
    """
    message = str(exc.orig) if exc.orig is not None else str(exc)
    if "uq_graph_themes_name_base_theme" in message:
        raise DuplicateNameError(
            "A theme with this name already exists for this base mode."
        ) from exc
    raise exc


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
    """Create a new user theme as a full snapshot of the effective theme."""
    theme = GraphTheme(
        name=payload.name,
        base_theme=payload.base_theme,
        is_default=False,
        overrides=_snapshot_overrides(payload.base_theme, payload.overrides),
        source=SOURCE_USER,
    )
    try:
        theme = await qry.add_theme(db, theme)
        await db.commit()
        await db.refresh(theme)
    except IntegrityError as exc:
        await db.rollback()
        _raise_on_duplicate_name(exc)
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

    # Determine the effective base after this update. If the base is actually
    # changing, guard against orphaning the current default for the old base
    # mode (same contract as deleting a default).
    new_base = (
        payload.base_theme if payload.base_theme is not None else theme.base_theme
    )
    if payload.base_theme is not None and new_base != theme.base_theme:
        _require_not_default(theme)

    if payload.name is not None:
        theme.name = payload.name
    if payload.base_theme is not None and new_base != theme.base_theme:
        # Re-base the theme: recover the user's deltas from the existing full
        # snapshot (diffed against the OLD base), then re-snapshot those deltas
        # against the NEW base. Re-snapshotting the snapshot verbatim would be
        # a no-op because a full snapshot is immune to base changes.
        theme.overrides = _snapshot_overrides(
            new_base,
            parse_overrides(
                _snapshot_delta(theme.base_theme, theme.overrides or {})
            ),
        )
    if payload.overrides is not None:
        theme.overrides = _snapshot_overrides(new_base, payload.overrides)
    theme.base_theme = new_base

    try:
        theme = await qry.touch_theme(db, theme)
        await db.commit()
        await db.refresh(theme)
    except IntegrityError as exc:
        await db.rollback()
        _raise_on_duplicate_name(exc)
    logger.info("Updated graph theme '%s' (id=%s)", theme.name, theme.id)
    return theme


async def delete_theme(db: AsyncSession, theme_id: int) -> None:
    """Delete a user theme (builtin → :class:`BuiltinImmutableError`).

    The current default theme is also protected (→ :class:`DefaultThemeError`),
    so a base mode never silently falls back to the hardcoded base palette.
    """
    theme = await get_theme(db, theme_id)
    _require_user_theme(theme)
    _require_not_default(theme)
    name = theme.name
    await qry.delete_theme(db, theme)
    await db.commit()
    logger.info("Deleted graph theme '%s' (id=%s)", name, theme_id)


async def clone_theme(db: AsyncSession, theme_id: int) -> GraphTheme:
    """Copy-on-write: create a new user row from an existing theme.

    Works for both builtin and user sources. The clone is never a default and
    is named ``<name> (copy)``. The clone is stored as a **full snapshot** of
    the source's effective theme (immune to future base-palette changes).
    """
    source = await get_theme(db, theme_id)
    clone = GraphTheme(
        name=f"{source.name} (copy)",
        base_theme=source.base_theme,
        is_default=False,
        overrides=_snapshot_overrides(source.base_theme, parse_overrides(source.overrides or {})),
        source=SOURCE_USER,
    )
    try:
        clone = await qry.add_theme(db, clone)
        await db.commit()
        await db.refresh(clone)
    except IntegrityError as exc:
        await db.rollback()
        _raise_on_duplicate_name(exc)
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
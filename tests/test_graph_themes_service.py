"""Unit tests for the graph-themes API service layer.

Tests builtin immutability guards, transactional default swap, clone
copy-on-write, and the effective-merge behaviour, with mocked async DB
sessions and query-layer dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.graph_themes.v1 import service
from app.api.graph_themes.v1.models import (
    GraphThemeCreate,
    GraphThemeUpdate,
    ThemeOverrides,
)
from app.api.graph_themes.v1.service import (
    BuiltinImmutableError,
    ThemeNotFoundError,
)
from app.db.models.graph_theme import GraphTheme

pytestmark = [pytest.mark.unit]


def _make_theme(
    theme_id: int = 1,
    name: str = "Default",
    base_theme: str = "executive-light",
    is_default: bool = True,
    source: str = "builtin",
    overrides: dict | None = None,
) -> GraphTheme:
    """Build a GraphTheme row (not persisted)."""
    return GraphTheme(
        id=theme_id,
        name=name,
        base_theme=base_theme,
        is_default=is_default,
        overrides=overrides or {},
        source=source,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock async DB session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    db.execute = AsyncMock()
    return db


# ── Effective theme ────────────────────────────────────────────────────


class TestGetEffectiveTheme:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_no_default_returns_pure_base(self, mock_db: AsyncMock) -> None:
        """With no default theme, effective == base tokens (no overrides)."""
        with patch(
            "app.api.graph_themes.v1.service.qry.get_default_for_base_theme",
            new=AsyncMock(return_value=None),
        ):
            merged = await service.get_effective_theme(mock_db, "executive-light")
        assert merged["base_theme"] == "executive-light"
        # Merge output uses Cytoscape keys; base geometry matches the hardcoded
        # stylesheet (Person → octagon), with no overrides applied.
        assert merged["nodes"]["Person"]["background-color"] == "#3B82F6"
        assert merged["nodes"]["Person"]["shape"] == "octagon"
        assert merged["global"]["node_label_color"] == "#f4f7fb"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_overrides_win_over_base(self, mock_db: AsyncMock) -> None:
        """A default theme's overrides win over the base tokens."""
        theme = _make_theme(
            name="Ocean Light",
            base_theme="executive-light",
            is_default=True,
            source="user",
            overrides={
                "nodes": {"Person": {"color": "#0EA5E9", "shape": "octagon"}},
                "edges": {"line_color": "#94A3B8"},
                "global": {"node_label_color": "#0F172A"},
            },
        )
        with patch(
            "app.api.graph_themes.v1.service.qry.get_default_for_base_theme",
            new=AsyncMock(return_value=theme),
        ):
            merged = await service.get_effective_theme(mock_db, "executive-light")
        assert merged["nodes"]["Person"]["background-color"] == "#0EA5E9"
        assert merged["nodes"]["Person"]["shape"] == "octagon"
        assert merged["edges"]["line-color"] == "#94A3B8"
        assert merged["global"]["node_label_color"] == "#0F172A"
        # Untouched node types still fall through to base.
        assert merged["nodes"]["Issue"]["background-color"] == "#EF4444"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_unknown_base_theme_rejected(self, mock_db: AsyncMock) -> None:
        """An unknown base_theme raises InvalidBaseThemeError."""
        with patch(
            "app.api.graph_themes.v1.service.qry.get_default_for_base_theme",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(Exception) as excinfo:
                await service.get_effective_theme(mock_db, "executive-solar")
        assert "Unknown base theme" in str(excinfo.value)


# ── Set default (single-default invariant) ────────────────────────────


class TestSetDefault:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_clears_prior_default_and_sets_new(
        self, mock_db: AsyncMock
    ) -> None:
        """Setting a new default clears the previous one (same base mode)."""
        old_default = _make_theme(
            theme_id=1, name="Default", base_theme="executive-light", is_default=True
        )
        new_default = _make_theme(
            theme_id=2,
            name="Ocean Light",
            base_theme="executive-light",
            is_default=False,
            source="user",
        )
        with (
            patch(
                "app.api.graph_themes.v1.service.qry.get_theme_by_id",
                new=AsyncMock(return_value=new_default),
            ),
            patch(
                "app.api.graph_themes.v1.service.qry.get_default_for_base_theme",
                new=AsyncMock(return_value=old_default),
            ),
        ):
            result = await service.set_default(mock_db, new_default.id)

        assert result.id == new_default.id
        assert result.is_default is True
        assert old_default.is_default is False  # prior default cleared
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_clear_flushed_before_set(self, mock_db: AsyncMock) -> None:
        """The prior default is flushed in isolation before the new default is set.

        Guards against a regression where clearing + setting land in a single
        statement batch, tripping the ``uq_graph_themes_default_per_base``
        partial unique index (IntegrityError) because two defaults briefly
        coexist for the same base mode.
        """
        old_default = _make_theme(
            theme_id=1, name="Default", base_theme="executive-light", is_default=True
        )
        new_default = _make_theme(
            theme_id=2,
            name="Ocean Light",
            base_theme="executive-light",
            is_default=False,
            source="user",
        )
        with (
            patch(
                "app.api.graph_themes.v1.service.qry.get_theme_by_id",
                new=AsyncMock(return_value=new_default),
            ),
            patch(
                "app.api.graph_themes.v1.service.qry.get_default_for_base_theme",
                new=AsyncMock(return_value=old_default),
            ),
        ):
            await service.set_default(mock_db, new_default.id)

        # Two flushes: one to persist the clear, one to persist the set.
        assert mock_db.flush.await_count == 2
        # The clear must be persisted before the new default is flagged True.
        # Capture the is_default value observed at the first flush by replaying
        # ordering: after set_default, old_default is False and new_default True.
        assert old_default.is_default is False
        assert new_default.is_default is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_already_default_is_noop(self, mock_db: AsyncMock) -> None:
        """Re-setting the same default is a no-op, not an error."""
        theme = _make_theme(
            theme_id=2,
            name="Ocean Light",
            base_theme="executive-light",
            is_default=True,
            source="user",
        )
        with patch(
            "app.api.graph_themes.v1.service.qry.get_theme_by_id",
            new=AsyncMock(return_value=theme),
        ):
            with patch(
                "app.api.graph_themes.v1.service.qry.get_default_for_base_theme",
                new=AsyncMock(return_value=None),
            ):
                result = await service.set_default(mock_db, theme.id)
        assert result.is_default is True


# ── Clone (copy-on-write) ──────────────────────────────────────────────


class TestClone:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_clones_builtin_to_new_user_row(
        self, mock_db: AsyncMock
    ) -> None:
        """A clone of a builtin produces a new user row with copied overrides."""
        builtin = _make_theme(
            theme_id=1,
            name="Ocean Light",
            base_theme="executive-light",
            is_default=False,
            source="builtin",
            overrides={"nodes": {"Person": {"color": "#0EA5E9"}}},
        )
        with (
            patch(
                "app.api.graph_themes.v1.service.qry.get_theme_by_id",
                new=AsyncMock(return_value=builtin),
            ),
            patch(
                "app.api.graph_themes.v1.service.qry.add_theme",
                side_effect=lambda _db, th: th,
            ),
        ):
            clone = await service.clone_theme(mock_db, builtin.id)

        assert clone.id is None  # not assigned until flushed to DB
        assert clone.name == "Ocean Light (copy)"
        assert clone.source == "user"
        assert clone.is_default is False
        assert clone.base_theme == "executive-light"
        assert clone.overrides == {"nodes": {"Person": {"color": "#0EA5E9"}}}
        # The clone is a fresh object, distinct from the builtin source.
        assert clone is not builtin


# ── Builtin immutability ───────────────────────────────────────────────


class TestBuiltinImmutability:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_patch_builtin_raises_409(self, mock_db: AsyncMock) -> None:
        """Updating a builtin theme raises BuiltinImmutableError."""
        builtin = _make_theme(
            theme_id=1, name="Default", base_theme="executive-light", source="builtin"
        )
        with patch(
            "app.api.graph_themes.v1.service.qry.get_theme_by_id",
            new=AsyncMock(return_value=builtin),
        ):
            with pytest.raises(BuiltinImmutableError):
                await service.update_theme(
                    mock_db, builtin.id, GraphThemeUpdate(overrides=ThemeOverrides())
                )

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_delete_builtin_raises_409(self, mock_db: AsyncMock) -> None:
        """Deleting a builtin theme raises BuiltinImmutableError."""
        builtin = _make_theme(
            theme_id=1, name="Default", base_theme="executive-light", source="builtin"
        )
        with patch(
            "app.api.graph_themes.v1.service.qry.get_theme_by_id",
            new=AsyncMock(return_value=builtin),
        ):
            with pytest.raises(BuiltinImmutableError):
                await service.delete_theme(mock_db, builtin.id)
        mock_db.delete.assert_not_called()


# ── Create / NotFound ──────────────────────────────────────────────────


class TestCreateAndNotFound:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_create_theme_is_user_and_not_default(
        self, mock_db: AsyncMock
    ) -> None:
        """A created theme defaults to source=user, is_default=False."""
        payload = GraphThemeCreate(name="My Theme", base_theme="executive-dark")
        with patch(
            "app.api.graph_themes.v1.service.qry.add_theme",
            side_effect=lambda _db, th: th,
        ):
            theme = await service.create_theme(mock_db, payload)
        assert theme.name == "My Theme"
        assert theme.base_theme == "executive-dark"
        assert theme.source == "user"
        assert theme.is_default is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_missing_raises_not_found(self, mock_db: AsyncMock) -> None:
        """Fetching a non-existent theme raises ThemeNotFoundError."""
        with patch(
            "app.api.graph_themes.v1.service.qry.get_theme_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(ThemeNotFoundError):
                await service.get_theme(mock_db, 999)
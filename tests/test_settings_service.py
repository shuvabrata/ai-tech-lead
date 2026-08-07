"""Unit tests for the settings API service layer.

Tests source precedence, unknown-key rejection, candidate validation, and
reset behavior with mocked database and query dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.settings.v1 import service, query as qry
from app.db.models.application_settings import ApplicationSettings
from common.runtime_settings import RuntimeConfig, RuntimeConfigCache

pytestmark = [pytest.mark.unit]


# ── Fixtures ───────────────────────────────────────────────────────────


def _make_row(
    key: str,
    value: object | None = None,
    value_type: str = "integer",
    category: str | None = "network",
    apply_mode: str = "dynamic",
    is_sensitive: bool = False,
) -> ApplicationSettings:
    """Build an ApplicationSettings row for testing."""
    return ApplicationSettings(
        key=key,
        value=value,
        value_type=value_type,
        category=category,
        description=f"{key} description",
        apply_mode=apply_mode,
        is_sensitive=is_sensitive,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock async DB session."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def fresh_cache() -> RuntimeConfigCache:
    """Replace the module-level cache with a fresh one, then restore."""
    original = service.get_runtime_cache()
    cache = RuntimeConfigCache()
    service.set_runtime_cache(cache)
    yield cache
    service.set_runtime_cache(original)


# ── Source precedence ──────────────────────────────────────────────────


class TestSourcePrecedence:
    @pytest.mark.unit
    def test_db_override_wins(self, mock_db: AsyncMock) -> None:
        """A non-null DB value takes precedence over env/default."""
        value, source = service._resolve_source(90, "HTTP_REQUEST_TIMEOUT")
        assert value == 90
        assert source == "db"

    @pytest.mark.unit
    @patch.dict(service.os.environ, {"TIMEZONE": "Asia/Kolkata"}, clear=False)
    def test_env_value_when_db_null(self, mock_db: AsyncMock) -> None:
        """A null DB value falls back to the env value."""
        value, source = service._resolve_source(None, "TIMEZONE")
        assert value == "Asia/Kolkata"
        assert source == "env"

    @pytest.mark.unit
    @patch.dict(service.os.environ, {}, clear=True)
    def test_default_when_db_null_and_no_env(self, mock_db: AsyncMock) -> None:
        """A null DB value and no env falls back to the code default."""
        value, source = service._resolve_source(None, "HTTP_REQUEST_TIMEOUT")
        assert value == 60
        assert source == "default"

    @pytest.mark.unit
    @patch.dict(service.os.environ, {}, clear=True)
    def test_default_value_from_runtime_config(self, mock_db: AsyncMock) -> None:
        """The default is read from RuntimeConfig model fields."""
        value, source = service._resolve_source(None, "RECENT_ACTIONS_LIMIT")
        assert value == 5
        assert source == "default"


# ── get_all_settings ───────────────────────────────────────────────────


class TestGetAllSettings:
    pytestmark = [pytest.mark.asyncio]

    @pytest.mark.unit
    @patch.dict(service.os.environ, {}, clear=True)
    async def test_returns_source_aware_rows(self, mock_db: AsyncMock) -> None:
        """get_all_settings returns effective values with correct source."""
        rows = [
            _make_row("HTTP_REQUEST_TIMEOUT", value=90),
            _make_row("TIMEZONE", value=None, value_type="string"),
        ]
        with patch.object(qry, "get_all_settings", AsyncMock(return_value=rows)):
            result = await service.get_all_settings(mock_db)

        assert len(result) == 2
        by_key = {r["key"]: r for r in result}
        assert by_key["HTTP_REQUEST_TIMEOUT"]["effective_value"] == 90
        assert by_key["HTTP_REQUEST_TIMEOUT"]["source"] == "db"
        assert by_key["TIMEZONE"]["source"] == "default"


# ── get_runtime_snapshot ──────────────────────────────────────────────


class TestRuntimeSnapshot:
    pytestmark = [pytest.mark.asyncio]

    @pytest.mark.unit
    async def test_builds_runtime_config(self, mock_db: AsyncMock) -> None:
        """get_runtime_snapshot returns a valid RuntimeConfig."""
        rows = [_make_row("HTTP_REQUEST_TIMEOUT", value=120)]
        with patch.object(qry, "get_all_settings", AsyncMock(return_value=rows)):
            config = await service.get_runtime_snapshot(mock_db)

        assert isinstance(config, RuntimeConfig)
        assert config.HTTP_REQUEST_TIMEOUT == 120
        assert config.RECENT_ACTIONS_LIMIT == 5  # default

    @pytest.mark.unit
    async def test_invalid_override_falls_back(self, mock_db: AsyncMock) -> None:
        """An invalid persisted override falls back to default, not crash."""
        # RECENT_ACTIONS_LIMIT=999 is out of range; RuntimeConfig would reject it.
        rows = [_make_row("RECENT_ACTIONS_LIMIT", value=999)]
        with patch.object(qry, "get_all_settings", AsyncMock(return_value=rows)):
            config = await service.get_runtime_snapshot(mock_db)
        # Falls back to default 5.
        assert config.RECENT_ACTIONS_LIMIT == 5


# ── bulk_update ───────────────────────────────────────────────────────


class TestBulkUpdate:
    pytestmark = [pytest.mark.asyncio]

    @pytest.mark.unit
    async def test_rejects_unknown_key(
        self, mock_db: AsyncMock, fresh_cache: RuntimeConfigCache
    ) -> None:
        """Unknown keys are rejected with ValueError."""
        rows = [
            _make_row("HTTP_REQUEST_TIMEOUT"),
            _make_row("TIMEZONE", value_type="string"),
        ]
        with patch.object(qry, "get_all_settings", AsyncMock(return_value=rows)):
            with pytest.raises(ValueError, match="Unknown setting keys"):
                await service.bulk_update(mock_db, {"NOT_A_KEY": 1})

    @pytest.mark.unit
    async def test_rejects_invalid_value(
        self, mock_db: AsyncMock, fresh_cache: RuntimeConfigCache
    ) -> None:
        """Out-of-range values are rejected with ValidationError."""
        rows = [_make_row("RECENT_ACTIONS_LIMIT")]
        with patch.object(qry, "get_all_settings", AsyncMock(return_value=rows)):
            with pytest.raises(ValidationError):
                await service.bulk_update(mock_db, {"RECENT_ACTIONS_LIMIT": 999})

    @pytest.mark.unit
    async def test_valid_update_persists_and_refreshes(
        self, mock_db: AsyncMock, fresh_cache: RuntimeConfigCache
    ) -> None:
        """Valid updates persist and refresh the local cache."""
        row = _make_row("HTTP_REQUEST_TIMEOUT", value=None)
        updated_rows = [_make_row("HTTP_REQUEST_TIMEOUT", value=90)]

        with patch.object(qry, "bulk_update_values", AsyncMock(return_value=updated_rows)), \
             patch.object(qry, "get_all_settings", AsyncMock(return_value=updated_rows)):
            result = await service.bulk_update(mock_db, {"HTTP_REQUEST_TIMEOUT": 90})

        assert result["updated"]["HTTP_REQUEST_TIMEOUT"] == 90
        assert result["propagation_warning"] is None
        # Cache refreshed.
        assert fresh_cache.get_int("HTTP_REQUEST_TIMEOUT") == 90


# ── reset ─────────────────────────────────────────────────────────────


class TestReset:
    pytestmark = [pytest.mark.asyncio]

    @pytest.mark.unit
    async def test_reset_single_unknown_key(
        self, mock_db: AsyncMock, fresh_cache: RuntimeConfigCache
    ) -> None:
        """Resetting an unknown key raises ValueError."""
        with patch.object(qry, "reset_setting_value", AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="Unknown setting key"):
                await service.reset_single(mock_db, "NOT_A_KEY")

    @pytest.mark.unit
    async def test_reset_single_sets_null(
        self, mock_db: AsyncMock, fresh_cache: RuntimeConfigCache
    ) -> None:
        """Resetting sets value to None and falls back to env/default."""
        row = _make_row("HTTP_REQUEST_TIMEOUT", value=None)
        with patch.object(qry, "reset_setting_value", AsyncMock(return_value=row)), \
             patch.object(qry, "get_all_settings", AsyncMock(return_value=[row])):
            result = await service.reset_single(mock_db, "HTTP_REQUEST_TIMEOUT")

        assert result["value"] is None
        assert result["source"] in ("env", "default")
        assert result["effective_value"] == 60  # default

    @pytest.mark.unit
    async def test_reset_all_clears_overrides(
        self, mock_db: AsyncMock, fresh_cache: RuntimeConfigCache
    ) -> None:
        """reset_all returns source-aware rows with None values."""
        rows = [
            _make_row("HTTP_REQUEST_TIMEOUT", value=90),
            _make_row("TIMEZONE", value=None, value_type="string"),
        ]
        with patch.object(qry, "reset_all_values", AsyncMock(return_value=rows)):
            result = await service.reset_all(mock_db)

        assert len(result) == 2
        by_key = {r["key"]: r for r in result}
        assert by_key["HTTP_REQUEST_TIMEOUT"]["value"] is None
        assert by_key["TIMEZONE"]["value"] is None
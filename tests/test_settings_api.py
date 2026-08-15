"""Integration tests for the settings API.

Tests full HTTP round-trips against a running app server at
``http://localhost:8000``.  Requires the app to be started separately::

    PYTHONPATH=src uvicorn app.main:app --reload

Markers: ``integration``, ``server``.

**Safety:** A session-scoped fixture snapshots the initial DB state and
restores it after all tests complete, even if tests fail midway.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.server]

BASE_URL = "http://localhost:8000"


# ── Snapshot / restore ────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def settings_snapshot() -> dict[str, object | None]:
    """Capture initial setting values before any test, restore after all.

    Uses a synchronous ``httpx.Client`` to avoid event-loop issues with
    session-scoped async fixtures.
    """
    # --- setup: snapshot current values ---
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        resp = client.get("/api/v1/settings/")
        resp.raise_for_status()
        snapshot: dict[str, object | None] = {
            s["key"]: s["value"] for s in resp.json()
        }

    yield snapshot

    # --- teardown: restore original values ---
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        # Reset all to clear any overrides left by tests.
        client.post("/api/v1/settings/reset", json={})
        # Re-apply any original non-None values.
        overrides = {k: v for k, v in snapshot.items() if v is not None}
        if overrides:
            client.patch("/api/v1/settings/", json={"updates": overrides})


def _setting_map(settings: list[dict]) -> dict[str, dict]:
    """Index a list of setting dicts by key for easy assertion."""
    return {s["key"]: s for s in settings}


# ── GET /api/v1/settings/ ─────────────────────────────────────────────


class TestGetSettings:
    """Verify the GET endpoint returns source-aware metadata."""

    @pytest.mark.asyncio
    async def test_returns_53_settings(self) -> None:
        """GET returns exactly 53 settings."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.get("/api/v1/settings/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 53

    @pytest.mark.asyncio
    async def test_response_shape(self) -> None:
        """Each setting has the expected fields."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.get("/api/v1/settings/")
        assert resp.status_code == 200
        data = resp.json()
        for item in data:
            assert "key" in item
            assert "value" in item
            assert "effective_value" in item
            assert "source" in item
            assert item["source"] in ("db", "env", "default")
            assert "value_type" in item
            assert item["value_type"] in ("string", "integer", "boolean")
            assert "apply_mode" in item
            assert item["apply_mode"] in ("dynamic", "restart")
            assert "is_sensitive" in item
            assert isinstance(item["is_sensitive"], bool)
            assert "updated_at" in item

    @pytest.mark.asyncio
    async def test_source_is_default_when_no_override(self) -> None:
        """Settings with no DB override and no env var show source=default."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.get("/api/v1/settings/")
        assert resp.status_code == 200
        by_key = _setting_map(resp.json())
        assert by_key["RECENT_ACTIONS_LIMIT"]["source"] in ("env", "default")
        assert by_key["RECENT_ACTIONS_LIMIT"]["effective_value"] == 5


# ── PATCH /api/v1/settings/ (bulk) ────────────────────────────────────


class TestBulkUpdate:
    """Verify the bulk update endpoint."""

    @pytest.mark.asyncio
    async def test_valid_update(
        self, settings_snapshot: dict,
    ) -> None:
        """A valid bulk update persists and returns the new values."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.patch(
                "/api/v1/settings/",
                json={"updates": {"HTTP_REQUEST_TIMEOUT": 90}},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["updated"]["HTTP_REQUEST_TIMEOUT"] == 90
            # propagation_warning is None when RabbitMQ is available, or a
            # string when the broker is not reachable — both are valid.
            assert data["propagation_warning"] is None or isinstance(
                data["propagation_warning"], str
            )

            # Verify it persisted — reuse the same client.
            resp2 = await client.get("/api/v1/settings/")
            by_key = _setting_map(resp2.json())
            assert by_key["HTTP_REQUEST_TIMEOUT"]["value"] == 90
            assert by_key["HTTP_REQUEST_TIMEOUT"]["source"] == "db"

    @pytest.mark.asyncio
    async def test_unknown_key_returns_422(self) -> None:
        """Unknown keys are rejected with 422."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.patch(
                "/api/v1/settings/",
                json={"updates": {"NOT_A_REAL_KEY": 1}},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_out_of_range_value_returns_422(self) -> None:
        """Out-of-range values are rejected with 422."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.patch(
                "/api/v1/settings/",
                json={"updates": {"RECENT_ACTIONS_LIMIT": 999}},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_conflict_returns_409(self) -> None:
        """A stale expected_updated_at returns 409."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.patch(
                "/api/v1/settings/",
                json={
                    "updates": {"HTTP_REQUEST_TIMEOUT": 120},
                    "expected_updated_at": "2026-01-01T00:00:00Z",
                },
            )
        assert resp.status_code == 409
        data = resp.json()
        assert "conflicting_keys" in data["detail"]
        assert "HTTP_REQUEST_TIMEOUT" in data["detail"]["conflicting_keys"]


# ── PATCH /api/v1/settings/{key} (single) ─────────────────────────────


class TestSingleUpdate:
    """Verify the single-key update endpoint."""

    @pytest.mark.asyncio
    async def test_valid_update(
        self, settings_snapshot: dict,
    ) -> None:
        """A valid single update persists and returns source-aware data."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.patch(
                "/api/v1/settings/TIMEZONE",
                json={"value": "America/New_York"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "TIMEZONE"
        assert data["value"] == "America/New_York"
        assert data["source"] == "db"
        assert data["effective_value"] == "America/New_York"

    @pytest.mark.asyncio
    async def test_unknown_key_returns_422(self) -> None:
        """An unknown key returns 422."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.patch(
                "/api/v1/settings/NOT_A_KEY",
                json={"value": 1},
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_conflict_returns_409(self) -> None:
        """A stale expected_updated_at returns 409."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.patch(
                "/api/v1/settings/TIMEZONE",
                json={
                    "value": "Asia/Kolkata",
                    "expected_updated_at": "2026-01-01T00:00:00Z",
                },
            )
        assert resp.status_code == 409
        data = resp.json()
        assert "conflicting_keys" in data["detail"]


# ── POST /api/v1/settings/{key}/reset ─────────────────────────────────


class TestResetSingle:
    """Verify the single-key reset endpoint."""

    @pytest.mark.asyncio
    async def test_reset_clears_override(
        self, settings_snapshot: dict,
    ) -> None:
        """Resetting a setting sets value to None and falls back."""
        # First set a value to reset.
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            await client.patch(
                "/api/v1/settings/TIMEZONE",
                json={"value": "America/New_York"},
            )

            # Fetch the current timestamp — like the app does on page load.
            get_resp = await client.get("/api/v1/settings/")
            settings = _setting_map(get_resp.json())
            updated_at = settings["TIMEZONE"]["updated_at"]

            resp = await client.post(
                "/api/v1/settings/TIMEZONE/reset",
                json={"expected_updated_at": updated_at},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "TIMEZONE"
        assert data["value"] is None
        assert data["source"] in ("env", "default")

    @pytest.mark.asyncio
    async def test_unknown_key_returns_422(self) -> None:
        """Resetting an unknown key returns 422."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.post("/api/v1/settings/NOT_A_KEY/reset")
        assert resp.status_code == 422


# ── POST /api/v1/settings/reset (bulk) ────────────────────────────────


class TestResetAll:
    """Verify the bulk reset endpoint."""

    @pytest.mark.asyncio
    async def test_reset_all_clears_overrides(
        self, settings_snapshot: dict,
    ) -> None:
        """Resetting all sets all values to None."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            # Fetch current timestamps — like the app does on page load.
            get_resp = await client.get("/api/v1/settings/")
            settings = get_resp.json()
            timestamps = [s["updated_at"] for s in settings if s.get("updated_at")]
            expected_updated_at = max(timestamps) if timestamps else None

            resp = await client.post(
                "/api/v1/settings/reset",
                json={"expected_updated_at": expected_updated_at},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 53
        for item in data:
            assert item["value"] is None


# ── Reset conflict tests ──────────────────────────────────────────────


class TestResetConflicts:
    """Verify reset endpoints reject stale data."""

    @pytest.mark.asyncio
    async def test_reset_single_rejects_stale_data(self) -> None:
        """POST /settings/{key}/reset with stale expected_updated_at returns 409."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            # First, get current state.
            get_resp = await client.get("/api/v1/settings/")
            assert get_resp.status_code == 200
            settings = _setting_map(get_resp.json())
            timeout_setting = settings["HTTP_REQUEST_TIMEOUT"]
            stale_updated_at = timeout_setting["updated_at"]

            # Make a concurrent change.
            await client.patch(
                "/api/v1/settings/",
                json={"updates": {"HTTP_REQUEST_TIMEOUT": 99}},
            )

            # Now try to reset with the stale timestamp — should get 409.
            resp = await client.post(
                "/api/v1/settings/HTTP_REQUEST_TIMEOUT/reset",
                json={"expected_updated_at": stale_updated_at},
            )
            assert resp.status_code == 409
            data = resp.json()
            assert "conflicting_keys" in data["detail"]
            assert "HTTP_REQUEST_TIMEOUT" in data["detail"]["conflicting_keys"]

    @pytest.mark.asyncio
    async def test_reset_all_rejects_stale_data(self) -> None:
        """POST /settings/reset with stale expected_updated_at returns 409."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            get_resp = await client.get("/api/v1/settings/")
            assert get_resp.status_code == 200
            settings = _setting_map(get_resp.json())
            timeout_setting = settings["HTTP_REQUEST_TIMEOUT"]
            stale_updated_at = timeout_setting["updated_at"]

            # Make a concurrent change.
            await client.patch(
                "/api/v1/settings/",
                json={"updates": {"HTTP_REQUEST_TIMEOUT": 88}},
            )

            resp = await client.post(
                "/api/v1/settings/reset",
                json={"expected_updated_at": stale_updated_at},
            )
            assert resp.status_code == 409


# ── GET /api/v1/settings/runtime-snapshot ─────────────────────────────


class TestRuntimeSnapshot:
    """Verify the runtime-snapshot endpoint."""

    @pytest.mark.asyncio
    async def test_returns_valid_runtime_config(self) -> None:
        """The snapshot returns all 37 fields with correct types."""
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            resp = await client.get("/api/v1/settings/runtime-snapshot")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 37
        assert isinstance(data["HTTP_REQUEST_TIMEOUT"], int)
        assert isinstance(data["TIMEZONE"], str)
        assert isinstance(data["FF_NEO4J_USE_PROVIDER_PIPELINE"], bool)
        assert isinstance(data["RECENT_ACTIONS_LIMIT"], int)
        assert 1 <= data["RECENT_ACTIONS_LIMIT"] <= 50
        # New fields
        assert isinstance(data["LLM_PROVIDER"], str)
        assert isinstance(data["MAX_TOKENS"], int)
        assert isinstance(data["GITHUB_MCP_ENABLED"], bool)
        assert isinstance(data["NEO4J_ENABLED"], bool)
        assert isinstance(data["LOG_LEVEL"], str)
        assert isinstance(data["ENABLE_FILE_LOGGING"], bool)
        assert isinstance(data["COMMIT_DAYS_LIMIT"], int)
        assert isinstance(data["JIRA_LOOKBACK_DAYS"], int)
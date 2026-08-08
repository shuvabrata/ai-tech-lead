"""Integration tests for the Dash Settings UI.

Tests that the settings page renders correctly, loads data from the API, and
that edit → save → verify and reset flows work end-to-end.

Requires a running app server::

    PYTHONPATH=src uvicorn app.main:app --reload

Markers: ``integration``, ``server``.

**Safety:** A session-scoped fixture snapshots the initial DB state and
restores it after all tests complete, even if tests fail midway.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.server]

BASE_URL = "http://localhost:8000"
APP_BASE = f"{BASE_URL}/app"


# ── Snapshot / restore ────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def settings_snapshot() -> Iterator[dict[str, object | None]]:
    """Capture initial setting values before any test, restore after all.

    Uses a synchronous ``httpx.Client`` to avoid event-loop issues with
    session-scoped async fixtures.
    """
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        resp = client.get("/api/v1/settings/")
        resp.raise_for_status()
        snapshot: dict[str, object | None] = {
            s["key"]: s["value"] for s in resp.json()
        }

    yield snapshot

    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        client.post("/api/v1/settings/reset")
        overrides = {k: v for k, v in snapshot.items() if v is not None}
        if overrides:
            client.patch("/api/v1/settings/", json={"updates": overrides})


# ── Helpers ────────────────────────────────────────────────────────────


def _setting_map(settings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index a list of setting dicts by key for easy assertion."""
    return {s["key"]: s for s in settings}


# ── Tests ──────────────────────────────────────────────────────────────


class TestSettingsDashboardRenders:
    """Verify the settings page loads and shows the correct structure."""

    def test_settings_page_returns_200(self) -> None:
        """The Dash settings page returns HTTP 200."""
        resp = httpx.get(f"{APP_BASE}/settings", timeout=10)
        assert resp.status_code == 200

    def test_settings_page_contains_runtime_settings_header(self) -> None:
        """The page contains the 'Runtime Settings' header text."""
        resp = httpx.get(f"{APP_BASE}/settings", timeout=10)
        assert resp.status_code == 200
        assert "Runtime Settings" in resp.text

    def test_settings_page_contains_save_all_button(self) -> None:
        """The page contains the 'Save All Changes' button."""
        resp = httpx.get(f"{APP_BASE}/settings", timeout=10)
        assert resp.status_code == 200
        assert "Save All Changes" in resp.text

    def test_settings_page_contains_reset_all_button(self) -> None:
        """The page contains the 'Reset All to Default' button."""
        resp = httpx.get(f"{APP_BASE}/settings", timeout=10)
        assert resp.status_code == 200
        assert "Reset All to Default" in resp.text


class TestSettingsDataLoaded:
    """Verify settings data is loaded from the API and rendered correctly."""

    def test_settings_api_returns_all_13_settings(self) -> None:
        """GET /api/v1/settings/ returns exactly 13 settings."""
        resp = httpx.get(f"{BASE_URL}/api/v1/settings/", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 13

    def test_all_categories_present(self) -> None:
        """All expected categories appear in the settings response."""
        resp = httpx.get(f"{BASE_URL}/api/v1/settings/", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        categories = {s["category"] for s in data}
        expected = {"network", "graph", "connectors", "ui", "ai", "feature_flags"}
        assert categories == expected

    def test_page_renders_setting_keys_in_html(self) -> None:
        """The settings HTML contains key names from the API."""
        resp = httpx.get(f"{BASE_URL}/api/v1/settings/", timeout=10)
        assert resp.status_code == 200
        settings = resp.json()
        key_names = [s["key"] for s in settings]

        page_resp = httpx.get(f"{APP_BASE}/settings", timeout=10)
        assert page_resp.status_code == 200

        for key in key_names:
            assert key in page_resp.text, (
                f"Setting key '{key}' not found in settings page HTML"
            )

    def test_page_renders_source_badges(self) -> None:
        """The page HTML contains source indicator text (db/env/default)."""
        page_resp = httpx.get(f"{APP_BASE}/settings", timeout=10)
        assert page_resp.status_code == 200
        # The API returns these as badge text in the rendered HTML.
        for source in ("env", "default"):
            assert source in page_resp.text, (
                f"Source badge '{source}' not found in settings page HTML"
            )


class TestSettingsEditSaveReset:
    """Verify the edit → save → verify and reset flows end-to-end."""

    def test_edit_and_save_integer_setting(self) -> None:
        """Edit HTTP_REQUEST_TIMEOUT, save, and verify the change."""
        new_value = 75
        resp = httpx.patch(
            f"{BASE_URL}/api/v1/settings/",
            json={"updates": {"HTTP_REQUEST_TIMEOUT": new_value}},
            timeout=10,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["updated"]["HTTP_REQUEST_TIMEOUT"] == new_value

        # Verify via GET.
        verify = httpx.get(f"{BASE_URL}/api/v1/settings/", timeout=10)
        assert verify.status_code == 200
        settings = _setting_map(verify.json())
        assert settings["HTTP_REQUEST_TIMEOUT"]["effective_value"] == new_value
        assert settings["HTTP_REQUEST_TIMEOUT"]["source"] == "db"

    def test_edit_and_save_string_setting(self) -> None:
        """Edit TIMEZONE, save, and verify."""
        new_value = "Asia/Kolkata"
        resp = httpx.patch(
            f"{BASE_URL}/api/v1/settings/",
            json={"updates": {"TIMEZONE": new_value}},
            timeout=10,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["updated"]["TIMEZONE"] == new_value

        verify = httpx.get(f"{BASE_URL}/api/v1/settings/", timeout=10)
        assert verify.status_code == 200
        settings = _setting_map(verify.json())
        assert settings["TIMEZONE"]["effective_value"] == new_value
        assert settings["TIMEZONE"]["source"] == "db"

    def test_edit_and_save_boolean_setting(self) -> None:
        """Toggle FF_NEO4J_USE_PROVIDER_PIPELINE, save, and verify."""
        new_value = True
        resp = httpx.patch(
            f"{BASE_URL}/api/v1/settings/",
            json={"updates": {"FF_NEO4J_USE_PROVIDER_PIPELINE": new_value}},
            timeout=10,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["updated"]["FF_NEO4J_USE_PROVIDER_PIPELINE"] is new_value

        verify = httpx.get(f"{BASE_URL}/api/v1/settings/", timeout=10)
        assert verify.status_code == 200
        settings = _setting_map(verify.json())
        assert settings["FF_NEO4J_USE_PROVIDER_PIPELINE"]["effective_value"] is new_value
        assert settings["FF_NEO4J_USE_PROVIDER_PIPELINE"]["source"] == "db"

    def test_invalid_value_returns_422(self) -> None:
        """Sending an out-of-range integer returns 422."""
        resp = httpx.patch(
            f"{BASE_URL}/api/v1/settings/",
            json={"updates": {"RECENT_ACTIONS_LIMIT": 999}},
            timeout=10,
        )
        assert resp.status_code == 422

    def test_unknown_key_returns_422(self) -> None:
        """Sending an unknown setting key returns 422."""
        resp = httpx.patch(
            f"{BASE_URL}/api/v1/settings/",
            json={"updates": {"NONEXISTENT_KEY": "value"}},
            timeout=10,
        )
        assert resp.status_code == 422

    def test_reset_single_setting(self) -> None:
        """Reset a single setting and verify it returns to env/default."""
        # First set a value.
        httpx.patch(
            f"{BASE_URL}/api/v1/settings/",
            json={"updates": {"HTTP_REQUEST_TIMEOUT": 120}},
            timeout=10,
        )
        resp = httpx.post(
            f"{BASE_URL}/api/v1/settings/HTTP_REQUEST_TIMEOUT/reset",
            timeout=10,
        )
        assert resp.status_code == 200

        verify = httpx.get(f"{BASE_URL}/api/v1/settings/", timeout=10)
        assert verify.status_code == 200
        settings = _setting_map(verify.json())
        # After reset, source should be 'env' or 'default' (not 'db').
        assert settings["HTTP_REQUEST_TIMEOUT"]["source"] != "db"
        assert settings["HTTP_REQUEST_TIMEOUT"]["value"] is None

    def test_reset_all_settings(self) -> None:
        """Reset all settings and verify they return to env/default."""
        # Set some values first.
        httpx.patch(
            f"{BASE_URL}/api/v1/settings/",
            json={"updates": {"HTTP_REQUEST_TIMEOUT": 90, "TIMEZONE": "America/New_York"}},
            timeout=10,
        )
        resp = httpx.post(f"{BASE_URL}/api/v1/settings/reset", timeout=10)
        assert resp.status_code == 200

        verify = httpx.get(f"{BASE_URL}/api/v1/settings/", timeout=10)
        assert verify.status_code == 200
        for setting in verify.json():
            assert setting["value"] is None, (
                f"Setting '{setting['key']}' was not reset"
            )
            assert setting["source"] != "db"

    def test_runtime_snapshot_returns_valid_config(self) -> None:
        """GET /api/v1/settings/runtime-snapshot returns a valid RuntimeConfig."""
        resp = httpx.get(
            f"{BASE_URL}/api/v1/settings/runtime-snapshot", timeout=10
        )
        assert resp.status_code == 200
        config = resp.json()
        # Check a few key fields exist and have correct types.
        assert isinstance(config["HTTP_REQUEST_TIMEOUT"], int)
        assert isinstance(config["TIMEZONE"], str)
        assert isinstance(config["FF_NEO4J_USE_PROVIDER_PIPELINE"], bool)
        assert config["HTTP_REQUEST_TIMEOUT"] >= 1
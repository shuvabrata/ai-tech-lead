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
from dash import no_update

from app.dash_app.pages.settings import (
    CATEGORY_META,
    CATEGORY_ORDER,
    _build_category_section,
    _build_setting_row,
    get_layout,
    render_settings,
)

pytestmark = [pytest.mark.integration, pytest.mark.server]

BASE_URL = "http://localhost:8000"
APP_BASE = f"{BASE_URL}/app"


# ── Helpers ────────────────────────────────────────────────────────────


def _flatten_text(component: Any) -> str:
    """Flatten a Dash component tree into a single text string."""
    if isinstance(component, (str, int, float, bool)):
        return str(component)
    if isinstance(component, list):
        return " ".join(_flatten_text(c) for c in component)
    parts: list[str] = []
    children = getattr(component, "children", None)
    if children is None:
        return ""
    if not isinstance(children, list):
        children = [children]
    for child in children:
        parts.append(_flatten_text(child))
    return " ".join(parts)


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
        client.post("/api/v1/settings/reset", json={})
        overrides = {k: v for k, v in snapshot.items() if v is not None}
        if overrides:
            client.patch("/api/v1/settings/", json={"updates": overrides})


# ── Helpers ────────────────────────────────────────────────────────────


def _setting_map(settings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index a list of setting dicts by key for easy assertion."""
    return {s["key"]: s for s in settings}


# ── Tests ──────────────────────────────────────────────────────────────


class TestSettingsDashboardRenders:
    """Verify the settings page layout produces the correct component tree."""

    def test_settings_page_returns_200(self) -> None:
        """The Dash settings page returns HTTP 200."""
        resp = httpx.get(f"{APP_BASE}/settings", timeout=10)
        assert resp.status_code == 200

    def test_settings_page_contains_runtime_settings_header(self) -> None:
        """The layout contains the 'Runtime Settings' header text."""
        layout = get_layout()
        text = _flatten_text(layout)
        assert "Runtime Settings" in text

    def test_settings_page_contains_save_all_button(self) -> None:
        """The layout contains the 'Save All Changes' button."""
        layout = get_layout()
        text = _flatten_text(layout)
        assert "Save All Changes" in text

    def test_settings_page_contains_reset_all_button(self) -> None:
        """The layout contains the 'Reset All to Default' button."""
        layout = get_layout()
        text = _flatten_text(layout)
        assert "Reset All to Default" in text


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
        """The rendered settings content contains key names from the API."""
        resp = httpx.get(f"{BASE_URL}/api/v1/settings/", timeout=10)
        assert resp.status_code == 200
        settings = resp.json()
        key_names = [s["key"] for s in settings]

        children, feedback, initial = render_settings(settings)
        text = _flatten_text(children)

        for key in key_names:
            assert key in text, (
                f"Setting key '{key}' not found in rendered settings content"
            )

    def test_page_renders_source_badges(self) -> None:
        """The rendered settings content contains source indicator text."""
        resp = httpx.get(f"{BASE_URL}/api/v1/settings/", timeout=10)
        assert resp.status_code == 200
        settings = resp.json()

        children, feedback, initial = render_settings(settings)
        text = _flatten_text(children)

        for source in ("env", "default"):
            assert source in text, (
                f"Source badge '{source}' not found in rendered settings content"
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

        # Fetch the current timestamp — like the app does on page load.
        get_resp = httpx.get(f"{BASE_URL}/api/v1/settings/", timeout=10)
        settings = _setting_map(get_resp.json())
        updated_at = settings["HTTP_REQUEST_TIMEOUT"]["updated_at"]

        resp = httpx.post(
            f"{BASE_URL}/api/v1/settings/HTTP_REQUEST_TIMEOUT/reset",
            json={"expected_updated_at": updated_at},
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

        # Fetch current timestamps — like the app does on page load.
        get_resp = httpx.get(f"{BASE_URL}/api/v1/settings/", timeout=10)
        timestamps = [s["updated_at"] for s in get_resp.json() if s.get("updated_at")]
        expected_updated_at = max(timestamps) if timestamps else None

        resp = httpx.post(
            f"{BASE_URL}/api/v1/settings/reset",
            json={"expected_updated_at": expected_updated_at},
            timeout=10,
        )
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


# ===========================================================================
# Unit tests — pure logic, no server required
# ===========================================================================


def _make_setting(
    key: str,
    category: str | None = None,
    value_type: str = "string",
    effective_value: str = "foo",
    source: str = "default",
    description: str = "A test setting.",
) -> dict[str, Any]:
    """Build a minimal setting dict as returned by the API."""
    return {
        "key": key,
        "category": category,
        "value_type": value_type,
        "effective_value": effective_value,
        "source": source,
        "description": description,
    }


@pytest.mark.unit
class TestCategoryOrder:
    """``CATEGORY_ORDER`` includes the catch-all ``"others"`` key."""

    def test_includes_others(self) -> None:
        assert "others" in CATEGORY_ORDER

    def test_others_is_last(self) -> None:
        """The catch-all category should be last in the order."""
        assert CATEGORY_ORDER[-1] == "others"


@pytest.mark.unit
class TestCategoryMeta:
    """``CATEGORY_META`` does not define ``"others"`` (uses fallback)."""

    def test_others_not_in_meta(self) -> None:
        assert "others" not in CATEGORY_META


@pytest.mark.unit
class TestBuildCategorySection:
    """Unknown categories get a sensible fallback label and icon."""

    def test_unknown_category_uses_fallback_label(self) -> None:
        section = _build_category_section("others", [])
        label_span = section.children[0].children[1]
        assert label_span.children == "others"

    def test_unknown_category_uses_gear_icon(self) -> None:
        section = _build_category_section("others", [])
        icon = section.children[0].children[0]
        assert "fa-gear" in icon.className

    def test_known_category_uses_meta_label(self) -> None:
        section = _build_category_section("network", [])
        label_span = section.children[0].children[1]
        assert label_span.children == "Network"

    def test_known_category_uses_meta_icon(self) -> None:
        section = _build_category_section("network", [])
        icon = section.children[0].children[0]
        assert "fa-globe" in icon.className

    def test_shows_setting_count(self) -> None:
        settings = [_make_setting("a"), _make_setting("b")]
        section = _build_category_section("others", settings)
        count_span = section.children[0].children[2]
        assert count_span.children == " (2)"


@pytest.mark.unit
class TestBuildSettingRow:
    """Each setting renders a row with key, input, source badge, and reset."""

    def test_row_has_correct_key(self) -> None:
        setting = _make_setting("TEST_KEY")
        row = _build_setting_row(setting)
        assert row.id == {"type": "settings-row", "key": "TEST_KEY"}

    def test_row_shows_key_label(self) -> None:
        setting = _make_setting("TEST_KEY")
        row = _build_setting_row(setting)
        key_div = row.children[0].children[0].children[0]
        assert key_div.children == "TEST_KEY"

    def test_row_shows_description(self) -> None:
        setting = _make_setting("TEST_KEY", description="My description")
        row = _build_setting_row(setting)
        desc_div = row.children[0].children[0].children[1]
        assert desc_div.children == "My description"

    def test_row_has_reset_button(self) -> None:
        setting = _make_setting("TEST_KEY")
        row = _build_setting_row(setting)
        reset_col = row.children[0].children[3]
        inner_div = reset_col.children
        btn = inner_div.children
        assert btn.children == "Reset"
        assert btn.id == {"type": "settings-reset-btn", "key": "TEST_KEY"}


@pytest.mark.unit
class TestRenderSettings:
    """``render_settings`` groups settings by category and renders sections."""

    def test_returns_loading_when_store_is_none(self) -> None:
        content, feedback, initial = render_settings(None)
        assert feedback is None
        assert initial is None
        assert "Loading" in str(content[0].children)

    def test_returns_error_alert_on_api_error(self) -> None:
        store = {"status": "error", "message": "Connection refused"}
        content, feedback, initial = render_settings(store)
        assert content == []
        assert initial is None
        assert "Failed to load" in str(feedback)

    def test_returns_error_on_unexpected_format(self) -> None:
        store = {"unexpected": True}
        content, feedback, initial = render_settings(store)
        assert "Unexpected response format" in str(content[0].children)

    def test_renders_known_category(self) -> None:
        store = [_make_setting("TIMEOUT", category="network")]
        content, feedback, initial = render_settings(store)
        assert feedback is no_update or feedback is None
        assert len(content) == 1

    def test_renders_uncategorized_under_others(self) -> None:
        """Settings with ``category=None`` appear under the ``"others"`` section."""
        store = [_make_setting("MY_SETTING", category=None)]
        content, feedback, initial = render_settings(store)
        assert feedback is no_update or feedback is None
        assert len(content) == 1
        section = content[0].children
        label_span = section.children[0].children[1]
        assert label_span.children == "others"

    def test_renders_explicit_others_category(self) -> None:
        """Settings with ``category="others"`` appear under ``"others"`` section."""
        store = [_make_setting("MY_SETTING", category="others")]
        content, feedback, initial = render_settings(store)
        assert feedback is no_update or feedback is None
        assert len(content) == 1

    def test_omits_empty_category_section(self) -> None:
        """A category with no settings should not produce a section."""
        store = [_make_setting("TIMEOUT", category="network")]
        content, feedback, initial = render_settings(store)
        section = content[0].children
        label_span = section.children[0].children[1]
        assert label_span.children == "Network"

    def test_initial_store_contains_all_keys(self) -> None:
        store = [
            _make_setting("A", category="network", effective_value="x"),
            _make_setting("B", category="graph", effective_value="y"),
        ]
        content, feedback, initial = render_settings(store)
        assert initial == {
            "A": {"value": "x", "updated_at": None},
            "B": {"value": "y", "updated_at": None},
        }

    def test_mixed_known_and_uncategorized(self) -> None:
        """Known categories and uncategorized settings all render."""
        store = [
            _make_setting("TIMEOUT", category="network"),
            _make_setting("MY_FLAG", category=None),
            _make_setting("MODEL", category="ai"),
        ]
        content, feedback, initial = render_settings(store)
        assert feedback is no_update or feedback is None
        assert len(content) == 3  # network, ai, others
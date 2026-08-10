"""Unit tests for the Dash Settings UI — pure logic, no server required."""

from __future__ import annotations

from typing import Any

import pytest
from dash import no_update

from app.dash_app.pages.settings import (
    CATEGORY_META,
    CATEGORY_ORDER,
    _build_category_section,
    _build_setting_row,
    render_settings,
)

pytestmark = [pytest.mark.unit]


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


class TestCategoryOrder:
    """``CATEGORY_ORDER`` includes the catch-all ``"others"`` key."""

    def test_includes_others(self) -> None:
        assert "others" in CATEGORY_ORDER

    def test_others_is_last(self) -> None:
        """The catch-all category should be last in the order."""
        assert CATEGORY_ORDER[-1] == "others"


class TestCategoryMeta:
    """``CATEGORY_META`` does not define ``"others"`` (uses fallback)."""

    def test_others_not_in_meta(self) -> None:
        assert "others" not in CATEGORY_META


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
        # Key div now contains a list: [key_text, badge]
        assert key_div.children[0] == "TEST_KEY"

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


class TestSensitiveSettingRow:
    """Sensitive settings render password-type inputs."""

    def test_sensitive_setting_uses_password_input(self) -> None:
        setting = _make_setting("OPENAI_API_KEY", effective_value="sk-abc…xyz")
        setting["is_sensitive"] = True
        row = _build_setting_row(setting)
        input_col = row.children[0].children[1]
        inner_div = input_col.children
        input_component = inner_div.children
        assert input_component.type == "password"

    def test_sensitive_setting_shows_placeholder(self) -> None:
        setting = _make_setting("OPENAI_API_KEY", effective_value="")
        setting["is_sensitive"] = True
        row = _build_setting_row(setting)
        input_col = row.children[0].children[1]
        inner_div = input_col.children
        input_component = inner_div.children
        assert "(sensitive" in (input_component.placeholder or "")


class TestApplyModeBadge:
    """Apply-mode badge renders correctly."""

    def test_dynamic_mode_no_badge(self) -> None:
        """Dynamic settings do not show an apply-mode badge."""
        setting = _make_setting("HTTP_REQUEST_TIMEOUT")
        setting["apply_mode"] = "dynamic"
        row = _build_setting_row(setting)
        key_div = row.children[0].children[0].children[0]
        # No badge rendered for dynamic — children[2] is an empty string
        assert key_div.children[2] == ""

    def test_restart_mode_badge(self) -> None:
        """Restart settings show a 'restart' badge."""
        setting = _make_setting("NEO4J_ENABLED")
        setting["apply_mode"] = "restart"
        row = _build_setting_row(setting)
        key_div = row.children[0].children[0].children[0]
        badge = key_div.children[2]
        assert badge.children == "restart"
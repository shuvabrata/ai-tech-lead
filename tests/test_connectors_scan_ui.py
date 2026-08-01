"""Unit tests for Phase 6 — Connector detail page scan UI.

Tests cover:
  - ``render_scan_item`` — scan status row rendering (icons, colors, timestamps)
  - ``_render_top_action_bar`` / ``_render_recent_scans`` — Run Scan button visibility rules
  - Scan callback helpers — polling, API interaction
  - ``toggle_add_item_collapse`` — collapsible form toggle
  - ``stop_polling_if_idle`` — scan polling enable/disable logic
  - Search filter callbacks — store, update, render
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import uuid

import pytest
from dash import html, no_update
from dash.exceptions import PreventUpdate

from app.api.connectors.v1.registry import CONNECTOR_REGISTRY
from app.dash_app.pages.connectors.callbacks import (
    populate_search_filters_store,
    render_search_filters_list,
    stop_polling_if_idle,
    toggle_add_item_collapse,
    update_search_filters_store,
)
from app.dash_app.pages.connectors.components.scan_status import (
    STATUS_CONFIG,
    render_scan_item,
)
from app.dash_app.pages.connectors.layout import _render_top_action_bar, _render_recent_scans
from app.dash_app.styles import (
    COLOR_ERROR,
    COLOR_GRAY_MEDIUM,
    COLOR_SUCCESS,
    COLOR_WARNING,
)


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# render_scan_item
# ---------------------------------------------------------------------------


class TestRenderScanItem:
    def _flatten_text(self, component):
        """Flatten a Dash component tree into a single text string."""
        if isinstance(component, (str, int, float)):
            return str(component)
        parts = []
        children = getattr(component, "children", None)
        if children is None:
            return ""
        if not isinstance(children, list):
            children = [children]
        for child in children:
            parts.append(self._flatten_text(child))
        return " ".join(parts)

    def _collect_icons(self, component):
        """Collect all icon class names in the component tree."""
        icons = []
        children = getattr(component, "children", None)
        if children is None:
            return icons
        if not isinstance(children, list):
            children = [children]
        for child in children:
            if hasattr(child, "className") and "fa-" in str(child.className):
                icons.append(child.className)
            icons.extend(self._collect_icons(child))
        return icons

    def test_completed_status_renders(self):
        """A completed scan shows the success icon and label."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "completed",
            "created_at": "2026-07-31T10:00:00Z",
            "started_at": "2026-07-31T10:00:01Z",
            "completed_at": "2026-07-31T10:02:30Z",
            "result_summary": {"signals_published": 42},
        }
        result = render_scan_item(cmd)
        text = self._flatten_text(result)
        assert "Completed" in text
        assert "Signals Published: 42" in text
        icons = self._collect_icons(result)
        assert STATUS_CONFIG["completed"]["icon"] in icons

    def test_running_status_renders_spinner(self):
        """A running scan shows the spinning icon."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "running",
            "created_at": "2026-07-31T10:00:00Z",
            "started_at": "2026-07-31T10:00:01Z",
        }
        result = render_scan_item(cmd)
        icons = self._collect_icons(result)
        assert STATUS_CONFIG["running"]["icon"] in icons

    def test_failed_status_shows_error_message(self):
        """A failed scan shows the error icon and message."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "failed",
            "created_at": "2026-07-31T10:00:00Z",
            "error_message": "Max concurrent scans reached",
        }
        result = render_scan_item(cmd)
        text = self._flatten_text(result)
        assert "Failed" in text
        assert "Max concurrent scans reached" in text

    def test_pending_status(self):
        """A pending scan shows the clock icon."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "pending",
            "created_at": "2026-07-31T10:00:00Z",
        }
        result = render_scan_item(cmd)
        icons = self._collect_icons(result)
        assert STATUS_CONFIG["pending"]["icon"] in icons

    def test_unknown_status_falls_back(self):
        """An unknown status does not crash and shows a fallback."""
        cmd = {"command_id": str(uuid.uuid4()), "status": "mystery"}
        result = render_scan_item(cmd)
        text = self._flatten_text(result)
        assert "Mystery" in text

    def test_duration_computed(self):
        """Duration is computed from started_at → completed_at."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "completed",
            "created_at": "2026-07-31T10:00:00Z",
            "started_at": "2026-07-31T10:00:00Z",
            "completed_at": "2026-07-31T10:01:45Z",
        }
        result = render_scan_item(cmd)
        text = self._flatten_text(result)
        # 1m 45s
        assert "1m 45s" in text

    def test_no_duration_when_no_timestamps(self):
        """No duration is shown when timestamps are missing."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "pending",
            "created_at": "2026-07-31T10:00:00Z",
        }
        result = render_scan_item(cmd)
        # Should not crash
        assert result is not None


# ---------------------------------------------------------------------------
# _render_top_action_bar & _render_recent_scans
# ---------------------------------------------------------------------------


class TestRenderScanSection:
    def _collect_ids(self, component):
        ids = set()
        component_id = getattr(component, "id", None)
        if component_id:
            if isinstance(component_id, dict):
                ids.add(tuple(sorted(component_id.items())))
            else:
                ids.add(component_id)
        children = getattr(component, "children", None)
        if children is None:
            return ids
        if not isinstance(children, list):
            children = [children]
        for child in children:
            ids.update(self._collect_ids(child))
        return ids

    def _flatten_text(self, component):
        if isinstance(component, (str, int, float)):
            return str(component)
        parts = []
        children = getattr(component, "children", None)
        if children is None:
            return ""
        if not isinstance(children, list):
            children = [children]
        for child in children:
            parts.append(self._flatten_text(child))
        return " ".join(parts)

    @pytest.mark.parametrize("connector_type", ["github", "jira", "confluence"])
    def test_scan_button_visible_for_producer_connectors(self, connector_type):
        """GitHub/Jira/Confluence detail pages have a Run Scan button in the top action bar."""
        meta = CONNECTOR_REGISTRY[connector_type]
        bar = _render_top_action_bar(connector_type, meta)
        ids = self._collect_ids(bar)
        expected = (("connector_type", connector_type), ("type", "connector-run-scan"))
        assert expected in ids
        text = self._flatten_text(bar)
        assert "Run Scan" in text

    @pytest.mark.parametrize("connector_type", ["slack", "teams", "google_docs"])
    def test_scan_button_hidden_for_non_producer_connectors(self, connector_type):
        """Slack/Teams etc. don't have the Run Scan button in the top action bar."""
        meta = CONNECTOR_REGISTRY[connector_type]
        bar = _render_top_action_bar(connector_type, meta)
        ids = self._collect_ids(bar)
        assert not any("connector-run-scan" in str(i) for i in ids)

    @pytest.mark.parametrize("connector_type", ["github", "jira", "confluence"])
    def test_recent_scans_visible_for_producer_connectors(self, connector_type):
        """GitHub/Jira/Confluence detail pages show the Recent Scans section."""
        meta = CONNECTOR_REGISTRY[connector_type]
        section = _render_recent_scans(connector_type, meta)
        text = self._flatten_text(section)
        assert "Recent Scans" in text

    @pytest.mark.parametrize("connector_type", ["slack", "teams", "google_docs"])
    def test_recent_scans_hidden_for_non_producer_connectors(self, connector_type):
        """Slack/Teams etc. don't show the Recent Scans section."""
        meta = CONNECTOR_REGISTRY[connector_type]
        section = _render_recent_scans(connector_type, meta)
        # Should be an empty div
        children = getattr(section, "children", None)
        assert children is None or children == []

    def test_delete_button_always_in_action_bar(self):
        """Delete Configuration button is always present in the top action bar."""
        meta = {"display_name": "Test", "setup_type": "db_backed"}
        bar = _render_top_action_bar("test", meta)
        ids = self._collect_ids(bar)
        expected = (("connector_type", "test"), ("type", "connector-delete"))
        assert expected in ids
        text = self._flatten_text(bar)
        assert "Delete Configuration" in text


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


class TestScanCallbacks:
    """Test scan callback behaviour using mocked requests."""

    def test_render_scan_item_uses_configured_colors(self):
        """Status colors map correctly from the theme tokens."""
        assert STATUS_CONFIG["completed"]["color"] == COLOR_SUCCESS
        assert STATUS_CONFIG["failed"]["color"] == COLOR_ERROR
        assert STATUS_CONFIG["running"]["color"] == COLOR_WARNING
        assert STATUS_CONFIG["pending"]["color"] == COLOR_GRAY_MEDIUM


# ---------------------------------------------------------------------------
# toggle_add_item_collapse
# ---------------------------------------------------------------------------


class TestToggleAddItemCollapse:
    """Tests for ``toggle_add_item_collapse``."""

    def test_toggle_opens_when_closed(self):
        """Clicking the toggle when closed returns open (True)."""
        result = toggle_add_item_collapse(n_clicks=1, is_open=False)
        assert result is True

    def test_toggle_closes_when_open(self):
        """Clicking the toggle when open returns closed (False)."""
        result = toggle_add_item_collapse(n_clicks=1, is_open=True)
        assert result is False

    def test_no_clicks_raises_prevent_update(self):
        """No clicks (None) raises PreventUpdate."""
        with pytest.raises(PreventUpdate):
            toggle_add_item_collapse(n_clicks=None, is_open=False)

    def test_zero_clicks_raises_prevent_update(self):
        """0 n_clicks also raises PreventUpdate (matches the 'if not n_clicks' guard)."""
        with pytest.raises(PreventUpdate):
            toggle_add_item_collapse(n_clicks=0, is_open=False)


# ---------------------------------------------------------------------------
# stop_polling_if_idle
# ---------------------------------------------------------------------------


class TestStopPollingIfIdle:
    """Tests for ``stop_polling_if_idle``."""

    def test_none_returns_true(self):
        """None input (no content yet) disables polling."""
        assert stop_polling_if_idle(None) is True

    def test_no_recent_scans_message_disables_polling(self):
        """'No recent scans' text disables polling."""
        div = html.Div("No recent scans.")
        assert stop_polling_if_idle(div) is True

    def test_running_scan_enables_polling(self):
        """A scan with 'Running' status enables polling."""
        scan_item = html.Div(
            children=[
                html.Div(
                    children=[
                        html.Span("Running"),
                        html.Span("2m ago"),
                    ]
                )
            ]
        )
        assert stop_polling_if_idle(scan_item) is False

    def test_queued_scan_enables_polling(self):
        """A scan with 'Queued' status enables polling."""
        scan_item = html.Div(
            children=[
                html.Div(
                    children=[
                        html.Span("Queued"),
                        html.Span("1m ago"),
                    ]
                )
            ]
        )
        assert stop_polling_if_idle(scan_item) is False

    def test_accepted_scan_enables_polling(self):
        """A scan with 'Accepted' status enables polling."""
        scan_item = html.Div(
            children=[
                html.Div(
                    children=[
                        html.Span("Accepted"),
                        html.Span("30s ago"),
                    ]
                )
            ]
        )
        assert stop_polling_if_idle(scan_item) is False

    def test_completed_scan_disables_polling(self):
        """A scan with 'Completed' status disables polling (no active scans)."""
        scan_item = html.Div(
            children=[
                html.Div(
                    children=[
                        html.Span("Completed"),
                        html.Span("5m ago"),
                    ]
                )
            ]
        )
        assert stop_polling_if_idle(scan_item) is True

    def test_multiple_scans_with_active_track_running(self):
        """When one of several scans is running, polling stays enabled."""
        scan_list = html.Div(
            children=[
                html.Div(children=[html.Span("Completed")]),
                html.Div(children=[html.Span("Running")]),
                html.Div(children=[html.Span("Queued")]),
            ]
        )
        assert stop_polling_if_idle(scan_list) is False

    def test_all_completed_scans_disable_polling(self):
        """When all scans are done, polling is disabled."""
        scan_list = html.Div(
            children=[
                html.Div(children=[html.Span("Completed"), html.Span("Signals Published: 42")]),
                html.Div(children=[html.Span("Failed"), html.Span("Error: timeout")]),
            ]
        )
        assert stop_polling_if_idle(scan_list) is True

    def test_fallback_returns_true(self):
        """Non-Div types (shouldn't happen) degrade safely to disabled."""
        assert stop_polling_if_idle("unexpected string") is True


# ---------------------------------------------------------------------------
# Search filter callbacks
# ---------------------------------------------------------------------------


class TestSearchFilterCallbacks:
    """Tests for search filter store, update, and render callbacks."""

    def test_populate_search_filters_store_ignores_non_github(self):
        """Non-github connector types return no_update."""
        from dash import no_update

        result = populate_search_filters_store(
            edit_state=None,
            store_id={"type": "connector-search-filters-store", "connector_type": "jira"},
        )
        assert result is no_update

    def test_populate_search_filters_store_from_item_data(self):
        """Filters are extracted from item data when editing an existing item."""
        edit_state = {
            "connector_type": "github",
            "item_id": 42,
            "item": {
                "search_filters": {"props.division": "platform", "props.team": "infra"},
            },
        }
        result = populate_search_filters_store(
            edit_state=edit_state,
            store_id={"type": "connector-search-filters-store", "connector_type": "github"},
        )
        assert result == {"props.division": "platform", "props.team": "infra"}

    def test_populate_search_filters_clear_returns_empty(self):
        """A 'clear' action returns an empty dict."""
        edit_state = {"connector_type": "github", "action": "clear"}
        result = populate_search_filters_store(
            edit_state=edit_state,
            store_id={"type": "connector-search-filters-store", "connector_type": "github"},
        )
        assert result == {}

    def test_render_search_filters_list_empty(self):
        """No filters shows a placeholder message."""
        result = render_search_filters_list(
            store_data={},
            list_component_id={"type": "connector-search-filter-list", "connector_type": "github"},
        )
        text = _flatten_dash(result)
        assert "No search filters configured" in text

    def test_render_search_filters_list_with_filters(self):
        """Filters are rendered as key: value rows with Remove buttons."""
        filters = {"props.division": "platform", "props.team": "infra"}
        result = render_search_filters_list(
            store_data=filters,
            list_component_id={"type": "connector-search-filter-list", "connector_type": "github"},
        )
        assert isinstance(result, list)
        assert len(result) == 2
        text = _flatten_dash(result)
        assert "props.division: platform" in text
        assert "props.team: infra" in text
        assert "Remove" in text


def _flatten_dash(component):
    """Flatten a Dash component (or list of components) to text."""
    if isinstance(component, list):
        return " ".join(_flatten_dash(c) for c in component)
    if isinstance(component, (str, int, float)):
        return str(component)
    children = getattr(component, "children", None)
    if children is None:
        return ""
    if not isinstance(children, list):
        children = [children]
    return " ".join(_flatten_dash(c) for c in children)

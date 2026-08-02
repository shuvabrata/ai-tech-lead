"""Unit tests for Phase 6 — Connector detail page scan UI.

Tests cover:
  - ``render_scan_item`` — scan status row rendering (icons, colors, timestamps)
  - ``_render_top_action_bar`` / ``_render_recent_scans`` — Run Scan button visibility rules
  - Scan callback helpers — polling, API interaction
  - ``toggle_add_item_collapse`` — collapsible form toggle
  - Search filter callbacks — store, update, render
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import uuid

import pytest
from dash import no_update
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc

from app.api.connectors.v1.registry import CONNECTOR_REGISTRY
from app.dash_app.pages.connectors.callbacks import (
    populate_search_filters_store,
    render_search_filters_list,
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
        }
        result = render_scan_item(cmd)
        text = self._flatten_text(result)
        assert "Completed" in text
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
        # Duration is now labeled
        assert "Duration: 1m 45s" in text

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

    def test_error_none_label_present(self):
        """Error: None label is shown even when no error_message is supplied."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "completed",
            "created_at": "2026-07-31T10:00:00Z",
            "started_at": "2026-07-31T10:00:01Z",
            "completed_at": "2026-07-31T10:02:30Z",
        }
        result = render_scan_item(cmd)
        text = self._flatten_text(result)
        assert "Error: None" in text

    def test_error_message_shown(self):
        """Error message is shown when present."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "failed",
            "created_at": "2026-07-31T10:00:00Z",
            "error_message": "Max concurrent scans reached",
        }
        result = render_scan_item(cmd)
        text = self._flatten_text(result)
        assert "Error: Max concurrent scans reached" in text

    def test_labeled_timestamps_present(self):
        """Created, Started, Completed labels appear in output."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "completed",
            "created_at": "2026-07-31T10:00:00Z",
            "started_at": "2026-07-31T10:00:01Z",
            "completed_at": "2026-07-31T10:02:30Z",
        }
        result = render_scan_item(cmd)
        text = self._flatten_text(result)
        assert "Created:" in text
        assert "Started:" in text
        assert "Completed:" in text


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
        """GitHub/Jira/Confluence detail pages show the Recent Actions section."""
        meta = CONNECTOR_REGISTRY[connector_type]
        section = _render_recent_scans(connector_type, meta)
        text = self._flatten_text(section)
        assert "Recent Actions" in text

    @pytest.mark.parametrize("connector_type", ["slack", "teams", "google_docs"])
    def test_recent_scans_hidden_for_non_producer_connectors(self, connector_type):
        """Slack/Teams etc. don't show the Recent Actions section."""
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
# stop_polling_if_idle — MOVED TO CLIENT-SIDE
# ---------------------------------------------------------------------------
# The ``stop_polling_if_idle`` logic was migrated to a ``clientside_callback``
# in ``callbacks.py`` (JavaScript running in the browser).  It is no longer a
# Python serverside callback and cannot be unit-tested from Python.
#
# The JS function recursively walks the serialized Dash component tree
# (``props.children``) looking for the strings "Running", "Queued", or
# "Accepted".  If any are found, it returns ``false`` (keep polling);
# otherwise it returns ``true`` (disable the poll interval).
# ---------------------------------------------------------------------------


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


# ═══════════════════════════════════════════════════════════════════════════
#  Cancel button tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCancelButtonVisibility:
    """Verify the Cancel button appears only for active scan statuses."""

    def _has_cancel_button(self, result) -> bool:
        """Check if result contains a Cancel dbc.Button."""
        if isinstance(result, list):
            for item in result:
                if self._has_cancel_button(item):
                    return True
            return False
        # Check if this component is a dbc.Button with Cancel text
        if hasattr(result, "className") and "btn" in str(result.className):
            text = _flatten_dash(result)
            return "Cancel" in text and "Cancelled" not in text
        children = getattr(result, "children", None)
        if not children:
            return False
        if isinstance(children, list):
            for child in children:
                if self._has_cancel_button(child):
                    return True
            return False
        return self._has_cancel_button(children)

    @staticmethod
    def _is_cancel_button(component) -> bool:
        text = _flatten_dash(component)
        return "Cancel" in text

    def test_cancel_button_visible_for_running(self):
        """Running scan row has Cancel button."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "running",
            "created_at": "2026-07-31T10:00:00Z",
        }
        result = render_scan_item(cmd)
        text = _flatten_dash(result)
        assert "Cancel" in text

    def test_cancel_button_visible_for_accepted(self):
        """Accepted scan row has Cancel button."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "accepted",
            "created_at": "2026-07-31T10:00:00Z",
        }
        result = render_scan_item(cmd)
        text = _flatten_dash(result)
        assert "Cancel" in text

    def test_cancel_button_hidden_for_completed(self):
        """Completed scan row has no Cancel button."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "completed",
            "created_at": "2026-07-31T10:00:00Z",
        }
        result = render_scan_item(cmd)
        assert not self._has_cancel_button(result)

    def test_cancel_button_hidden_for_failed(self):
        """Failed scan row has no Cancel button."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "failed",
            "created_at": "2026-07-31T10:00:00Z",
        }
        result = render_scan_item(cmd)
        assert not self._has_cancel_button(result)

    def test_cancel_button_hidden_for_cancelled(self):
        """Cancelled scan row has no Cancel button."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "cancelled",
            "created_at": "2026-07-31T10:00:00Z",
        }
        result = render_scan_item(cmd)
        assert not self._has_cancel_button(result)

    def test_cancel_button_hidden_for_pending(self):
        """Pending scan row has no Cancel button."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "status": "pending",
            "created_at": "2026-07-31T10:00:00Z",
        }
        result = render_scan_item(cmd)
        assert not self._has_cancel_button(result)


def test_cancelled_status_config_exists():
    """The cancelled status has an entry in STATUS_CONFIG."""
    assert "cancelled" in STATUS_CONFIG
    assert STATUS_CONFIG["cancelled"]["label"] == "Cancelled"
    assert "fa-regular fa-circle-stop" in STATUS_CONFIG["cancelled"]["icon"]


class TestCancelButtonCallback:
    """Tests for the ``handle_cancel_scan`` callback."""

    def _make_triggered_id(self, command_id: str) -> dict:
        return {"type": "connector-cancel-scan", "command_id": command_id}

    def test_cancel_click_sends_api_request(self):
        """Button click triggers POST to /api/v1/commands/ with cancel command."""
        from app.dash_app.pages.connectors.callbacks import handle_cancel_scan

        scan_command_id = str(uuid.uuid4())

        with (
            patch("app.dash_app.pages.connectors.callbacks.callback_context") as mock_ctx,
            patch("app.dash_app.pages.connectors.callbacks.requests.post") as mock_post,
        ):
            mock_ctx.triggered = [
                {
                    "prop_id": f".{self._make_triggered_id(scan_command_id)}.n_clicks",
                    "value": 1,
                    "type": "",
                    "index": "",
                }
            ]
            mock_ctx.triggered_id = self._make_triggered_id(scan_command_id)
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            result = handle_cancel_scan([1], "/app/connectors/github")

        assert result is not None
        alert, poll_disabled = result
        assert "Cancel sent" in _flatten_dash(alert)
        assert poll_disabled is False
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["command_type"] == "cancel"
        assert call_kwargs["json"]["parameters"]["cancel_command_id"] == scan_command_id

    def test_cancel_no_trigger_returns_no_update(self):
        """No trigger → returns no_update for both outputs."""
        from app.dash_app.pages.connectors.callbacks import handle_cancel_scan

        with patch("app.dash_app.pages.connectors.callbacks.callback_context") as mock_ctx:
            mock_ctx.triggered = []

            result = handle_cancel_scan([None], "/app/connectors/github")

        assert result == (no_update, no_update)

    def test_cancel_no_pathname_returns_no_update(self):
        """No pathname → returns no_update."""
        from app.dash_app.pages.connectors.callbacks import handle_cancel_scan

        with patch("app.dash_app.pages.connectors.callbacks.callback_context") as mock_ctx:
            scan_command_id = str(uuid.uuid4())
            mock_ctx.triggered = [
                {
                    "prop_id": f".{self._make_triggered_id(scan_command_id)}.n_clicks",
                    "value": 1,
                    "type": "",
                    "index": "",
                }
            ]
            mock_ctx.triggered_id = self._make_triggered_id(scan_command_id)

            result = handle_cancel_scan([1], None)

        assert result == (no_update, no_update)


# ═══════════════════════════════════════════════════════════════════════════
#  Command type badge tests
# ═══════════════════════════════════════════════════════════════════════════


class TestCommandTypeBadge:
    """Verify the command_type badge appears in scan rows."""

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

    def test_scan_badge_visible(self):
        """A scan command shows [SCAN] badge."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "command_type": "scan",
            "status": "running",
            "created_at": "2026-07-31T10:00:00Z",
        }
        result = render_scan_item(cmd)
        text = self._flatten_text(result)
        assert "[SCAN]" in text

    def test_test_badge_visible(self):
        """A test command shows [TEST] badge."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "command_type": "test",
            "status": "completed",
            "created_at": "2026-07-31T10:00:00Z",
        }
        result = render_scan_item(cmd)
        text = self._flatten_text(result)
        assert "[TEST]" in text

    def test_cancel_badge_visible(self):
        """A cancel command shows [CANCEL] badge."""
        cmd = {
            "command_id": str(uuid.uuid4()),
            "command_type": "cancel",
            "status": "completed",
            "created_at": "2026-07-31T10:00:00Z",
        }
        result = render_scan_item(cmd)
        text = self._flatten_text(result)
        assert "[CANCEL]" in text


# ═══════════════════════════════════════════════════════════════════════════
#  Test Connection button callback tests
# ═══════════════════════════════════════════════════════════════════════════


class TestTestConnectionCallback:
    """Tests for the ``handle_item_test_connection`` callback."""

    def test_test_connection_button_sends_command(self):
        """Button click POSTs to /api/v1/commands/ with command_type: test."""
        from app.dash_app.pages.connectors.callbacks import handle_item_test_connection

        with (
            patch("app.dash_app.pages.connectors.callbacks.callback_context") as mock_ctx,
            patch("app.dash_app.pages.connectors.callbacks.requests.post") as mock_post,
        ):
            mock_ctx.triggered = [
                {
                    "prop_id": '.{"type":"connector-item-test","connector_type":"github","item_id":1}.n_clicks',
                    "value": 1,
                    "type": "",
                    "index": "",
                }
            ]
            mock_ctx.triggered_id = {"type": "connector-item-test", "connector_type": "github", "item_id": 1}
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {"command_id": "abc-123"}
            mock_post.return_value = mock_response

            result = handle_item_test_connection([1])

        assert result is not None
        alert, poll_disabled = result
        alert_text = _flatten_dash(alert)
        assert "Test triggered" in alert_text
        assert "Recent Actions" in alert_text
        assert poll_disabled is False
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["command_type"] == "test"
        assert call_kwargs["json"]["parameters"]["item_id"] == 1

    def test_test_connection_no_producer_container(self):
        """Non-producer connector shows warning, no API call."""
        from app.dash_app.pages.connectors.callbacks import handle_item_test_connection

        with (
            patch("app.dash_app.pages.connectors.callbacks.callback_context") as mock_ctx,
            patch("app.dash_app.pages.connectors.callbacks.requests.post") as mock_post,
        ):
            mock_ctx.triggered = [
                {
                    "prop_id": '.{"type":"connector-item-test","connector_type":"slack","item_id":1}.n_clicks',
                    "value": 1,
                    "type": "",
                    "index": "",
                }
            ]
            mock_ctx.triggered_id = {"type": "connector-item-test", "connector_type": "slack", "item_id": 1}

            result = handle_item_test_connection([1])

        assert result is not None
        alert, poll_disabled = result
        alert_text = _flatten_dash(alert)
        assert "No producer container for slack" in alert_text
        assert poll_disabled is no_update
        mock_post.assert_not_called()

    def test_test_connection_no_trigger(self):
        """No trigger → returns no_update for both outputs."""
        from app.dash_app.pages.connectors.callbacks import handle_item_test_connection

        with patch("app.dash_app.pages.connectors.callbacks.callback_context") as mock_ctx:
            mock_ctx.triggered = []
            result = handle_item_test_connection([None])

        assert result == (no_update, no_update)

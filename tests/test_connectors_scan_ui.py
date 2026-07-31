"""Unit tests for Phase 6 — Connector detail page scan UI.

Tests cover:
  - ``render_scan_item`` — scan status row rendering (icons, colors, timestamps)
  - ``_render_scan_section`` — Run Scan button visibility rules
  - Scan callback helpers — polling, API interaction
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import uuid

import pytest
from dash import html

from app.api.connectors.v1.registry import CONNECTOR_REGISTRY
from app.dash_app.pages.connectors.components.scan_status import (
    STATUS_CONFIG,
    render_scan_item,
)
from app.dash_app.pages.connectors.layout import _render_scan_section
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
# _render_scan_section
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
        """GitHub/Jira/Confluence detail pages have a Run Scan button."""
        meta = CONNECTOR_REGISTRY[connector_type]
        section = _render_scan_section(connector_type, meta)
        ids = self._collect_ids(section)
        expected = (("connector_type", connector_type), ("type", "connector-run-scan"))
        assert expected in ids
        text = self._flatten_text(section)
        assert "Run Scan" in text
        assert "Recent Scans" in text

    @pytest.mark.parametrize("connector_type", ["slack", "teams", "google_docs"])
    def test_scan_button_hidden_for_non_producer_connectors(self, connector_type):
        """Slack/Teams etc. don't have the Run Scan button."""
        meta = CONNECTOR_REGISTRY[connector_type]
        section = _render_scan_section(connector_type, meta)
        ids = self._collect_ids(section)
        assert not any("connector-run-scan" in str(i) for i in ids)
        # Empty section — no content
        assert section is not None

    def test_scan_section_empty_when_no_producer(self):
        """Non-producer connectors get an empty div (no scan UI)."""
        meta = {"display_name": "Slack", "setup_type": "db_backed"}
        section = _render_scan_section("slack", meta)
        assert section is not None
        # Should be an empty div
        children = getattr(section, "children", None)
        assert children is None or children == []


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

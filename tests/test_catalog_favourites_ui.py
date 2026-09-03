"""Unit tests for the catalog favourites UI (Phase 3).

Covers:
  - Star renders filled for a favourited query, outline for a non-favourite.
  - The toggle callback fires ``PUT /catalog-metadata/{catalog_id}`` with the
    correct flipped payload.
  - The metadata store updates after a successful toggle (star flips in place).
  - No re-sort occurs on toggle (list order unchanged).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from dash import html

from app.dash_app.pages.graph.callbacks import catalog as catalog_cb
from app.dash_app.pages.graph.callbacks.catalog import (
    render_catalog_query_list,
    toggle_catalog_favourite,
)

pytestmark = pytest.mark.unit


def _query(catalog_id: str, name: str, namespace: str = "schema") -> dict:
    """Build a minimal catalog query dict."""
    return {
        "id": catalog_id,
        "name": name,
        "description": "",
        "summary": "",
        "namespace": {"directory": namespace, "name": namespace.title()},
        "tags": [],
        "available_views": ["graph"],
        "status": "active",
    }


def _flatten_text(component) -> str:
    """Recursively flatten a Dash component tree to text."""
    if isinstance(component, (str, int, float)):
        return str(component)
    parts = []
    children = getattr(component, "children", None)
    if children is None:
        return ""
    if not isinstance(children, list):
        children = [children]
    for child in children:
        parts.append(_flatten_text(child))
    return " ".join(parts)


def _collect_star_buttons(component) -> list:
    """Collect all favourite-toggle buttons in a component tree."""
    buttons = []
    component_id = getattr(component, "id", None)
    if isinstance(component_id, dict) and component_id.get("type") == "catalog-favourite-toggle":
        buttons.append(component)
    children = getattr(component, "children", None)
    if children is None:
        return buttons
    if not isinstance(children, list):
        children = [children]
    for child in children:
        buttons.extend(_collect_star_buttons(child))
    return buttons


def _star_icon_class(button) -> str:
    """Return the icon class of a star button (filled vs outline)."""
    icon = button.children
    if isinstance(icon, html.I):
        return icon.className
    return ""


class TestStarRendering:
    def test_favourited_query_renders_filled_star(self) -> None:
        """A favourited query renders a filled (fas) star."""
        queries = [_query("schema/a", "Alpha")]
        metadata = {"schema/a": {"is_favourite": True, "updated_at": "2026-09-03T00:00:00Z"}}
        result = render_catalog_query_list(queries, "__all__", None, None, metadata)
        buttons = _collect_star_buttons(result)
        assert len(buttons) == 1
        assert "fas fa-star" in _star_icon_class(buttons[0])
        assert "is-favourite" in buttons[0].className

    def test_non_favourited_query_renders_outline_star(self) -> None:
        """A non-favourited query renders an outline (far) star."""
        queries = [_query("schema/a", "Alpha")]
        metadata = {"schema/a": {"is_favourite": False, "updated_at": None}}
        result = render_catalog_query_list(queries, "__all__", None, None, metadata)
        buttons = _collect_star_buttons(result)
        assert len(buttons) == 1
        assert "far fa-star" in _star_icon_class(buttons[0])
        assert "is-favourite" not in buttons[0].className

    def test_missing_metadata_renders_outline_star(self) -> None:
        """A query with no metadata row renders an outline star."""
        queries = [_query("schema/a", "Alpha")]
        result = render_catalog_query_list(queries, "__all__", None, None, {})
        buttons = _collect_star_buttons(result)
        assert len(buttons) == 1
        assert "far fa-star" in _star_icon_class(buttons[0])

    def test_star_button_has_catalog_id(self) -> None:
        """The star button carries the query's catalog_id in its id."""
        queries = [_query("schema/a", "Alpha")]
        result = render_catalog_query_list(queries, "__all__", None, None, {})
        buttons = _collect_star_buttons(result)
        assert buttons[0].id == {"type": "catalog-favourite-toggle", "catalog_id": "schema/a"}


class TestToggleCallback:
    def _patch_ctx(self, triggered_id):
        """Patch the catalog module's ``ctx`` singleton with a mock."""
        fake_ctx = MagicMock()
        fake_ctx.triggered_id = triggered_id
        return patch.object(catalog_cb, "ctx", fake_ctx)

    def test_toggle_fires_put_with_flipped_payload(self) -> None:
        """Toggling a non-favourite fires PUT with is_favourite=true."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "catalog_id": "schema/a",
            "is_favourite": True,
            "updated_at": "2026-09-03T00:00:00Z",
        }
        with self._patch_ctx(
            {"type": "catalog-favourite-toggle", "catalog_id": "schema/a"}
        ), patch(
            "app.dash_app.pages.graph.callbacks.catalog.requests.put",
            return_value=mock_response,
        ) as mock_put:
            result = toggle_catalog_favourite([1], {})

        mock_put.assert_called_once()
        args, kwargs = mock_put.call_args
        assert "/api/v1/queries/catalog-metadata/schema/a" in args[0]
        assert kwargs["json"] == {"is_favourite": True}
        assert result["schema/a"]["is_favourite"] is True

    def test_toggle_flips_favourite_to_false(self) -> None:
        """Toggling a favourited query fires PUT with is_favourite=false."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "catalog_id": "schema/a",
            "is_favourite": False,
            "updated_at": "2026-09-03T00:00:01Z",
        }
        with self._patch_ctx(
            {"type": "catalog-favourite-toggle", "catalog_id": "schema/a"}
        ), patch(
            "app.dash_app.pages.graph.callbacks.catalog.requests.put",
            return_value=mock_response,
        ) as mock_put:
            result = toggle_catalog_favourite(
                [1], {"schema/a": {"is_favourite": True, "updated_at": "2026-09-03T00:00:00Z"}}
            )

        _, kwargs = mock_put.call_args
        assert kwargs["json"] == {"is_favourite": False}
        assert result["schema/a"]["is_favourite"] is False

    def test_store_updates_in_place(self) -> None:
        """The store is updated in place after a successful toggle."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "catalog_id": "schema/a",
            "is_favourite": True,
            "updated_at": "2026-09-03T00:00:00Z",
        }
        with self._patch_ctx(
            {"type": "catalog-favourite-toggle", "catalog_id": "schema/a"}
        ), patch(
            "app.dash_app.pages.graph.callbacks.catalog.requests.put",
            return_value=mock_response,
        ):
            result = toggle_catalog_favourite([1], {})

        assert result["schema/a"]["is_favourite"] is True
        assert result["schema/a"]["updated_at"] == "2026-09-03T00:00:00Z"

    def test_no_resort_on_toggle(self) -> None:
        """Toggling a favourite does not re-sort the list (Option B)."""
        queries = [
            _query("schema/a", "Alpha"),
            _query("schema/b", "Beta"),
        ]
        metadata = {"schema/a": {"is_favourite": True, "updated_at": "2026-09-03T00:00:00Z"}}
        result = render_catalog_query_list(queries, "__all__", None, None, metadata)
        text = _flatten_text(result)
        # Order preserved: Alpha before Beta (no re-sort on toggle).
        assert text.index("Alpha") < text.index("Beta")

    def test_toggle_preserves_other_entries(self) -> None:
        """Toggling one query leaves other metadata entries untouched."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "catalog_id": "schema/a",
            "is_favourite": True,
            "updated_at": "2026-09-03T00:00:00Z",
        }
        with self._patch_ctx(
            {"type": "catalog-favourite-toggle", "catalog_id": "schema/a"}
        ), patch(
            "app.dash_app.pages.graph.callbacks.catalog.requests.put",
            return_value=mock_response,
        ):
            result = toggle_catalog_favourite(
                [1], {"schema/b": {"is_favourite": True, "updated_at": "2026-09-03T00:00:00Z"}}
            )

        assert result["schema/b"]["is_favourite"] is True
        assert result["schema/a"]["is_favourite"] is True
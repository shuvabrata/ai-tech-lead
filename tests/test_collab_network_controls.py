"""Unit tests for C5-P4 collab network controls and properties panel callbacks.

Tests cover:
  - display_collab_properties (node selected, edge selected, nothing selected)
  - toggle_collab_fullwidth (fullwidth on/off)
  - update_collab_stylesheet (merged theme → stylesheet)
"""

from unittest.mock import patch

import pytest
from dash import html

from app.dash_app.pages.collaboration_network.callbacks.display import (
    display_collab_properties,
    update_collab_stylesheet,
)
from app.dash_app.pages.collaboration_network.callbacks.navigation import (
    toggle_collab_fullwidth,
)


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# display_collab_properties
# ---------------------------------------------------------------------------

class TestDisplayCollabProperties:
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

    def _collect_ids(self, component):
        ids = set()
        component_id = getattr(component, "id", None)
        if component_id:
            ids.add(component_id)
        children = getattr(component, "children", None)
        if children is None:
            return ids
        if not isinstance(children, list):
            children = [children]
        for child in children:
            ids |= self._collect_ids(child)
        return ids

    def test_nothing_selected_returns_placeholder(self):
        result = display_collab_properties(None, None)
        assert isinstance(result, html.P)
        text = self._flatten_text(result)
        assert "Select a node" in text

    def test_empty_lists_return_placeholder(self):
        result = display_collab_properties([], [])
        assert isinstance(result, html.P)

    def test_node_selected_returns_div(self):
        node = {"id": "n1", "wba_id": "github::Person::alice", "label": "Alice", "nodeType": "Person"}
        result = display_collab_properties([node], [])
        assert isinstance(result, html.Div)

    def test_node_selected_shows_label(self):
        node = {"id": "n1", "wba_id": "github::Person::alice", "label": "Alice", "nodeType": "Person"}
        result = display_collab_properties([node], [])
        text = self._flatten_text(result)
        assert "Alice" in text

    def test_node_selected_expand_button_has_no_id(self):
        """Expand Node button must be disabled and have no id on collab page."""
        node = {"id": "n1", "label": "Alice", "nodeType": "Person"}
        result = display_collab_properties([node], [])
        ids = self._collect_ids(result)
        assert "expand-node-btn" not in ids

    def test_edge_selected_returns_div(self):
        edge = {"id": "e1", "source": "n1", "target": "n2", "relType": "COLLABORATED"}
        result = display_collab_properties([], [edge])
        assert isinstance(result, html.Div)

    def test_edge_selected_shows_rel_type(self):
        edge = {"id": "e1", "source": "n1", "target": "n2", "relType": "COLLABORATED"}
        result = display_collab_properties([], [edge])
        text = self._flatten_text(result)
        assert "COLLABORATED" in text

    def test_edge_selected_no_expand_button(self):
        edge = {"id": "e1", "source": "n1", "target": "n2", "relType": "COLLABORATED"}
        result = display_collab_properties([], [edge])
        ids = self._collect_ids(result)
        assert "expand-node-btn" not in ids

    def test_node_takes_priority_over_edge(self):
        node = {"id": "n1", "label": "Alice", "nodeType": "Person"}
        edge = {"id": "e1", "source": "n1", "target": "n2", "relType": "COLLABORATED"}
        result = display_collab_properties([node], [edge])
        text = self._flatten_text(result)
        assert "Alice" in text


# ---------------------------------------------------------------------------
# toggle_collab_fullwidth
# ---------------------------------------------------------------------------

class TestToggleCollabFullwidth:
    def test_toggle_on_hides_panel(self):
        new_state, viz_width, panel_style = toggle_collab_fullwidth(1, False)
        assert new_state is True
        assert viz_width == 12
        assert panel_style == {"display": "none"}

    def test_toggle_off_shows_panel(self):
        new_state, viz_width, panel_style = toggle_collab_fullwidth(2, True)
        assert new_state is False
        assert viz_width == 8
        assert panel_style == {}

    def test_toggle_returns_tuple_of_three(self):
        result = toggle_collab_fullwidth(1, False)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# update_collab_stylesheet
# ---------------------------------------------------------------------------

class TestUpdateCollabStylesheet:
    def _selector_map(self, stylesheet):
        return {rule["selector"]: rule["style"] for rule in stylesheet}

    def test_fallback_to_base_on_fetch_error(self):
        """When /effective fails, the stylesheet falls back to base tokens."""
        with patch(
            "app.dash_app.pages.collaboration_network.callbacks.display._fetch_effective_theme",
            return_value=None,
        ):
            stylesheet = update_collab_stylesheet("executive-light")
        by_sel = self._selector_map(stylesheet)
        # Base palette (no override) → Person stays blue.
        person = by_sel['node[nodeType = "Person"]']
        assert person["background-color"] == "#3B82F6"
        assert person["shape"] == "octagon"

    def test_merged_override_applies_to_person(self):
        """A merged effective theme override propagates to the stylesheet."""
        from app.common.graph_theme import NodeOverride, ThemeOverrides, merge_theme_overrides
        from app.dash_app.styles import get_theme_tokens

        effective = merge_theme_overrides(
            get_theme_tokens("executive-light"),
            ThemeOverrides(nodes={"Person": NodeOverride(color="#00FF00")}),
        )
        with patch(
            "app.dash_app.pages.collaboration_network.callbacks.display._fetch_effective_theme",
            return_value=effective,
        ):
            stylesheet = update_collab_stylesheet("executive-light")
        by_sel = self._selector_map(stylesheet)
        person = by_sel['node[nodeType = "Person"]']
        assert person["background-color"] == "#00FF00"

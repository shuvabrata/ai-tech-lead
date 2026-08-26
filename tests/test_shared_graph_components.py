"""Unit tests for shared graph visualization components in components/common.py.

Tests cover:
  - toggle_details_panel
  - create_controls_bar
  - build_element_properties_content
"""

import pytest
import dash_bootstrap_components as dbc
from dash import html

from app.dash_app.components.common import (
    build_element_properties_content,
    create_controls_bar,
    toggle_details_panel,
)


# ---------------------------------------------------------------------------
# toggle_details_panel
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestToggleDetailsPanel:
    def test_fullwidth_returns_12_and_hidden_style(self):
        width, style = toggle_details_panel(True)
        assert width == 12
        assert style == {"display": "none"}

    def test_normal_returns_8_and_empty_style(self):
        width, style = toggle_details_panel(False)
        assert width == 8
        assert style == {}

    def test_return_is_tuple_of_two(self):
        result = toggle_details_panel(True)
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# create_controls_bar
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCreateControlsBar:
    def _find_component(self, component, component_type, **props):
        """Recursively search for a component matching type and props."""
        if isinstance(component, component_type):
            match = all(
                getattr(component, k, None) == v or
                (hasattr(component, '__dict__') and component.__dict__.get(k) == v)
                for k, v in props.items()
            )
            if match:
                return component
        children = getattr(component, 'children', None)
        if children is None:
            return None
        if not isinstance(children, list):
            children = [children]
        for child in children:
            result = self._find_component(child, component_type, **props)
            if result is not None:
                return result
        return None

    def _collect_ids(self, component):
        """Collect all component IDs recursively."""
        ids = set()
        component_id = getattr(component, 'id', None)
        if component_id:
            ids.add(component_id)
        children = getattr(component, 'children', None)
        if children is None:
            return ids
        if not isinstance(children, list):
            children = [children]
        for child in children:
            ids |= self._collect_ids(child)
        return ids

    def test_returns_dbc_row(self):
        result = create_controls_bar("graph")
        assert isinstance(result, dbc.Row)

    def test_graph_prefix_ids(self):
        result = create_controls_bar("graph")
        ids = self._collect_ids(result)
        assert "graph-layout-selector" in ids
        assert "graph-spotlight-input" in ids
        assert "graph-spotlight-count" in ids
        assert "graph-fit-btn" in ids
        assert "graph-reset-btn" in ids
        assert "graph-fullwidth-btn" in ids

    def test_collab_prefix_ids(self):
        result = create_controls_bar("collab")
        ids = self._collect_ids(result)
        assert "collab-layout-selector" in ids
        assert "collab-spotlight-input" in ids
        assert "collab-fit-btn" in ids

    def test_layout_selector_enabled_by_default(self):
        result = create_controls_bar("graph")

        def find_select(c):
            if isinstance(c, dbc.Select) and getattr(c, 'id', None) == "graph-layout-selector":
                return c
            for child in (getattr(c, 'children', None) or []):
                if not isinstance(child, list):
                    child = [child]
                for item in (child if isinstance(child, list) else [child]):
                    found = find_select(item)
                    if found:
                        return found
            return None

        # Walk children directly since Row has Col list
        selector = None
        for col in (result.children or []):
            for item in (col.children if isinstance(col.children, list) else [col.children]):
                if isinstance(item, dbc.Select) and getattr(item, 'id', None) == "graph-layout-selector":
                    selector = item
                    break

        assert selector is not None
        assert selector.disabled is False or selector.disabled is None

    def test_layout_selector_disabled_when_layout_disabled(self):
        result = create_controls_bar("collab", layout_enabled=False)
        selector = None
        for col in (result.children or []):
            children = col.children if isinstance(col.children, list) else [col.children]
            for item in children:
                if isinstance(item, dbc.Select) and getattr(item, 'id', None) == "collab-layout-selector":
                    selector = item
                    break
        assert selector is not None
        assert selector.disabled is True

    def test_has_three_cols(self):
        result = create_controls_bar("graph")
        assert len(result.children) == 3

    def test_row_has_mb2_class(self):
        result = create_controls_bar("graph")
        assert "mb-2" in (result.className or "")


# ---------------------------------------------------------------------------
# build_element_properties_content
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildElementPropertiesContent:
    def _flatten_text(self, component):
        """Recursively collect all string/int children as a single string."""
        if isinstance(component, (str, int, float)):
            return str(component)
        parts = []
        children = getattr(component, 'children', None)
        if children is None:
            return ""
        if not isinstance(children, list):
            children = [children]
        for child in children:
            parts.append(self._flatten_text(child))
        return " ".join(parts)

    def _collect_ids(self, component):
        ids = set()
        component_id = getattr(component, 'id', None)
        if component_id:
            ids.add(component_id)
        children = getattr(component, 'children', None)
        if children is None:
            return ids
        if not isinstance(children, list):
            children = [children]
        for child in children:
            ids |= self._collect_ids(child)
        return ids

    # --- Node cases ---

    def test_node_returns_html_div(self):
        data = {"id": "n1", "label": "Alice", "nodeType": "Person"}
        result = build_element_properties_content(data)
        assert isinstance(result, html.Div)

    def test_node_shows_label(self):
        data = {"id": "n1", "label": "Alice", "nodeType": "Person"}
        result = build_element_properties_content(data)
        text = self._flatten_text(result)
        assert "Alice" in text

    def test_node_shows_node_type(self):
        data = {"id": "n1", "label": "Alice", "nodeType": "Person"}
        result = build_element_properties_content(data)
        text = self._flatten_text(result)
        assert "Person" in text

    def test_node_uses_wba_id_as_display_id(self):
        data = {
            "id": "neo4j-internal-id",
            "wba_id": "github::Person::alice",
            "label": "Alice",
            "nodeType": "Person",
        }
        result = build_element_properties_content(data)
        text = self._flatten_text(result)
        assert "github::Person::alice" in text
        assert "neo4j-internal-id" not in text

    def test_node_expand_button_has_id_when_enabled(self):
        data = {"id": "n1", "label": "Alice", "nodeType": "Person"}
        result = build_element_properties_content(data, expand_node_enabled=True)
        ids = self._collect_ids(result)
        assert "expand-node-btn" in ids

    def test_node_expand_button_has_no_id_when_disabled(self):
        data = {"id": "n1", "label": "Alice", "nodeType": "Person"}
        result = build_element_properties_content(data, expand_node_enabled=False)
        ids = self._collect_ids(result)
        assert "expand-node-btn" not in ids

    def test_node_expand_button_disabled_when_expand_disabled(self):
        data = {"id": "n1", "label": "Alice", "nodeType": "Person"}
        result = build_element_properties_content(data, expand_node_enabled=False)

        def find_expand_btn(c):
            if isinstance(c, dbc.Button) and c.disabled is True:
                children = c.children or []
                if not isinstance(children, list):
                    children = [children]
                texts = " ".join(
                    str(ch) for ch in children if isinstance(ch, str)
                )
                if "Expand Node" in texts:
                    return c
            for child in (getattr(c, 'children', None) or []):
                if not isinstance(child, list):
                    child = [child]
                for item in (child if isinstance(child, list) else [child]):
                    found = find_expand_btn(item)
                    if found:
                        return found
            return None

        btn = find_expand_btn(result)
        assert btn is not None

    def test_node_extra_props_visible(self):
        data = {
            "id": "n1",
            "wba_id": "github::Person::alice",
            "label": "Alice",
            "nodeType": "Person",
            "email": "alice@example.com",
        }
        result = build_element_properties_content(data)
        text = self._flatten_text(result)
        assert "email" in text
        assert "alice@example.com" in text

    def test_node_internal_keys_hidden(self):
        data = {
            "id": "n1",
            "label": "Alice",
            "nodeType": "Person",
            "elementType": "node",
            "displayLabel": "Alice D",
        }
        result = build_element_properties_content(data)
        text = self._flatten_text(result)
        assert "elementType" not in text
        assert "displayLabel" not in text

    # --- Edge cases ---

    def test_edge_detected_by_element_type(self):
        data = {
            "id": "e1",
            "source": "n1",
            "target": "n2",
            "label": "WORKED_WITH",
            "relType": "WORKED_WITH",
            "elementType": "edge",
        }
        result = build_element_properties_content(data)
        assert isinstance(result, html.Div)

    def test_edge_shows_rel_type(self):
        data = {
            "id": "e1",
            "source": "n1",
            "target": "n2",
            "relType": "COLLABORATED",
            "elementType": "edge",
        }
        result = build_element_properties_content(data)
        text = self._flatten_text(result)
        assert "COLLABORATED" in text

    def test_edge_shows_relationship_subtype(self):
        data = {
            "id": "e1",
            "source": "n1",
            "target": "n2",
            "relType": "WORKED_WITH",
            "elementType": "edge",
        }
        result = build_element_properties_content(data)
        text = self._flatten_text(result)
        assert "Relationship" in text

    def test_edge_shows_from_and_to(self):
        data = {
            "id": "e1",
            "source": "alice",
            "target": "bob",
            "relType": "WORKED_WITH",
            "elementType": "edge",
        }
        result = build_element_properties_content(data)
        text = self._flatten_text(result)
        assert "from" in text
        assert "to" in text

    def test_edge_no_expand_button(self):
        data = {
            "id": "e1",
            "source": "n1",
            "target": "n2",
            "relType": "X",
            "elementType": "edge",
        }
        result = build_element_properties_content(data)
        ids = self._collect_ids(result)
        assert "expand-node-btn" not in ids

    def test_edge_extra_props_visible(self):
        data = {
            "id": "e1",
            "source": "n1",
            "target": "n2",
            "relType": "WORKED_WITH",
            "weight": 5,
            "elementType": "edge",
        }
        result = build_element_properties_content(data)
        text = self._flatten_text(result)
        assert "weight" in text

    # --- Node with a `source` property (regression) ---

    def test_node_with_source_property_is_not_misclassified_as_edge(self):
        """A node carrying a legitimate ``source`` Neo4j property (e.g. a Jira
        Issue) must not be treated as an edge.  Regression guard for the
        ``"source" in data`` heuristic that previously leaked ``wba_id`` as
        ``WBA_ID`` and dropped the synthetic ``ID`` row."""
        data = {
            "id": "neo4j-internal-id",
            "wba_id": "jira::Issue::PROJ-123",
            "label": "PROJ-123",
            "nodeType": "Issue",
            "elementType": "node",
            "source": "jira",
            "summary": "Fix the login bug",
        }
        result = build_element_properties_content(data)
        text = self._flatten_text(result)
        assert "Relationship" not in text
        assert "from" not in text
        assert "jira::Issue::PROJ-123" in text
        assert "neo4j-internal-id" not in text


# ---------------------------------------------------------------------------
# create_time_slider_pair
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCreateTimeSliderPair:
    """Tests for ``create_time_slider_pair`` in graph/components/sliders.py."""

    def _collect_ids(self, component):
        """Collect all component IDs recursively."""
        ids = set()
        component_id = getattr(component, 'id', None)
        if component_id:
            ids.add(component_id)
        children = getattr(component, 'children', None)
        if children is None:
            return ids
        if not isinstance(children, list):
            children = [children]
        for child in children:
            ids |= self._collect_ids(child)
        return ids

    def test_returns_html_div(self):
        """T1.1: Verify create_time_slider_pair returns a html.Div."""
        from app.dash_app.pages.graph.components.sliders import create_time_slider_pair
        result = create_time_slider_pair("created", "Created At")
        assert isinstance(result, html.Div)

    def test_has_four_children(self):
        """T1.1: Verify the div has 4 children: label, coarse, fine, value label."""
        from app.dash_app.pages.graph.components.sliders import create_time_slider_pair
        result = create_time_slider_pair("created", "Created At")
        assert result.children is not None
        children = result.children
        assert isinstance(children, list)
        assert len(children) == 4

    def test_children_types(self):
        """T1.1: Verify the 4 children have the correct types."""
        from app.dash_app.pages.graph.components.sliders import create_time_slider_pair
        result = create_time_slider_pair("created", "Created At")
        children = result.children
        assert isinstance(children[0], html.Label)
        # Check the slider instances via repr/type check
        from dash import dcc
        assert isinstance(children[1], dcc.RangeSlider)
        assert isinstance(children[2], dcc.RangeSlider)
        assert isinstance(children[3], html.Small)

    def test_fine_slider_matches_coarse_initially(self):
        """T1.2: Fine slider min/max/value matches coarse slider initially."""
        from app.dash_app.pages.graph.components.sliders import create_time_slider_pair
        result = create_time_slider_pair("created", "Created At")
        children = result.children
        coarse = children[1]
        fine = children[2]
        assert fine.min == coarse.min
        assert fine.max == coarse.max
        assert fine.value == coarse.value

    def test_correct_ids(self):
        """T1.1/T1.2: Verify component IDs based on suffix."""
        from app.dash_app.pages.graph.components.sliders import create_time_slider_pair
        result = create_time_slider_pair("seen", "Last Seen")
        ids = self._collect_ids(result)
        assert "time-slider-seen" in ids
        assert "time-slider-seen-fine" in ids
        assert "time-slider-seen-label" in ids

    def test_section_style_matches_details_panel(self):
        """T1.3: Verify the section div uses the same boxed style as the details panel."""
        from app.dash_app.pages.graph.components.sliders import create_time_slider_pair
        result = create_time_slider_pair("updated", "Last Updated")
        style = result.style or {}
        assert "var(--color-background-pale)" in str(style.get("backgroundColor", ""))
        assert "var(--color-border-gray)" in str(style.get("border", ""))
        assert style.get("borderRadius") == "4px"
        assert style.get("padding") == "8px"

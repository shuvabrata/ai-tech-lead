"""Tests for graph filter panel local refinement behavior."""

import pytest

from app.dash_app.pages.graph.callbacks import filtering as filtering_callbacks


pytestmark = pytest.mark.unit


def test_apply_relationship_filters_ignores_weight_controls_for_unweighted_graph():
    """Unweighted graphs should not be truncated by stale weight/top-N selections."""
    unfiltered_elements = [
        {"data": {"id": "n1", "nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "n2", "nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "n3", "nodeType": "Repository", "elementType": "node"}},
        {"data": {"id": "e1", "source": "n1", "target": "n2", "relType": "KNOWS", "elementType": "edge"}},
        {"data": {"id": "e2", "source": "n2", "target": "n3", "relType": "WORKS_ON", "elementType": "edge"}},
    ]

    filtered = filtering_callbacks.apply_relationship_filters(
        selected_node_types=["Person", "Repository"],
        selected_rel_types=["KNOWS", "WORKS_ON"],
        weight_threshold=75,
        top_n_mode="top50",
        unfiltered_elements=unfiltered_elements,
        created_range=[0, 1],
        updated_range=[0, 1],
        seen_range=[0, 1],
        full_ranges={},
    )

    assert filtered == unfiltered_elements


def test_apply_relationship_filters_raises_when_edge_id_missing():
    """Filtering should fail fast when an edge is missing required id."""
    unfiltered_elements = [
        {"data": {"id": "n1", "nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "n2", "nodeType": "Person", "elementType": "node"}},
        {"data": {"source": "n1", "target": "n2", "relType": "COLLABORATES", "elementType": "edge"}},
    ]

    with pytest.raises(filtering_callbacks.FilteringDataValidationError, match="edge.*id"):
        filtering_callbacks.apply_relationship_filters(
            selected_node_types=["Person"],
            selected_rel_types=["COLLABORATES"],
            weight_threshold=0,
            top_n_mode="all",
            unfiltered_elements=unfiltered_elements,
            created_range=[0, 1],
            updated_range=[0, 1],
            seen_range=[0, 1],
            full_ranges={},
        )


def test_apply_relationship_filters_raises_when_node_id_missing():
    """Filtering should fail fast when a node is missing required id."""
    unfiltered_elements = [
        {"data": {"nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "n2", "nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "e1", "source": "n2", "target": "n2", "relType": "COLLABORATES", "elementType": "edge"}},
    ]

    with pytest.raises(filtering_callbacks.FilteringDataValidationError, match="node.*id"):
        filtering_callbacks.apply_relationship_filters(
            selected_node_types=["Person"],
            selected_rel_types=["COLLABORATES"],
            weight_threshold=0,
            top_n_mode="all",
            unfiltered_elements=unfiltered_elements,
            created_range=[0, 1],
            updated_range=[0, 1],
            seen_range=[0, 1],
            full_ranges={},
        )


def test_update_filter_panel_feedback_hides_weight_controls_for_unweighted_graph():
    """Weight-specific controls should be hidden when the graph has no edge weights."""
    unfiltered_elements = [
        {"data": {"id": "n1", "nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "n2", "nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "e1", "source": "n1", "target": "n2", "relType": "KNOWS", "elementType": "edge"}},
    ]

    summary, chips, weight_group_style, weight_note_style = filtering_callbacks.update_filter_panel_feedback(
        unfiltered_elements=unfiltered_elements,
        selected_node_types=["Person"],
        selected_rel_types=["KNOWS"],
        weight_threshold=0,
        top_n_mode="all",
        node_type_options=[{"label": "Person (2)", "value": "Person"}],
        rel_type_options=[{"label": "KNOWS (1)", "value": "KNOWS"}],
        created_range=[0, 1],
        updated_range=[0, 1],
        seen_range=[0, 1],
        full_ranges={},
    )

    assert summary == "Showing 2 nodes / 1 edges from 2 nodes / 1 edges"
    assert chips[0].children == "No active filters"
    assert weight_group_style == {"display": "none"}
    assert weight_note_style == {"display": "block"}


def test_update_node_type_filter_defaults_to_all_on_fresh_graph_load():
    """Resetting the available-store should force a clean all-selected state."""
    unfiltered_elements = [
        {"data": {"id": "n1", "nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "n2", "nodeType": "Repository", "elementType": "node"}},
    ]

    options, values, available = filtering_callbacks.update_node_type_filter(
        unfiltered_elements=unfiltered_elements,
        current_values=["Person"],
        previous_available=None,
    )

    assert options == [
        {"label": "Person (1)", "value": "Person"},
        {"label": "Repository (1)", "value": "Repository"},
    ]
    assert values == ["Person", "Repository"]
    assert available == ["Person", "Repository"]


def test_update_relationship_type_filter_defaults_to_all_on_fresh_graph_load():
    """Resetting the available-store should force a clean all-selected state."""
    unfiltered_elements = [
        {"data": {"id": "n1", "nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "n2", "nodeType": "Repository", "elementType": "node"}},
        {"data": {"id": "e1", "source": "n1", "target": "n2", "relType": "WORKS_ON", "elementType": "edge"}},
    ]

    options, values, available = filtering_callbacks.update_relationship_type_filter(
        unfiltered_elements=unfiltered_elements,
        current_values=[],
        previous_available=None,
    )

    assert options == [
        {"label": "WORKS_ON (1)", "value": "WORKS_ON"},
    ]
    assert values == ["WORKS_ON"]
    assert available == ["WORKS_ON"]


# ── _summarize_time_filter ───────────────────────────────────────────────


def test_summarize_time_filter_none_when_full_range():
    """When range_value equals full_range, should return None."""
    result = filtering_callbacks._summarize_time_filter(
        [100, 200], [100, 200], "Created"
    )
    assert result is None


def test_summarize_time_filter_none_when_none():
    """When range_value or full_range is None, should return None."""
    assert filtering_callbacks._summarize_time_filter(None, [100, 200], "Created") is None
    assert filtering_callbacks._summarize_time_filter([100, 200], None, "Created") is None


def test_summarize_time_filter_returns_chip():
    """When narrowed, should return a formatted chip string."""
    result = filtering_callbacks._summarize_time_filter(
        [150, 200], [100, 200], "Updated"
    )
    assert result is not None
    assert result.startswith("Updated:")
    assert "–" in result


def test_summarize_time_filter_uses_format_day_label():
    """Chip label should contain formatted dates from _format_day_label."""
    result = filtering_callbacks._summarize_time_filter(
        [20103, 20423], [20103, 20423], "Created"
    )
    assert result is None  # full range


# ── clear_all_filters ────────────────────────────────────────────────────


def test_clear_all_filters_resets_time_sliders():
    """Clear All should reset time sliders to full ranges from the store."""
    result = filtering_callbacks.clear_all_filters(
        n_clicks=1,
        node_type_options=[{"label": "Person (2)", "value": "Person"}],
        rel_type_options=[{"label": "KNOWS (1)", "value": "KNOWS"}],
        full_ranges={
            "_created_at": [20103, 20423],
            "_last_updated_at": [20240, 20423],
            "_last_seen_at": [20000, 20500],
        },
    )
    # Returns: node_types, rel_types, weight, top_n, created, updated, seen
    assert result[0] == ["Person"]
    assert result[1] == ["KNOWS"]
    assert result[2] == 0
    assert result[3] == "all"
    assert result[4] == [20103, 20423]  # created reset
    assert result[5] == [20240, 20423]  # updated reset
    assert result[6] == [20000, 20500]  # seen reset


def test_clear_all_filters_no_clicks():
    """When n_clicks is falsy, should raise PreventUpdate."""
    from dash.exceptions import PreventUpdate

    with pytest.raises(PreventUpdate):
        filtering_callbacks.clear_all_filters(
            n_clicks=None,
            node_type_options=[],
            rel_type_options=[],
            full_ranges={},
        )


def test_clear_all_filters_empty_full_ranges():
    """When full_ranges is empty, time sliders should reset to [0, 1]."""
    result = filtering_callbacks.clear_all_filters(
        n_clicks=1,
        node_type_options=[],
        rel_type_options=[],
        full_ranges={},
    )
    assert result[4] == [0, 1]
    assert result[5] == [0, 1]
    assert result[6] == [0, 1]


# ── toggle_time_filters_collapse ─────────────────────────────────────────


def test_toggle_time_filters_collapse_opens():
    """Toggling from closed should open and show chevron-down."""
    is_open, children = filtering_callbacks.toggle_time_filters_collapse(
        n_clicks=1, is_open=False
    )
    assert is_open is True
    assert "chevron-down" in children[0].className


def test_toggle_time_filters_collapse_closes():
    """Toggling from open should close and show chevron-right."""
    is_open, children = filtering_callbacks.toggle_time_filters_collapse(
        n_clicks=1, is_open=True
    )
    assert is_open is False
    assert "chevron-right" in children[0].className


def test_toggle_time_filters_collapse_no_clicks():
    """When n_clicks is falsy, should raise PreventUpdate."""
    from dash.exceptions import PreventUpdate

    with pytest.raises(PreventUpdate):
        filtering_callbacks.toggle_time_filters_collapse(
            n_clicks=None, is_open=False
        )


# ── update_time_filter_ranges ────────────────────────────────────────────


def _make_node(node_id, **props):
    """Build a minimal Cytoscape node element dict."""
    data = {"id": node_id, "elementType": "node", **props}
    return {"data": data}


def test_update_time_filter_ranges_computes_ranges():
    """Should compute correct min/max from unfiltered nodes."""
    elements = [
        _make_node("n1", _created_at="2025-01-15T00:00:00Z"),
        _make_node("n2", _created_at="2025-12-01T00:00:00Z"),
    ]
    result = filtering_callbacks.update_time_filter_ranges(
        unfiltered_elements=elements,
        previous_ranges={},
    )
    ranges_dict = result[0]
    assert "_created_at" in ranges_dict
    assert ranges_dict["_created_at"][0] == 20103  # Jan 15, 2025
    assert ranges_dict["_created_at"][1] == 20423  # Dec 1, 2025


def test_update_time_filter_ranges_empty_elements():
    """Empty elements should raise PreventUpdate."""
    from dash.exceptions import PreventUpdate

    with pytest.raises(PreventUpdate):
        filtering_callbacks.update_time_filter_ranges(
            unfiltered_elements=[],
            previous_ranges={},
        )


def test_update_time_filter_ranges_preserves_previous_value():
    """When previous range matches computed range, value should be preserved."""
    elements = [
        _make_node("n1", _created_at="2025-01-15T00:00:00Z"),
        _make_node("n2", _created_at="2025-12-01T00:00:00Z"),
    ]
    result = filtering_callbacks.update_time_filter_ranges(
        unfiltered_elements=elements,
        previous_ranges={
            "_created_at": [20103, 20423],
            "_last_updated_at": [0, 1],
            "_last_seen_at": [0, 1],
        },
    )
    assert result[3] == [20103, 20423]  # created value


def test_update_time_filter_ranges_single_node_pads():
    """Single node with min==max should pad by ±1 day."""
    elements = [
        _make_node("n1", _created_at="2025-06-15T00:00:00Z"),
    ]
    result = filtering_callbacks.update_time_filter_ranges(
        unfiltered_elements=elements,
        previous_ranges={},
    )
    ranges_dict = result[0]
    created_range = ranges_dict["_created_at"]
    # 2025-06-15 = day 20254, padded to [20253, 20255]
    assert created_range[0] == 20253
    assert created_range[1] == 20255


# ── update_time_filter_labels ────────────────────────────────────────────


def test_update_time_filter_labels_full_range():
    """When slider is at full range, label should say 'All dates'."""
    labels = filtering_callbacks.update_time_filter_labels(
        created_val=[20103, 20423],
        updated_val=[20240, 20423],
        seen_val=[20000, 20500],
        full_ranges={
            "_created_at": [20103, 20423],
            "_last_updated_at": [20240, 20423],
            "_last_seen_at": [20000, 20500],
        },
    )
    assert "All dates" in labels[0]
    assert "All dates" in labels[1]
    assert "All dates" in labels[2]


def test_update_time_filter_labels_narrowed():
    """When slider is narrowed, label should show the date range."""
    labels = filtering_callbacks.update_time_filter_labels(
        created_val=[20103, 20200],
        updated_val=[20240, 20423],
        seen_val=[20000, 20500],
        full_ranges={
            "_created_at": [20103, 20423],
            "_last_updated_at": [20240, 20423],
            "_last_seen_at": [20000, 20500],
        },
    )
    assert "All dates" not in labels[0]  # narrowed
    assert "–" in labels[0]


def test_update_time_filter_labels_no_full_ranges():
    """When full_ranges is None/empty, should return empty strings."""
    labels = filtering_callbacks.update_time_filter_labels(
        created_val=[0, 1],
        updated_val=[0, 1],
        seen_val=[0, 1],
        full_ranges=None,
    )
    assert labels == ("", "", "")

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

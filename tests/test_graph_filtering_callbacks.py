"""Tests for graph filter panel local refinement behavior."""

from app.dash_app.pages.graph.callbacks import filtering as filtering_callbacks


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


def test_update_filter_panel_feedback_hides_weight_controls_for_unweighted_graph():
    """Weight-specific controls should be hidden when the graph has no edge weights."""
    graph_elements = [
        {"data": {"id": "n1", "nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "n2", "nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "e1", "source": "n1", "target": "n2", "relType": "KNOWS", "elementType": "edge"}},
    ]

    summary, chips, weight_group_style, weight_note_style = filtering_callbacks.update_filter_panel_feedback(
        current_elements=graph_elements,
        unfiltered_elements=graph_elements,
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

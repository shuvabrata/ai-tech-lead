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
        display_mode="hide",
        unfiltered_elements=unfiltered_elements,
    )

    assert filtered == unfiltered_elements


def test_apply_relationship_filters_dim_mode_keeps_all_elements_and_marks_non_matches():
    """Dim mode should retain non-matching elements and tag them with the dimmed class."""
    unfiltered_elements = [
        {"data": {"id": "n1", "nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "n2", "nodeType": "Repository", "elementType": "node"}},
        {"data": {"id": "e1", "source": "n1", "target": "n2", "relType": "WORKS_ON", "elementType": "edge"}},
    ]

    rendered = filtering_callbacks.apply_relationship_filters(
        selected_node_types=["Person"],
        selected_rel_types=["WORKS_ON"],
        weight_threshold=0,
        top_n_mode="all",
        display_mode="dim",
        unfiltered_elements=unfiltered_elements,
    )

    assert len(rendered) == 3
    rendered_by_id = {elem["data"]["id"]: elem for elem in rendered if "id" in elem["data"]}
    assert "classes" not in rendered_by_id["n1"]
    assert rendered_by_id["n2"]["classes"] == "dimmed"
    assert rendered_by_id["e1"]["classes"] == "dimmed"


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
            display_mode="dim",
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
            display_mode="dim",
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
        _display_mode="hide",
        node_type_options=[{"label": "Person (2)", "value": "Person"}],
        rel_type_options=[{"label": "KNOWS (1)", "value": "KNOWS"}],
    )

    assert summary == "Showing 2 nodes / 1 edges from 2 nodes / 1 edges"
    assert chips[0].children == "No active filters"
    assert weight_group_style == {"display": "none"}
    assert weight_note_style == {"display": "block"}


def test_update_filter_panel_feedback_uses_logical_counts_in_dim_mode():
    """Dim mode should report visible counts, not total rendered element counts."""
    unfiltered_elements = [
        {"data": {"id": "n1", "nodeType": "Person", "elementType": "node"}},
        {"data": {"id": "n2", "nodeType": "Repository", "elementType": "node"}},
        {"data": {"id": "e1", "source": "n1", "target": "n2", "relType": "WORKS_ON", "elementType": "edge"}},
    ]

    summary, chips, _weight_group_style, weight_note_style = filtering_callbacks.update_filter_panel_feedback(
        unfiltered_elements=unfiltered_elements,
        selected_node_types=["Person"],
        selected_rel_types=["WORKS_ON"],
        weight_threshold=0,
        top_n_mode="all",
        _display_mode="dim",
        node_type_options=[
            {"label": "Person (1)", "value": "Person"},
            {"label": "Repository (1)", "value": "Repository"},
        ],
        rel_type_options=[{"label": "WORKS_ON (1)", "value": "WORKS_ON"}],
    )

    assert summary == "Showing 1 nodes / 0 edges from 2 nodes / 1 edges"
    assert chips[0].children == "Node types: Person"
    assert weight_note_style == {"display": "block"}


@pytest.mark.xfail(reason="Known Dim mode issue: stale dimmed class not removed on re-selection. See Phase 2 doc: Dim mode + edge hover interaction conflict")
def test_apply_relationship_filters_dim_mode_un_dims_reselected_elements_with_stale_class():
    """Visible elements should have stale dimmed class removed when they become selected again."""
    unfiltered_elements = [
        {"data": {"id": "n1", "nodeType": "Person", "elementType": "node"}, "classes": "dimmed"},
        {"data": {"id": "n2", "nodeType": "Repository", "elementType": "node"}, "classes": "dimmed"},
        {"data": {"id": "e1", "source": "n1", "target": "n2", "relType": "WORKS_ON", "elementType": "edge"}, "classes": "dimmed"},
    ]

    rendered = filtering_callbacks.apply_relationship_filters(
        selected_node_types=["Person", "Repository"],
        selected_rel_types=["WORKS_ON"],
        weight_threshold=0,
        top_n_mode="all",
        display_mode="dim",
        unfiltered_elements=unfiltered_elements,
    )

    rendered_by_id = {elem["data"]["id"]: elem for elem in rendered if "id" in elem["data"]}
    assert "classes" not in rendered_by_id["n1"]
    assert "classes" not in rendered_by_id["n2"]
    assert "classes" not in rendered_by_id["e1"]


@pytest.mark.xfail(reason="Known Dim mode issue: stale dimmed class persists in Hide mode. See Phase 2 doc: Dim mode + edge hover interaction conflict")
def test_apply_relationship_filters_hide_mode_un_dims_visible_elements_with_stale_class():
    """Hide mode should not return stale dimmed classes on visible elements."""
    unfiltered_elements = [
        {"data": {"id": "n1", "nodeType": "Person", "elementType": "node"}, "classes": "dimmed"},
        {"data": {"id": "n2", "nodeType": "Repository", "elementType": "node"}, "classes": "dimmed"},
        {"data": {"id": "e1", "source": "n1", "target": "n2", "relType": "WORKS_ON", "elementType": "edge"}, "classes": "dimmed"},
    ]

    rendered = filtering_callbacks.apply_relationship_filters(
        selected_node_types=["Person", "Repository"],
        selected_rel_types=["WORKS_ON"],
        weight_threshold=0,
        top_n_mode="all",
        display_mode="hide",
        unfiltered_elements=unfiltered_elements,
    )

    rendered_by_id = {elem["data"]["id"]: elem for elem in rendered if "id" in elem["data"]}
    assert "classes" not in rendered_by_id["n1"]
    assert "classes" not in rendered_by_id["n2"]
    assert "classes" not in rendered_by_id["e1"]

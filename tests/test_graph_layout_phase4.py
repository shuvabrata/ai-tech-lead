"""Layout smoke tests for the Phase 4 Graph page workbench."""

import pytest

from app.dash_app.pages.graph.layout import get_layout


pytestmark = pytest.mark.unit


def test_graph_layout_includes_catalog_workbench_components():
    layout = get_layout()
    component_ids = set()

    def walk(component):
        if component is None:
            return
        component_id = getattr(component, "id", None)
        if component_id is not None:
            component_ids.add(str(component_id))
        children = getattr(component, "children", None)
        if isinstance(children, (list, tuple)):
            for child in children:
                walk(child)
        elif children is not None:
            walk(children)

    walk(layout)

    assert "graph-catalog-section" in component_ids
    assert "query-catalog-store" in component_ids
    assert "selected-catalog-query-store" in component_ids
    assert "catalog-parameters-store" in component_ids
    assert "catalog-namespace-filter" in component_ids
    assert "catalog-search-input" in component_ids
    assert "catalog-view-filter" in component_ids
    assert "catalog-query-list" in component_ids
    assert "catalog-query-detail" in component_ids
    assert "catalog-query-view-toggle" in component_ids
    assert "catalog-parameter-inputs" in component_ids
    assert "catalog-run-btn" in component_ids
    assert "catalog-load-console-btn" in component_ids

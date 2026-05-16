"""Unit tests for graph details display helpers."""

from app.dash_app.pages.graph.callbacks.display import (
    _build_visible_properties,
    _resolve_edge_endpoint_id,
)


def test_build_visible_properties_hides_internal_neo4j_and_underscore_fields():
    data = {
        "id": "person_123",
        "ID": 99,
        "elementID": "4:abc",
        "elementId": "4:def",
        "_last_synced_at": "2026-05-16T00:00:00Z",
        "name": "Ada",
        "email": None,
    }

    visible = _build_visible_properties(data, exclude_keys=set())

    assert visible == {"id": "person_123", "name": "Ada"}


def test_build_visible_properties_applies_exclude_keys():
    data = {
        "id": "person_123",
        "label": "Ada Lovelace",
        "nodeType": "Person",
        "role": "Engineer",
    }

    visible = _build_visible_properties(data, exclude_keys={"id", "label", "nodeType"})

    assert visible == {"role": "Engineer"}


def test_resolve_edge_endpoint_id_prefers_explicit_endpoint_id():
    edge_data = {
        "source_id": "person_alice",
        "source": "cyto_source_fallback",
    }

    assert _resolve_edge_endpoint_id(edge_data, "source") == "person_alice"


def test_resolve_edge_endpoint_id_supports_nested_id_and_fallback():
    nested_edge_data = {
        "targetId": {"id": "person_bob"},
        "target": "cyto_target_fallback",
    }
    fallback_edge_data = {"target": "person_charlie"}

    assert _resolve_edge_endpoint_id(nested_edge_data, "target") == "person_bob"
    assert _resolve_edge_endpoint_id(fallback_edge_data, "target") == "person_charlie"

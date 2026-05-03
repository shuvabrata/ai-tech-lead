"""Unit tests for Graph page catalog callback helpers."""

import pytest

from app.dash_app.pages.graph.callbacks import catalog as catalog_callbacks


pytestmark = pytest.mark.unit


def test_filter_catalog_queries_respects_namespace_search_and_view():
    catalog_queries = [
        {
            "id": "github/top_contributors",
            "name": "Top Contributors",
            "description": "Commit leaderboard",
            "namespace": {"name": "GitHub", "directory": "github"},
            "available_views": ["tabular", "graph"],
            "tags": ["people"],
        },
        {
            "id": "jira/open_bugs",
            "name": "Open Bugs",
            "description": "Active defects",
            "namespace": {"name": "Jira", "directory": "jira"},
            "available_views": ["tabular"],
            "tags": ["bugs"],
        },
    ]

    filtered = catalog_callbacks.filter_catalog_queries(
        catalog_queries,
        namespace_filter="github",
        search_text="contributors",
        view_filter="graph",
    )

    assert [query["id"] for query in filtered] == ["github/top_contributors"]


def test_parse_catalog_deep_link_extracts_catalog_and_valid_view():
    catalog_id, view = catalog_callbacks.parse_catalog_deep_link(
        "?catalog=person_to_person/direct_code_reviews&view=tabular"
    )

    assert catalog_id == "person_to_person/direct_code_reviews"
    assert view == "tabular"


def test_parse_catalog_deep_link_ignores_invalid_view():
    catalog_id, view = catalog_callbacks.parse_catalog_deep_link(
        "?catalog=github/top_contributors&view=auto"
    )

    assert catalog_id == "github/top_contributors"
    assert view is None


def test_determine_catalog_view_prefers_current_then_requested_then_graph():
    catalog_query = {"available_views": ["tabular", "graph"]}

    assert catalog_callbacks.determine_catalog_view(catalog_query, "graph", "tabular") == "tabular"
    assert catalog_callbacks.determine_catalog_view(catalog_query, "graph", None) == "graph"
    assert catalog_callbacks.determine_catalog_view({"available_views": ["tabular"]}, None, None) == "tabular"


def test_required_parameters_missing_reports_only_unfilled_required_inputs():
    catalog_query = {
        "parameters": [
            {"name": "person1_id", "required": True},
            {"name": "person2_id", "required": True},
            {"name": "optional_repo", "required": False},
        ]
    }

    missing = catalog_callbacks.required_parameters_missing(
        catalog_query,
        {"person1_id": "alice", "person2_id": "   "},
    )

    assert missing == ["person2_id"]


def test_build_namespace_options_includes_all_namespaces_first():
    options = catalog_callbacks.build_namespace_options(
        [
            {"namespace": {"name": "GitHub", "directory": "github"}},
            {"namespace": {"name": "Jira", "directory": "jira"}},
        ]
    )

    assert options == [
        {"label": "All namespaces", "value": catalog_callbacks.ALL_NAMESPACES},
        {"label": "GitHub", "value": "github"},
        {"label": "Jira", "value": "jira"},
    ]

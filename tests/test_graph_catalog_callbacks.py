"""Unit tests for Graph page catalog callback helpers."""

import pytest

from app.dash_app.pages.graph.callbacks import catalog as catalog_callbacks


pytestmark = pytest.mark.unit


def _flatten_text(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        texts = []
        for child in value:
            texts.extend(_flatten_text(child))
        return texts
    children = getattr(value, "children", None)
    if isinstance(children, (list, tuple)):
        texts = []
        for child in children:
            texts.extend(_flatten_text(child))
        return texts
    if children is not None:
        return _flatten_text(children)
    return []


def test_filter_catalog_queries_respects_namespace_search_and_view():
    catalog_queries = [
        {
            "id": "github/top_contributors",
            "name": "Top Contributors",
            "description": "Commit leaderboard",
            "summary": "Repository commit leaders",
            "namespace": {"name": "GitHub", "directory": "github"},
            "available_views": ["tabular", "graph"],
            "tags": ["people"],
            "owner": "graph-team",
            "status": "active",
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
    catalog_query = {"available_views": ["tabular", "graph"], "default_view": "tabular"}

    assert catalog_callbacks.determine_catalog_view(catalog_query, "graph", "tabular") == "tabular"
    assert catalog_callbacks.determine_catalog_view(catalog_query, "graph", None) == "graph"
    assert catalog_callbacks.determine_catalog_view(catalog_query, None, None) == "tabular"
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


def test_filter_catalog_queries_matches_summary_owner_and_status_text():
    catalog_queries = [
        {
            "id": "person_to_person/direct_code_reviews",
            "name": "Direct Code Reviews",
            "description": "Review collaboration",
            "summary": "Compare two people by direct code review activity.",
            "namespace": {"name": "Person-to-Person", "directory": "person_to_person"},
            "available_views": ["tabular", "graph"],
            "tags": ["people"],
            "owner": "graph-team",
            "status": "active",
        }
    ]

    filtered = catalog_callbacks.filter_catalog_queries(
        catalog_queries,
        namespace_filter=catalog_callbacks.ALL_NAMESPACES,
        search_text="graph-team active",
        view_filter=catalog_callbacks.ALL_VIEWS,
    )

    assert [query["id"] for query in filtered] == ["person_to_person/direct_code_reviews"]


def test_render_catalog_query_detail_uses_rich_metadata_and_default_view():
    catalog_query = {
        "id": "person_to_person/direct_code_reviews",
        "name": "Direct Code Reviews",
        "description": "Find all PRs created by one and reviewed by the other.",
        "summary": "Compare two people by direct code review activity.",
        "namespace": {"name": "Person-to-Person", "directory": "person_to_person"},
        "available_views": ["tabular", "graph"],
        "default_view": "tabular",
        "parameters": [
            {
                "name": "person1_id",
                "required": True,
                "label": "First person",
                "type": "person_id",
                "placeholder": "Enter first person id",
                "description": "Neo4j Person.id for the first person.",
                "env_var": "PERSON1_ID",
            }
        ],
        "tags": ["code-review"],
        "owner": "graph-team",
        "status": "active",
    }

    (
        detail_children,
        _view_options,
        selected_view,
        parameter_children,
        run_disabled,
        load_disabled,
    ) = catalog_callbacks.render_catalog_query_detail(
        selected_query={"id": "person_to_person/direct_code_reviews"},
        catalog_queries=[catalog_query],
        parameter_values={"person1_id": "person_123"},
        current_view=None,
    )

    detail_text = " ".join(_flatten_text(detail_children))
    parameter_text = " ".join(_flatten_text(parameter_children))
    first_parameter_block = parameter_children[0]
    parameter_input = first_parameter_block.children[1]

    assert selected_view == "tabular"
    assert "Compare two people by direct code review activity." in detail_text
    assert "Owner: graph-team" in detail_text
    assert "Active" in detail_text
    assert first_parameter_block.children[0].children == "First person *"
    assert parameter_input.placeholder == "Enter first person id"
    assert "Neo4j Person.id for the first person." in parameter_text
    assert "Type: person_id" in parameter_text
    assert "Env hint: PERSON1_ID" in parameter_text
    assert run_disabled is False
    assert load_disabled is False

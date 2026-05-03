"""Unit tests for the query catalog metadata API."""

import pytest
from fastapi import HTTPException

from app.api.queries.v1 import router


pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_list_catalog_queries():
    response = await router.list_catalog_queries(namespace=None, tag=None, q=None, view=None)
    data = response.model_dump()

    assert data["count"] == 64
    assert len(data["items"]) == 64
    assert data["items"][0]["id"] == "schema/view_all_node_types"
    assert set(data["items"][0]["queries"]) == {"tabular", "graph"}
    assert data["items"][0]["summary"] == "Count all nodes by type."
    assert data["items"][0]["default_view"] == "tabular"
    assert data["items"][0]["owner"] == "graph-platform"
    assert data["items"][0]["status"] == "active"


async def test_filter_catalog_by_namespace():
    response = await router.list_catalog_queries(namespace="github", tag=None, q=None, view=None)
    data = response.model_dump()

    assert data["count"] == 25
    assert all(item["namespace"]["directory"] == "github" for item in data["items"])


async def test_filter_catalog_by_namespace_display_name():
    response = await router.list_catalog_queries(namespace="GitHub", tag=None, q=None, view=None)
    data = response.model_dump()

    assert data["count"] == 25


async def test_filter_catalog_by_view():
    response = await router.list_catalog_queries(namespace=None, tag=None, q=None, view="graph")
    data = response.model_dump()

    assert data["count"] == 64
    assert all("graph" in item["available_views"] for item in data["items"])


async def test_search_catalog_queries():
    response = await router.list_catalog_queries(
        namespace=None,
        tag=None,
        q="direct code reviews",
        view=None,
    )
    data = response.model_dump()

    assert data["count"] == 1
    assert data["items"][0]["id"] == "person_to_person/direct_code_reviews"
    assert data["items"][0]["summary"] == "Compare two people by direct code review activity."
    assert data["items"][0]["owner"] == "graph-team"
    assert data["items"][0]["status"] == "active"


async def test_search_catalog_queries_by_owner_and_status_metadata():
    response = await router.list_catalog_queries(
        namespace=None,
        tag=None,
        q="graph-team active",
        view=None,
    )
    data = response.model_dump()

    assert data["count"] == 11
    assert all(item["owner"] == "graph-team" for item in data["items"])
    assert all(item["status"] == "active" for item in data["items"])


async def test_get_catalog_query_detail():
    response = await router.get_catalog_query("github", "top_contributors")
    data = response.model_dump()

    assert data["id"] == "github/top_contributors"
    assert data["name"] == "Top Contributors"
    assert data["namespace"]["name"] == "GitHub"
    assert "LIMIT 10" in data["queries"]["tabular"]
    assert data["summary"] == "Top 10 contributors by commit count."
    assert data["default_view"] == "tabular"
    assert data["owner"] == "github-analytics"
    assert data["status"] == "active"


async def test_get_catalog_query_detail_includes_rich_metadata():
    response = await router.get_catalog_query("person_to_person", "direct_code_reviews")
    data = response.model_dump()

    assert data["default_view"] == "tabular"
    assert data["summary"] == "Compare two people by direct code review activity."
    assert data["owner"] == "graph-team"
    assert data["status"] == "active"
    assert data["parameters"][0]["label"] == "First person"
    assert data["parameters"][0]["type"] == "person_id"
    assert data["parameters"][0]["placeholder"] == "Enter first person id"


async def test_get_catalog_query_missing_returns_404():
    with pytest.raises(HTTPException) as exc_info:
        await router.get_catalog_query("github", "does_not_exist")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Catalog query not found"


async def test_list_catalog_namespaces():
    response = await router.list_catalog_namespaces()
    data = response.model_dump()

    assert data["count"] == 6
    assert [item["directory"] for item in data["items"]] == [
        "schema",
        "cross_domain",
        "github",
        "jira",
        "people_and_identity",
        "person_to_person",
    ]

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


async def test_get_catalog_query_detail():
    response = await router.get_catalog_query("github", "top_contributors")
    data = response.model_dump()

    assert data["id"] == "github/top_contributors"
    assert data["name"] == "Top Contributors"
    assert data["namespace"]["name"] == "GitHub"
    assert "LIMIT 10" in data["queries"]["tabular"]


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

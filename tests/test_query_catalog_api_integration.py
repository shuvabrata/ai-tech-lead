"""HTTP integration tests for the YAML-backed query catalog API."""

from __future__ import annotations

import httpx
import pytest

from app.main import app


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _get(path: str, *, params: dict[str, str] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.get(path, params=params)


async def test_catalog_list_endpoint_returns_normalized_catalog():
    response = await _get("/api/v1/queries/catalog")

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 64
    assert len(data["items"]) == 64

    first_item = data["items"][0]
    assert first_item["id"] == "schema/view_all_node_types"
    assert first_item["slug"] == "view_all_node_types"
    assert first_item["namespace"]["directory"] == "schema"
    assert set(first_item["queries"]) == {"tabular", "graph"}
    assert first_item["available_views"] == ["tabular", "graph"]


async def test_catalog_namespaces_endpoint_returns_display_order():
    response = await _get("/api/v1/queries/catalog/namespaces")

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 6
    assert [item["directory"] for item in data["items"]] == [
        "schema",
        "cross_domain",
        "github",
        "jira",
        "people_and_identity",
        "person_to_person",
    ]
    assert [item["order"] for item in data["items"]] == list(range(6))


@pytest.mark.parametrize("namespace", ["github", "GitHub"])
async def test_catalog_list_endpoint_filters_by_namespace_directory_or_display_name(namespace: str):
    response = await _get("/api/v1/queries/catalog", params={"namespace": namespace})

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 25
    assert all(item["namespace"]["directory"] == "github" for item in data["items"])


async def test_catalog_list_endpoint_filters_by_search_text():
    response = await _get(
        "/api/v1/queries/catalog",
        params={"q": "direct code reviews"},
    )

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 1
    assert data["items"][0]["id"] == "person_to_person/direct_code_reviews"
    assert data["items"][0]["parameters"] == [
        {"name": "person1_id", "env_var": "PERSON1_ID", "required": True},
        {"name": "person2_id", "env_var": "PERSON2_ID", "required": True},
    ]


async def test_catalog_list_endpoint_filters_by_view():
    response = await _get("/api/v1/queries/catalog", params={"view": "graph"})

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 64
    assert all("graph" in item["available_views"] for item in data["items"])


async def test_catalog_list_endpoint_rejects_invalid_view_filter():
    response = await _get("/api/v1/queries/catalog", params={"view": "invalid"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "view"]


async def test_catalog_detail_endpoint_returns_full_query_entry():
    response = await _get("/api/v1/queries/catalog/github/top_contributors")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == "github/top_contributors"
    assert data["slug"] == "top_contributors"
    assert data["name"] == "Top Contributors"
    assert data["namespace"]["name"] == "GitHub"
    assert data["available_views"] == ["tabular", "graph"]
    assert "LIMIT 10" in data["queries"]["tabular"]
    assert "LIMIT 100" in data["queries"]["graph"]


async def test_catalog_detail_endpoint_returns_404_for_missing_query():
    response = await _get("/api/v1/queries/catalog/github/does_not_exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Catalog query not found"}

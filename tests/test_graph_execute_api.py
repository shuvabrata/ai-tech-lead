"""Tests for the unified graph execution API."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.api.graph.v1 import service
from app.main import app
from app.query_catalog import CatalogNamespace, CatalogQuery


pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def _post_execute(payload: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.post("/api/v1/graph/execute", json=payload)


def _tabular_records(query: str, **kwargs: Any) -> list[dict[str, Any]]:
    _ = query, kwargs
    return [{"ok": True}]


def _catalog_query(
    *,
    catalog_id: str = "test/write_query",
    queries: dict[str, str] | None = None,
) -> CatalogQuery:
    namespace_directory, slug = catalog_id.split("/", 1)
    namespace = CatalogNamespace(name="Test", directory=namespace_directory, order=0)
    return CatalogQuery(
        id=catalog_id,
        slug=slug,
        namespace=namespace,
        name="Test Query",
        description="Test query for graph execute API.",
        queries=queries or {"graph": "MATCH (n) RETURN n"},
        available_views=list((queries or {"graph": "MATCH (n) RETURN n"}).keys()),
        parameters=[],
        tags=[],
        source_path=f"queries_catalog/{catalog_id}.yaml",
    )


async def test_execute_raw_query_validates_and_returns_graph_response(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_execute(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        captured["query"] = query
        captured["parameters"] = kwargs.get("parameters")
        return [{"answer": 42}]

    monkeypatch.setattr(service, "execute_cypher_query", fake_execute)

    response = await _post_execute(
        {
            "source": "raw",
            "query": "  RETURN 42 AS answer  ",
            "parameters": {"limit": 10},
        }
    )

    assert response.status_code == 200
    assert response.json() == {
        "nodes": [],
        "relationships": [],
        "rawResults": [{"answer": 42}],
        "isGraph": False,
        "resultCount": 1,
    }
    assert captured == {"query": "RETURN 42 AS answer", "parameters": {"limit": 10}}


async def test_execute_raw_query_requires_query():
    response = await _post_execute({"source": "raw"})

    assert response.status_code == 422
    assert "source='raw' requires query" in str(response.json()["detail"])


async def test_execute_catalog_query_resolves_query_and_parameters(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_execute(query: str, **kwargs: Any) -> list[dict[str, Any]]:
        captured["query"] = query
        captured["parameters"] = kwargs.get("parameters")
        return [{"review_count": 3}]

    monkeypatch.setattr(service, "execute_cypher_query", fake_execute)

    response = await _post_execute(
        {
            "source": "catalog",
            "catalog_id": "person_to_person/direct_code_reviews",
            "view": "tabular",
            "parameters": {
                "person1_id": "person-1",
                "person2_id": "person-2",
            },
        }
    )

    assert response.status_code == 200
    assert response.json()["rawResults"] == [{"review_count": 3}]
    assert "MATCH (p1:Person {id: $person1_id})" in captured["query"]
    assert captured["parameters"] == {
        "person1_id": "person-1",
        "person2_id": "person-2",
    }


async def test_execute_catalog_query_returns_404_when_missing():
    response = await _post_execute(
        {
            "source": "catalog",
            "catalog_id": "github/does_not_exist",
            "view": "graph",
        }
    )

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["error"] == "Catalog query not found"
    assert detail["catalog_id"] == "github/does_not_exist"


async def test_execute_catalog_query_rejects_missing_required_parameter(monkeypatch):
    monkeypatch.setattr(service, "execute_cypher_query", _tabular_records)

    response = await _post_execute(
        {
            "source": "catalog",
            "catalog_id": "person_to_person/direct_code_reviews",
            "view": "graph",
            "parameters": {"person1_id": "person-1"},
        }
    )

    assert response.status_code == 400
    assert "person2_id" in response.json()["detail"]["message"]


async def test_execute_catalog_query_rejects_unknown_parameter(monkeypatch):
    monkeypatch.setattr(service, "execute_cypher_query", _tabular_records)

    response = await _post_execute(
        {
            "source": "catalog",
            "catalog_id": "person_to_person/direct_code_reviews",
            "view": "graph",
            "parameters": {
                "person1_id": "person-1",
                "person2_id": "person-2",
                "extra": "surprise",
            },
        }
    )

    assert response.status_code == 400
    assert "extra" in response.json()["detail"]["message"]


async def test_execute_catalog_query_rejects_auto_view(monkeypatch):
    monkeypatch.setattr(service, "execute_cypher_query", _tabular_records)

    response = await _post_execute(
        {
            "source": "catalog",
            "catalog_id": "github/top_contributors",
            "view": "auto",
        }
    )

    assert response.status_code == 400
    assert "requires view='graph' or view='tabular'" in response.json()["detail"]["message"]


async def test_execute_catalog_query_rejects_unavailable_view(monkeypatch):
    monkeypatch.setattr(
        service,
        "_get_catalog_query_or_404",
        lambda _catalog_id: _catalog_query(queries={"graph": "MATCH (n) RETURN n"}),
    )
    monkeypatch.setattr(service, "execute_cypher_query", _tabular_records)

    response = await _post_execute(
        {
            "source": "catalog",
            "catalog_id": "test/write_query",
            "view": "tabular",
        }
    )

    assert response.status_code == 400
    assert "does not define a 'tabular' view" in response.json()["detail"]["message"]


async def test_execute_raw_write_query_is_blocked(monkeypatch):
    monkeypatch.setattr(service, "execute_cypher_query", _tabular_records)

    response = await _post_execute(
        {
            "source": "raw",
            "query": "CREATE (n:Test) RETURN n",
        }
    )

    assert response.status_code == 400
    assert "write operations" in response.json()["detail"]["message"].lower()


async def test_execute_catalog_write_query_is_blocked(monkeypatch):
    monkeypatch.setattr(
        service,
        "_get_catalog_query_or_404",
        lambda _catalog_id: _catalog_query(queries={"graph": "CREATE (n:Test) RETURN n"}),
    )
    monkeypatch.setattr(service, "execute_cypher_query", _tabular_records)

    response = await _post_execute(
        {
            "source": "catalog",
            "catalog_id": "test/write_query",
            "view": "graph",
        }
    )

    assert response.status_code == 400
    assert "write operations" in response.json()["detail"]["message"].lower()

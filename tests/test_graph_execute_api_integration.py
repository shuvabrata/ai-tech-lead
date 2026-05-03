"""Live integration tests for the unified graph execution endpoint.

These tests call /api/v1/graph/execute through the mounted FastAPI app and
execute against Neo4j. They require NEO4J_ENABLED=true and a reachable Neo4j
instance.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.main import app
from app.settings import settings


pytestmark = [
    pytest.mark.integration,
    pytest.mark.neo4j,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not settings.NEO4J_ENABLED,
        reason="Neo4j is not enabled (NEO4J_ENABLED=false)",
    ),
]


async def _post_execute(payload: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.post("/api/v1/graph/execute", json=payload)


def _assert_graph_response_shape(data: dict[str, Any]) -> None:
    assert set(data) == {"nodes", "relationships", "rawResults", "isGraph", "resultCount"}
    assert isinstance(data["nodes"], list)
    assert isinstance(data["relationships"], list)
    assert isinstance(data["rawResults"], list)
    assert isinstance(data["isGraph"], bool)
    assert isinstance(data["resultCount"], int)


async def test_execute_raw_parameterized_query_against_neo4j():
    response = await _post_execute(
        {
            "source": "raw",
            "query": "RETURN $value AS value, $count AS count",
            "parameters": {"value": "phase3-ok", "count": 3},
        }
    )

    assert response.status_code == 200
    data = response.json()
    _assert_graph_response_shape(data)
    assert data["isGraph"] is False
    assert data["rawResults"] == [{"value": "phase3-ok", "count": 3}]
    assert data["resultCount"] == 1


async def test_execute_catalog_tabular_query_against_neo4j():
    response = await _post_execute(
        {
            "source": "catalog",
            "catalog_id": "github/top_contributors",
            "view": "tabular",
        }
    )

    assert response.status_code == 200
    data = response.json()
    _assert_graph_response_shape(data)
    assert data["isGraph"] is False
    assert data["nodes"] == []
    assert data["relationships"] == []
    assert data["resultCount"] == len(data["rawResults"])

    if data["rawResults"]:
        assert set(data["rawResults"][0]) == {"name", "title", "commits"}


async def test_execute_parameterized_catalog_query_against_neo4j():
    response = await _post_execute(
        {
            "source": "catalog",
            "catalog_id": "person_to_person/direct_code_reviews",
            "view": "tabular",
            "parameters": {
                "person1_id": "__phase3_integration_person_1__",
                "person2_id": "__phase3_integration_person_2__",
            },
        }
    )

    assert response.status_code == 200
    data = response.json()
    _assert_graph_response_shape(data)
    assert data["isGraph"] is False
    assert data["nodes"] == []
    assert data["relationships"] == []
    assert data["rawResults"] == []
    assert data["resultCount"] == 0

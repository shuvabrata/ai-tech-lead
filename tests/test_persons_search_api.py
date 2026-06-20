"""Integration tests for GET /api/v1/search/persons.

Test strategy
-------------
These tests follow the same seed-then-teardown approach as ``test_search_api.py``:
documents are indexed directly into Elasticsearch via ``index_signal()``, then
the new ``/api/v1/search/persons`` endpoint is exercised through ASGI transport.

Seeded documents use the ``wbatst`` source prefix to avoid polluting real data.

Run with:
    pytest -m "integration and elasticsearch" tests/test_persons_search_api.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generator

import httpx
import pytest

from app.main import app
from app.settings import settings
from connectors.consumers.sinks.elasticsearch_sink import index_signal
from common.activity_signal.models import (
    ActivitySignal,
    PersonAttributes,
    IssueAttributes,
)
from elasticsearch import Elasticsearch


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.integration,
    pytest.mark.elasticsearch,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not settings.ELASTICSEARCH_ENABLED,
        reason="Elasticsearch is not enabled (ELASTICSEARCH_ENABLED=false)",
    ),
]

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_SOURCE_CONFIG = "http://wbatst-persons-test"
_CONNECTOR_URL = "http://wbatst-persons-test/connector/1"
_EVENT_TIME = datetime(2026, 1, 20, 9, 0, 0, tzinfo=timezone.utc)

_TEST_PERSONS: list[ActivitySignal] = [
    # GitHub person with full_name + email
    ActivitySignal(
        source="github",
        id="wbatst_alice",
        source_config=_SOURCE_CONFIG,
        connector_url=_CONNECTOR_URL,
        event_time=_EVENT_TIME,
        version="1.0",
        attributes=PersonAttributes(
            full_name="Alice Wbatst",
            login="wbatst_alice",
            email="alice.wbatst@example.com",
            url="http://wbatst.example.com/wbatst_alice",
        ),
    ),
    # GitHub person with full_name but no email
    ActivitySignal(
        source="github",
        id="wbatst_bob",
        source_config=_SOURCE_CONFIG,
        connector_url=_CONNECTOR_URL,
        event_time=_EVENT_TIME,
        version="1.0",
        attributes=PersonAttributes(
            full_name="Bob Wbatst",
            login="wbatst_bob",
            email=None,
            url=None,
        ),
    ),
    # Jira person with account-style id
    ActivitySignal(
        source="jira",
        id="wbatst_charlie",
        source_config=_SOURCE_CONFIG,
        connector_url=_CONNECTOR_URL,
        event_time=_EVENT_TIME,
        version="1.0",
        attributes=PersonAttributes(
            full_name="Charlie Wbatst",
            login="wbatst_charlie",
            email="charlie.wbatst@example.com",
            url=None,
        ),
    ),
]

# Non-person signal to verify entity_type scoping
_NON_PERSON_SIGNAL = ActivitySignal(
    source="jira",
    id="WBATST-PERSONS-9999",
    source_config=_SOURCE_CONFIG,
    connector_url=_CONNECTOR_URL,
    event_time=_EVENT_TIME,
    version="1.0",
    attributes=IssueAttributes(
        key="WBATST-PERSONS-9999",
        summary="wbatst persons test issue (should not appear in /persons endpoint)",
        priority="Low",
        status="Open",
        type="Task",
        created_at=_EVENT_TIME.isoformat(),
        url=None,
    ),
)

_ALL_TEST_SIGNALS = _TEST_PERSONS + [_NON_PERSON_SIGNAL]

_SEEDED_WBA_IDS: set[str] = {
    f"{s.source}::{s.entity_type}::{s.id}" for s in _ALL_TEST_SIGNALS
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_es_client() -> Elasticsearch:
    if settings.ELASTIC_PASSWORD:
        return Elasticsearch(
            settings.ELASTICSEARCH_URL,
            basic_auth=("elastic", settings.ELASTIC_PASSWORD),
        )
    return Elasticsearch(settings.ELASTICSEARCH_URL)


@pytest.fixture(scope="module")
def seeded_es() -> Generator[None, None, None]:
    """Seed test persons (and one non-person) into ES, tear down after module."""
    client = _make_es_client()

    for signal in _ALL_TEST_SIGNALS:
        index_signal(client, signal)

    client.indices.refresh(index="wba_all")
    yield

    for wba_id in _SEEDED_WBA_IDS:
        parts = wba_id.split("::", 2)
        source, entity_type = parts[0], parts[1]
        index_name = f"{source}_{entity_type.lower()}_index"
        try:
            client.delete(index=index_name, id=wba_id)
        except Exception:
            pass

    client.indices.refresh(index="wba_all")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get(path: str, **params: Any) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.get(path, params=params)


# ---------------------------------------------------------------------------
# Response shape tests
# ---------------------------------------------------------------------------


async def test_persons_endpoint_returns_expected_shape(seeded_es: None) -> None:
    """Response has a 'results' list with PersonSuggestion fields."""
    resp = await _get("/api/v1/search/persons", q="wbatst")
    assert resp.status_code == 200

    data = resp.json()
    assert "results" in data
    assert isinstance(data["results"], list)

    for suggestion in data["results"]:
        assert "wba_id" in suggestion
        assert "name" in suggestion
        assert "source" in suggestion
        # email and login may be None but must be present as keys
        assert "email" in suggestion
        assert "login" in suggestion


async def test_persons_endpoint_returns_only_persons(seeded_es: None) -> None:
    """The endpoint must NOT return Issues even when the query token matches."""
    resp = await _get("/api/v1/search/persons", q="wbatst", page_size=20)
    assert resp.status_code == 200

    results = resp.json()["results"]
    for suggestion in results:
        wba_id: str = suggestion["wba_id"]
        entity_type = wba_id.split("::")[1] if "::" in wba_id else ""
        assert entity_type == "Person", (
            f"Non-Person entity returned: {wba_id}"
        )


async def test_persons_endpoint_matches_by_full_name(seeded_es: None) -> None:
    """Searching a first name prefix returns the matching person."""
    resp = await _get("/api/v1/search/persons", q="Alice")
    assert resp.status_code == 200

    wba_ids = {r["wba_id"] for r in resp.json()["results"]}
    assert "github::Person::wbatst_alice" in wba_ids


async def test_persons_endpoint_matches_by_email_prefix(seeded_es: None) -> None:
    """Searching an email prefix matches the Person with that email."""
    resp = await _get("/api/v1/search/persons", q="alice.wbatst")
    assert resp.status_code == 200

    wba_ids = {r["wba_id"] for r in resp.json()["results"]}
    assert "github::Person::wbatst_alice" in wba_ids


async def test_persons_endpoint_person_without_email_has_null_email(seeded_es: None) -> None:
    """A Person with no email must have email=null in the response, not omitted."""
    resp = await _get("/api/v1/search/persons", q="wbatst_bob", page_size=10)
    assert resp.status_code == 200

    results = resp.json()["results"]
    bob_results = [r for r in results if "wbatst_bob" in r["wba_id"]]
    assert len(bob_results) >= 1

    bob = bob_results[0]
    assert "email" in bob
    assert bob["email"] is None


async def test_persons_endpoint_wba_id_is_canonical_person_format(seeded_es: None) -> None:
    """Every wba_id returned must follow source::Person::id format."""
    resp = await _get("/api/v1/search/persons", q="wbatst", page_size=20)
    assert resp.status_code == 200

    for suggestion in resp.json()["results"]:
        parts = suggestion["wba_id"].split("::")
        assert len(parts) == 3, f"wba_id not in canonical format: {suggestion['wba_id']}"
        assert parts[1] == "Person", f"entity_type must be 'Person', got '{parts[1]}'"


async def test_persons_endpoint_source_field_is_populated(seeded_es: None) -> None:
    """source field must be non-empty for all results."""
    resp = await _get("/api/v1/search/persons", q="wbatst", page_size=20)
    assert resp.status_code == 200

    for suggestion in resp.json()["results"]:
        assert suggestion["source"], f"source is empty for {suggestion['wba_id']}"


# ---------------------------------------------------------------------------
# Minimum character enforcement
# ---------------------------------------------------------------------------


async def test_persons_endpoint_rejects_query_shorter_than_3_chars(seeded_es: None) -> None:
    """q with fewer than 3 characters must return HTTP 422 (FastAPI validation error)."""
    resp = await _get("/api/v1/search/persons", q="ab")
    assert resp.status_code == 422


async def test_persons_endpoint_accepts_exactly_3_chars(seeded_es: None) -> None:
    """q with exactly 3 characters must return HTTP 200."""
    resp = await _get("/api/v1/search/persons", q="ali")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# page_size enforcement
# ---------------------------------------------------------------------------


async def test_persons_endpoint_respects_page_size(seeded_es: None) -> None:
    """page_size limits the number of results returned."""
    resp = await _get("/api/v1/search/persons", q="wbatst", page_size=1)
    assert resp.status_code == 200
    assert len(resp.json()["results"]) <= 1


async def test_persons_endpoint_rejects_page_size_over_20(seeded_es: None) -> None:
    """page_size > 20 must return HTTP 422."""
    resp = await _get("/api/v1/search/persons", q="wbatst", page_size=21)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# No results
# ---------------------------------------------------------------------------


async def test_persons_endpoint_returns_empty_for_no_match(seeded_es: None) -> None:
    """A query with no matches returns 200 with an empty results list."""
    resp = await _get("/api/v1/search/persons", q="xyznonexistentperson999")
    assert resp.status_code == 200
    assert resp.json()["results"] == []

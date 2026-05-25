"""Integration tests for GET /api/v1/search.

Test strategy
-------------
These tests seed Elasticsearch directly using the same ``index_signal()``
function the consumer pipeline uses, bypassing RabbitMQ and Neo4j.  This
avoids three problems with the full-pipeline approach:

* The consumer writes to Neo4j first — test signals would create real
  graph nodes that pollute the database and require coordinated cleanup.
* Consumer processing is asynchronous — a sleep/poll loop would make tests
  timing-dependent and flaky.
* The search API talks only to ES — the consumer pipeline is already covered
  by ``test_consumer_phase5.py``.

Seeded documents use wba_id values prefixed with ``wbatst::`` so they are
trivially identifiable and deleted in teardown without touching any real data.

Run with:
    pytest -m "integration and elasticsearch" tests/test_search_api.py -v
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
    IssueAttributes,
    PersonAttributes,
    PullRequestAttributes,
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
# Test data — all wba_id values use the "wbatst" source prefix so they are
# easy to identify and clean up without touching any real indexed documents.
# ---------------------------------------------------------------------------

_EVENT_TIME = "2026-01-15T10:00:00+00:00"
_SOURCE_CONFIG = "http://wbatst-integration-test"
_CONNECTOR_URL = "http://wbatst-integration-test/connector/1"

# Distinctive token used to verify free-text search without matching real data.
_SEARCH_TOKEN = "wbatst"

_TEST_SIGNALS: list[ActivitySignal] = [
    # --- Jira Issues (5) — used for pagination and key-lookup tests --------
    ActivitySignal(
        source="jira",
        id="WBATST-10001",
        source_config=_SOURCE_CONFIG,
        connector_url=_CONNECTOR_URL,
        event_time=datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        version="1.0",
        attributes=IssueAttributes(
            key="WBATST-10001",
            summary="wbatst alpha issue for integration test",
            priority="High",
            status="Open",
            type="Bug",
            created_at=_EVENT_TIME,
            url="http://wbatst.example.com/WBATST-10001",
        ),
    ),
    ActivitySignal(
        source="jira",
        id="WBATST-10002",
        source_config=_SOURCE_CONFIG,
        connector_url=_CONNECTOR_URL,
        event_time=datetime(2026, 1, 15, 10, 1, 0, tzinfo=timezone.utc),
        version="1.0",
        attributes=IssueAttributes(
            key="WBATST-10002",
            summary="wbatst beta issue for integration test",
            priority="Medium",
            status="In Progress",
            type="Task",
            created_at=_EVENT_TIME,
            url="http://wbatst.example.com/WBATST-10002",
        ),
    ),
    ActivitySignal(
        source="jira",
        id="WBATST-10003",
        source_config=_SOURCE_CONFIG,
        connector_url=_CONNECTOR_URL,
        event_time=datetime(2026, 1, 15, 10, 2, 0, tzinfo=timezone.utc),
        version="1.0",
        attributes=IssueAttributes(
            key="WBATST-10003",
            summary="wbatst gamma issue for integration test",
            priority="Low",
            status="Done",
            type="Story",
            created_at=_EVENT_TIME,
            url="http://wbatst.example.com/WBATST-10003",
        ),
    ),
    ActivitySignal(
        source="jira",
        id="WBATST-10004",
        source_config=_SOURCE_CONFIG,
        connector_url=_CONNECTOR_URL,
        event_time=datetime(2026, 1, 15, 10, 3, 0, tzinfo=timezone.utc),
        version="1.0",
        attributes=IssueAttributes(
            key="WBATST-10004",
            summary="wbatst delta issue for integration test",
            priority="High",
            status="Open",
            type="Bug",
            created_at=_EVENT_TIME,
            url="http://wbatst.example.com/WBATST-10004",
        ),
    ),
    ActivitySignal(
        source="jira",
        id="WBATST-10005",
        source_config=_SOURCE_CONFIG,
        connector_url=_CONNECTOR_URL,
        event_time=datetime(2026, 1, 15, 10, 4, 0, tzinfo=timezone.utc),
        version="1.0",
        attributes=IssueAttributes(
            key="WBATST-10005",
            summary="wbatst epsilon issue for integration test",
            priority="Medium",
            status="In Progress",
            type="Task",
            created_at=_EVENT_TIME,
            url="http://wbatst.example.com/WBATST-10005",
        ),
    ),
    # --- GitHub Person — used for partial login / email match tests --------
    ActivitySignal(
        source="github",
        id="wbatst_devperson",
        source_config=_SOURCE_CONFIG,
        connector_url=_CONNECTOR_URL,
        event_time=datetime(2026, 1, 15, 10, 5, 0, tzinfo=timezone.utc),
        version="1.0",
        attributes=PersonAttributes(
            full_name="Wbatst Dev Person",
            login="wbatst_devperson",
            email="wbatst_devperson@example.com",
            url="http://wbatst.example.com/wbatst_devperson",
        ),
    ),
    # --- GitHub PullRequest — used for source filter and shape tests ------
    ActivitySignal(
        source="github",
        id="wbatst-repo::9001",
        source_config=_SOURCE_CONFIG,
        connector_url=_CONNECTOR_URL,
        event_time=datetime(2026, 1, 15, 10, 6, 0, tzinfo=timezone.utc),
        version="1.0",
        attributes=PullRequestAttributes(
            repo_name="wbatst-repo",
            pull_request_number=9001,
            title="wbatst pull request for integration test",
            state="open",
            created_at=_EVENT_TIME,
            user="wbatst_devperson",
            url="http://wbatst.example.com/wbatst-repo/pull/9001",
        ),
    ),
]

# Pre-computed set of all seeded wba_ids for fixture cleanup.
_SEEDED_WBA_IDS: set[str] = {
    f"{s.source}::{s.entity_type}::{s.id}" for s in _TEST_SIGNALS
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
    """Seed test signals into ES and tear them down after the module."""
    client = _make_es_client()

    for signal in _TEST_SIGNALS:
        index_signal(client, signal)

    # Refresh all managed indexes so documents are immediately searchable.
    client.indices.refresh(index="wba_all")

    yield

    # --- Teardown: delete only the documents we seeded --------------------
    for wba_id in _SEEDED_WBA_IDS:
        parts = wba_id.split("::", 2)
        source, entity_type = parts[0], parts[1]
        index_name = f"{source}_{entity_type.lower()}_index"
        try:
            client.delete(index=index_name, id=wba_id)
        except Exception:
            pass  # already gone or never created — not a teardown failure

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


async def test_basic_search_returns_expected_shape(seeded_es: None) -> None:
    """?q= returns wba_id, score, url, event_time, and highlight in every result."""
    resp = await _get("/api/v1/search", q=_SEARCH_TOKEN, page_size=10)
    assert resp.status_code == 200

    data = resp.json()
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) > 0

    for result in data["results"]:
        assert "wba_id" in result
        assert "score" in result
        # url and event_time are optional but all our test docs have them
        assert result.get("url") is not None
        assert result.get("event_time") is not None


async def test_highlight_present_when_q_matches(seeded_es: None) -> None:
    """Highlight fragment with <em> tags is returned when a query term matches."""
    resp = await _get("/api/v1/search", q=_SEARCH_TOKEN, page_size=10)
    assert resp.status_code == 200

    results = resp.json()["results"]
    assert len(results) > 0

    highlights_with_em = [r for r in results if r.get("highlight") and "<em>" in r["highlight"]]
    assert len(highlights_with_em) > 0, "Expected at least one result with <em> highlight tags"


async def test_full_true_returns_flat_attributes(seeded_es: None) -> None:
    """?full=true includes a flat attributes dict — not a nested ActivitySignal shape."""
    resp = await _get("/api/v1/search", q=_SEARCH_TOKEN, full=True, page_size=5)
    assert resp.status_code == 200

    results = resp.json()["results"]
    assert len(results) > 0

    for result in results:
        attrs = result.get("attributes")
        assert attrs is not None, "Expected attributes dict when full=true"
        assert isinstance(attrs, dict)

        # Must be flat — no nested ActivitySignal sub-objects
        assert "attributes" not in attrs, "attributes must not be nested inside itself"
        assert "relationships" not in attrs, "relationships must be stored as relationship_ids, not nested objects"
        assert "signal_id" not in attrs, "ActivitySignal envelope field signal_id must not appear in attributes"

        # entity_type must be a top-level field in the stored document
        assert "entity_type" in attrs


async def test_full_false_omits_attributes(seeded_es: None) -> None:
    """?full=false (default) must not include the attributes dict."""
    resp = await _get("/api/v1/search", q=_SEARCH_TOKEN, page_size=5)
    assert resp.status_code == 200

    for result in resp.json()["results"]:
        assert "attributes" not in result or result["attributes"] is None


# ---------------------------------------------------------------------------
# wba_id integrity
# ---------------------------------------------------------------------------


async def test_wba_id_matches_canonical_key_pattern(seeded_es: None) -> None:
    """Every wba_id in the response must follow {source}::{entity_type}::{id}."""
    resp = await _get("/api/v1/search", q=_SEARCH_TOKEN, page_size=20)
    assert resp.status_code == 200

    for result in resp.json()["results"]:
        wba_id = result["wba_id"]
        parts = wba_id.split("::")
        assert len(parts) >= 3, f"wba_id '{wba_id}' does not follow source::entity_type::id pattern"


# ---------------------------------------------------------------------------
# Free-text search and partial matching
# ---------------------------------------------------------------------------


async def test_person_partial_login_match(seeded_es: None) -> None:
    """Searching the login prefix matches the full login token via standard analyser."""
    # "wbatst" is a prefix of "wbatst_devperson" — standard analyser tokenises on underscore
    # so "wbatst" is a standalone token and must match.
    resp = await _get("/api/v1/search", q="wbatst", entity_type="Person", page_size=10)
    assert resp.status_code == 200

    wba_ids = {r["wba_id"] for r in resp.json()["results"]}
    assert "github::Person::wbatst_devperson" in wba_ids


async def test_person_email_local_part_match(seeded_es: None) -> None:
    """Searching the local part of an email address matches the Person document."""
    resp = await _get("/api/v1/search", q="wbatst_devperson", entity_type="Person", page_size=10)
    assert resp.status_code == 200

    wba_ids = {r["wba_id"] for r in resp.json()["results"]}
    assert "github::Person::wbatst_devperson" in wba_ids


async def test_jira_key_prefix_matches_issue(seeded_es: None) -> None:
    """Searching the project prefix (WBATST) matches Issues with that key prefix."""
    resp = await _get("/api/v1/search", q="WBATST", entity_type="Issue", page_size=10)
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] >= 5  # all 5 seeded issues have WBATST key prefix


async def test_jira_key_number_token_matches_issue(seeded_es: None) -> None:
    """Searching just the numeric part of a Jira key matches the specific Issue."""
    resp = await _get("/api/v1/search", q="10001", entity_type="Issue", page_size=10)
    assert resp.status_code == 200

    wba_ids = {r["wba_id"] for r in resp.json()["results"]}
    assert "jira::Issue::WBATST-10001" in wba_ids


async def test_jira_full_key_matches_issue(seeded_es: None) -> None:
    """Searching the full Jira key (WBATST-10001) matches the specific Issue."""
    resp = await _get("/api/v1/search", q="WBATST-10001", entity_type="Issue", page_size=10)
    assert resp.status_code == 200

    wba_ids = {r["wba_id"] for r in resp.json()["results"]}
    assert "jira::Issue::WBATST-10001" in wba_ids


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------


async def test_entity_type_filter_scopes_to_correct_index(seeded_es: None) -> None:
    """entity_type filter returns only documents of that type."""
    resp = await _get("/api/v1/search", q=_SEARCH_TOKEN, entity_type="PullRequest", page_size=20)
    assert resp.status_code == 200

    results = resp.json()["results"]
    assert len(results) > 0
    for result in results:
        assert result["wba_id"].split("::")[1] == "PullRequest"


async def test_source_filter_returns_only_that_source(seeded_es: None) -> None:
    """source filter returns only documents from that source."""
    resp = await _get("/api/v1/search", q=_SEARCH_TOKEN, source="github", page_size=20)
    assert resp.status_code == 200

    results = resp.json()["results"]
    assert len(results) > 0
    for result in results:
        assert result["wba_id"].startswith("github::")


async def test_status_filter_narrows_results(seeded_es: None) -> None:
    """status filter returns only Issues with that exact status value."""
    resp = await _get("/api/v1/search", q=_SEARCH_TOKEN, entity_type="Issue", status="Open", page_size=20)
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] >= 1

    # All returned Issues must have status=Open (check via full=true)
    resp_full = await _get(
        "/api/v1/search", q=_SEARCH_TOKEN, entity_type="Issue", status="Open",
        full=True, page_size=20,
    )
    for result in resp_full.json()["results"]:
        if result["wba_id"] in _SEEDED_WBA_IDS:
            assert result["attributes"]["status"] == "Open"


async def test_no_q_returns_all_documents_sorted_by_event_time(seeded_es: None) -> None:
    """Omitting q returns all docs sorted by event_time desc."""
    # Use source_config filter via status=Open to narrow to our seeded docs only.
    # Instead, filter by entity_type=Issue and source=jira and rely on our seeded
    # docs being the only ones with exactly our known wba_ids.
    resp = await _get("/api/v1/search", source="jira", entity_type="Issue", page_size=5)
    assert resp.status_code == 200

    data = resp.json()
    assert data["total"] >= 5  # at minimum our 5 seeded Issues

    # Results should be sorted event_time descending — verify for adjacent pairs.
    times = [r["event_time"] for r in data["results"] if r["event_time"]]
    for i in range(len(times) - 1):
        assert times[i] >= times[i + 1], "Results must be sorted event_time desc when q is absent"


# ---------------------------------------------------------------------------
# Pagination tests
# ---------------------------------------------------------------------------


async def test_pagination_page1_returns_correct_slice(seeded_es: None) -> None:
    """page=1&page_size=2 returns 2 results and correct total."""
    resp = await _get("/api/v1/search", q=_SEARCH_TOKEN, entity_type="Issue", page=1, page_size=2)
    assert resp.status_code == 200

    data = resp.json()
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["results"]) == 2
    assert data["total"] >= 5  # at least our 5 seeded issues


async def test_pagination_page2_returns_different_slice(seeded_es: None) -> None:
    """page=2 returns a different set of results from page=1."""
    resp1 = await _get("/api/v1/search", q=_SEARCH_TOKEN, entity_type="Issue", page=1, page_size=2)
    resp2 = await _get("/api/v1/search", q=_SEARCH_TOKEN, entity_type="Issue", page=2, page_size=2)

    ids_page1 = {r["wba_id"] for r in resp1.json()["results"]}
    ids_page2 = {r["wba_id"] for r in resp2.json()["results"]}

    assert ids_page1.isdisjoint(ids_page2), "page=1 and page=2 must not overlap"


async def test_pagination_beyond_total_returns_empty(seeded_es: None) -> None:
    """A page well beyond the result set returns an empty results list."""
    # With only a small number of seeded Issues, page=500 is definitively beyond
    # the result set while staying within ES's max_result_window (500*20=10000).
    resp = await _get("/api/v1/search", q=_SEARCH_TOKEN, entity_type="Issue", page=500, page_size=20)
    assert resp.status_code == 200

    data = resp.json()
    assert data["results"] == []

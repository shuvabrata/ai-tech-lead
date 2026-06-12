from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from common.activity_signal.models import (
    ActivitySignal,
    BlogpostAttributes,
    PageAttributes,
    PersonAttributes,
    Relationship,
    RelationshipTarget,
    SpaceAttributes,
)
from connectors.commons.person_cache import PersonCache
from connectors.consumers.sinks.neo4j_sink import upsert_signal


pytestmark = pytest.mark.unit

_EVENT_TIME = datetime(2026, 5, 31, 12, 0, 0, tzinfo=timezone.utc)
_INGESTION_TIME = datetime(2026, 5, 31, 12, 5, 0, tzinfo=timezone.utc)


def _signal(source: str, attrs, *, relationships=None, signal_id: str) -> ActivitySignal:
    return ActivitySignal(
        source=source,
        id=signal_id,
        source_config="https://example.atlassian.net",
        connector_url="https://example.atlassian.net/connectors/confluence",
        event_time=_EVENT_TIME,
        version="1.0",
        attributes=attrs,
        relationships=relationships or [],
        ingestion_time=_INGESTION_TIME,
    )


def test_upsert_space_signal_calls_merge_space() -> None:
    session = MagicMock()
    signal = _signal(
        "confluence",
        SpaceAttributes(
            key="ENG",
            name="Engineering",
            type="global",
            url="https://example.atlassian.net/wiki/spaces/ENG",
        ),
        signal_id="ENG",
    )

    with patch("connectors.consumers.sinks.neo4j_sink.merge_space") as mock_merge:
        canonical_id = upsert_signal(session, signal)

    assert canonical_id == "confluence::Space::ENG"
    mock_merge.assert_called_once()
    space = mock_merge.call_args.args[1]
    assert space.id == "confluence::Space::ENG"
    assert space.key == "ENG"
    assert space.name == "Engineering"
    assert space._last_synced_at == _INGESTION_TIME.isoformat()


def test_upsert_page_signal_converts_relationships() -> None:
    session = MagicMock()

    def run_side_effect(query: str, **_kwargs):
        if "WHERE p.email = $email" in query:
            return _SingleResult(None)
        if "WHERE n.url = $url" in query:
            return _SingleResult(None)
        if "WHERE im.id IN $identity_ids" in query:
            return _SingleResult(None)
        if "WHERE p.id IN $person_ids" in query:
            return _SingleResult(None)
        raise AssertionError(f"Unexpected query: {query}")

    session.run.side_effect = run_side_effect

    signal = _signal(
        "confluence",
        PageAttributes(
            title="Design Notes",
            created_at="2026-05-01T10:00:00Z",
            last_updated_at="2026-05-31T10:00:00Z",
            url="https://example.atlassian.net/wiki/pages/2001",
            version=3,
            status="current",
        ),
        signal_id="2001",
        relationships=[
            Relationship(
                type="CREATED",
                direction="IN",
                target=RelationshipTarget(
                    source="confluence",
                    entity_type="Person",
                    id="acc123",
                ),
            ),
            Relationship(
                type="IN_SPACE",
                target=RelationshipTarget(
                    source="confluence",
                    entity_type="Space",
                    id="ENG",
                ),
            ),
        ],
    )

    with patch("connectors.consumers.sinks.neo4j_sink.merge_page") as mock_merge:
        canonical_id = upsert_signal(session, signal)

    assert canonical_id == "confluence::Page::2001"
    mock_merge.assert_called_once()
    page = mock_merge.call_args.args[1]
    rels = mock_merge.call_args.kwargs["relationships"]

    assert page.id == "confluence::Page::2001"
    assert page.title == "Design Notes"
    assert page._last_synced_at == _INGESTION_TIME.isoformat()
    assert len(rels) == 2
    assert {rel.type for rel in rels} == {"CREATED", "IN_SPACE"}

    created_rel = next(rel for rel in rels if rel.type == "CREATED")
    assert created_rel.from_type == "Person"
    assert created_rel.to_type == "Page"
    assert created_rel.from_id == "confluence::Person::acc123"
    assert created_rel.to_id == "confluence::Page::2001"

    in_space_rel = next(rel for rel in rels if rel.type == "IN_SPACE")
    assert in_space_rel.from_type == "Page"
    assert in_space_rel.to_type == "Space"
    assert in_space_rel.from_id == "confluence::Page::2001"
    assert in_space_rel.to_id == "confluence::Space::ENG"


def test_upsert_blogpost_signal_calls_merge_blogpost() -> None:
    session = MagicMock()
    signal = _signal(
        "confluence",
        BlogpostAttributes(
            title="Weekly Update",
            created_at="2026-05-30T08:00:00Z",
            last_updated_at="2026-05-31T08:00:00Z",
            url="https://example.atlassian.net/wiki/blogposts/3001",
            version=2,
            status="current",
        ),
        signal_id="3001",
    )

    with patch("connectors.consumers.sinks.neo4j_sink.merge_blogpost") as mock_merge:
        canonical_id = upsert_signal(session, signal)

    assert canonical_id == "confluence::Blogpost::3001"
    mock_merge.assert_called_once()
    blogpost = mock_merge.call_args.args[1]
    assert blogpost.id == "confluence::Blogpost::3001"
    assert blogpost.title == "Weekly Update"
    assert blogpost._last_synced_at == _INGESTION_TIME.isoformat()


def test_upsert_person_signal_uses_merge_person() -> None:
    session = MagicMock()
    signal = _signal(
        "confluence",
        PersonAttributes(
            full_name="Alice Dev",
            email="alice@example.com",
            account_id="acc123",
        ),
        signal_id="acc123",
    )

    with patch("connectors.consumers.sinks.neo4j_sink.merge_person") as mock_merge:
        canonical_id = upsert_signal(session, signal)

    assert canonical_id == "confluence::Person::acc123"
    mock_merge.assert_called_once()
    person = mock_merge.call_args.args[1]
    assert person.id == "confluence::Person::acc123"
    assert person.name == "Alice Dev"
    assert person.email == "alice@example.com"


class _SingleResult:
    def __init__(self, row):
        self._row = row

    def single(self):
        return self._row


def test_upsert_person_signal_with_person_cache_queues_confluence_identity_mapping() -> None:
    session = MagicMock()
    signal = _signal(
        "confluence",
        PersonAttributes(
            full_name="Alice Dev",
            email="Alice@Example.com",
            account_id="acc123",
        ),
        signal_id="acc123",
    )
    person_cache = PersonCache()

    def run_side_effect(query: str, **_kwargs):
        if "WHERE p.email = $email" in query:
            return _SingleResult(None)
        if "WHERE im.id IN $identity_ids" in query:
            return _SingleResult(None)
        if "WHERE p.id IN $person_ids" in query:
            return _SingleResult(None)
        if "MATCH (p:Person {id: $pid})" in query:
            return _SingleResult(None)
        raise AssertionError(f"Unexpected query: {query}")

    session.run.side_effect = run_side_effect

    with patch("connectors.commons.person_cache.merge_person") as mock_merge_person, patch(
        "connectors.commons.person_cache.merge_identity_mapping"
    ) as mock_merge_identity_mapping:
        canonical_id = upsert_signal(session, signal, person_cache=person_cache)

    assert canonical_id == "confluence::Person::acc123"
    mock_merge_person.assert_called_once()
    person = mock_merge_person.call_args.args[1]
    assert person.id == "confluence::Person::acc123"
    assert person.email == "alice@example.com"

    mock_merge_identity_mapping.assert_called_once()
    identity = mock_merge_identity_mapping.call_args.args[1]
    relationship = mock_merge_identity_mapping.call_args.kwargs["relationships"][0]
    assert identity.id == "confluence::IdentityMapping::acc123"
    assert identity.provider == "Confluence"
    assert identity.email == "alice@example.com"
    assert relationship.to_id == "confluence::Person::acc123"


def test_upsert_person_signal_with_person_cache_reuses_existing_jira_person_by_account_id() -> None:
    session = MagicMock()
    signal = _signal(
        "confluence",
        PersonAttributes(
            full_name="Alice Dev",
            email=None,
            account_id="acc123",
        ),
        signal_id="acc123",
    )
    person_cache = PersonCache()

    def run_side_effect(query: str, **_kwargs):
        if "WHERE im.id IN $identity_ids" in query:
            return _SingleResult({"id": "jira::Person::acc123"})
        raise AssertionError(f"Unexpected query: {query}")

    session.run.side_effect = run_side_effect

    with patch("connectors.commons.person_cache.merge_person") as mock_merge_person, patch(
        "connectors.commons.person_cache.merge_identity_mapping"
    ) as mock_merge_identity_mapping, patch(
        "connectors.consumers.sinks.neo4j_sink._rehome_person_stub"
    ) as mock_rehome_person_stub:
        canonical_id = upsert_signal(session, signal, person_cache=person_cache)

    assert canonical_id == "jira::Person::acc123"
    mock_rehome_person_stub.assert_called_once_with(
        session,
        "confluence::Person::acc123",
        "jira::Person::acc123",
    )
    mock_merge_person.assert_called_once()
    person = mock_merge_person.call_args.args[1]
    assert person.id == "jira::Person::acc123"
    assert person.name == "Alice Dev"

    mock_merge_identity_mapping.assert_called_once()
    relationship = mock_merge_identity_mapping.call_args.kwargs["relationships"][0]
    assert relationship.to_id == "jira::Person::acc123"


class _DataResult:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return self._rows


def test_rehome_person_stub_moves_relationships_and_deletes_stale_node() -> None:
    from connectors.consumers.sinks.neo4j_sink import _rehome_person_stub

    session = MagicMock()

    def run_side_effect(query: str, **_kwargs):
        if "MATCH (stale:Person {id: $stale_id})-[r]->(other)" in query:
            return _DataResult(
                [
                    {
                        "rel_type": "CREATED",
                        "other_labels": ["Page"],
                        "other_id": "confluence::Page::123",
                        "props": {},
                    }
                ]
            )
        if "MATCH (other)-[r]->(stale:Person {id: $stale_id})" in query:
            return _DataResult(
                [
                    {
                        "rel_type": "MAPS_TO",
                        "other_labels": ["IdentityMapping"],
                        "other_id": "confluence::IdentityMapping::acc123",
                        "props": {},
                    }
                ]
            )
        return MagicMock()

    session.run.side_effect = run_side_effect

    with patch("connectors.consumers.sinks.neo4j_sink.merge_relationship") as mock_merge_relationship:
        _rehome_person_stub(session, "confluence::Person::acc123", "jira::Person::acc123")

    assert mock_merge_relationship.call_count == 2
    outgoing_rel = mock_merge_relationship.call_args_list[0].args[1]
    incoming_rel = mock_merge_relationship.call_args_list[1].args[1]
    assert outgoing_rel.from_id == "jira::Person::acc123"
    assert outgoing_rel.to_id == "confluence::Page::123"
    assert incoming_rel.from_id == "confluence::IdentityMapping::acc123"
    assert incoming_rel.to_id == "jira::Person::acc123"

    delete_call = session.run.call_args_list[-1]
    assert delete_call.args[0] == "MATCH (stale:Person {id: $stale_id}) DETACH DELETE stale"
    assert delete_call.kwargs["stale_id"] == "confluence::Person::acc123"

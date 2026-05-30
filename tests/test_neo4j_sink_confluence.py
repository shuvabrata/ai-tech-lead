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

"""Unit tests for connectors/consumers/sinks/elasticsearch_sink.py.

Verifies:
- _build_document produces a flat dict with all envelope fields at top level
- relationship_ids is a plain list of WBA canonical key strings
- index_signal calls client.index() with the correct index name, _id, and document
- index_signal_with_canonical_id routes to client.index() (no dedup) or
  client.update() (cross-provider Person dedup)
- build_es_client() returns None when ELASTICSEARCH_ENABLED is falsy

Run with:
    pytest -m unit tests/test_elasticsearch_sink.py -v
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from common.activity_signal.models import (
    ActivitySignal,
    IssueAttributes,
    PersonAttributes,
    Relationship,
    RelationshipTarget,
)
from connectors.consumers.sinks.elasticsearch_sink import (
    _build_document,
    build_es_client,
    index_signal,
    index_signal_with_canonical_id,
)

pytestmark = [pytest.mark.unit]

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_EVENT_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _issue_signal(*, relationships: list | None = None) -> ActivitySignal:
    return ActivitySignal(
        source="jira",
        id="PROJ-1",
        source_config="https://test.atlassian.net",
        connector_url="https://test.atlassian.net/connector",
        event_time=_EVENT_TIME,
        version="1.0",
        attributes=IssueAttributes(
            key="PROJ-1",
            summary="Test issue",
            priority="High",
            status="Open",
            type="Story",
            created_at="2026-01-01T00:00:00Z",
        ),
        relationships=relationships or [],
    )


def _person_signal() -> ActivitySignal:
    return ActivitySignal(
        source="jira",
        id="jira-user-99",
        source_config="https://test.atlassian.net",
        connector_url="https://test.atlassian.net/connector",
        event_time=_EVENT_TIME,
        version="1.0",
        attributes=PersonAttributes(full_name="Alice"),
    )


# ---------------------------------------------------------------------------
# _build_document — envelope fields
# ---------------------------------------------------------------------------


def test_build_document_contains_wba_id() -> None:
    doc = _build_document(_issue_signal())
    assert doc["wba_id"] == "jira::Issue::PROJ-1"


def test_build_document_contains_source() -> None:
    doc = _build_document(_issue_signal())
    assert doc["source"] == "jira"


def test_build_document_contains_entity_type() -> None:
    doc = _build_document(_issue_signal())
    assert doc["entity_type"] == "Issue"


def test_build_document_contains_source_config() -> None:
    doc = _build_document(_issue_signal())
    assert doc["source_config"] == "https://test.atlassian.net"


def test_build_document_contains_event_time() -> None:
    doc = _build_document(_issue_signal())
    assert doc["event_time"] == _EVENT_TIME.isoformat()


# ---------------------------------------------------------------------------
# _build_document — flat attribute fields (no nesting)
# ---------------------------------------------------------------------------


def test_build_document_attribute_fields_appear_at_top_level() -> None:
    doc = _build_document(_issue_signal())
    # IssueAttributes fields must be flattened into the root document
    assert "key" in doc
    assert doc["key"] == "PROJ-1"
    assert "summary" in doc
    assert doc["summary"] == "Test issue"


def test_build_document_has_no_nested_attributes_key() -> None:
    """The raw 'attributes' sub-object must not appear in the document."""
    doc = _build_document(_issue_signal())
    assert "attributes" not in doc


def test_build_document_values_are_not_nested_dicts() -> None:
    """Every scalar value must be a primitive/list — no embedded dicts from sub-models."""
    doc = _build_document(_issue_signal())
    for key, value in doc.items():
        if key == "relationship_ids":
            continue  # list[str] is expected
        assert not isinstance(value, dict), (
            f"Field '{key}' is a nested dict — document shape must be fully flat"
        )


# ---------------------------------------------------------------------------
# _build_document — relationship_ids
# ---------------------------------------------------------------------------


def test_build_document_relationship_ids_empty_when_no_relationships() -> None:
    doc = _build_document(_issue_signal())
    assert doc["relationship_ids"] == []


def test_build_document_relationship_ids_are_wba_key_strings() -> None:
    rel = Relationship(
        type="ASSIGNED_TO",
        target=RelationshipTarget(
            source="github",
            entity_type="Person",
            id="alice",
        ),
    )
    doc = _build_document(_issue_signal(relationships=[rel]))
    assert doc["relationship_ids"] == ["github::Person::alice"]
    assert all(isinstance(r, str) for r in doc["relationship_ids"])


def test_build_document_relationship_ids_multiple_relationships() -> None:
    rels = [
        Relationship(
            type="ASSIGNED_TO",
            target=RelationshipTarget(source="github", entity_type="Person", id="alice"),
        ),
        Relationship(
            type="BELONGS_TO",
            target=RelationshipTarget(source="jira", entity_type="Project", id="MYPROJ"),
        ),
    ]
    doc = _build_document(_issue_signal(relationships=rels))
    assert len(doc["relationship_ids"]) == 2
    assert "github::Person::alice" in doc["relationship_ids"]
    assert "jira::Project::MYPROJ" in doc["relationship_ids"]


# ---------------------------------------------------------------------------
# index_signal — client.index() call contract
# ---------------------------------------------------------------------------


def test_index_signal_calls_client_index_once() -> None:
    client = MagicMock()
    index_signal(client, _issue_signal())
    client.index.assert_called_once()


def test_index_signal_uses_correct_index_name() -> None:
    client = MagicMock()
    index_signal(client, _issue_signal())
    call_kwargs = client.index.call_args.kwargs
    assert call_kwargs["index"] == "jira_issue_index"


def test_index_signal_uses_wba_id_as_document_id() -> None:
    client = MagicMock()
    index_signal(client, _issue_signal())
    call_kwargs = client.index.call_args.kwargs
    assert call_kwargs["id"] == "jira::Issue::PROJ-1"


def test_index_signal_document_matches_build_document() -> None:
    client = MagicMock()
    signal = _issue_signal()
    index_signal(client, signal)
    call_kwargs = client.index.call_args.kwargs
    expected = _build_document(signal)
    assert call_kwargs["document"] == expected


def test_index_signal_propagates_exceptions() -> None:
    """index_signal() has no internal try/except — exceptions propagate to the caller.

    The consumer (main.py) is responsible for catching ES failures non-fatally.
    """
    client = MagicMock()
    client.index.side_effect = RuntimeError("ES unavailable")
    with pytest.raises(RuntimeError, match="ES unavailable"):
        index_signal(client, _issue_signal())


# ---------------------------------------------------------------------------
# index_signal_with_canonical_id — dispatch logic
# ---------------------------------------------------------------------------


def test_index_signal_with_canonical_id_no_dedup_calls_client_index() -> None:
    """When canonical_wba_id == signal wba_id, route to client.index()."""
    client = MagicMock()
    signal = _issue_signal()
    index_signal_with_canonical_id(client, signal, "jira::Issue::PROJ-1")

    client.index.assert_called_once()
    client.update.assert_not_called()


def test_index_signal_with_canonical_id_dedup_calls_client_update() -> None:
    """When canonical_wba_id differs from signal wba_id, route to client.update()."""
    client = MagicMock()
    signal = _person_signal()
    # Simulate: Jira person merged into existing GitHub Person node
    index_signal_with_canonical_id(client, signal, "github::Person::alice")

    client.update.assert_called_once()
    client.index.assert_not_called()


def test_index_signal_with_canonical_id_dedup_update_targets_canonical_index() -> None:
    client = MagicMock()
    signal = _person_signal()
    index_signal_with_canonical_id(client, signal, "github::Person::alice")

    call_kwargs = client.update.call_args.kwargs
    assert call_kwargs["index"] == "github_person_index"
    assert call_kwargs["id"] == "github::Person::alice"


# ---------------------------------------------------------------------------
# build_es_client — disabled when ELASTICSEARCH_ENABLED is falsy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("env_value", ["false", "0", "no", ""])
def test_build_es_client_returns_none_when_disabled(env_value: str) -> None:
    with patch.dict(os.environ, {"ELASTICSEARCH_ENABLED": env_value}):
        result = build_es_client()
    assert result is None


def test_build_es_client_returns_none_when_env_var_absent() -> None:
    env_without_es = {k: v for k, v in os.environ.items() if k != "ELASTICSEARCH_ENABLED"}
    with patch.dict(os.environ, env_without_es, clear=True):
        result = build_es_client()
    assert result is None

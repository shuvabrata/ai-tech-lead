"""Unit tests for the Phase 5 Neo4j consumer (neo4j_sink + main).

Tests cover:
- ``upsert_signal`` generates correct Cypher for each entity type.
- Idempotency guard: older event_time → property SET is skipped.
- Stub nodes created for relationship targets.
- All three direction semantics: None, OUT, IN.
- Relationship MERGE skipped when target has no external_id.
- ``main.consume_queue`` acks on success, nacks on Neo4j error.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from common.activity_signal.models import (
    ActivitySignal,
    BranchAttributes,
    CommitAttributes,
    IssueAttributes,
    PullRequestAttributes,
    Relationship,
    RelationshipTarget,
    RepositoryAttributes,
)
from connectors.consumers.sinks.neo4j_sink import _label, upsert_signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc)


def _make_signal(
    entity_type: str = "Repository",
    external_id: str = "repo_1",
    source: str = "github",
    relationships: list[Relationship] | None = None,
    event_time: datetime = _NOW,
) -> ActivitySignal:
    """Build a minimal but valid ActivitySignal for the given entity_type."""
    attrs_map = {
        "Repository": RepositoryAttributes(
            id=external_id,
            full_name="org/repo",
            name="repo",
            created_at="2023-01-01",
            updated_at="2024-01-01",
            url="https://github.com/org/repo",
        ),
        "Branch": BranchAttributes(
            name="main",
            commit_sha="abc123",
        ),
        "Commit": CommitAttributes(
            sha="abc123",
            message="fix: bug",
            author="Alice",
            committed_date="2026-05-01T10:00:00",
        ),
        "PullRequest": PullRequestAttributes(
            id="pr_1",
            number=42,
            title="Feature X",
            state="open",
            created_at="2026-05-01T10:00:00",
            user="alice",
        ),
        "Issue": IssueAttributes(
            id="issue_1",
            key="PROJ-1",
            summary="Bug fix",
            priority="High",
            status="Open",
            issue_type="Bug",
            created="2026-05-01",
        ),
    }
    attrs = attrs_map.get(entity_type, attrs_map["Repository"])

    return ActivitySignal(
        source=source,
        external_id=external_id,
        source_config="https://github.com",
        connector_url="http://localhost:8000/connectors/github",
        event_time=event_time,
        ingestion_time=_NOW,
        version="1.0",
        attributes=attrs,
        relationships=relationships or [],
    )


def _mock_session() -> MagicMock:
    """Return a mock Neo4j Session."""
    session = MagicMock()
    session.run = MagicMock()
    return session


# ---------------------------------------------------------------------------
# Label mapping
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "entity_type,expected",
    [
        ("Repository", "Repository"),
        ("PullRequest", "PullRequest"),
        ("Person", "Person"),
        ("Issue", "Issue"),
        ("UnknownType", "UnknownType"),  # falls back to entity_type itself
    ],
)
def test_label_mapping(entity_type: str, expected: str) -> None:
    assert _label(entity_type) == expected


# ---------------------------------------------------------------------------
# upsert_signal — node MERGE
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_signal_runs_merge_query() -> None:
    """upsert_signal calls session.run at least once with a MERGE query."""
    session = _mock_session()
    signal = _make_signal()

    upsert_signal(session, signal)

    assert session.run.called
    first_call_query: str = session.run.call_args_list[0].args[0]
    assert "MERGE" in first_call_query
    assert "Repository" in first_call_query


@pytest.mark.unit
def test_upsert_signal_uses_external_id_as_id() -> None:
    """The MERGE uses external_id as the ``id`` property."""
    session = _mock_session()
    signal = _make_signal(external_id="repo_xyz")

    upsert_signal(session, signal)

    # First run call is the node MERGE; node_id param should be "repo_xyz"
    params = session.run.call_args_list[0].kwargs
    assert params.get("node_id") == "repo_xyz"


@pytest.mark.unit
def test_upsert_signal_sets_idempotency_meta() -> None:
    """_last_signal_id and _last_event_time are always written."""
    session = _mock_session()
    signal = _make_signal()

    upsert_signal(session, signal)

    first_query: str = session.run.call_args_list[0].args[0]
    assert "_last_signal_id" in first_query
    assert "_last_event_time" in first_query


@pytest.mark.unit
def test_upsert_signal_idempotency_guard_in_query() -> None:
    """The conditional SET clause guards on _last_event_time."""
    session = _mock_session()
    signal = _make_signal()

    upsert_signal(session, signal)

    first_query: str = session.run.call_args_list[0].args[0]
    assert "_last_event_time < $event_time" in first_query


@pytest.mark.unit
def test_upsert_signal_sets_stub_false_on_create() -> None:
    """ON CREATE SET n._stub = false so new nodes are not marked as stubs."""
    session = _mock_session()
    signal = _make_signal()

    upsert_signal(session, signal)

    first_query: str = session.run.call_args_list[0].args[0]
    assert "_stub = false" in first_query


# ---------------------------------------------------------------------------
# upsert_signal — relationships
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_signal_creates_stub_for_target() -> None:
    """A MERGE stub query is run for each relationship target."""
    session = _mock_session()
    rel = Relationship(
        type="AUTHORED_BY",
        direction=None,
        target=RelationshipTarget(
            source="github",
            entity_type="Person",
            external_id="person_github_alice",
        ),
    )
    signal = _make_signal(entity_type="Commit", external_id="commit_1", relationships=[rel])

    upsert_signal(session, signal)

    # Calls: 1 node MERGE + 1 stub MERGE + 1 rel MERGE = 3 total
    assert session.run.call_count == 3
    stub_query: str = session.run.call_args_list[1].args[0]
    assert "_stub = true" in stub_query
    assert "Person" in stub_query


@pytest.mark.unit
def test_upsert_signal_direction_none_produces_forward_edge() -> None:
    """direction=None stores (from)-[:REL]->(to) by convention."""
    session = _mock_session()
    rel = Relationship(
        type="PART_OF",
        direction=None,
        target=RelationshipTarget(
            source="github",
            entity_type="Branch",
            external_id="branch_main",
        ),
    )
    signal = _make_signal(entity_type="Commit", external_id="commit_1", relationships=[rel])

    upsert_signal(session, signal)

    rel_query: str = session.run.call_args_list[2].args[0]
    assert "(from)-[:PART_OF]->(to)" in rel_query


@pytest.mark.unit
def test_upsert_signal_direction_out_produces_forward_edge() -> None:
    """direction='OUT' stores (from)-[:REL]->(to)."""
    session = _mock_session()
    rel = Relationship(
        type="MERGED_INTO",
        direction="OUT",
        target=RelationshipTarget(
            source="github",
            entity_type="Branch",
            external_id="branch_main",
        ),
    )
    signal = _make_signal(entity_type="PullRequest", external_id="pr_1", relationships=[rel])

    upsert_signal(session, signal)

    rel_query: str = session.run.call_args_list[2].args[0]
    assert "(from)-[:MERGED_INTO]->(to)" in rel_query


@pytest.mark.unit
def test_upsert_signal_direction_in_produces_reverse_edge() -> None:
    """direction='IN' stores (to)-[:REL]->(from)."""
    session = _mock_session()
    rel = Relationship(
        type="REVIEWS",
        direction="IN",
        target=RelationshipTarget(
            source="github",
            entity_type="Person",
            external_id="person_github_alice",
        ),
    )
    signal = _make_signal(entity_type="PullRequest", external_id="pr_1", relationships=[rel])

    upsert_signal(session, signal)

    rel_query: str = session.run.call_args_list[2].args[0]
    assert "(to)-[:REVIEWS]->(from)" in rel_query


@pytest.mark.unit
def test_upsert_signal_skips_relationship_with_no_external_id() -> None:
    """Relationships where target.external_id is None are skipped (no run call)."""
    session = _mock_session()
    rel = Relationship(
        type="PART_OF",
        direction=None,
        target=RelationshipTarget(source="github", entity_type="Branch"),
    )
    signal = _make_signal(entity_type="Commit", external_id="commit_1", relationships=[rel])

    upsert_signal(session, signal)

    # Only 1 call — the node MERGE; no stub or rel MERGE
    assert session.run.call_count == 1


@pytest.mark.unit
def test_upsert_signal_multiple_relationships() -> None:
    """Multiple relationships each produce a stub + rel MERGE pair."""
    session = _mock_session()
    rels = [
        Relationship(
            type="AUTHORED_BY",
            direction=None,
            target=RelationshipTarget(
                source="github",
                entity_type="Person",
                external_id="person_github_alice",
            ),
        ),
        Relationship(
            type="PART_OF",
            direction=None,
            target=RelationshipTarget(
                source="github",
                entity_type="Branch",
                external_id="branch_main",
            ),
        ),
    ]
    signal = _make_signal(entity_type="Commit", external_id="commit_1", relationships=rels)

    upsert_signal(session, signal)

    # 1 node MERGE + (1 stub + 1 rel) × 2 rels = 5 calls
    assert session.run.call_count == 5


# ---------------------------------------------------------------------------
# consume_queue — ack / nack behaviour
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_consume_queue_acks_on_success() -> None:
    """consume_queue acks the message when upsert_signal succeeds."""
    from connectors.consumers.main import consume_queue

    signal = _make_signal()
    mock_message = AsyncMock()

    with (
        patch(
            "connectors.consumers.main.RabbitMQConsumer"
        ) as MockConsumer,
        patch(
            "connectors.consumers.main.GraphDatabase"
        ) as MockDriver,
        patch(
            "connectors.consumers.main.upsert_signal"
        ) as mock_upsert,
    ):
        # Make the async generator yield exactly one (signal, message) pair.
        async def _gen():
            yield signal, mock_message

        mock_consumer_instance = MagicMock()
        mock_consumer_instance.consume.return_value = _gen()
        MockConsumer.return_value = mock_consumer_instance

        mock_session = MagicMock().__enter__.return_value = MagicMock()
        MockDriver.driver.return_value.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        MockDriver.driver.return_value.session.return_value.__exit__ = MagicMock(return_value=False)

        await consume_queue(
            queue_name="github_repository_queue",
            rabbitmq_url="amqp://guest:guest@localhost:5672/",
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
        )

    mock_message.ack.assert_awaited_once()
    mock_message.nack.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_consume_queue_nacks_on_upsert_failure() -> None:
    """consume_queue nacks with requeue=False when upsert_signal raises."""
    from connectors.consumers.main import consume_queue

    signal = _make_signal()
    mock_message = AsyncMock()

    with (
        patch(
            "connectors.consumers.main.RabbitMQConsumer"
        ) as MockConsumer,
        patch(
            "connectors.consumers.main.GraphDatabase"
        ) as MockDriver,
        patch(
            "connectors.consumers.main.upsert_signal",
            side_effect=RuntimeError("Neo4j unavailable"),
        ),
    ):
        async def _gen():
            yield signal, mock_message

        mock_consumer_instance = MagicMock()
        mock_consumer_instance.consume.return_value = _gen()
        MockConsumer.return_value = mock_consumer_instance

        MockDriver.driver.return_value.session.return_value.__enter__ = MagicMock(return_value=MagicMock())
        MockDriver.driver.return_value.session.return_value.__exit__ = MagicMock(return_value=False)

        await consume_queue(
            queue_name="github_repository_queue",
            rabbitmq_url="amqp://guest:guest@localhost:5672/",
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
        )

    mock_message.nack.assert_awaited_once_with(requeue=False)
    mock_message.ack.assert_not_called()

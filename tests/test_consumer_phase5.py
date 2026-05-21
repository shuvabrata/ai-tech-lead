"""Unit tests for the Neo4j consumer sink (neo4j_sink) and consume_queue.

Tests verify that upsert_signal dispatches to the correct merge_* function
with the correctly constructed neo4j_db dataclass, mirroring the logic in the
original sync modules (modules/github/, modules/jira/).

Key behaviours tested:
- Each entity_type calls the right merge_* function.
- Signal attributes are mapped to dataclass fields (including Phase-B aliases).
- Relationships from the signal are converted and passed to merge_*.
- Direction=IN swaps from/to on the DbRelationship.
- Targets without identifier are skipped.
- Unknown entity_type is logged and skipped (no merge call).
- consume_queue acks on success, nacks on failure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from common.activity_signal.models import (
    ActivitySignal,
    BranchAttributes,
    CommitAttributes,
    EpicAttributes,
    InitiativeAttributes,
    IssueAttributes,
    PersonAttributes,
    ProjectAttributes,
    PullRequestAttributes,
    Relationship,
    RelationshipTarget,
    RepositoryAttributes,
    SprintAttributes,
    TeamAttributes,
)
from connectors.commons.person_cache import PersonCache
from connectors.consumers.sinks.neo4j_sink import _label, _to_db_relationships, upsert_signal
from connectors.neo4j_db.models import Relationship as DbRelationship


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 10, 12, 0, 0, tzinfo=timezone.utc)
_SOURCE = "github"
_CONFIG = "https://github.com"
_CONNECTOR_URL = "http://localhost:8000/connectors/github"


def _make_signal(
    attributes: object,
    source: str = _SOURCE,
    id: str = "node_1",
    relationships: list[Relationship] | None = None,
) -> ActivitySignal:
    return ActivitySignal(
        source=source,
        id=id,
        source_config=_CONFIG,
        connector_url=_CONNECTOR_URL,
        event_time=_NOW,
        ingestion_time=_NOW,
        version="1.0",
        attributes=attributes,
        relationships=relationships or [],
    )


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.run = MagicMock()
    return session


# ---------------------------------------------------------------------------
# _label
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "entity_type",
    [
        "Repository",
        "Branch",
        "Commit",
        "PullRequest",
        "Person",
        "Team",
        "Project",
        "Initiative",
        "Epic",
        "Sprint",
        "Issue",
        "UnknownType",
    ],
)
def test_label_returns_entity_type_unchanged(entity_type: str) -> None:
    assert _label(entity_type) == entity_type


# ---------------------------------------------------------------------------
# _to_db_relationships
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_to_db_relationships_direction_none_is_forward() -> None:
    mock_session = MagicMock()
    mock_session.run.return_value.single.return_value = None
    rel = Relationship(
        type="PART_OF",
        direction=None,
        target=RelationshipTarget(source="github", entity_type="Repository", id="repo_1"),
    )
    result = _to_db_relationships(mock_session, [rel], "branch_1", "Branch")
    assert len(result) == 1
    db_rel = result[0]
    assert db_rel.from_id == "branch_1"
    assert db_rel.to_id == "github::Repository::repo_1"
    assert db_rel.from_type == "Branch"
    assert db_rel.to_type == "Repository"
    assert db_rel.type == "PART_OF"


@pytest.mark.unit
def test_to_db_relationships_direction_out_is_forward() -> None:
    mock_session = MagicMock()
    mock_session.run.return_value.single.return_value = None
    rel = Relationship(
        type="MERGED_INTO",
        direction="OUT",
        target=RelationshipTarget(source="github", entity_type="Branch", id="branch_main"),
    )
    result = _to_db_relationships(mock_session, [rel], "pr_1", "PullRequest")
    assert result[0].from_id == "pr_1"
    assert result[0].to_id == "github::Branch::branch_main"


@pytest.mark.unit
def test_to_db_relationships_direction_in_swaps_from_to() -> None:
    mock_session = MagicMock()
    mock_session.run.return_value.single.return_value = None
    rel = Relationship(
        type="REVIEWS",
        direction="IN",
        target=RelationshipTarget(source="github", entity_type="Person", id="bob"),
    )
    result = _to_db_relationships(mock_session, [rel], "pr_1", "PullRequest")
    assert len(result) == 1
    db_rel = result[0]
    # "IN" means target-[:REL]->source, so from_id is the target
    assert db_rel.from_id == "github::Person::bob"
    assert db_rel.to_id == "pr_1"
    assert db_rel.from_type == "Person"
    assert db_rel.to_type == "PullRequest"


@pytest.mark.unit
def test_to_db_relationships_no_identifier_skipped() -> None:
    mock_session = MagicMock()
    rel = Relationship(
        type="PART_OF",
        direction=None,
        target=RelationshipTarget(entity_type="Repository"),  # no identifier at all
    )
    result = _to_db_relationships(mock_session, [rel], "branch_1", "Branch")
    assert result == []


@pytest.mark.unit
def test_to_db_relationships_multiple() -> None:
    mock_session = MagicMock()
    mock_session.run.return_value.single.return_value = None
    rels = [
        Relationship(
            type="AUTHORED_BY",
            direction=None,
            target=RelationshipTarget(source="github", entity_type="Person", id="alice"),
        ),
        Relationship(
            type="PART_OF",
            direction=None,
            target=RelationshipTarget(source="github", entity_type="Branch", id="branch_main"),
        ),
    ]
    result = _to_db_relationships(mock_session, rels, "commit_1", "Commit")
    assert len(result) == 2
    types = {r.type for r in result}
    assert types == {"AUTHORED_BY", "PART_OF"}


# ---------------------------------------------------------------------------
# upsert_signal — Repository
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_repository_calls_merge_repository() -> None:
    attrs = RepositoryAttributes(
        name="repo",
        created_at="2023-01-01",
        updated_at="2024-01-01",
        url="https://github.com/org/repo",
        language="Python",
        is_private=True,
        topics=["api", "python"],
    )
    signal = _make_signal(attrs, id="org/repo")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_repository") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    repo_arg = mock_merge.call_args.args[1]
    assert repo_arg.id == "github::Repository::org/repo"
    assert repo_arg.name == "org/repo"
    assert repo_arg.language == "Python"
    assert repo_arg.is_private is True
    assert repo_arg.topics == ["api", "python"]
    assert repo_arg.created_at == "2023-01-01"


# ---------------------------------------------------------------------------
# upsert_signal — Branch
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_branch_calls_merge_branch() -> None:
    attrs = BranchAttributes(
        repo_name="org/repo",
        branch_name="main",
        last_commit_sha="abc123def",
        is_default=True,
        url="https://github.com/org/repo/tree/main",
    )
    signal = _make_signal(attrs, id="org/repo::main")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_branch") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    branch_arg = mock_merge.call_args.args[1]
    assert branch_arg.id == "github::Branch::org/repo::main"
    assert branch_arg.name == "main"
    assert branch_arg.is_default is True
    assert branch_arg.last_commit_sha == "abc123def"


# ---------------------------------------------------------------------------
# upsert_signal — Commit
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_commit_calls_merge_commit() -> None:
    attrs = CommitAttributes(
        sha="abc123",
        message="fix: bug",
        author="Alice",
        created_at="2026-05-01T10:00:00",
        additions=10,
        deletions=3,
        files_changed=2,
        url="https://github.com/org/repo/commit/abc123",
    )
    signal = _make_signal(attrs, id="abc123")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_commit") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    commit_arg = mock_merge.call_args.args[1]
    assert commit_arg.id == "github::Commit::abc123"
    assert commit_arg.sha == "abc123"
    assert commit_arg.message == "fix: bug"
    assert commit_arg.created_at == "2026-05-01T10:00:00"
    assert commit_arg.additions == 10
    assert commit_arg.deletions == 3
    assert commit_arg.files_changed == 2


# ---------------------------------------------------------------------------
# upsert_signal — PullRequest
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_pull_request_calls_merge_pull_request() -> None:
    attrs = PullRequestAttributes(
        repo_name="org/repo",
        pull_request_number=42,
        title="feat: Auth",
        state="merged",
        created_at="2026-04-01T09:00:00",
        user="alice",
        url="https://github.com/org/repo/pull/42",
        merged_at="2026-04-10T10:00:00",
    )
    signal = _make_signal(attrs, id="org/repo::42")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_pull_request") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    pr_arg = mock_merge.call_args.args[1]
    assert pr_arg.id == "github::PullRequest::org/repo::42"
    assert pr_arg.number == 42
    assert pr_arg.title == "feat: Auth"
    assert pr_arg.state == "merged"
    assert pr_arg.merged_at == "2026-04-10T10:00:00"


# ---------------------------------------------------------------------------
# upsert_signal — Person
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_person_calls_merge_person() -> None:
    attrs = PersonAttributes(
        full_name="Alice",
        login="alice",
        email="alice@example.com",
    )
    signal = _make_signal(attrs, id="alice")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_person") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    person_arg = mock_merge.call_args.args[1]
    assert person_arg.id == "github::Person::alice"
    assert person_arg.name == "Alice"
    assert person_arg.email == "alice@example.com"


# ---------------------------------------------------------------------------
# upsert_signal — Team
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_team_calls_merge_team() -> None:
    attrs = TeamAttributes(
        name="Platform Team",
        url="https://github.com/orgs/org/teams/platform",
    )
    signal = _make_signal(attrs, id="platform", source="github")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_team") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    team_arg = mock_merge.call_args.args[1]
    assert team_arg.id == "github::Team::platform"
    assert team_arg.name == "Platform Team"
    assert team_arg.source == "github"


# ---------------------------------------------------------------------------
# upsert_signal — Project
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_project_calls_merge_project() -> None:
    attrs = ProjectAttributes(
        project_id="10001",
        project_key="ENG",
        project_name="Engineering",
        status="active",
        project_type="software",
        url="https://jira.example.com/projects/ENG",
    )
    signal = _make_signal(attrs, source="jira", id="ENG")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_project") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    proj_arg = mock_merge.call_args.args[1]
    assert proj_arg.id == "jira::Project::ENG"
    assert proj_arg.key == "ENG"
    assert proj_arg.name == "Engineering"
    assert proj_arg.status == "active"
    assert proj_arg.project_type == "software"


# ---------------------------------------------------------------------------
# upsert_signal — Initiative
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_initiative_calls_merge_initiative() -> None:
    attrs = InitiativeAttributes(
        key="INIT-1",
        summary="Platform Modernization",
        priority="High",
        status="In Progress",
        created_at="2025-12-01",
        updated_at="2026-01-15",
        duedate="2026-06-30",
        labels=["platform"],
        components=["Infrastructure"],
        url="https://jira.example.com/browse/INIT-1",
    )
    signal = _make_signal(attrs, source="jira", id="INIT-1")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_initiative") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    init_arg = mock_merge.call_args.args[1]
    assert init_arg.id == "jira::Initiative::INIT-1"
    assert init_arg.key == "INIT-1"
    assert init_arg.summary == "Platform Modernization"
    assert init_arg.priority == "High"
    assert init_arg.duedate == "2026-06-30"
    assert init_arg.labels == ["platform"]
    assert init_arg._last_synced_at is not None


# ---------------------------------------------------------------------------
# upsert_signal — Epic
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_epic_calls_merge_epic() -> None:
    attrs = EpicAttributes(
        key="PLAT-1",
        summary="Migrate to Kubernetes",
        priority="High",
        status="In Progress",
        created_at="2025-12-01",
        updated_at="2026-02-01",
        start_date="2025-12-01",
        due_date="2026-06-30",
        url="https://jira.example.com/browse/PLAT-1",
    )
    signal = _make_signal(attrs, source="jira", id="PLAT-1")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_epic") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    epic_arg = mock_merge.call_args.args[1]
    assert epic_arg.id == "jira::Epic::PLAT-1"
    assert epic_arg.key == "PLAT-1"
    assert epic_arg.start_date == "2025-12-01"
    assert epic_arg.due_date == "2026-06-30"
    assert epic_arg._last_synced_at is not None


# ---------------------------------------------------------------------------
# upsert_signal — Sprint
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_sprint_calls_merge_sprint() -> None:
    attrs = SprintAttributes(
        name="Sprint 1",
        status="Completed",
        goal="Foundations",
        start_date="2025-12-09",
        end_date="2025-12-20",
    )
    signal = _make_signal(attrs, id="42575", source="jira")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_sprint") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    sprint_arg = mock_merge.call_args.args[1]
    assert sprint_arg.id == "jira::Sprint::42575"
    assert sprint_arg.name == "Sprint 1"
    assert sprint_arg.goal == "Foundations"
    assert sprint_arg.start_date == "2025-12-09"
    assert sprint_arg.end_date == "2025-12-20"
    assert sprint_arg.status == "Completed"


# ---------------------------------------------------------------------------
# upsert_signal — Issue
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_issue_calls_merge_issue() -> None:
    attrs = IssueAttributes(
        key="PLAT-1",
        summary="Implement Kubernetes deployment",
        priority="High",
        status="In Progress",
        type="Story",
        created_at="2026-01-10",
        updated_at="2026-02-01",
        story_points=5,
        url="https://jira.example.com/browse/PLAT-1",
    )
    signal = _make_signal(attrs, id="PLAT-1", source="jira")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_issue") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    issue_arg = mock_merge.call_args.args[1]
    assert issue_arg.id == "jira::Issue::PLAT-1"
    assert issue_arg.key == "PLAT-1"
    assert issue_arg.type == "Story"
    assert issue_arg.story_points == 5
    assert issue_arg.created_at == "2026-01-10"
    assert issue_arg._last_synced_at is not None


# ---------------------------------------------------------------------------
# upsert_signal — unknown entity_type
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_unknown_entity_type_is_skipped() -> None:
    """Signals with an unrecognised entity_type are logged and skipped."""
    # We can't construct an ActivitySignal with an unknown entity_type directly
    # (Pydantic will reject it). Instead, mock entity_type on the signal object.
    signal = MagicMock(spec=ActivitySignal)
    signal.entity_type = "UnknownEntity"
    signal.signal_id = "test-uuid"
    session = _mock_session()

    with (
        patch("connectors.consumers.sinks.neo4j_sink.merge_repository") as mock_repo,
        patch("connectors.consumers.sinks.neo4j_sink.merge_person") as mock_person,
    ):
        upsert_signal(session, signal)

    mock_repo.assert_not_called()
    mock_person.assert_not_called()
    session.run.assert_not_called()


# ---------------------------------------------------------------------------
# upsert_signal — relationships passed through
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_signal_relationships_converted_and_passed() -> None:
    """Relationships on the signal are converted to DbRelationship and passed to merge_*."""
    rels = [
        Relationship(
            type="AUTHORED_BY",
            direction=None,
            target=RelationshipTarget(source="github", entity_type="Person", id="alice"),
        ),
        Relationship(
            type="PART_OF",
            direction=None,
            target=RelationshipTarget(source="github", entity_type="Branch", id="branch_main"),
        ),
    ]
    attrs = CommitAttributes(
        sha="abc123",
        message="fix",
        author="Alice",
        created_at="2026-01-01T00:00:00",
    )
    signal = _make_signal(attrs, id="abc123", relationships=rels)
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_commit") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    passed_rels = mock_merge.call_args.kwargs.get("relationships") or mock_merge.call_args.args[2]
    assert len(passed_rels) == 2
    rel_types = {r.type for r in passed_rels}
    assert rel_types == {"AUTHORED_BY", "PART_OF"}


@pytest.mark.unit
def test_upsert_signal_relationship_target_no_identifier_excluded() -> None:
    """Relationships with no identifier (id/email/url) are excluded from the passed list."""
    rels = [
        Relationship(
            type="PART_OF",
            direction=None,
            target=RelationshipTarget(entity_type="Repository"),  # no identifier
        ),
    ]
    attrs = BranchAttributes(repo_name="org/repo", branch_name="main", last_commit_sha="abc")
    signal = _make_signal(attrs, id="org/repo::main", relationships=rels)
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_branch") as mock_merge:
        upsert_signal(session, signal)

    passed_rels = mock_merge.call_args.kwargs.get("relationships", [])
    assert passed_rels == []


@pytest.mark.unit
def test_upsert_signal_direction_in_swaps_from_to_in_db_relationship() -> None:
    """direction=IN produces a DbRelationship with from/to swapped."""
    rels = [
        Relationship(
            type="REVIEWS",
            direction="IN",
            target=RelationshipTarget(source="github", entity_type="Person", id="bob"),
        ),
    ]
    attrs = PullRequestAttributes(
        repo_name="org/repo",
        pull_request_number=1,
        title="T",
        state="open",
        created_at="2026-01-01",
        user="alice",
    )
    signal = _make_signal(attrs, id="org/repo::1", relationships=rels)
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_pull_request") as mock_merge:
        upsert_signal(session, signal)

    passed_rels = mock_merge.call_args.kwargs.get("relationships") or mock_merge.call_args.args[2]
    assert len(passed_rels) == 1
    db_rel = passed_rels[0]
    # "IN" → target becomes from, signal node becomes to
    assert db_rel.from_id == "github::Person::bob"
    assert db_rel.to_id == "github::PullRequest::org/repo::1"
    assert db_rel.from_type == "Person"
    assert db_rel.to_type == "PullRequest"


# ---------------------------------------------------------------------------
# consume_queue — ack / nack behaviour
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_consume_queue_acks_on_success() -> None:
    """consume_queue acks the message when upsert_signal succeeds."""
    from connectors.consumers.main import consume_queue

    attrs = RepositoryAttributes(
        name="repo",
        created_at="2023-01-01",
        updated_at="2024-01-01",
        url="https://github.com/org/repo",
    )
    signal = _make_signal(attrs, id="repo_1")
    mock_message = AsyncMock()

    with (
        patch("connectors.consumers.main.RabbitMQConsumer") as MockConsumer,
        patch("connectors.consumers.main.GraphDatabase") as MockDriver,
        patch("connectors.consumers.main.upsert_signal"),
    ):
        async def _gen():
            yield signal, mock_message

        mock_consumer_instance = MagicMock()
        mock_consumer_instance.consume.return_value = _gen()
        MockConsumer.return_value = mock_consumer_instance

        MockDriver.driver.return_value.session.return_value.__enter__ = MagicMock(return_value=MagicMock())
        MockDriver.driver.return_value.session.return_value.__exit__ = MagicMock(return_value=False)

        await consume_queue(
            queue_name="github_queue",
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

    attrs = RepositoryAttributes(
        name="repo",
        created_at="2023-01-01",
        updated_at="2024-01-01",
        url="https://github.com/org/repo",
    )
    signal = _make_signal(attrs, id="repo_1")
    mock_message = AsyncMock()

    with (
        patch("connectors.consumers.main.RabbitMQConsumer") as MockConsumer,
        patch("connectors.consumers.main.GraphDatabase") as MockDriver,
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
            queue_name="github_queue",
            rabbitmq_url="amqp://guest:guest@localhost:5672/",
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
        )

    mock_message.nack.assert_awaited_once_with(requeue=False)
    mock_message.ack.assert_not_called()


# ---------------------------------------------------------------------------
# Phase E — PersonCache + IdentityMapping in the consumer
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_github_person_calls_person_cache_get_or_create() -> None:
    """GitHub Person signal: PersonCache.get_or_create_person called with login as external_id,
    and flush_identity_mappings is called after upsert_signal returns."""
    attrs = PersonAttributes(
        full_name="Alice",
        login="alice",
        email="alice@example.com",
    )
    signal = _make_signal(attrs, source="github", id="alice")
    session = _mock_session()

    person_cache = MagicMock(spec=PersonCache)
    person_cache.get_or_create_person.return_value = ("person_github_alice", False)

    upsert_signal(session, signal, person_cache=person_cache)

    person_cache.get_or_create_person.assert_called_once()
    call_kwargs = person_cache.get_or_create_person.call_args
    assert call_kwargs.kwargs.get("external_id") == "alice"
    assert call_kwargs.kwargs.get("provider") == "github"
    person_cache.flush_identity_mappings.assert_called_once_with(session)


@pytest.mark.unit
def test_upsert_jira_person_calls_person_cache_with_account_id() -> None:
    """Jira Person signal: PersonCache.get_or_create_person called with account_id as external_id."""
    attrs = PersonAttributes(
        full_name="Bob",
        account_id="abc123",
        email="bob@example.com",
    )
    signal = _make_signal(attrs, source="jira", id="abc123")
    session = _mock_session()

    person_cache = MagicMock(spec=PersonCache)
    person_cache.get_or_create_person.return_value = ("person_jira_abc123", False)

    upsert_signal(session, signal, person_cache=person_cache)

    person_cache.get_or_create_person.assert_called_once()
    call_kwargs = person_cache.get_or_create_person.call_args
    assert call_kwargs.kwargs.get("external_id") == "abc123"
    assert call_kwargs.kwargs.get("provider") == "jira"
    person_cache.flush_identity_mappings.assert_called_once_with(session)


@pytest.mark.unit
def test_person_cache_hit_prevents_duplicate_merge_person() -> None:
    """Two Person signals with the same login: merge_person fires only once (cache hit on second call)."""
    attrs = PersonAttributes(
        full_name="Alice",
        login="alice",
        email="alice@example.com",
    )
    signal = _make_signal(attrs, source="github", id="alice")

    session = _mock_session()
    # No existing person in DB — simulate empty result
    session.run.return_value.single.return_value = None

    person_cache = PersonCache()

    with patch("connectors.commons.person_cache.merge_person") as mock_merge_person:
        with patch("connectors.commons.person_cache.merge_identity_mapping"):
            upsert_signal(session, signal, person_cache=person_cache)
            upsert_signal(session, signal, person_cache=person_cache)

    # merge_person should only be called once (cache hit on second call)
    assert mock_merge_person.call_count == 1


@pytest.mark.unit
def test_person_cache_queues_and_flushes_identity_mapping() -> None:
    """GitHub Person signal: IdentityMapping is queued and flushed with the expected external_id."""
    attrs = PersonAttributes(
        full_name="Alice",
        login="alice",
        email="alice@example.com",
    )
    signal = _make_signal(attrs, source="github", id="alice")

    session = _mock_session()
    session.run.return_value.single.return_value = None

    person_cache = PersonCache()

    with patch("connectors.commons.person_cache.merge_person"):
        with patch("connectors.commons.person_cache.merge_identity_mapping") as mock_merge_identity:
            upsert_signal(session, signal, person_cache=person_cache)

    mock_merge_identity.assert_called_once()
    identity_arg = mock_merge_identity.call_args.args[1]
    assert identity_arg.id == "github::IdentityMapping::alice"
    assert identity_arg.provider == "GitHub"
    assert identity_arg.username == "alice"


# ---------------------------------------------------------------------------
# File handler
# ---------------------------------------------------------------------------

from common.activity_signal.models import FileAttributes
from connectors.consumers.sinks.neo4j_sink import _HANDLERS
from common.activity_signal.models import SUPPORTED_ENTITY_TYPES


@pytest.mark.unit
def test_handle_file_upserts_correct_node() -> None:
    attrs = FileAttributes(
        path="src/app/main.py",
        repo_name="myrepo",
        name="main.py",
        extension=".py",
        language="Python",
        is_test=False,
        last_updated_at="2024-06-01T10:00:00",
    )
    signal = _make_signal(attrs, source="github", id="myrepo::src/app/main.py")
    session = _mock_session()
    session.run.return_value.single.return_value = None

    with patch("connectors.consumers.sinks.neo4j_sink.merge_file") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    file_node = mock_merge.call_args.args[1]
    assert file_node.id == "github::File::myrepo::src/app/main.py"
    assert file_node.path == "src/app/main.py"
    assert file_node.repo_name == "myrepo"
    assert file_node.language == "Python"


@pytest.mark.unit
def test_handle_file_creates_modifies_relationship() -> None:
    attrs = FileAttributes(
        path="src/app/main.py",
        repo_name="myrepo",
    )
    signal = _make_signal(
        attrs,
        source="github",
        id="myrepo::src/app/main.py",
        relationships=[
            Relationship(
                type="MODIFIES",
                direction="IN",
                target=RelationshipTarget(source="github", entity_type="Commit", id="abc123"),
                properties={"additions": 3, "deletions": 1},
            )
        ],
    )
    session = _mock_session()
    session.run.return_value.single.return_value = None

    with patch("connectors.consumers.sinks.neo4j_sink.merge_file") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    db_rels = mock_merge.call_args.kwargs.get("relationships") or mock_merge.call_args.args[2]
    assert len(db_rels) == 1
    db_rel = db_rels[0]
    # direction=IN swaps from/to: (Commit)-[:MODIFIES]->(File)
    assert db_rel.type == "MODIFIES"
    assert db_rel.to_id == "github::File::myrepo::src/app/main.py"
    assert db_rel.from_id == "github::Commit::abc123"


# ---------------------------------------------------------------------------
# Migration completeness guard
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_supported_entity_types_have_handlers() -> None:
    """Every entity type in SUPPORTED_ENTITY_TYPES must have a consumer handler.

    Person is handled directly in upsert_signal (outside _HANDLERS) to support
    PersonCache injection, so it is excluded from the _HANDLERS check.
    """
    covered = set(_HANDLERS.keys()) | {"Person"}
    missing = SUPPORTED_ENTITY_TYPES - covered
    assert not missing, (
        f"No consumer handler for entity type(s): {missing}. "
        "Add a handler to _HANDLERS in neo4j_sink.py and a test in test_consumer_phase5.py."
    )

"""Unit tests for the Neo4j consumer sink (neo4j_sink) and consume_queue.

Tests verify that upsert_signal dispatches to the correct merge_* function
with the correctly constructed neo4j_db dataclass, mirroring the logic in the
original sync modules (modules/github/, modules/jira/).

Key behaviours tested:
- Each entity_type calls the right merge_* function.
- Signal attributes are mapped to dataclass fields (including Phase-B aliases).
- Relationships from the signal are converted and passed to merge_*.
- Direction=IN swaps from/to on the DbRelationship.
- Targets without external_id are skipped.
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
    external_id: str = "node_1",
    relationships: list[Relationship] | None = None,
) -> ActivitySignal:
    return ActivitySignal(
        source=source,
        external_id=external_id,
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
    rel = Relationship(
        type="PART_OF",
        direction=None,
        target=RelationshipTarget(entity_type="Repository", external_id="repo_1"),
    )
    result = _to_db_relationships([rel], "branch_1", "Branch")
    assert len(result) == 1
    db_rel = result[0]
    assert db_rel.from_id == "branch_1"
    assert db_rel.to_id == "repo_1"
    assert db_rel.from_type == "Branch"
    assert db_rel.to_type == "Repository"
    assert db_rel.type == "PART_OF"


@pytest.mark.unit
def test_to_db_relationships_direction_out_is_forward() -> None:
    rel = Relationship(
        type="MERGED_INTO",
        direction="OUT",
        target=RelationshipTarget(entity_type="Branch", external_id="branch_main"),
    )
    result = _to_db_relationships([rel], "pr_1", "PullRequest")
    assert result[0].from_id == "pr_1"
    assert result[0].to_id == "branch_main"


@pytest.mark.unit
def test_to_db_relationships_direction_in_swaps_from_to() -> None:
    rel = Relationship(
        type="REVIEWS",
        direction="IN",
        target=RelationshipTarget(entity_type="Person", external_id="person_alice"),
    )
    result = _to_db_relationships([rel], "pr_1", "PullRequest")
    assert len(result) == 1
    db_rel = result[0]
    # "IN" means target-[:REL]->source, so from_id is the target
    assert db_rel.from_id == "person_alice"
    assert db_rel.to_id == "pr_1"
    assert db_rel.from_type == "Person"
    assert db_rel.to_type == "PullRequest"


@pytest.mark.unit
def test_to_db_relationships_no_external_id_skipped() -> None:
    rel = Relationship(
        type="PART_OF",
        direction=None,
        target=RelationshipTarget(entity_type="Repository"),  # no external_id
    )
    result = _to_db_relationships([rel], "branch_1", "Branch")
    assert result == []


@pytest.mark.unit
def test_to_db_relationships_multiple() -> None:
    rels = [
        Relationship(
            type="AUTHORED_BY",
            direction=None,
            target=RelationshipTarget(entity_type="Person", external_id="person_alice"),
        ),
        Relationship(
            type="PART_OF",
            direction=None,
            target=RelationshipTarget(entity_type="Branch", external_id="branch_main"),
        ),
    ]
    result = _to_db_relationships(rels, "commit_1", "Commit")
    assert len(result) == 2
    types = {r.type for r in result}
    assert types == {"AUTHORED_BY", "PART_OF"}


# ---------------------------------------------------------------------------
# upsert_signal — Repository
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_repository_calls_merge_repository() -> None:
    attrs = RepositoryAttributes(
        id="repo_1",
        full_name="org/repo",
        name="repo",
        created_at="2023-01-01",
        updated_at="2024-01-01",
        url="https://github.com/org/repo",
        language="Python",
        is_private=True,
        topics=["api", "python"],
    )
    signal = _make_signal(attrs, external_id="repo_1")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_repository") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    repo_arg = mock_merge.call_args.args[1]
    assert repo_arg.id == "repo_1"
    assert repo_arg.name == "repo"
    assert repo_arg.full_name == "org/repo"
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
        name="main",
        last_commit_sha="abc123def",
        id="branch_repo_main",
        is_default=True,
        url="https://github.com/org/repo/tree/main",
    )
    signal = _make_signal(attrs, external_id="branch_repo_main")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_branch") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    branch_arg = mock_merge.call_args.args[1]
    assert branch_arg.id == "branch_repo_main"
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
        id="commit_abc123",
        additions=10,
        deletions=3,
        files_changed=2,
        url="https://github.com/org/repo/commit/abc123",
    )
    signal = _make_signal(attrs, external_id="commit_abc123")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_commit") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    commit_arg = mock_merge.call_args.args[1]
    assert commit_arg.id == "commit_abc123"
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
        id="pr_42",
        number=42,
        title="feat: Auth",
        state="merged",
        created_at="2026-04-01T09:00:00",
        user="alice",
        url="https://github.com/org/repo/pull/42",
        merged_at="2026-04-10T10:00:00",
    )
    signal = _make_signal(attrs, external_id="pr_42")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_pull_request") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    pr_arg = mock_merge.call_args.args[1]
    assert pr_arg.id == "pr_42"
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
        id="github_person_alice",
        name="Alice",
        login="alice",
        email="alice@example.com",
    )
    signal = _make_signal(attrs, external_id="github_person_alice")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_person") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    person_arg = mock_merge.call_args.args[1]
    assert person_arg.id == "github_person_alice"
    assert person_arg.name == "Alice"
    assert person_arg.email == "alice@example.com"


# ---------------------------------------------------------------------------
# upsert_signal — Team
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_team_calls_merge_team() -> None:
    attrs = TeamAttributes(
        id="team_github_platform",
        name="Platform Team",
        slug="platform",
        url="https://github.com/orgs/org/teams/platform",
    )
    signal = _make_signal(attrs, external_id="team_github_platform", source="github")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_team") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    team_arg = mock_merge.call_args.args[1]
    assert team_arg.id == "team_github_platform"
    assert team_arg.name == "Platform Team"
    assert team_arg.source == "github"


# ---------------------------------------------------------------------------
# upsert_signal — Project
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_upsert_project_calls_merge_project() -> None:
    attrs = ProjectAttributes(
        id="project_jira_ENG",
        key="ENG",
        name="Engineering",
        status="active",
        project_type="software",
        url="https://jira.example.com/projects/ENG",
    )
    signal = _make_signal(attrs, external_id="project_jira_ENG", source="jira")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_project") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    proj_arg = mock_merge.call_args.args[1]
    assert proj_arg.id == "project_jira_ENG"
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
        id="initiative_jira_INIT1",
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
    signal = _make_signal(attrs, external_id="initiative_jira_INIT1", source="jira")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_initiative") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    init_arg = mock_merge.call_args.args[1]
    assert init_arg.id == "initiative_jira_INIT1"
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
        id="epic_jira_PLAT1",
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
    signal = _make_signal(attrs, external_id="epic_jira_PLAT1", source="jira")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_epic") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    epic_arg = mock_merge.call_args.args[1]
    assert epic_arg.id == "epic_jira_PLAT1"
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
        id="sprint_jira_1",
        name="Sprint 1",
        status="Completed",
        goal="Foundations",
        start_date="2025-12-09",
        end_date="2025-12-20",
    )
    signal = _make_signal(attrs, external_id="sprint_jira_1", source="jira")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_sprint") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    sprint_arg = mock_merge.call_args.args[1]
    assert sprint_arg.id == "sprint_jira_1"
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
        id="issue_jira_PLAT1",
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
    signal = _make_signal(attrs, external_id="issue_jira_PLAT1", source="jira")
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_issue") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    issue_arg = mock_merge.call_args.args[1]
    assert issue_arg.id == "issue_jira_PLAT1"
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
            target=RelationshipTarget(entity_type="Person", external_id="github_person_alice"),
        ),
        Relationship(
            type="PART_OF",
            direction=None,
            target=RelationshipTarget(entity_type="Branch", external_id="branch_main"),
        ),
    ]
    attrs = CommitAttributes(
        sha="abc123",
        message="fix",
        author="Alice",
        created_at="2026-01-01T00:00:00",
        id="commit_1",
    )
    signal = _make_signal(attrs, external_id="commit_1", relationships=rels)
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_commit") as mock_merge:
        upsert_signal(session, signal)

    mock_merge.assert_called_once()
    passed_rels = mock_merge.call_args.kwargs.get("relationships") or mock_merge.call_args.args[2]
    assert len(passed_rels) == 2
    rel_types = {r.type for r in passed_rels}
    assert rel_types == {"AUTHORED_BY", "PART_OF"}


@pytest.mark.unit
def test_upsert_signal_relationship_target_no_external_id_excluded() -> None:
    """Relationships with no external_id are excluded from the passed list."""
    rels = [
        Relationship(
            type="PART_OF",
            direction=None,
            target=RelationshipTarget(entity_type="Repository"),  # no external_id
        ),
    ]
    attrs = BranchAttributes(name="main", last_commit_sha="abc", id="branch_1")
    signal = _make_signal(attrs, external_id="branch_1", relationships=rels)
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
            target=RelationshipTarget(entity_type="Person", external_id="github_person_bob"),
        ),
    ]
    attrs = PullRequestAttributes(
        id="pr_1",
        number=1,
        title="T",
        state="open",
        created_at="2026-01-01",
        user="alice",
    )
    signal = _make_signal(attrs, external_id="pr_1", relationships=rels)
    session = _mock_session()

    with patch("connectors.consumers.sinks.neo4j_sink.merge_pull_request") as mock_merge:
        upsert_signal(session, signal)

    passed_rels = mock_merge.call_args.kwargs.get("relationships") or mock_merge.call_args.args[2]
    assert len(passed_rels) == 1
    db_rel = passed_rels[0]
    # "IN" → target becomes from, signal node becomes to
    assert db_rel.from_id == "github_person_bob"
    assert db_rel.to_id == "pr_1"
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
        id="repo_1",
        full_name="org/repo",
        name="repo",
        created_at="2023-01-01",
        updated_at="2024-01-01",
        url="https://github.com/org/repo",
    )
    signal = _make_signal(attrs, external_id="repo_1")
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

    attrs = RepositoryAttributes(
        id="repo_1",
        full_name="org/repo",
        name="repo",
        created_at="2023-01-01",
        updated_at="2024-01-01",
        url="https://github.com/org/repo",
    )
    signal = _make_signal(attrs, external_id="repo_1")
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
            queue_name="github_repository_queue",
            rabbitmq_url="amqp://guest:guest@localhost:5672/",
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="password",
        )

    mock_message.nack.assert_awaited_once_with(requeue=False)
    mock_message.ack.assert_not_called()


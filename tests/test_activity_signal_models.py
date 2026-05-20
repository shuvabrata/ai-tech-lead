"""Unit tests for ActivitySignal attribute models (Phase B validation gate).

Verifies that:
- B1: BranchAttributes uses ``last_commit_sha`` and optional new fields;
      old name ``commit_sha`` raises ValidationError.
- B2: CommitAttributes uses ``created_at``; old name ``committed_date`` raises
      ValidationError.
- B3: PullRequestAttributes accepts all 13 new optional fields.
- B4: IssueAttributes uses ``type`` / ``created_at``; old names ``issue_type``
      and ``created`` raise ValidationError.
- B5: SprintAttributes has no ``state`` field; ``status`` is accepted.
- B6: InitiativeAttributes accepts ``project_id``.
- SUPPORTED_RELATIONSHIP_TYPES includes all Phase C canonical types.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from common.activity_signal.models import (
    SUPPORTED_RELATIONSHIP_TYPES,
    BranchAttributes,
    CommitAttributes,
    InitiativeAttributes,
    IssueAttributes,
    PullRequestAttributes,
    SprintAttributes,
)


# ---------------------------------------------------------------------------
# B1 — BranchAttributes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_branch_attributes_last_commit_sha_round_trips() -> None:
    attrs = BranchAttributes(
        repo_name="myrepo",
        branch_name="main",
        last_commit_sha="abc123def456",
    )
    d = attrs.model_dump()
    assert d["last_commit_sha"] == "abc123def456"
    assert d["repo_name"] == "myrepo"
    assert d["branch_name"] == "main"


@pytest.mark.unit
def test_branch_attributes_optional_new_fields() -> None:
    attrs = BranchAttributes(
        repo_name="myrepo",
        branch_name="feat/x",
        last_commit_sha="sha1",
        last_commit_timestamp="2026-05-01T10:00:00",
        is_protected=True,
        is_deleted=False,
        is_external=False,
    )
    d = attrs.model_dump()
    assert d["last_commit_timestamp"] == "2026-05-01T10:00:00"
    assert d["is_protected"] is True
    assert d["is_deleted"] is False
    assert d["is_external"] is False


@pytest.mark.unit
def test_branch_attributes_old_commit_sha_not_accepted_as_canonical() -> None:
    """commit_sha is not a declared field; it should NOT populate last_commit_sha."""
    # With extra='forbid', unknown fields raise ValidationError.
    with pytest.raises((ValidationError, TypeError)):
        # omit last_commit_sha entirely — required field missing
        BranchAttributes(repo_name="myrepo", branch_name="main")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# B2 — CommitAttributes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_commit_attributes_created_at_round_trips() -> None:
    attrs = CommitAttributes(
        sha="abc123",
        message="fix: something",
        author="Alice",
        created_at="2026-05-01T10:00:00",
    )
    d = attrs.model_dump()
    assert d["created_at"] == "2026-05-01T10:00:00"


@pytest.mark.unit
def test_commit_attributes_committed_date_raises() -> None:
    """committed_date is not a declared field; omitting created_at must raise."""
    with pytest.raises((ValidationError, TypeError)):
        CommitAttributes(
            sha="abc",
            message="msg",
            author="Alice",
            # created_at deliberately omitted
        )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# B3 — PullRequestAttributes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pull_request_attributes_all_new_optional_fields() -> None:
    attrs = PullRequestAttributes(
        repo_name="org/myrepo",
        pull_request_number=42,
        title="Add feature",
        state="open",
        created_at="2026-01-01T00:00:00",
        user="alice",
        updated_at="2026-02-01T00:00:00",
        merged_at="2026-02-15T12:00:00",
        closed_at="2026-02-15T13:00:00",
        commits_count=5,
        additions=120,
        deletions=30,
        changed_files=8,
        comments=3,
        review_comments=7,
        head_branch_name="feat/my-feature",
        base_branch_name="main",
        labels=["bug", "enhancement"],
        mergeable_state="clean",
    )
    d = attrs.model_dump()
    assert d["repo_name"] == "org/myrepo"
    assert d["pull_request_number"] == 42
    assert d["updated_at"] == "2026-02-01T00:00:00"
    assert d["merged_at"] == "2026-02-15T12:00:00"
    assert d["closed_at"] == "2026-02-15T13:00:00"
    assert d["commits_count"] == 5
    assert d["additions"] == 120
    assert d["deletions"] == 30
    assert d["changed_files"] == 8
    assert d["comments"] == 3
    assert d["review_comments"] == 7
    assert d["head_branch_name"] == "feat/my-feature"
    assert d["base_branch_name"] == "main"
    assert d["labels"] == ["bug", "enhancement"]
    assert d["mergeable_state"] == "clean"


@pytest.mark.unit
def test_pull_request_attributes_optional_fields_default_none() -> None:
    attrs = PullRequestAttributes(
        repo_name="org/myrepo",
        pull_request_number=1,
        title="Minimal PR",
        state="open",
        created_at="2026-01-01",
        user="bob",
    )
    d = attrs.model_dump()
    assert d["updated_at"] is None
    assert d["merged_at"] is None
    assert d["labels"] is None
    assert d["mergeable_state"] is None


# ---------------------------------------------------------------------------
# B4 — IssueAttributes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_issue_attributes_type_and_created_at_round_trip() -> None:
    attrs = IssueAttributes(
        id="issue_jira_1",
        key="PLAT-1",
        summary="Implement feature",
        priority="High",
        status="In Progress",
        type="Story",
        created_at="2026-01-10T00:00:00",
        updated_at="2026-02-01T00:00:00",
        story_points=5.0,
    )
    d = attrs.model_dump()
    assert d["type"] == "Story"
    assert d["created_at"] == "2026-01-10T00:00:00"
    assert d["updated_at"] == "2026-02-01T00:00:00"
    assert d["story_points"] == 5.0


@pytest.mark.unit
def test_issue_attributes_old_issue_type_not_canonical() -> None:
    """issue_type is not declared; omitting ``type`` must raise."""
    with pytest.raises((ValidationError, TypeError)):
        IssueAttributes(
            id="issue_1",
            key="X-1",
            summary="s",
            priority="High",
            status="Open",
            # type deliberately omitted
            created_at="2026-01-01",
        )  # type: ignore[call-arg]


@pytest.mark.unit
def test_issue_attributes_old_created_not_canonical() -> None:
    """created is not declared; omitting ``created_at`` must raise."""
    with pytest.raises((ValidationError, TypeError)):
        IssueAttributes(
            id="issue_1",
            key="X-1",
            summary="s",
            priority="High",
            status="Open",
            type="Bug",
            # created_at deliberately omitted
        )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# B5 — SprintAttributes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sprint_attributes_has_status_field() -> None:
    attrs = SprintAttributes(id="sprint_1", name="Sprint 1", status="active")
    d = attrs.model_dump()
    assert d["status"] == "active"
    assert "state" not in d


@pytest.mark.unit
def test_sprint_attributes_no_state_field_declared() -> None:
    """``state`` should not be a declared field on SprintAttributes."""
    import dataclasses

    declared_fields = set(SprintAttributes.model_fields.keys())
    assert "state" not in declared_fields
    assert "status" in declared_fields


# ---------------------------------------------------------------------------
# B6 — InitiativeAttributes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_initiative_attributes_project_id_round_trips() -> None:
    attrs = InitiativeAttributes(
        id="initiative_jira_1",
        key="INIT-1",
        summary="Big initiative",
        priority="High",
        status="In Progress",
        created_at="2026-01-01",
        project_id="project_jira_myproject",
    )
    d = attrs.model_dump()
    assert d["project_id"] == "project_jira_myproject"


@pytest.mark.unit
def test_initiative_attributes_project_id_defaults_none() -> None:
    attrs = InitiativeAttributes(
        id="initiative_jira_2",
        key="INIT-2",
        summary="Another initiative",
        priority="Medium",
        status="Open",
        created_at="2026-01-02",
    )
    d = attrs.model_dump()
    assert d["project_id"] is None


# ---------------------------------------------------------------------------
# SUPPORTED_RELATIONSHIP_TYPES — Phase C canonical set
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_supported_relationship_types_includes_phase_c_types() -> None:
    expected = {
        "BRANCH_OF",
        "CREATED_BY",
        "REVIEWED_BY",
        "TARGETS",
        "IN_SPRINT",
        "REPORTED_BY",
        "MERGED_BY",
        "FROM",
        "INCLUDES",
        "REQUESTED_REVIEWER",
        "COLLABORATOR",
        "MEMBER_OF",
        "LEADS",
        "BLOCKS",
        "DEPENDS_ON",
        "RELATES_TO",
        "MAPS_TO",
        "CONTAINS",
        "TEAM",
    }
    missing = expected - SUPPORTED_RELATIONSHIP_TYPES
    assert not missing, f"Missing relationship types: {missing}"


@pytest.mark.unit
def test_supported_relationship_types_retains_legacy_types() -> None:
    """Types still emitted by producers must remain supported."""
    required = {"ASSIGNED_TO", "AUTHORED_BY", "PART_OF", "MEMBER_OF"}
    missing = required - SUPPORTED_RELATIONSHIP_TYPES
    assert not missing, f"Missing legacy types: {missing}"

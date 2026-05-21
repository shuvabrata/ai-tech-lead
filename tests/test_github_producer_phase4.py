"""Unit tests for github_producer.py (Phase 4).

Tests cover:
- Signal builder functions for each entity type.
- Validation failures return None (no signal emitted).
- Relationship generation.
- Text truncation on long fields.
- process_repo_signals wires fetch → map → publish correctly (mocked I/O).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.producers.github.constants import (
    _TEXT_MAX,
    _truncate
)

from connectors.producers.github.build_branch_signal import build_branch_signal
from connectors.producers.github.build_commit_signal import build_commit_signal
from connectors.producers.github.build_person_signal import build_person_signal
from connectors.producers.github.build_pull_request_signal import build_pull_request_signal
from connectors.producers.github.build_repository_signal import build_repository_signal
from connectors.producers.github.process_repo_signals import (
    process_repo_signals,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": "repo_myrepo",
        "name": "myrepo",
        "full_name": "org/myrepo",
        "url": "https://github.com/org/myrepo",
        "language": "Python",
        "is_private": False,
        "topics": ["ai", "analytics"],
        "created_at": "2023-01-01",
        "updated_at": "2024-06-01",
    }
    data.update(overrides)
    return data


def _branch_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": "branch_myrepo_main",
        "name": "main",
        "repo_name": "myrepo",
        "is_default": True,
        "is_protected": False,
        "last_commit_sha": "abc123",
        "last_commit_timestamp": "2024-06-01T10:00:00",
        "url": "https://github.com/org/myrepo/tree/main",
    }
    data.update(overrides)
    return data


def _author_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "login": "devuser",
        "name": "Dev User",
        "email": "dev@example.com",
    }
    data.update(overrides)
    return data


def _commit_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": "commit_abc123",
        "sha": "abc123",
        "message": "Fix bug",
        "created_at": "2024-06-01T10:00:00",
        "additions": 10,
        "deletions": 5,
        "files_changed": 3,
        "url": "https://github.com/org/myrepo/commit/abc123",
    }
    data.update(overrides)
    return data


def _pr_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": "12345",
        "number": 42,
        "title": "Add feature",
        "state": "merged",
        "created_at": "2024-05-01",
        "updated_at": "2024-06-01T10:00:00",
        "merged_at": "2024-06-01",
        "base_branch_id": "myrepo::main",
        "head_branch_id": "myrepo::feature",
        "url": "https://github.com/org/myrepo/pull/42",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Repository signal
# ---------------------------------------------------------------------------


class TestBuildRepositorySignal:
    def test_valid(self) -> None:
        sig = build_repository_signal(_repo_data())
        assert sig is not None
        assert sig.source == "github"
        assert sig.id == "org/myrepo"
        assert sig.attributes.entity_type == "Repository"  # type: ignore[union-attr]

    def test_missing_mandatory_full_name_returns_none(self) -> None:
        d = _repo_data()
        del d["full_name"]
        sig = build_repository_signal(d)
        assert sig is None

    def test_missing_name_returns_none(self) -> None:
        d = _repo_data()
        del d["name"]
        sig = build_repository_signal(d)
        assert sig is None

    def test_extra_fields_pass_through(self) -> None:
        sig = build_repository_signal(_repo_data())
        assert sig is not None
        attrs_dict = sig.attributes.model_dump()
        assert attrs_dict["language"] == "Python"
        assert attrs_dict["topics"] == ["ai", "analytics"]


# ---------------------------------------------------------------------------
# Branch signal
# ---------------------------------------------------------------------------


class TestBuildBranchSignal:
    def test_valid(self) -> None:
        sig = build_branch_signal(_branch_data(), _repo_data())
        assert sig is not None
        assert sig.attributes.entity_type == "Branch"  # type: ignore[union-attr]
        assert sig.id == "myrepo::main"

    def test_relationship_to_repo(self) -> None:
        sig = build_branch_signal(_branch_data(), _repo_data())
        assert sig is not None
        assert len(sig.relationships) == 1
        rel = sig.relationships[0]
        assert rel.type == "BRANCH_OF"
        assert rel.direction is None
        assert rel.target.entity_type == "Repository"
        assert rel.target.id == "org/myrepo"

    def test_missing_commit_sha_returns_none(self) -> None:
        d = _branch_data()
        del d["last_commit_sha"]
        sig = build_branch_signal(d, _repo_data())
        assert sig is None

    def test_missing_name_returns_none(self) -> None:
        d = _branch_data()
        del d["name"]
        sig = build_branch_signal(d, _repo_data())
        assert sig is None

    def test_event_time_parsed_from_timestamp(self) -> None:
        sig = build_branch_signal(_branch_data(last_commit_timestamp="2024-06-01T10:00:00"), _repo_data())
        assert sig is not None
        assert sig.event_time.year == 2024

    def test_missing_timestamp_uses_now(self) -> None:
        d = _branch_data()
        d["last_commit_timestamp"] = None
        sig = build_branch_signal(d, _repo_data())
        assert sig is not None


# ---------------------------------------------------------------------------
# Person signal
# ---------------------------------------------------------------------------


class TestBuildPersonSignal:
    def test_valid(self) -> None:
        sig = build_person_signal(_author_data())
        assert sig is not None
        assert sig.id == "devuser"

    def test_id_derived_from_login(self) -> None:
        sig = build_person_signal({"login": "alice", "name": "Alice", "email": ""})
        assert sig is not None
        assert sig.id == "alice"

    def test_login_fallback_to_name(self) -> None:
        sig = build_person_signal({"name": "Bob", "email": ""})
        assert sig is not None
        assert "Bob" in sig.id

    def test_extra_fields_present(self) -> None:
        sig = build_person_signal(_author_data())
        assert sig is not None
        attrs_dict = sig.attributes.model_dump()
        assert attrs_dict["email"] == "dev@example.com"
        assert attrs_dict["login"] == "devuser"


# ---------------------------------------------------------------------------
# Commit signal
# ---------------------------------------------------------------------------


class TestBuildCommitSignal:
    def test_valid(self) -> None:
        sig = build_commit_signal(_commit_data(), _author_data(), _branch_data())
        assert sig is not None
        assert sig.id == "abc123"

    def test_relationships_authored_by_and_part_of(self) -> None:
        sig = build_commit_signal(_commit_data(), _author_data(), _branch_data())
        assert sig is not None
        types = [r.type for r in sig.relationships]
        assert "AUTHORED_BY" in types
        assert "PART_OF" in types

    def test_no_branch_omits_part_of(self) -> None:
        sig = build_commit_signal(_commit_data(), _author_data(), None)
        assert sig is not None
        types = [r.type for r in sig.relationships]
        assert "PART_OF" not in types
        assert "AUTHORED_BY" in types

    def test_long_message_truncated(self) -> None:
        long_msg = "x" * (_TEXT_MAX + 500)
        sig = build_commit_signal(_commit_data(message=long_msg), _author_data(), None)
        assert sig is not None
        attrs_dict = sig.attributes.model_dump()
        assert len(attrs_dict["message"]) == _TEXT_MAX

    def test_missing_sha_returns_none(self) -> None:
        d = _commit_data()
        del d["sha"]
        sig = build_commit_signal(d, _author_data(), None)
        assert sig is None

    def test_authored_by_targets_person(self) -> None:
        sig = build_commit_signal(_commit_data(), _author_data(), None)
        assert sig is not None
        authored_by = next(r for r in sig.relationships if r.type == "AUTHORED_BY")
        assert authored_by.target.entity_type == "Person"
        assert authored_by.target.id == "devuser"


# ---------------------------------------------------------------------------
# PullRequest signal
# ---------------------------------------------------------------------------


class TestBuildPullRequestSignal:
    def test_valid(self) -> None:
        sig = build_pull_request_signal(_pr_data(), _author_data(), [], _repo_data())
        assert sig is not None
        assert sig.id == "myrepo::42"

    def test_authored_by_relationship(self) -> None:
        sig = build_pull_request_signal(_pr_data(), _author_data(), [], _repo_data())
        assert sig is not None
        types = [r.type for r in sig.relationships]
        assert "CREATED_BY" in types

    def test_targets_relationship(self) -> None:
        sig = build_pull_request_signal(_pr_data(), _author_data(), [], _repo_data())
        assert sig is not None
        targets = [r for r in sig.relationships if r.type == "TARGETS"]
        assert len(targets) == 1
        assert targets[0].direction == "OUT"
        assert targets[0].target.entity_type == "Branch"
        assert targets[0].target.id == "myrepo::main"

    def test_reviewed_by_relationships(self) -> None:
        sig = build_pull_request_signal(
            _pr_data(), _author_data(), ["reviewer1", "reviewer2"], _repo_data()
        )
        assert sig is not None
        reviews = [r for r in sig.relationships if r.type == "REVIEWED_BY"]
        assert len(reviews) == 2
        reviewer_ids = {r.target.id for r in reviews}
        assert reviewer_ids == {"reviewer1", "reviewer2"}

    def test_no_base_branch_omits_targets(self) -> None:
        d = _pr_data()
        d["base_branch_id"] = None
        sig = build_pull_request_signal(d, _author_data(), [], _repo_data())
        assert sig is not None
        assert all(r.type != "TARGETS" for r in sig.relationships)

    def test_long_title_truncated(self) -> None:
        long_title = "T" * (_TEXT_MAX + 100)
        sig = build_pull_request_signal(_pr_data(title=long_title), _author_data(), [], _repo_data())
        assert sig is not None
        attrs_dict = sig.attributes.model_dump()
        assert len(attrs_dict["title"]) == _TEXT_MAX

    def test_missing_mandatory_number_returns_none(self) -> None:
        d = _pr_data()
        del d["number"]
        sig = build_pull_request_signal(d, _author_data(), [], _repo_data())
        assert sig is None

    def test_missing_mandatory_id_accepted(self) -> None:
        """id is no longer in PullRequestAttributes; signal should build fine."""
        d = _pr_data()
        d.pop("id", None)
        sig = build_pull_request_signal(d, _author_data(), [], _repo_data())
        assert sig is not None


# ---------------------------------------------------------------------------
# Truncation helper
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_value_unchanged(self) -> None:
        assert _truncate("hello") == "hello"

    def test_long_value_truncated_to_max(self) -> None:
        val = "a" * (_TEXT_MAX + 1000)
        result = _truncate(val)
        assert len(result) == _TEXT_MAX

    def test_non_string_converted(self) -> None:
        assert _truncate(42) == "42"


# ---------------------------------------------------------------------------
# process_repo_signals integration (fully mocked I/O)
# ---------------------------------------------------------------------------


class TestProcessRepoSignals:
    """Verify that process_repo_signals calls publish for each entity type."""

    def _make_mock_repo(self) -> MagicMock:
        repo = MagicMock()
        repo.full_name = "org/myrepo"
        repo.name = "myrepo"
        repo.html_url = "https://github.com/org/myrepo"
        repo.language = "Python"
        repo.private = False
        repo.default_branch = "main"
        repo.created_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
        repo.updated_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        return repo

    def _make_mock_branch(self) -> MagicMock:
        branch = MagicMock()
        branch.name = "main"
        branch.protected = False
        commit = MagicMock()
        commit.sha = "abc123"
        commit.commit.author.date = datetime(2024, 6, 1, tzinfo=timezone.utc)
        branch.commit = commit
        return branch

    def _make_mock_commit(self) -> MagicMock:
        commit = MagicMock()
        commit.sha = "abc123"
        commit.commit.message = "Fix bug"

        # Author must be set before assigning to commit.commit.author so that
        # author.date is accessible after the assignment (MagicMock chain quirk).
        author = MagicMock()
        author.login = "devuser"
        author.name = "Dev User"
        author.email = "dev@example.com"
        author.date = datetime(2024, 6, 1, tzinfo=timezone.utc)

        commit.author = author
        commit.commit.author = author
        return commit

    def _make_mock_pr(self) -> MagicMock:
        pr = MagicMock()
        pr.number = 1
        pr.id = 999
        pr.title = "Test PR"
        pr.state = "closed"
        pr.merged = True
        pr.created_at = datetime(2024, 5, 1, tzinfo=timezone.utc)
        pr.updated_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        pr.merged_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        pr.closed_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        pr.html_url = "https://github.com/org/myrepo/pull/1"
        pr.commits = 3
        pr.additions = 10
        pr.deletions = 5
        pr.changed_files = 2
        pr.comments = 0
        pr.review_comments = 1
        pr.labels = []
        pr.mergeable_state = "clean"
        pr.requested_reviewers = []

        # Author
        author = MagicMock()
        author.login = "devuser"
        author.name = "Dev User"
        author.email = "dev@example.com"
        pr.user = author

        # Base branch
        base = MagicMock()
        base.ref = "main"
        base.repo = MagicMock()
        base.repo.id = 42
        pr.base = base

        # Head branch (same repo)
        head = MagicMock()
        head.ref = "feature"
        head.repo = MagicMock()
        head.repo.id = 42
        head.repo.owner.login = "org"
        head.repo.name = "myrepo"
        pr.head = head

        # No merged_by to avoid MagicMock cascade in process_single_pr
        pr.merged_by = None

        return pr

    @pytest.mark.asyncio
    async def test_publishes_all_entity_types(self) -> None:
        mock_repo = self._make_mock_repo()
        mock_branch = self._make_mock_branch()
        mock_commit = self._make_mock_commit()
        mock_pr = self._make_mock_pr()

        publisher = AsyncMock()
        publisher.publish = AsyncMock()
        published: Dict[str, int] = {}

        with (
            patch("connectors.producers.github.process_repo_signals.fetch_repo_topics", return_value=["ai"]),
            patch("connectors.producers.github.process_branches.fetch_branches", return_value=[mock_branch]),
            patch("connectors.producers.github.process_commits.fetch_commits", return_value=[mock_commit]),
            patch("connectors.producers.github.process_prs.fetch_pull_requests_direct", return_value=[mock_pr]),
            patch("connectors.producers.github.process_single_pr.fetch_pr_reviews", return_value=[]),
            patch("connectors.producers.github.process_single_pr.fetch_pr_commits", return_value=[]),
            patch("connectors.producers.github.process_teams.fetch_repo_teams", return_value=[]),
            patch(
                "connectors.producers.github.process_prs.resolve_prs_since_date",
                return_value=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ),
        ):
            await process_repo_signals(publisher, mock_repo, "org", None, published)

        assert published.get("Repository", 0) >= 1
        assert published.get("Branch", 0) >= 1
        assert published.get("Commit", 0) >= 1
        assert published.get("PullRequest", 0) >= 1
        assert published.get("Person", 0) >= 1

    @pytest.mark.asyncio
    async def test_repo_without_created_at_skips_gracefully(self) -> None:
        mock_repo = self._make_mock_repo()
        mock_repo.created_at = None  # triggers ValueError in map_repo

        publisher = AsyncMock()
        published: Dict[str, int] = {}

        with (
            patch("connectors.producers.github.process_repo_signals.fetch_repo_topics", return_value=[]),
        ):
            await process_repo_signals(publisher, mock_repo, "org", None, published)

        # Nothing should be published
        publisher.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_deduplicates_person_signals(self) -> None:
        """The same author for commit + PR should only emit one Person signal."""
        mock_repo = self._make_mock_repo()
        mock_branch = self._make_mock_branch()
        mock_commit = self._make_mock_commit()  # author: devuser
        mock_pr = self._make_mock_pr()          # author: devuser

        publisher = AsyncMock()
        publisher.publish = AsyncMock()
        published: Dict[str, int] = {}

        with (
            patch("connectors.producers.github.process_repo_signals.fetch_repo_topics", return_value=[]),
            patch("connectors.producers.github.process_branches.fetch_branches", return_value=[mock_branch]),
            patch("connectors.producers.github.process_commits.fetch_commits", return_value=[mock_commit]),
            patch("connectors.producers.github.process_prs.fetch_pull_requests_direct", return_value=[mock_pr]),
            patch("connectors.producers.github.process_single_pr.fetch_pr_reviews", return_value=[]),
            patch("connectors.producers.github.process_single_pr.fetch_pr_commits", return_value=[]),
            patch(
                "connectors.producers.github.process_prs.resolve_prs_since_date",
                return_value=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ),
            patch("connectors.producers.github.process_teams.fetch_repo_teams", return_value=[]),
        ):
            await process_repo_signals(publisher, mock_repo, "org", None, published)

        # devuser should appear exactly once
        assert published.get("Person", 0) == 1

    @pytest.mark.asyncio
    async def test_pr_date_cutoff_stops_loop(self) -> None:
        """A PR older than pr_since must halt the loop; no signal emitted for it."""
        mock_repo = self._make_mock_repo()

        recent_pr = self._make_mock_pr()   # updated_at 2024-06-01, will be processed

        old_pr = self._make_mock_pr()
        old_pr.number = 99
        old_pr.updated_at = datetime(2019, 1, 1, tzinfo=timezone.utc)  # before cutoff

        publisher = AsyncMock()
        publisher.publish = AsyncMock()
        published: Dict[str, int] = {}

        with (
            patch("connectors.producers.github.process_repo_signals.fetch_repo_topics", return_value=[]),
            patch("connectors.producers.github.process_branches.fetch_branches", return_value=[]),
            patch("connectors.producers.github.process_commits.fetch_commits", return_value=[]),
            patch(
                "connectors.producers.github.process_prs.fetch_pull_requests_direct",
                return_value=[recent_pr, old_pr],
            ),
            patch("connectors.producers.github.process_single_pr.fetch_pr_reviews", return_value=[]),
            patch("connectors.producers.github.process_single_pr.fetch_pr_commits", return_value=[]),
            patch(
                "connectors.producers.github.process_prs.resolve_prs_since_date",
                return_value=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ),
            patch("connectors.producers.github.process_teams.fetch_repo_teams", return_value=[]),
        ):
            await process_repo_signals(publisher, mock_repo, "org", None, published)

        # The recent PR should be published; old PR halts the loop before emission
        assert published.get("PullRequest", 0) == 1

    @pytest.mark.asyncio
    async def test_seen_commits_not_reemitted_from_pr_loop(self) -> None:
        """A commit processed in the main loop must not be re-emitted when it also appears in a PR."""
        mock_repo = self._make_mock_repo()
        mock_commit = self._make_mock_commit()  # sha = "abc123"
        mock_pr = self._make_mock_pr()

        publisher = AsyncMock()
        publisher.publish = AsyncMock()
        published: Dict[str, int] = {}

        # fetch_pr_commits returns the same commit already processed in the main loop
        with (
            patch("connectors.producers.github.process_repo_signals.fetch_repo_topics", return_value=[]),
            patch("connectors.producers.github.process_branches.fetch_branches", return_value=[]),
            patch("connectors.producers.github.process_commits.fetch_commits", return_value=[mock_commit]),
            patch(
                "connectors.producers.github.process_prs.fetch_pull_requests_direct",
                return_value=[mock_pr],
            ),
            patch("connectors.producers.github.process_single_pr.fetch_pr_reviews", return_value=[]),
            patch(
                "connectors.producers.github.process_single_pr.fetch_pr_commits",
                return_value=[mock_commit],  # same sha as main-loop commit
            ),
            patch(
                "connectors.producers.github.process_prs.resolve_prs_since_date",
                return_value=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ),
            patch("connectors.producers.github.process_teams.fetch_repo_teams", return_value=[]),
        ):
            await process_repo_signals(publisher, mock_repo, "org", None, published)

        # Commit must be published exactly once despite appearing in both loops
        assert published.get("Commit", 0) == 1

    @pytest.mark.asyncio
    async def test_team_signal_emitted_with_collaborator_and_member_of(self) -> None:
        """process_repo_signals with a team → Team signal emitted; member gets MEMBER_OF rel."""
        mock_repo = self._make_mock_repo()

        # Mock team with one member
        mock_member = MagicMock()
        mock_member.login = "teammember"
        mock_member.name = "Team Member"
        mock_member.email = "teammember@example.com"
        mock_team = MagicMock()
        mock_team.name = "Engineering"
        mock_team.slug = "engineering"
        mock_team.permission = "push"
        mock_team.get_members = MagicMock(return_value=[mock_member])

        publisher = AsyncMock()
        publisher.publish = AsyncMock()
        published: Dict[str, int] = {}

        with (
            patch("connectors.producers.github.process_repo_signals.fetch_repo_topics", return_value=[]),
            patch("connectors.producers.github.process_branches.fetch_branches", return_value=[]),
            patch("connectors.producers.github.process_commits.fetch_commits", return_value=[]),
            patch("connectors.producers.github.process_prs.fetch_pull_requests_direct", return_value=[]),
            patch("connectors.producers.github.process_teams.fetch_repo_teams", return_value=[mock_team]),
        ):
            await process_repo_signals(publisher, mock_repo, "org", None, published)

        # Team signal published
        assert published.get("Team", 0) >= 1

        # Collect published signals
        all_sigs = [call.args[0] for call in publisher.publish.call_args_list]
        team_sigs = [s for s in all_sigs if s.entity_type == "Team"]
        assert len(team_sigs) == 1
        team_sig = team_sigs[0]

        # Team signal has COLLABORATOR relationship to repo
        collab_rels = [r for r in team_sig.relationships if r.type == "COLLABORATOR"]
        assert len(collab_rels) == 1
        assert collab_rels[0].target.entity_type == "Repository"

        # Member Person signal has MEMBER_OF relationship to team
        person_sigs = [s for s in all_sigs if s.entity_type == "Person" and s.id == "teammember"]
        assert len(person_sigs) == 1
        member_of_rels = [r for r in person_sigs[0].relationships if r.type == "MEMBER_OF"]
        assert len(member_of_rels) == 1
        assert member_of_rels[0].target.entity_type == "Team"

    @pytest.mark.asyncio
    async def test_person_collaborator_signal_has_permission_in_properties(self) -> None:
        """Person collaborator signal → COLLABORATOR rel has properties dict with permission key."""
        mock_repo = self._make_mock_repo()

        mock_member = MagicMock()
        mock_member.login = "collab_user"
        mock_member.name = "Collab User"
        mock_member.email = "collab@example.com"

        mock_team = MagicMock()
        mock_team.name = "Ops"
        mock_team.slug = "ops"
        mock_team.permission = "admin"
        mock_team.get_members = MagicMock(return_value=[mock_member])

        publisher = AsyncMock()
        publisher.publish = AsyncMock()
        published: Dict[str, int] = {}

        with (
            patch("connectors.producers.github.process_repo_signals.fetch_repo_topics", return_value=[]),
            patch("connectors.producers.github.process_branches.fetch_branches", return_value=[]),
            patch("connectors.producers.github.process_commits.fetch_commits", return_value=[]),
            patch("connectors.producers.github.process_prs.fetch_pull_requests_direct", return_value=[]),
            patch("connectors.producers.github.process_teams.fetch_repo_teams", return_value=[mock_team]),
        ):
            await process_repo_signals(publisher, mock_repo, "org", None, published)

        all_sigs = [call.args[0] for call in publisher.publish.call_args_list]
        person_sigs = [s for s in all_sigs if s.entity_type == "Person" and s.id == "collab_user"]
        assert len(person_sigs) == 1

        collab_rels = [r for r in person_sigs[0].relationships if r.type == "COLLABORATOR"]
        assert len(collab_rels) == 1
        assert collab_rels[0].properties is not None
        assert "permission" in collab_rels[0].properties
        assert collab_rels[0].properties["permission"] == "admin"


# ---------------------------------------------------------------------------
# Phase D: PR relationship tests
# ---------------------------------------------------------------------------


class TestBuildPullRequestSignalPhaseD:
    """Phase D: FROM, REQUESTED_REVIEWER, MERGED_BY, INCLUDES relationships."""

    def test_from_relationship(self) -> None:
        """PR with head_branch_id → FROM relationship present."""
        sig = build_pull_request_signal(_pr_data(head_branch_id="myrepo::feature"), _author_data(), [], _repo_data())
        assert sig is not None
        from_rels = [r for r in sig.relationships if r.type == "FROM"]
        assert len(from_rels) == 1
        assert from_rels[0].target.entity_type == "Branch"
        assert from_rels[0].target.id == "myrepo::feature"

    def test_from_relationship_absent_when_no_head_branch(self) -> None:
        d = _pr_data()
        d["head_branch_id"] = None
        sig = build_pull_request_signal(d, _author_data(), [], _repo_data())
        assert sig is not None
        assert all(r.type != "FROM" for r in sig.relationships)

    def test_requested_reviewer_relationship(self) -> None:
        """PR with requested_reviewer_logins → REQUESTED_REVIEWER relationships."""
        sig = build_pull_request_signal(
            _pr_data(), _author_data(), [], _repo_data(),
            requested_reviewer_logins=["alice", "bob"],
        )
        assert sig is not None
        rr_rels = [r for r in sig.relationships if r.type == "REQUESTED_REVIEWER"]
        assert len(rr_rels) == 2
        rr_ids = {r.target.id for r in rr_rels}
        assert rr_ids == {"alice", "bob"}

    def test_requested_reviewer_absent_when_empty(self) -> None:
        sig = build_pull_request_signal(_pr_data(), _author_data(), [], _repo_data(), requested_reviewer_logins=[])
        assert sig is not None
        assert all(r.type != "REQUESTED_REVIEWER" for r in sig.relationships)

    def test_merged_by_relationship_when_merged(self) -> None:
        """PR state=merged + merger_login → MERGED_BY relationship present."""
        sig = build_pull_request_signal(
            _pr_data(state="merged"), _author_data(), [], _repo_data(), merger_login="bob"
        )
        assert sig is not None
        merged_rels = [r for r in sig.relationships if r.type == "MERGED_BY"]
        assert len(merged_rels) == 1
        assert merged_rels[0].target.entity_type == "Person"
        assert merged_rels[0].target.id == "bob"

    def test_merged_by_absent_when_open(self) -> None:
        """PR state=open → MERGED_BY not emitted even if merger_login provided."""
        sig = build_pull_request_signal(
            _pr_data(state="open"), _author_data(), [], _repo_data(), merger_login="bob"
        )
        assert sig is not None
        assert all(r.type != "MERGED_BY" for r in sig.relationships)

    def test_includes_relationships(self) -> None:
        """PR with commit_shas → one INCLUDES relationship per SHA."""
        shas = ["aaa111", "bbb222", "ccc333"]
        sig = build_pull_request_signal(
            _pr_data(), _author_data(), [], _repo_data(), commit_shas=shas
        )
        assert sig is not None
        inc_rels = [r for r in sig.relationships if r.type == "INCLUDES"]
        assert len(inc_rels) == 3
        inc_ids = {r.target.id for r in inc_rels}
        assert inc_ids == {"aaa111", "bbb222", "ccc333"}

    def test_includes_absent_when_no_shas(self) -> None:
        sig = build_pull_request_signal(_pr_data(), _author_data(), [], _repo_data(), commit_shas=[])
        assert sig is not None
        assert all(r.type != "INCLUDES" for r in sig.relationships)


# ---------------------------------------------------------------------------
# Phase D: Commit REFERENCES tests
# ---------------------------------------------------------------------------


class TestBuildCommitSignalPhaseD:
    """Phase D: REFERENCES relationship from Jira keys in commit message."""

    def test_references_relationship_from_message(self) -> None:
        """Commit message with Jira key → REFERENCES relationship emitted."""
        sig = build_commit_signal(
            _commit_data(message="Fix PROJ-42: resolve the issue"), _author_data(), None
        )
        assert sig is not None
        ref_rels = [r for r in sig.relationships if r.type == "REFERENCES"]
        assert len(ref_rels) == 1
        assert ref_rels[0].target.entity_type == "Issue"
        assert ref_rels[0].target.id == "PROJ-42"
        assert ref_rels[0].target.source == "jira"

    def test_multiple_jira_keys_in_message(self) -> None:
        sig = build_commit_signal(
            _commit_data(message="Fixes PROJ-1 and resolves PROJ-2"), _author_data(), None
        )
        assert sig is not None
        ref_rels = [r for r in sig.relationships if r.type == "REFERENCES"]
        assert len(ref_rels) == 2
        ref_ids = {r.target.id for r in ref_rels}
        assert ref_ids == {"PROJ-1", "PROJ-2"}

    def test_no_jira_key_no_references(self) -> None:
        sig = build_commit_signal(
            _commit_data(message="Minor cleanup and refactor"), _author_data(), None
        )
        assert sig is not None
        assert all(r.type != "REFERENCES" for r in sig.relationships)


# ---------------------------------------------------------------------------
# File signal
# ---------------------------------------------------------------------------

from connectors.producers.github.build_file_signal import build_file_signal


def _file_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "filename": "src/app/main.py",
        "additions": 3,
        "deletions": 1,
        "name": "main.py",
        "extension": ".py",
        "language": "Python",
        "is_test": False,
    }
    data.update(overrides)
    return data


class TestBuildFileSignal:
    def test_happy_path(self) -> None:
        sig = build_file_signal(_file_data(), _commit_data(), _repo_data(name="myrepo", owner="org"))
        assert sig is not None
        assert sig.source == "github"
        assert sig.id == "myrepo::src/app/main.py"
        assert sig.entity_type == "File"
        assert sig.attributes.path == "src/app/main.py"  # type: ignore[union-attr]
        assert sig.attributes.repo_name == "myrepo"  # type: ignore[union-attr]
        assert len(sig.relationships) == 1

    def test_relationship_is_modifies_direction_in(self) -> None:
        sig = build_file_signal(_file_data(), _commit_data(), _repo_data(name="myrepo"))
        assert sig is not None
        rel = sig.relationships[0]
        assert rel.type == "MODIFIES"
        assert rel.direction == "IN"
        assert rel.target.entity_type == "Commit"
        assert rel.target.id == "abc123"
        assert rel.target.source == "github"

    def test_relationship_properties_carry_additions_deletions(self) -> None:
        sig = build_file_signal(_file_data(additions=5, deletions=2), _commit_data(), _repo_data(name="myrepo"))
        assert sig is not None
        props = sig.relationships[0].properties
        assert props is not None
        assert props["additions"] == 5
        assert props["deletions"] == 2

    def test_returns_none_on_missing_filename(self) -> None:
        sig = build_file_signal({}, _commit_data(), _repo_data(name="myrepo"))
        assert sig is None

    def test_returns_none_on_missing_sha(self) -> None:
        sig = build_file_signal(_file_data(), {"created_at": "2024-06-01T10:00:00"}, _repo_data(name="myrepo"))
        assert sig is None

    def test_url_generated_when_owner_present(self) -> None:
        sig = build_file_signal(
            _file_data(), _commit_data(), {"name": "myrepo", "owner": "org"}
        )
        assert sig is not None
        assert sig.attributes.url == "https://github.com/org/myrepo/blob/abc123/src/app/main.py"  # type: ignore[union-attr]

    def test_url_is_none_when_owner_absent(self) -> None:
        sig = build_file_signal(_file_data(), _commit_data(), {"name": "myrepo"})
        assert sig is not None
        assert sig.attributes.url is None  # type: ignore[union-attr]

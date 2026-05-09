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

from connectors.producers.github_producer import (
    _SOURCE,
    _TEXT_MAX,
    _truncate,
    build_branch_signal,
    build_commit_signal,
    build_person_signal,
    build_pull_request_signal,
    build_repository_signal,
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
        "base_branch_id": "branch_myrepo_main",
        "head_branch_id": "branch_myrepo_feature",
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
        assert sig.external_id == "repo_myrepo"
        assert sig.routing_key == "github.Repository"
        assert sig.attributes.entity_type == "Repository"  # type: ignore[union-attr]

    def test_missing_mandatory_id_returns_none(self) -> None:
        d = _repo_data()
        del d["id"]
        sig = build_repository_signal(d)
        assert sig is None

    def test_missing_updated_at_returns_none(self) -> None:
        d = _repo_data()
        del d["updated_at"]
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
        assert sig.routing_key == "github.Branch"
        assert sig.attributes.entity_type == "Branch"  # type: ignore[union-attr]

    def test_relationship_to_repo(self) -> None:
        sig = build_branch_signal(_branch_data(), _repo_data())
        assert sig is not None
        assert len(sig.relationships) == 1
        rel = sig.relationships[0]
        assert rel.type == "PART_OF"
        assert rel.direction is None
        assert rel.target.entity_type == "Repository"
        assert rel.target.external_id == "repo_myrepo"

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
        assert sig.routing_key == "github.Person"
        assert sig.external_id == "github_person_devuser"

    def test_id_derived_from_login(self) -> None:
        sig = build_person_signal({"login": "alice", "name": "Alice", "email": ""})
        assert sig is not None
        assert sig.external_id == "github_person_alice"

    def test_login_fallback_to_name(self) -> None:
        sig = build_person_signal({"name": "Bob", "email": ""})
        assert sig is not None
        assert "Bob" in sig.external_id

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
        assert sig.routing_key == "github.Commit"
        assert sig.external_id == "commit_abc123"

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
        assert authored_by.target.external_id == "github_person_devuser"


# ---------------------------------------------------------------------------
# PullRequest signal
# ---------------------------------------------------------------------------


class TestBuildPullRequestSignal:
    def test_valid(self) -> None:
        sig = build_pull_request_signal(_pr_data(), _author_data(), [], _repo_data())
        assert sig is not None
        assert sig.routing_key == "github.PullRequest"

    def test_authored_by_relationship(self) -> None:
        sig = build_pull_request_signal(_pr_data(), _author_data(), [], _repo_data())
        assert sig is not None
        types = [r.type for r in sig.relationships]
        assert "AUTHORED_BY" in types

    def test_merged_into_relationship(self) -> None:
        sig = build_pull_request_signal(_pr_data(), _author_data(), [], _repo_data())
        assert sig is not None
        merged = [r for r in sig.relationships if r.type == "MERGED_INTO"]
        assert len(merged) == 1
        assert merged[0].direction == "OUT"
        assert merged[0].target.entity_type == "Branch"
        assert merged[0].target.external_id == "branch_myrepo_main"

    def test_reviews_relationships(self) -> None:
        sig = build_pull_request_signal(
            _pr_data(), _author_data(), ["reviewer1", "reviewer2"], _repo_data()
        )
        assert sig is not None
        reviews = [r for r in sig.relationships if r.type == "REVIEWS"]
        assert len(reviews) == 2
        reviewer_ids = {r.target.external_id for r in reviews}
        assert reviewer_ids == {"github_person_reviewer1", "github_person_reviewer2"}

    def test_no_base_branch_omits_merged_into(self) -> None:
        d = _pr_data()
        d["base_branch_id"] = None
        sig = build_pull_request_signal(d, _author_data(), [], _repo_data())
        assert sig is not None
        assert all(r.type != "MERGED_INTO" for r in sig.relationships)

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
        pr.created_at = datetime(2024, 5, 1, tzinfo=timezone.utc)
        pr.updated_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        pr.merged_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
        pr.html_url = "https://github.com/org/myrepo/pull/1"

        # Author
        author = MagicMock()
        author.login = "devuser"
        author.name = "Dev User"
        author.email = "dev@example.com"
        pr.user = author

        # Base branch
        base = MagicMock()
        base.ref = "main"
        pr.base = base

        # Head branch (same repo)
        head = MagicMock()
        head.ref = "feature"
        head.repo = MagicMock()
        head.repo.owner.login = "org"
        head.repo.name = "myrepo"
        pr.head = head

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
            patch("connectors.producers.github_producer.fetch_repo_topics", return_value=["ai"]),
            patch("connectors.producers.github_producer.fetch_branches", return_value=[mock_branch]),
            patch("connectors.producers.github_producer.fetch_commits", return_value=[mock_commit]),
            patch("connectors.producers.github_producer.fetch_pull_requests_direct", return_value=[mock_pr]),
            patch("connectors.producers.github_producer.fetch_pr_reviews", return_value=[]),
            patch(
                "connectors.producers.github_producer.resolve_prs_since_date",
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
            patch("connectors.producers.github_producer.fetch_repo_topics", return_value=[]),
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
            patch("connectors.producers.github_producer.fetch_repo_topics", return_value=[]),
            patch("connectors.producers.github_producer.fetch_branches", return_value=[mock_branch]),
            patch("connectors.producers.github_producer.fetch_commits", return_value=[mock_commit]),
            patch("connectors.producers.github_producer.fetch_pull_requests_direct", return_value=[mock_pr]),
            patch("connectors.producers.github_producer.fetch_pr_reviews", return_value=[]),
            patch(
                "connectors.producers.github_producer.resolve_prs_since_date",
                return_value=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ),
        ):
            await process_repo_signals(publisher, mock_repo, "org", None, published)

        # devuser should appear exactly once
        assert published.get("Person", 0) == 1

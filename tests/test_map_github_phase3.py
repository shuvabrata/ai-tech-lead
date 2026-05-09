"""Unit tests for Phase 3: map_github pure mapping functions.

All tests use simple ``MagicMock`` objects to simulate PyGithub API objects so
no network or database access is required.  These tests validate the
transformation logic extracted from the legacy GitHub connector handlers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, PropertyMock
import pytest

from connectors.producers.map_github import (
    extract_issue_keys,
    extract_issue_keys_from_branch,
    map_branch,
    map_commit,
    map_commit_author,
    map_commit_files,
    map_external_branch,
    map_pr_reviews,
    map_pr_user,
    map_pull_request,
    map_repo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(
    name: str = "my-repo",
    full_name: str = "owner/my-repo",
    html_url: str = "https://github.com/owner/my-repo",
    language: Optional[str] = "Python",
    is_private: bool = False,
    created_at: Optional[datetime] = None,
    description: str = "",
) -> MagicMock:
    repo = MagicMock()
    repo.name = name
    repo.full_name = full_name
    repo.html_url = html_url
    repo.language = language
    repo.private = is_private
    repo.created_at = created_at or datetime(2023, 1, 15, tzinfo=timezone.utc)
    repo.description = description
    return repo


def _make_branch(
    name: str = "main",
    sha: str = "abc1234def5678",
    commit_date: Optional[datetime] = None,
    protected: bool = False,
) -> MagicMock:
    branch = MagicMock()
    branch.name = name
    branch.protected = protected
    commit = MagicMock()
    commit.sha = sha
    author_date = commit_date or datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    commit.commit.author.date = author_date
    branch.commit = commit
    return branch


def _make_commit(
    sha: str = "deadbeef1234567890abcdef",
    message: str = "feat: add feature",
    additions: int = 10,
    deletions: int = 3,
    total: int = 2,
    commit_date: Optional[datetime] = None,
) -> MagicMock:
    commit = MagicMock()
    commit.sha = sha
    commit.commit.message = message
    commit.commit.author.date = commit_date or datetime(2024, 5, 10, tzinfo=timezone.utc)
    stats = MagicMock()
    stats.additions = additions
    stats.deletions = deletions
    stats.total = total
    commit.stats = stats
    return commit


def _make_pr(
    number: int = 42,
    title: str = "Fix bug",
    merged: bool = True,
    state: str = "closed",
    labels: Optional[list] = None,
    head_ref: str = "feature/ABC-123-fix",
    base_ref: str = "main",
    created_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
    merged_at: Optional[datetime] = None,
    closed_at: Optional[datetime] = None,
    repo_id: int = 999,
) -> MagicMock:
    pr = MagicMock()
    pr.number = number
    pr.title = title
    pr.merged = merged
    pr.state = state
    pr.draft = False
    pr.commits = 3
    pr.additions = 50
    pr.deletions = 20
    pr.changed_files = 4
    pr.comments = 2
    pr.review_comments = 1
    pr.mergeable_state = "clean"
    pr.merged_by = None
    pr.requested_reviewers = []

    pr.head.ref = head_ref
    pr.head.repo.id = repo_id
    pr.base.ref = base_ref
    pr.base.repo.id = repo_id

    label_objs = []
    for lbl in (labels or ["bug"]):
        lm = MagicMock()
        lm.name = lbl
        label_objs.append(lm)
    pr.labels = label_objs

    dt_base = datetime(2024, 4, 1, tzinfo=timezone.utc)
    pr.created_at = created_at or dt_base
    pr.updated_at = updated_at or dt_base
    pr.merged_at = merged_at or dt_base
    pr.closed_at = closed_at or dt_base

    return pr


# ---------------------------------------------------------------------------
# map_repo
# ---------------------------------------------------------------------------


class TestMapRepo:
    def test_basic_mapping(self) -> None:
        repo = _make_repo()
        result = map_repo(repo, ["python", "analytics"])

        assert result["id"] == "repo_my_repo"
        assert result["name"] == "my-repo"
        assert result["full_name"] == "owner/my-repo"
        assert result["url"] == "https://github.com/owner/my-repo"
        assert result["language"] == "Python"
        assert result["is_private"] is False
        assert result["topics"] == ["python", "analytics"]
        assert result["created_at"] == "2023-01-15"

    def test_none_language_becomes_empty_string(self) -> None:
        repo = _make_repo(language=None)
        result = map_repo(repo, [])
        assert result["language"] == ""

    def test_raises_when_no_created_at(self) -> None:
        repo = _make_repo()
        repo.created_at = None
        with pytest.raises(ValueError, match="no created_at"):
            map_repo(repo, [])

    def test_hyphens_in_name_replaced_in_id(self) -> None:
        repo = _make_repo(name="my-cool-repo")
        result = map_repo(repo, [])
        assert result["id"] == "repo_my_cool_repo"


# ---------------------------------------------------------------------------
# map_branch
# ---------------------------------------------------------------------------


class TestMapBranch:
    def test_default_branch(self) -> None:
        branch = _make_branch(name="main", sha="abc1234")
        result = map_branch("my-repo", "main", branch, "owner")

        assert result["id"] == "branch_my-repo_main"
        assert result["name"] == "main"
        assert result["is_default"] is True
        assert result["is_protected"] is False
        assert result["is_deleted"] is False
        assert result["is_external"] is False
        assert result["last_commit_sha"] == "abc1234"
        assert result["url"] == "https://github.com/owner/my-repo/tree/main"

    def test_non_default_branch(self) -> None:
        branch = _make_branch(name="develop")
        result = map_branch("my-repo", "main", branch, "owner")
        assert result["is_default"] is False

    def test_url_is_none_when_no_owner(self) -> None:
        branch = _make_branch(name="main")
        result = map_branch("my-repo", "main", branch, None)
        assert result["url"] is None

    def test_branch_name_with_slashes_in_id(self) -> None:
        branch = _make_branch(name="feature/some-feature")
        result = map_branch("repo", "main", branch, None)
        assert "/" not in result["id"]
        assert result["id"] == "branch_repo_feature_some_feature"


# ---------------------------------------------------------------------------
# map_commit_author
# ---------------------------------------------------------------------------


class TestMapCommitAuthor:
    def test_full_user_object(self) -> None:
        author = MagicMock()
        author.login = "alice"
        author.name = "Alice Smith"
        author.email = "Alice@Example.com"

        result = map_commit_author(author)
        assert result["login"] == "alice"
        assert result["name"] == "Alice Smith"
        assert result["email"] == "alice@example.com"  # lowercased

    def test_name_email_only_object(self) -> None:
        author = MagicMock(spec=["name", "email"])
        author.name = "Bob Jones"
        author.email = "Bob@Example.com"

        result = map_commit_author(author)
        assert result["login"] == "Bob"  # email prefix keeps original case
        assert result["name"] == "Bob Jones"
        assert result["email"] == "bob@example.com"

    def test_name_email_only_no_email(self) -> None:
        author = MagicMock(spec=["name", "email"])
        author.name = "Charlie Brown"
        author.email = None

        result = map_commit_author(author)
        assert result["login"] == "charlie_brown"
        assert result["email"] == ""

    def test_unknown_author_format_fallback(self) -> None:
        author = MagicMock(spec=[])  # no login, no name
        result = map_commit_author(author)
        assert result["login"] == "unknown"
        assert result["name"] == "Unknown"
        assert result["email"] == ""

    def test_lazy_load_failure_on_name(self) -> None:
        author = MagicMock()
        author.login = "bot"
        type(author).name = PropertyMock(side_effect=Exception("lazy load failed"))
        type(author).email = PropertyMock(side_effect=Exception("lazy load failed"))

        result = map_commit_author(author)
        assert result["login"] == "bot"
        assert result["name"] == "bot"  # falls back to login
        assert result["email"] == ""


# ---------------------------------------------------------------------------
# map_commit
# ---------------------------------------------------------------------------


class TestMapCommit:
    def test_basic_commit(self) -> None:
        commit = _make_commit(sha="deadbeef1234567890abcdef")
        result = map_commit("my-repo", commit, "owner")

        assert result["id"] == "commit_my-repo_deadbeef"
        assert result["sha"] == "deadbeef1234567890abcdef"
        assert result["message"] == "feat: add feature"
        assert result["additions"] == 10
        assert result["deletions"] == 3
        assert result["files_changed"] == 2
        assert result["url"] == "https://github.com/owner/my-repo/commit/deadbeef1234567890abcdef"

    def test_url_none_when_no_owner(self) -> None:
        commit = _make_commit()
        result = map_commit("my-repo", commit, None)
        assert result["url"] is None

    def test_missing_stats_defaults_to_zero(self) -> None:
        commit = _make_commit()
        commit.stats = None  # simulate missing/null stats
        result = map_commit("my-repo", commit, None)
        assert result["additions"] == 0
        assert result["deletions"] == 0
        assert result["files_changed"] == 0


# ---------------------------------------------------------------------------
# map_commit_files
# ---------------------------------------------------------------------------


class TestMapCommitFiles:
    def test_maps_file_list(self) -> None:
        f1 = MagicMock()
        f1.filename = "src/app.py"
        f1.additions = 5
        f1.deletions = 2
        f2 = MagicMock()
        f2.filename = "tests/test_app.py"
        f2.additions = 10
        f2.deletions = 0

        result = map_commit_files([f1, f2])
        assert len(result) == 2
        assert result[0] == {"filename": "src/app.py", "additions": 5, "deletions": 2}
        assert result[1] == {"filename": "tests/test_app.py", "additions": 10, "deletions": 0}

    def test_empty_list(self) -> None:
        assert map_commit_files([]) == []


# ---------------------------------------------------------------------------
# map_pr_user
# ---------------------------------------------------------------------------


class TestMapPrUser:
    def test_basic_user(self) -> None:
        user = MagicMock()
        user.login = "alice"
        user.name = "Alice"
        user.email = "Alice@Example.com"

        result = map_pr_user(user)
        assert result == {"login": "alice", "name": "Alice", "email": "alice@example.com"}

    def test_none_user_returns_unknown(self) -> None:
        result = map_pr_user(None)
        assert result["login"] == "unknown"
        assert result["email"] is None

    def test_none_email_stays_none(self) -> None:
        user = MagicMock()
        user.login = "bob"
        user.name = "Bob"
        user.email = None

        result = map_pr_user(user)
        assert result["email"] is None


# ---------------------------------------------------------------------------
# map_pull_request
# ---------------------------------------------------------------------------


class TestMapPullRequest:
    def test_merged_pr(self) -> None:
        pr = _make_pr(number=42, merged=True, state="closed")
        result = map_pull_request("my-repo", pr, "owner")

        assert result["id"] == "pr_my-repo_42"
        assert result["state"] == "merged"
        assert result["url"] == "https://github.com/owner/my-repo/pull/42"
        assert result["base_branch_id"] == "branch_my-repo_main"
        assert result["labels"] == ["bug"]

    def test_open_pr(self) -> None:
        pr = _make_pr(merged=False, state="open")
        result = map_pull_request("my-repo", pr, "owner")
        assert result["state"] == "open"

    def test_closed_not_merged_pr(self) -> None:
        pr = _make_pr(merged=False, state="closed")
        result = map_pull_request("my-repo", pr, "owner")
        assert result["state"] == "closed"

    def test_url_none_when_no_owner(self) -> None:
        pr = _make_pr()
        result = map_pull_request("my-repo", pr, None)
        assert result["url"] is None

    def test_labels_empty_when_none(self) -> None:
        pr = _make_pr()
        pr.labels = None
        result = map_pull_request("my-repo", pr, "owner")
        assert result["labels"] == []


# ---------------------------------------------------------------------------
# map_pr_reviews
# ---------------------------------------------------------------------------


class TestMapPrReviews:
    def _make_review(self, login: str, state: str) -> MagicMock:
        review = MagicMock()
        review.user.login = login
        review.state = state
        return review

    def test_deduplicates_keeping_last(self) -> None:
        reviews = [
            self._make_review("alice", "COMMENTED"),
            self._make_review("alice", "APPROVED"),
        ]
        result = map_pr_reviews(reviews)
        assert result == {"alice": "APPROVED"}

    def test_dismissed_state_excluded(self) -> None:
        reviews = [self._make_review("bob", "DISMISSED")]
        result = map_pr_reviews(reviews)
        assert result == {}

    def test_multiple_reviewers(self) -> None:
        reviews = [
            self._make_review("alice", "APPROVED"),
            self._make_review("bob", "CHANGES_REQUESTED"),
        ]
        result = map_pr_reviews(reviews)
        assert result["alice"] == "APPROVED"
        assert result["bob"] == "CHANGES_REQUESTED"

    def test_empty_list(self) -> None:
        assert map_pr_reviews([]) == {}


# ---------------------------------------------------------------------------
# map_external_branch
# ---------------------------------------------------------------------------


class TestMapExternalBranch:
    def _make_head_ref(self, branch_name: str = "fix/issue", repo_id: int = 777) -> MagicMock:
        head_ref = MagicMock()
        head_ref.ref = branch_name
        head_ref.repo.id = repo_id
        head_ref.repo.name = "forked-repo"
        head_ref.repo.owner.login = "fork-owner"
        return head_ref

    def test_existing_fork(self) -> None:
        head_ref = self._make_head_ref()
        details = {
            "sha": "fork_sha_123",
            "timestamp": "2024-03-01T10:00:00",
            "is_protected": False,
        }
        result = map_external_branch("target-repo", head_ref, details)

        assert result["id"] == "branch_external_fork-owner_forked-repo_fix_issue"
        assert result["is_external"] is True
        assert result["is_deleted"] is False
        assert result["last_commit_sha"] == "fork_sha_123"
        assert "https://github.com/fork-owner/forked-repo/tree/fix/issue" == result["url"]

    def test_deleted_fork(self) -> None:
        head_ref = MagicMock()
        head_ref.ref = "feature/gone"
        head_ref.repo = None

        result = map_external_branch("target-repo", head_ref, None)
        assert result["is_deleted"] is True
        assert result["is_external"] is True
        assert result["last_commit_sha"] == "unknown"
        assert result["url"] is None


# ---------------------------------------------------------------------------
# extract_issue_keys
# ---------------------------------------------------------------------------


class TestExtractIssueKeys:
    def test_standard_key(self) -> None:
        keys = extract_issue_keys("Fixes PROJ-123 and closes ABC-456")
        assert set(keys) == {"PROJ-123", "ABC-456"}

    def test_no_keys(self) -> None:
        assert extract_issue_keys("just a regular commit message") == []

    def test_deduplication(self) -> None:
        keys = extract_issue_keys("PROJ-123 refs PROJ-123 again")
        assert keys == ["PROJ-123"]

    def test_short_prefix_not_matched(self) -> None:
        # Single-letter prefix should not match (min 2 uppercase letters)
        keys = extract_issue_keys("A-123 is not a valid key")
        assert keys == []


# ---------------------------------------------------------------------------
# extract_issue_keys_from_branch
# ---------------------------------------------------------------------------


class TestExtractIssueKeysFromBranch:
    def test_git_flow_feature(self) -> None:
        keys = extract_issue_keys_from_branch("feature/PROJ-123-add-login")
        assert "PROJ-123" in keys

    def test_git_flow_bugfix(self) -> None:
        keys = extract_issue_keys_from_branch("bugfix/ABC-456-fix-null-pointer")
        assert "ABC-456" in keys

    def test_direct_prefix(self) -> None:
        keys = extract_issue_keys_from_branch("STORY-789-implement-feature")
        assert "STORY-789" in keys

    def test_no_match(self) -> None:
        keys = extract_issue_keys_from_branch("chore/update-dependencies")
        assert keys == []

    def test_custom_patterns(self) -> None:
        keys = extract_issue_keys_from_branch(
            "my-branch/CUSTOM-99",
            patterns=[r"my-branch/([A-Z]{2,}-\d+)"],
        )
        assert "CUSTOM-99" in keys

    def test_invalid_regex_silently_skipped(self) -> None:
        # Should not raise; invalid patterns are skipped
        keys = extract_issue_keys_from_branch("feature/PROJ-1", patterns=["[invalid"])
        assert keys == []

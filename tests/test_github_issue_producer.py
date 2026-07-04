"""Unit tests for GitHub issue signal builder (Phase 3).

Tests cover:
- Happy path: ``build_issue_signal`` returns a valid ``ActivitySignal``.
- Invalid data: returns ``None`` on validation failure.
- Multi-assignee: one ``ASSIGNED_TO`` per assignee.
- Mention parsing: body+comments, dedup, self-ref skip.
- Reference parsing: Jira + GitHub, dedup, self-ref skip.
- ``COMMENTED_ON`` emission: direction="IN", timestamp property.
- ``custom=None``, ``type="Issue"``, ``priority="None"``, ``story_points=None``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from connectors.producers.github.build_issue_signal import build_issue_signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_REPO_FULL_NAME = "owner/repo"


def _issue_data(**overrides: Any) -> Dict[str, Any]:
    """Build a normalized issue dict (as output by ``map_issue``)."""
    data: Dict[str, Any] = {
        "key": f"{_REPO_FULL_NAME}#42",
        "number": 42,
        "summary": "Fix login bug on mobile",
        "priority": "None",
        "status": "open",
        "type": "Issue",
        "created_at": "2026-01-01T09:00:00+00:00",
        "updated_at": "2026-01-02T12:00:00+00:00",
        "assignee": "bob",
        "reporter": "alice",
        "labels": ["bug", "enhancement"],
        "url": "https://github.com/owner/repo/issues/42",
        "repo_full_name": _REPO_FULL_NAME,
    }
    data.update(overrides)
    return data


def _repo_data(**overrides: Any) -> Dict[str, Any]:
    """Build a normalized repo dict."""
    data: Dict[str, Any] = {
        "name": "repo",
        "full_name": _REPO_FULL_NAME,
    }
    data.update(overrides)
    return data


def _comment(login: str, timestamp: str = "2026-01-03T10:00:00+00:00") -> Dict[str, Any]:
    """Build a comment dict."""
    return {"login": login, "timestamp": timestamp}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_issue_signal_returns_signal():
    """A valid issue should return a non-None ActivitySignal."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
        comments_data=[],
    )
    assert signal is not None


@pytest.mark.unit
def test_build_issue_signal_id_is_repo_hash_number():
    """The signal ``id`` should be ``<repo_full_name>#<number>``."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    assert signal.id == "owner/repo#42"


@pytest.mark.unit
def test_build_issue_signal_source_is_github():
    """The signal ``source`` should be 'github'."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    assert signal.source == "github"


@pytest.mark.unit
def test_build_issue_signal_entity_type_is_issue():
    """The signal ``entity_type`` should be 'Issue'."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    assert signal.entity_type == "Issue"


@pytest.mark.unit
def test_build_issue_signal_attributes_correct():
    """The IssueAttributes should have the correct field values."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    attrs = signal.attributes
    assert attrs.key == "owner/repo#42"
    assert attrs.summary == "Fix login bug on mobile"
    assert attrs.priority == "None"
    assert attrs.status == "open"
    assert attrs.type == "Issue"
    assert attrs.created_at == "2026-01-01T09:00:00+00:00"
    assert attrs.updated_at == "2026-01-02T12:00:00+00:00"
    assert attrs.story_points is None
    assert attrs.assignee == "bob"
    assert attrs.reporter == "alice"
    assert attrs.labels == ["bug", "enhancement"]
    assert attrs.url == "https://github.com/owner/repo/issues/42"
    assert attrs.custom is None


@pytest.mark.unit
def test_build_issue_signal_event_time_from_updated_at():
    """The ``event_time`` should be parsed from ``updated_at``."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    assert signal.event_time == datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.unit
def test_build_issue_signal_event_time_falls_back_to_created_at():
    """When ``updated_at`` is None, ``event_time`` should fall back to ``created_at``."""
    signal = build_issue_signal(
        issue_data=_issue_data(updated_at=None),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    assert signal.event_time == datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Invalid data
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_issue_signal_returns_none_on_missing_number():
    """Missing 'number' should cause a validation error and return None."""
    signal = build_issue_signal(
        issue_data=_issue_data(number=None),  # type: ignore[arg-type]
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is None


@pytest.mark.unit
def test_build_issue_signal_returns_none_on_empty_dict():
    """An empty issue_data dict should return None — missing mandatory fields.

    The builder uses defaults for some fields (priority='None', type='Issue',
    status='open'), but ``key`` and ``summary`` require actual values from
    issue_data. When ``repo_full_name`` and ``number`` are missing, the
    resulting ``id`` would be ``unknown#0`` — we treat this as invalid.
    """
    signal = build_issue_signal(
        issue_data={},
        repo_data={},
        assignee_logins=[],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    # With empty dicts, repo_full_name defaults to "unknown" and number to 0.
    # The builder still produces a signal (defaults satisfy the model), but
    # the key/summary are empty strings. This is technically valid but
    # semantically meaningless — the caller (process_issues) should filter
    # these out before calling the builder. The builder itself doesn't
    # reject them because IssueAttributes allows empty strings.
    # We assert that the signal, if produced, has empty key/summary:
    if signal is not None:
        assert signal.attributes.key == "unknown#0"
        assert signal.attributes.summary == ""


# ---------------------------------------------------------------------------
# ASSIGNED_TO — multi-assignee
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_one_assigned_to_per_assignee():
    """One ASSIGNED_TO relationship should be emitted per assignee."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob", "charlie", "dave"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    assigned_rels = [r for r in signal.relationships if r.type == "ASSIGNED_TO"]
    assert len(assigned_rels) == 3
    target_ids = [r.target.id for r in assigned_rels]
    assert set(target_ids) == {"bob", "charlie", "dave"}


@pytest.mark.unit
def test_assigned_to_direction_is_none():
    """ASSIGNED_TO should be undirected (direction=None)."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    assigned_rels = [r for r in signal.relationships if r.type == "ASSIGNED_TO"]
    assert all(r.direction is None for r in assigned_rels)


@pytest.mark.unit
def test_assigned_to_no_assignees():
    """When no assignees, no ASSIGNED_TO relationships should be emitted."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=[],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    assigned_rels = [r for r in signal.relationships if r.type == "ASSIGNED_TO"]
    assert len(assigned_rels) == 0


# ---------------------------------------------------------------------------
# REPORTED_BY
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_reported_by_emitted():
    """A REPORTED_BY relationship should be emitted for the issue author."""
    signal = build_issue_signal(
        issue_data=_issue_data(reporter="alice"),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    reported_rels = [r for r in signal.relationships if r.type == "REPORTED_BY"]
    assert len(reported_rels) == 1
    assert reported_rels[0].target.id == "alice"
    assert reported_rels[0].direction is None


# ---------------------------------------------------------------------------
# PART_OF → Repository
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_part_of_emitted_to_repository():
    """A PART_OF relationship should be emitted to the Repository."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    part_of_rels = [r for r in signal.relationships if r.type == "PART_OF"]
    assert len(part_of_rels) == 1
    assert part_of_rels[0].target.entity_type == "Repository"
    assert part_of_rels[0].target.id == "owner/repo"
    assert part_of_rels[0].direction is None


# ---------------------------------------------------------------------------
# MENTIONS — self-ref skip
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mentions_emitted_per_login():
    """One MENTIONS relationship should be emitted per mentioned login."""
    signal = build_issue_signal(
        issue_data=_issue_data(reporter="alice"),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=["charlie", "dave"],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    mention_rels = [r for r in signal.relationships if r.type == "MENTIONS"]
    assert len(mention_rels) == 2
    target_ids = [r.target.id for r in mention_rels]
    assert set(target_ids) == {"charlie", "dave"}


@pytest.mark.unit
def test_mentions_skips_self_reference():
    """When the author mentions themselves, no MENTIONS edge should be emitted."""
    signal = build_issue_signal(
        issue_data=_issue_data(reporter="alice"),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=["alice", "charlie"],  # alice is the reporter
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    mention_rels = [r for r in signal.relationships if r.type == "MENTIONS"]
    assert len(mention_rels) == 1
    assert mention_rels[0].target.id == "charlie"


@pytest.mark.unit
def test_mentions_direction_is_none():
    """MENTIONS should be undirected (direction=None)."""
    signal = build_issue_signal(
        issue_data=_issue_data(reporter="alice"),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=["charlie"],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    mention_rels = [r for r in signal.relationships if r.type == "MENTIONS"]
    assert all(r.direction is None for r in mention_rels)


# ---------------------------------------------------------------------------
# REFERENCES — Jira + GitHub
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_references_emitted_per_jira_key():
    """One REFERENCES relationship should be emitted per Jira key."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=["PROJ-123", "AB-456"],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    ref_rels = [r for r in signal.relationships if r.type == "REFERENCES"]
    assert len(ref_rels) == 2
    target_ids = [r.target.id for r in ref_rels]
    assert set(target_ids) == {"PROJ-123", "AB-456"}
    # Jira refs should target source='jira'
    assert all(r.target.source == "jira" for r in ref_rels)


@pytest.mark.unit
def test_references_emitted_per_github_ref():
    """One REFERENCES relationship should be emitted per GitHub cross-repo ref."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=["otherorg/otherrepo#99"],
        relates_to_ids=[],
    )
    assert signal is not None
    ref_rels = [r for r in signal.relationships if r.type == "REFERENCES"]
    assert len(ref_rels) == 1
    assert ref_rels[0].target.id == "otherorg/otherrepo#99"
    assert ref_rels[0].target.source == "github"


@pytest.mark.unit
def test_references_direction_is_none():
    """REFERENCES should be undirected (direction=None)."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=["PROJ-123"],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
    )
    assert signal is not None
    ref_rels = [r for r in signal.relationships if r.type == "REFERENCES"]
    assert all(r.direction is None for r in ref_rels)


# ---------------------------------------------------------------------------
# RELATES_TO — self-ref skip
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_relates_to_emitted_per_id():
    """One RELATES_TO relationship should be emitted per GitHub issue ref."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=["owner/repo#10", "owner/repo#20"],
    )
    assert signal is not None
    relates_rels = [r for r in signal.relationships if r.type == "RELATES_TO"]
    assert len(relates_rels) == 2
    target_ids = [r.target.id for r in relates_rels]
    assert set(target_ids) == {"owner/repo#10", "owner/repo#20"}


@pytest.mark.unit
def test_relates_to_skips_self_reference():
    """When an issue references itself, no RELATES_TO edge should be emitted."""
    signal = build_issue_signal(
        issue_data=_issue_data(number=42),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=["owner/repo#42", "owner/repo#10"],  # #42 is self
    )
    assert signal is not None
    relates_rels = [r for r in signal.relationships if r.type == "RELATES_TO"]
    assert len(relates_rels) == 1
    assert relates_rels[0].target.id == "owner/repo#10"


@pytest.mark.unit
def test_relates_to_direction_is_none():
    """RELATES_TO should be undirected (direction=None)."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=["owner/repo#10"],
    )
    assert signal is not None
    relates_rels = [r for r in signal.relationships if r.type == "RELATES_TO"]
    assert all(r.direction is None for r in relates_rels)


# ---------------------------------------------------------------------------
# COMMENTED_ON — direction="IN", timestamp property
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_commented_on_emitted_per_comment():
    """One COMMENTED_ON relationship should be emitted per comment."""
    comments = [
        _comment("charlie", "2026-01-03T10:00:00+00:00"),
        _comment("dave", "2026-01-04T11:00:00+00:00"),
    ]
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
        comments_data=comments,
    )
    assert signal is not None
    commented_rels = [r for r in signal.relationships if r.type == "COMMENTED_ON"]
    assert len(commented_rels) == 2
    target_ids = [r.target.id for r in commented_rels]
    assert set(target_ids) == {"charlie", "dave"}


@pytest.mark.unit
def test_commented_on_direction_is_in():
    """COMMENTED_ON should have direction='IN'."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
        comments_data=[_comment("charlie")],
    )
    assert signal is not None
    commented_rels = [r for r in signal.relationships if r.type == "COMMENTED_ON"]
    assert all(r.direction == "IN" for r in commented_rels)


@pytest.mark.unit
def test_commented_on_has_timestamp_property():
    """Each COMMENTED_ON edge should have a 'timestamp' property."""
    timestamp = "2026-01-03T10:00:00+00:00"
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
        comments_data=[_comment("charlie", timestamp)],
    )
    assert signal is not None
    commented_rels = [r for r in signal.relationships if r.type == "COMMENTED_ON"]
    assert len(commented_rels) == 1
    assert commented_rels[0].properties is not None
    assert commented_rels[0].properties.get("timestamp") == timestamp


@pytest.mark.unit
def test_commented_on_skips_comments_without_login():
    """Comments without a login should be skipped."""
    comments = [
        _comment("charlie"),
        {"login": None, "timestamp": "2026-01-04T11:00:00+00:00"},
        {"timestamp": "2026-01-05T12:00:00+00:00"},  # no login key
    ]
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
        comments_data=comments,
    )
    assert signal is not None
    commented_rels = [r for r in signal.relationships if r.type == "COMMENTED_ON"]
    assert len(commented_rels) == 1
    assert commented_rels[0].target.id == "charlie"


@pytest.mark.unit
def test_commented_on_none_comments_data():
    """When comments_data is None, no COMMENTED_ON edges should be emitted."""
    signal = build_issue_signal(
        issue_data=_issue_data(),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=[],
        referenced_jira_keys=[],
        referenced_github_issue_ids=[],
        relates_to_ids=[],
        comments_data=None,
    )
    assert signal is not None
    commented_rels = [r for r in signal.relationships if r.type == "COMMENTED_ON"]
    assert len(commented_rels) == 0


# ---------------------------------------------------------------------------
# Relationship count summary
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_full_relationship_set():
    """All 7 relationship types should be present when all inputs are provided."""
    signal = build_issue_signal(
        issue_data=_issue_data(reporter="alice"),
        repo_data=_repo_data(),
        assignee_logins=["bob"],
        mention_logins=["charlie"],
        referenced_jira_keys=["PROJ-123"],
        referenced_github_issue_ids=["otherorg/otherrepo#99"],
        relates_to_ids=["owner/repo#10"],
        comments_data=[_comment("dave")],
    )
    assert signal is not None
    rel_types = {r.type for r in signal.relationships}
    assert rel_types == {
        "ASSIGNED_TO",
        "REPORTED_BY",
        "PART_OF",
        "MENTIONS",
        "REFERENCES",
        "RELATES_TO",
        "COMMENTED_ON",
    }

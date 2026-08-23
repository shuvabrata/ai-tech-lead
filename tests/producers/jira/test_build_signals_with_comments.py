"""Unit tests for Phase 2 — Jira signal building with comments and mentions.

Tests that ``build_initiative_signal``, ``build_epic_signal``, and
``build_issue_signal`` emit:

- ``COMMENTED_ON`` edges (direction="IN", timestamp property) per comment.
- ``MENTIONS`` edges (direction=None) per @mentioned accountId, skipping
  self-mentions.

All tests are pure — no network I/O or database writes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from connectors.producers.jira.main import (
    build_epic_signal,
    build_initiative_signal,
    build_issue_signal,
)

_BASE_URL = "https://jira.example.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _initiative_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "key": "INI-1",
        "summary": "Initiative summary",
        "priority": "High",
        "status": "In Progress",
        "created_at": "2024-01-01",
        "updated_at": "2024-06-01",
        "duedate": "2024-12-31",
        "labels": None,
        "components": None,
        "url": f"{_BASE_URL}/browse/INI-1",
    }
    data.update(overrides)
    return data


def _epic_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "key": "EPIC-1",
        "summary": "Epic summary",
        "priority": "Medium",
        "status": "To Do",
        "created_at": "2024-01-01",
        "updated_at": "2024-06-01",
        "start_date": "2024-01-01",
        "due_date": "2024-12-31",
        "url": f"{_BASE_URL}/browse/EPIC-1",
    }
    data.update(overrides)
    return data


def _issue_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "key": "PROJ-10",
        "summary": "Fix bug",
        "priority": "High",
        "status": "In Progress",
        "type": "Story",
        "created_at": "2024-03-01T10:00:00",
        "updated_at": "2024-06-01T10:00:00",
        "story_points": 3,
        "url": f"{_BASE_URL}/browse/PROJ-10",
        "issue_links_raw": [],
    }
    data.update(overrides)
    return data


def _comments_data(*account_ids: str) -> List[Dict[str, Any]]:
    return [
        {"accountId": account_id, "timestamp": "2024-06-01T10:00:00.000+0000"}
        for account_id in account_ids
    ]


def _rels_of_type(signal: Any, rel_type: str) -> List[Any]:
    return [r for r in (signal.relationships or []) if r.type == rel_type]


# ---------------------------------------------------------------------------
# COMMENTED_ON edges
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCommentedOnEdges:
    def test_build_issue_signal_with_comments(self) -> None:
        """COMMENTED_ON edges emitted with direction="IN" and timestamp."""
        signal = build_issue_signal(
            _issue_data(),
            _BASE_URL,
            comments_data=_comments_data("alice", "bob"),
        )
        assert signal is not None
        edges = _rels_of_type(signal, "COMMENTED_ON")
        assert len(edges) == 2
        for edge in edges:
            assert edge.direction == "IN"
            assert edge.target.entity_type == "Person"
            assert edge.properties == {
                "timestamp": "2024-06-01T10:00:00.000+0000"
            }
        target_ids = {e.target.id for e in edges}
        assert target_ids == {"alice", "bob"}

    def test_build_epic_signal_with_comments(self) -> None:
        """Same for Epics."""
        signal = build_epic_signal(
            _epic_data(),
            _BASE_URL,
            comments_data=_comments_data("alice"),
        )
        assert signal is not None
        edges = _rels_of_type(signal, "COMMENTED_ON")
        assert len(edges) == 1
        assert edges[0].direction == "IN"
        assert edges[0].target.id == "alice"

    def test_build_initiative_signal_with_comments(self) -> None:
        """Same for Initiatives."""
        signal = build_initiative_signal(
            _initiative_data(),
            _BASE_URL,
            comments_data=_comments_data("carol"),
        )
        assert signal is not None
        edges = _rels_of_type(signal, "COMMENTED_ON")
        assert len(edges) == 1
        assert edges[0].direction == "IN"
        assert edges[0].target.id == "carol"

    def test_no_comments_means_no_edges(self) -> None:
        """comments_data=None → no COMMENTED_ON edges."""
        signal = build_issue_signal(_issue_data(), _BASE_URL)
        assert signal is not None
        assert _rels_of_type(signal, "COMMENTED_ON") == []

    def test_empty_comments_means_no_edges(self) -> None:
        """comments_data=[] → no COMMENTED_ON edges."""
        signal = build_issue_signal(_issue_data(), _BASE_URL, comments_data=[])
        assert signal is not None
        assert _rels_of_type(signal, "COMMENTED_ON") == []

    def test_skips_comment_without_accountid(self) -> None:
        """Comment with missing accountId → skipped."""
        comments = [
            {"accountId": "", "timestamp": "2024-06-01T00:00:00"},
            {"accountId": "alice", "timestamp": "2024-06-01T00:00:00"},
        ]
        signal = build_issue_signal(_issue_data(), _BASE_URL, comments_data=comments)
        assert signal is not None
        edges = _rels_of_type(signal, "COMMENTED_ON")
        assert len(edges) == 1
        assert edges[0].target.id == "alice"


# ---------------------------------------------------------------------------
# MENTIONS edges
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMentionsEdges:
    def test_build_issue_signal_with_mentions(self) -> None:
        """MENTIONS edges emitted with direction=None and accountId target."""
        signal = build_issue_signal(
            _issue_data(),
            _BASE_URL,
            reporter_person_id="reporter1",
            mention_account_ids=["alice", "bob"],
        )
        assert signal is not None
        edges = _rels_of_type(signal, "MENTIONS")
        assert len(edges) == 2
        for edge in edges:
            assert edge.direction is None
            assert edge.target.entity_type == "Person"
        assert {e.target.id for e in edges} == {"alice", "bob"}

    def test_skips_self_mentions(self) -> None:
        """Reporter mentioning themselves → skipped."""
        signal = build_issue_signal(
            _issue_data(),
            _BASE_URL,
            reporter_person_id="reporter1",
            mention_account_ids=["reporter1", "alice"],
        )
        assert signal is not None
        edges = _rels_of_type(signal, "MENTIONS")
        assert len(edges) == 1
        assert edges[0].target.id == "alice"

    def test_no_mentions_means_no_edges(self) -> None:
        """mention_account_ids=None → no MENTIONS edges."""
        signal = build_issue_signal(_issue_data(), _BASE_URL)
        assert signal is not None
        assert _rels_of_type(signal, "MENTIONS") == []

    def test_epic_mentions_skips_self(self) -> None:
        """Epic reporter self-mention is skipped."""
        signal = build_epic_signal(
            _epic_data(),
            _BASE_URL,
            reporter_person_id="reporter1",
            mention_account_ids=["reporter1", "bob"],
        )
        assert signal is not None
        edges = _rels_of_type(signal, "MENTIONS")
        assert len(edges) == 1
        assert edges[0].target.id == "bob"

    def test_initiative_mentions(self) -> None:
        """Initiative mentions emit MENTIONS edges."""
        signal = build_initiative_signal(
            _initiative_data(),
            _BASE_URL,
            reporter_person_id="reporter1",
            mention_account_ids=["alice"],
        )
        assert signal is not None
        edges = _rels_of_type(signal, "MENTIONS")
        assert len(edges) == 1
        assert edges[0].direction is None
        assert edges[0].target.id == "alice"


# ---------------------------------------------------------------------------
# No signal when comments/mentions empty (regression guard)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEmptyInputsStillBuildSignal:
    def test_issue_builds_without_comments_or_mentions(self) -> None:
        """Existing behaviour: a valid issue still builds without comments/mentions."""
        signal = build_issue_signal(_issue_data(), _BASE_URL, reporter_person_id="r1")
        assert signal is not None
        assert signal.id == "PROJ-10"

    def test_initiative_builds_without_comments_or_mentions(self) -> None:
        signal = build_initiative_signal(_initiative_data(), _BASE_URL)
        assert signal is not None
        assert signal.id == "INI-1"

    def test_epic_builds_without_comments_or_mentions(self) -> None:
        signal = build_epic_signal(_epic_data(), _BASE_URL)
        assert signal is not None
        assert signal.id == "EPIC-1"
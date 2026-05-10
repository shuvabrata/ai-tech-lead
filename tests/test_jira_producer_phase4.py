"""Unit tests for jira_producer.py (Phase 4).

Tests cover:
- Signal builder functions for each entity type.
- Validation failures return None (no signal emitted).
- Relationship generation.
- Text truncation on long fields.
- publish_signals wires fetch → map → publish correctly (mocked I/O).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.producers.jira_producer import (
    _SOURCE,
    _TEXT_MAX,
    _event_time_from,
    _truncate,
    build_epic_signal,
    build_initiative_signal,
    build_issue_signal,
    build_person_signal,
    build_project_signal,
    build_sprint_signal,
    publish_signals,
)

_BASE_URL = "https://jira.example.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": "project_jira_10001",
        "key": "PROJ",
        "name": "Test Project",
        "status": "Active",
        "project_type": "software",
        "url": f"{_BASE_URL}/browse/PROJ",
    }
    data.update(overrides)
    return data


def _user_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "account_id": "acc123",
        "display_name": "Alice Dev",
        "email": "alice@example.com",
    }
    data.update(overrides)
    return data


def _initiative_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": "initiative_jira_20001",
        "key": "PROJ-1",
        "summary": "Q1 Initiative",
        "priority": "High",
        "status": "In Progress",
        "created_at": "2024-01-01",
        "updated_at": "2024-06-01",
        "duedate": None,
        "labels": None,
        "components": None,
        "project_key": "PROJ",
        "url": f"{_BASE_URL}/browse/PROJ-1",
    }
    data.update(overrides)
    return data


def _epic_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": "epic_jira_30001",
        "key": "PROJ-2",
        "summary": "Epic Summary",
        "priority": "Medium",
        "status": "To Do",
        "created_at": "2024-02-01",
        "updated_at": "2024-06-01",
        "start_date": "2024-02-01",
        "due_date": "2024-03-31",
        "parent_jira_id": "20001",
        "team_value": "Team Alpha",
        "url": f"{_BASE_URL}/browse/PROJ-2",
    }
    data.update(overrides)
    return data


def _sprint_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": "sprint_jira_40001",
        "name": "Sprint 1",
        "status": "Active",
        "goal": "Ship feature X",
        "start_date": "2024-05-01",
        "end_date": "2024-05-14",
    }
    data.update(overrides)
    return data


def _issue_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": "issue_jira_50001",
        "key": "PROJ-10",
        "summary": "Fix the bug",
        "priority": "High",
        "status": "In Progress",
        "type": "Story",
        "created_at": "2024-03-01T10:00:00",
        "updated_at": "2024-06-01T10:00:00",
        "story_points": 3,
        "team_value": "Team Alpha",
        "parent_jira_id": "30001",
        "sprint_refs": [{"id": "40001", "name": "Sprint 1"}],
        "issue_links_raw": [],
        "epic_link_raw": None,
        "url": f"{_BASE_URL}/browse/PROJ-10",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Project signal
# ---------------------------------------------------------------------------


class TestBuildProjectSignal:
    def test_valid(self) -> None:
        sig = build_project_signal(_project_data(), _BASE_URL)
        assert sig is not None
        assert sig.source == "jira"
        assert sig.external_id == "project_jira_10001"
        assert sig.routing_key == "jira.Project"
        assert sig.attributes.entity_type == "Project"  # type: ignore[union-attr]

    def test_missing_id_returns_none(self) -> None:
        d = _project_data()
        del d["id"]
        sig = build_project_signal(d, _BASE_URL)
        assert sig is None

    def test_missing_key_returns_none(self) -> None:
        d = _project_data()
        del d["key"]
        sig = build_project_signal(d, _BASE_URL)
        assert sig is None

    def test_extra_fields_pass_through(self) -> None:
        sig = build_project_signal(_project_data(), _BASE_URL)
        assert sig is not None
        attrs = sig.attributes.model_dump()
        assert attrs["url"] == f"{_BASE_URL}/browse/PROJ"


# ---------------------------------------------------------------------------
# Person signal
# ---------------------------------------------------------------------------


class TestBuildPersonSignal:
    def test_valid(self) -> None:
        sig = build_person_signal(_user_data(), _BASE_URL)
        assert sig is not None
        assert sig.routing_key == "jira.Person"
        assert sig.external_id == "jira_person_acc123"

    def test_id_derived_from_account_id(self) -> None:
        sig = build_person_signal({"account_id": "xyz", "display_name": "Bob", "email": ""}, _BASE_URL)
        assert sig is not None
        assert sig.external_id == "jira_person_xyz"

    def test_extra_fields_email_and_account_id(self) -> None:
        sig = build_person_signal(_user_data(), _BASE_URL)
        assert sig is not None
        attrs = sig.attributes.model_dump()
        assert attrs["email"] == "alice@example.com"
        assert attrs["account_id"] == "acc123"


# ---------------------------------------------------------------------------
# Initiative signal
# ---------------------------------------------------------------------------


class TestBuildInitiativeSignal:
    def test_valid(self) -> None:
        sig = build_initiative_signal(_initiative_data(), _BASE_URL)
        assert sig is not None
        assert sig.routing_key == "jira.Initiative"
        assert sig.external_id == "initiative_jira_20001"

    def test_part_of_project_relationship(self) -> None:
        sig = build_initiative_signal(_initiative_data(), _BASE_URL, project_id="project_jira_10001")
        assert sig is not None
        assert len(sig.relationships) == 1
        rel = sig.relationships[0]
        assert rel.type == "PART_OF"
        assert rel.target.entity_type == "Project"
        assert rel.target.external_id == "project_jira_10001"

    def test_no_project_id_no_relationships(self) -> None:
        sig = build_initiative_signal(_initiative_data(), _BASE_URL, project_id=None)
        assert sig is not None
        assert sig.relationships == []

    def test_missing_id_returns_none(self) -> None:
        d = _initiative_data()
        del d["id"]
        sig = build_initiative_signal(d, _BASE_URL)
        assert sig is None

    def test_long_summary_truncated(self) -> None:
        sig = build_initiative_signal(_initiative_data(summary="x" * (_TEXT_MAX + 100)), _BASE_URL)
        assert sig is not None
        assert len(sig.attributes.model_dump()["summary"]) == _TEXT_MAX  # type: ignore[index]

    def test_event_time_from_updated_at(self) -> None:
        sig = build_initiative_signal(_initiative_data(updated_at="2024-06-15"), _BASE_URL)
        assert sig is not None
        assert sig.event_time.year == 2024
        assert sig.event_time.month == 6


# ---------------------------------------------------------------------------
# Epic signal
# ---------------------------------------------------------------------------


class TestBuildEpicSignal:
    def test_valid(self) -> None:
        sig = build_epic_signal(_epic_data(), _BASE_URL)
        assert sig is not None
        assert sig.routing_key == "jira.Epic"

    def test_part_of_initiative(self) -> None:
        sig = build_epic_signal(_epic_data(), _BASE_URL, initiative_id="initiative_jira_20001")
        assert sig is not None
        rel = sig.relationships[0]
        assert rel.type == "PART_OF"
        assert rel.target.entity_type == "Initiative"

    def test_part_of_project_when_no_initiative(self) -> None:
        sig = build_epic_signal(_epic_data(), _BASE_URL, initiative_id=None, project_id="project_jira_10001")
        assert sig is not None
        rel = sig.relationships[0]
        assert rel.type == "PART_OF"
        assert rel.target.entity_type == "Project"

    def test_no_rels_when_no_parent(self) -> None:
        sig = build_epic_signal(_epic_data(), _BASE_URL)
        assert sig is not None
        assert sig.relationships == []

    def test_missing_id_returns_none(self) -> None:
        d = _epic_data()
        del d["id"]
        sig = build_epic_signal(d, _BASE_URL)
        assert sig is None


# ---------------------------------------------------------------------------
# Sprint signal
# ---------------------------------------------------------------------------


class TestBuildSprintSignal:
    def test_valid(self) -> None:
        sig = build_sprint_signal(_sprint_data(), _BASE_URL)
        assert sig is not None
        assert sig.routing_key == "jira.Sprint"
        assert sig.external_id == "sprint_jira_40001"

    def test_missing_id_returns_none(self) -> None:
        d = _sprint_data()
        del d["id"]
        sig = build_sprint_signal(d, _BASE_URL)
        assert sig is None

    def test_missing_name_returns_none(self) -> None:
        d = _sprint_data()
        del d["name"]
        sig = build_sprint_signal(d, _BASE_URL)
        assert sig is None


# ---------------------------------------------------------------------------
# Issue signal
# ---------------------------------------------------------------------------


class TestBuildIssueSignal:
    def test_valid(self) -> None:
        sig = build_issue_signal(_issue_data(), _BASE_URL)
        assert sig is not None
        assert sig.routing_key == "jira.Issue"
        assert sig.external_id == "issue_jira_50001"

    def test_part_of_epic_relationship(self) -> None:
        sig = build_issue_signal(_issue_data(), _BASE_URL, epic_id="epic_jira_30001")
        assert sig is not None
        parts = [r for r in sig.relationships if r.type == "PART_OF" and r.target.entity_type == "Epic"]
        assert len(parts) == 1

    def test_in_sprint_relationship(self) -> None:
        sig = build_issue_signal(_issue_data(), _BASE_URL, sprint_ids=["sprint_jira_40001"])
        assert sig is not None
        sprints = [r for r in sig.relationships if r.type == "IN_SPRINT" and r.target.entity_type == "Sprint"]
        assert len(sprints) == 1
        assert sprints[0].target.external_id == "sprint_jira_40001"

    def test_multiple_sprints(self) -> None:
        sig = build_issue_signal(
            _issue_data(), _BASE_URL, sprint_ids=["sprint_jira_1", "sprint_jira_2"]
        )
        assert sig is not None
        sprints = [r for r in sig.relationships if r.type == "IN_SPRINT" and r.target.entity_type == "Sprint"]
        assert len(sprints) == 2

    def test_assigned_to_relationship(self) -> None:
        sig = build_issue_signal(_issue_data(), _BASE_URL, assignee_person_id="person_jira_acc123")
        assert sig is not None
        assigned = [r for r in sig.relationships if r.type == "ASSIGNED_TO"]
        assert len(assigned) == 1
        assert assigned[0].target.entity_type == "Person"
        assert assigned[0].target.external_id == "person_jira_acc123"

    def test_long_summary_truncated(self) -> None:
        sig = build_issue_signal(_issue_data(summary="S" * (_TEXT_MAX + 200)), _BASE_URL)
        assert sig is not None
        assert len(sig.attributes.model_dump()["summary"]) == _TEXT_MAX  # type: ignore[index]

    def test_missing_id_returns_none(self) -> None:
        d = _issue_data()
        del d["id"]
        sig = build_issue_signal(d, _BASE_URL)
        assert sig is None

    def test_missing_key_returns_none(self) -> None:
        d = _issue_data()
        del d["key"]
        sig = build_issue_signal(d, _BASE_URL)
        assert sig is None


# ---------------------------------------------------------------------------
# _event_time_from helper
# ---------------------------------------------------------------------------


class TestEventTimeFrom:
    def test_iso_string_parsed(self) -> None:
        ts = _event_time_from("2024-06-01T10:00:00", "")
        assert ts.year == 2024 and ts.month == 6 and ts.day == 1

    def test_falls_back_to_created_at(self) -> None:
        ts = _event_time_from("", "2024-01-15")
        assert ts.year == 2024 and ts.month == 1

    def test_returns_now_on_empty(self) -> None:
        ts = _event_time_from("", "")
        assert ts.year >= 2024

    def test_z_suffix_handled(self) -> None:
        ts = _event_time_from("2024-06-01T10:00:00Z", "")
        assert ts.tzinfo is not None


# ---------------------------------------------------------------------------
# _truncate helper
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_unchanged(self) -> None:
        assert _truncate("hello") == "hello"

    def test_long_truncated(self) -> None:
        assert len(_truncate("a" * (_TEXT_MAX + 500))) == _TEXT_MAX

    def test_non_string_converted(self) -> None:
        assert _truncate(123) == "123"


# ---------------------------------------------------------------------------
# publish_signals integration (fully mocked I/O)
# ---------------------------------------------------------------------------


class TestPublishSignals:
    """Verify publish_signals calls publish for each entity type."""

    def _raw_project(self) -> Dict[str, Any]:
        return {
            "id": "10001",
            "key": "PROJ",
            "name": "Test Project",
            "projectTypeKey": "software",
            "style": "classic",
        }

    def _raw_initiative(self) -> Dict[str, Any]:
        return {
            "id": "20001",
            "key": "PROJ-1",
            "fields": {
                "summary": "Q1 Initiative",
                "priority": {"name": "High"},
                "status": {"name": "In Progress"},
                "created": "2024-01-01T00:00:00",
                "updated": "2024-06-01T00:00:00",
                "project": {"key": "PROJ"},
                "issuetype": {"name": "Initiative"},
            },
        }

    def _raw_epic(self) -> Dict[str, Any]:
        return {
            "id": "30001",
            "key": "PROJ-2",
            "fields": {
                "summary": "Epic",
                "priority": {"name": "Medium"},
                "status": {"name": "To Do"},
                "created": "2024-02-01T00:00:00",
                "updated": "2024-06-01T00:00:00",
                "project": {"key": "PROJ"},
                "issuetype": {"name": "Epic"},
                "parent": None,
            },
        }

    def _raw_sprint(self) -> Dict[str, Any]:
        return {
            "id": 40001,
            "name": "Sprint 1",
            "state": "active",
            "goal": "",
            "startDate": "2024-05-01",
            "endDate": "2024-05-14",
        }

    def _raw_issue(self) -> Dict[str, Any]:
        return {
            "id": "50001",
            "key": "PROJ-10",
            "fields": {
                "summary": "Fix bug",
                "priority": {"name": "High"},
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Story"},
                "created": "2024-03-01T10:00:00",
                "updated": "2024-06-01T10:00:00",
                "assignee": {
                    "accountId": "acc123",
                    "displayName": "Alice Dev",
                    "emailAddress": "alice@example.com",
                },
                "parent": {"id": "30001", "fields": {"issuetype": {"name": "Epic"}}},
                "customfield_10020": [{"id": 40001, "name": "Sprint 1"}],
                "issuelinks": [],
            },
        }

    @pytest.mark.asyncio
    async def test_publishes_all_entity_types(self) -> None:
        publisher = AsyncMock()
        publisher.publish = AsyncMock()
        jira = MagicMock()

        with (
            patch("connectors.producers.jira_producer.fetch_projects", return_value=[self._raw_project()]),
            patch("connectors.producers.jira_producer.fetch_initiatives", return_value=[self._raw_initiative()]),
            patch("connectors.producers.jira_producer.fetch_epics", return_value=[self._raw_epic()]),
            patch("connectors.producers.jira_producer.fetch_issues", return_value=[self._raw_issue()]),
            patch("connectors.producers.jira_producer.fetch_sprints_by_ids", return_value=[self._raw_sprint()]),
        ):
            published = await publish_signals(publisher, jira, _BASE_URL, 90, 100)

        assert published.get("Project", 0) >= 1
        assert published.get("Initiative", 0) >= 1
        assert published.get("Epic", 0) >= 1
        assert published.get("Sprint", 0) >= 1
        assert published.get("Issue", 0) >= 1
        assert published.get("Person", 0) >= 1

    @pytest.mark.asyncio
    async def test_deduplicates_person_signals(self) -> None:
        """Same assignee on two issues should produce only one Person signal."""
        publisher = AsyncMock()
        publisher.publish = AsyncMock()
        jira = MagicMock()

        two_issues = [self._raw_issue(), {**self._raw_issue(), "id": "50002", "key": "PROJ-11"}]

        with (
            patch("connectors.producers.jira_producer.fetch_projects", return_value=[]),
            patch("connectors.producers.jira_producer.fetch_initiatives", return_value=[]),
            patch("connectors.producers.jira_producer.fetch_epics", return_value=[]),
            patch("connectors.producers.jira_producer.fetch_issues", return_value=two_issues),
            patch("connectors.producers.jira_producer.fetch_sprints_by_ids", return_value=[]),
        ):
            published = await publish_signals(publisher, jira, _BASE_URL, 90, 100)

        assert published.get("Person", 0) == 1

    @pytest.mark.asyncio
    async def test_empty_config_publishes_nothing(self) -> None:
        publisher = AsyncMock()
        publisher.publish = AsyncMock()
        jira = MagicMock()

        with (
            patch("connectors.producers.jira_producer.fetch_projects", return_value=[]),
            patch("connectors.producers.jira_producer.fetch_initiatives", return_value=[]),
            patch("connectors.producers.jira_producer.fetch_epics", return_value=[]),
            patch("connectors.producers.jira_producer.fetch_issues", return_value=[]),
            patch("connectors.producers.jira_producer.fetch_sprints_by_ids", return_value=[]),
        ):
            published = await publish_signals(publisher, jira, _BASE_URL, 90, 100)

        publisher.publish.assert_not_called()
        assert sum(published.values()) == 0

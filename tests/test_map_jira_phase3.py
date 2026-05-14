"""Unit tests for connectors.producers.map_jira (Phase 3).

All tests are pure: no network I/O, no database, no mocking required beyond
plain dicts.  Environment variables that control custom field IDs are patched
per-test where needed.
"""

import os
import pytest
from connectors.producers.map_jira import (
    extract_sprint_ids_from_issues,
    map_epic,
    map_initiative,
    map_issue,
    map_jira_user,
    map_project,
    map_sprint,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(
    issue_id="10001",
    key="PROJ-1",
    issue_type="Story",
    summary="A story",
    priority="Medium",
    status="Open",
    created="2024-01-15T10:00:00.000+0000",
    updated="2024-02-20T12:00:00.000+0000",
    extra_fields: dict | None = None,
) -> dict:
    fields: dict = {
        "summary": summary,
        "issuetype": {"name": issue_type},
        "priority": {"name": priority},
        "status": {"name": status},
        "created": created,
        "updated": updated,
        "issuelinks": [],
    }
    if extra_fields:
        fields.update(extra_fields)
    return {"id": issue_id, "key": key, "fields": fields}


# ---------------------------------------------------------------------------
# map_project
# ---------------------------------------------------------------------------


class TestMapProject:
    def test_id_formula(self):
        data = {"id": "12345", "key": "PROJ", "name": "My Project"}
        result = map_project(data)
        assert result["id"] == "jira_project_12345"

    def test_url_with_base_url(self):
        data = {"id": "1", "key": "PROJ", "name": "X"}
        result = map_project(data, "https://acme.atlassian.net")
        assert result["url"] == "https://acme.atlassian.net/browse/PROJ"

    def test_url_without_base_url(self):
        data = {"id": "1", "key": "PROJ", "name": "X"}
        result = map_project(data)
        assert result["url"] is None

    def test_project_type_empty_becomes_none(self):
        data = {"id": "1", "key": "PROJ", "name": "X", "projectTypeKey": ""}
        result = map_project(data)
        assert result["project_type"] is None

    def test_project_type_set(self):
        data = {"id": "1", "key": "PROJ", "name": "X", "projectTypeKey": "software"}
        result = map_project(data)
        assert result["project_type"] == "software"

    def test_status_active_when_style_set(self):
        data = {"id": "1", "key": "PROJ", "name": "X", "style": "next-gen"}
        result = map_project(data)
        assert result["status"] == "Active"

    def test_status_none_when_no_style(self):
        data = {"id": "1", "key": "PROJ", "name": "X"}
        result = map_project(data)
        assert result["status"] is None

    def test_trailing_slash_stripped_from_base_url(self):
        data = {"id": "1", "key": "PROJ", "name": "X"}
        result = map_project(data, "https://acme.atlassian.net/")
        assert result["url"] == "https://acme.atlassian.net/browse/PROJ"


# ---------------------------------------------------------------------------
# map_jira_user
# ---------------------------------------------------------------------------


class TestMapJiraUser:
    def test_basic_extraction(self):
        data = {
            "accountId": "abc123",
            "displayName": "Alice Smith",
            "emailAddress": "Alice@Example.com",
        }
        result = map_jira_user(data)
        assert result["account_id"] == "abc123"
        assert result["display_name"] == "Alice Smith"
        assert result["email"] == "alice@example.com"

    def test_email_lowercased(self):
        data = {"accountId": "x", "displayName": "X", "emailAddress": "X@TEST.ORG"}
        assert map_jira_user(data)["email"] == "x@test.org"

    def test_missing_email_returns_empty_string(self):
        data = {"accountId": "x", "displayName": "X"}
        assert map_jira_user(data)["email"] == ""

    def test_missing_account_id_returns_empty_string(self):
        data = {"displayName": "X", "emailAddress": "x@x.com"}
        assert map_jira_user(data)["account_id"] == ""


# ---------------------------------------------------------------------------
# map_initiative
# ---------------------------------------------------------------------------


class TestMapInitiative:
    def test_id_formula(self):
        data = _make_issue("20001", "INI-1", "Initiative")
        result = map_initiative(data)
        assert result["id"] == "jira_initiative_20001"

    def test_url_construction(self):
        data = _make_issue("20001", "INI-1", "Initiative")
        result = map_initiative(data, "https://acme.atlassian.net")
        assert result["url"] == "https://acme.atlassian.net/browse/INI-1"

    def test_date_truncation(self):
        data = _make_issue(
            "20001", "INI-1", "Initiative",
            created="2024-03-10T08:00:00.000+0000",
            updated="2024-04-01T09:00:00.000+0000",
        )
        result = map_initiative(data)
        assert result["created_at"] == "2024-03-10"
        assert result["updated_at"] == "2024-04-01"

    def test_labels_none_when_absent(self):
        data = _make_issue("20001", "INI-1", "Initiative")
        result = map_initiative(data)
        assert result["labels"] is None

    def test_labels_returned_when_present(self):
        data = _make_issue("20001", "INI-1", "Initiative", extra_fields={"labels": ["alpha", "beta"]})
        result = map_initiative(data)
        assert result["labels"] == ["alpha", "beta"]

    def test_components_none_when_absent(self):
        data = _make_issue("20001", "INI-1", "Initiative")
        result = map_initiative(data)
        assert result["components"] is None

    def test_project_key_extracted(self):
        data = _make_issue("20001", "INI-1", "Initiative", extra_fields={"project": {"key": "PROJ"}})
        result = map_initiative(data)
        assert result["project_key"] == "PROJ"


# ---------------------------------------------------------------------------
# map_epic
# ---------------------------------------------------------------------------


class TestMapEpic:
    def test_id_formula(self):
        data = _make_issue("30001", "EPIC-1", "Epic")
        result = map_epic(data)
        assert result["id"] == "jira_epic_30001"

    def test_default_start_date_is_created(self):
        data = _make_issue("30001", "EPIC-1", "Epic", created="2024-01-10T00:00:00.000+0000")
        result = map_epic(data)
        assert result["start_date"] == "2024-01-10"

    def test_custom_start_date_field(self, monkeypatch):
        monkeypatch.setenv("JIRA_EPIC_START_DATE_FIELD", "customfield_99999")
        data = _make_issue(
            "30001", "EPIC-1", "Epic",
            created="2024-01-10T00:00:00.000+0000",
            extra_fields={"customfield_99999": "2024-02-01T00:00:00.000+0000"},
        )
        result = map_epic(data)
        assert result["start_date"] == "2024-02-01"

    def test_due_date_field_default(self):
        data = _make_issue("30001", "EPIC-1", "Epic", extra_fields={"duedate": "2024-12-31"})
        result = map_epic(data)
        assert result["due_date"] == "2024-12-31"

    def test_due_date_empty_when_absent(self):
        data = _make_issue("30001", "EPIC-1", "Epic")
        result = map_epic(data)
        assert result["due_date"] == ""

    def test_parent_jira_id_extracted(self):
        data = _make_issue(
            "30001", "EPIC-1", "Epic",
            extra_fields={"parent": {"id": "20001", "key": "INI-1"}},
        )
        result = map_epic(data)
        assert result["parent_jira_id"] == "20001"

    def test_parent_jira_id_none_when_absent(self):
        data = _make_issue("30001", "EPIC-1", "Epic")
        result = map_epic(data)
        assert result["parent_jira_id"] is None

    def test_team_value_from_string_field(self):
        data = _make_issue("30001", "EPIC-1", "Epic", extra_fields={"Team": "Platform"})
        result = map_epic(data)
        assert result["team_value"] == "Platform"

    def test_team_value_from_dict_field_value_key(self):
        data = _make_issue("30001", "EPIC-1", "Epic", extra_fields={"Team": {"value": "Backend"}})
        result = map_epic(data)
        assert result["team_value"] == "Backend"

    def test_team_value_from_dict_field_name_key(self):
        data = _make_issue("30001", "EPIC-1", "Epic", extra_fields={"Team": {"name": "Frontend"}})
        result = map_epic(data)
        assert result["team_value"] == "Frontend"

    def test_team_value_none_when_absent(self):
        data = _make_issue("30001", "EPIC-1", "Epic")
        result = map_epic(data)
        assert result["team_value"] is None

    def test_custom_team_field(self, monkeypatch):
        monkeypatch.setenv("JIRA_EPIC_TEAM_FIELD", "squad")
        data = _make_issue("30001", "EPIC-1", "Epic", extra_fields={"squad": "Payments"})
        result = map_epic(data)
        assert result["team_value"] == "Payments"


# ---------------------------------------------------------------------------
# map_sprint
# ---------------------------------------------------------------------------


class TestMapSprint:
    def test_id_formula(self):
        data = {"id": 42, "name": "Sprint 1", "state": "active"}
        assert map_sprint(data)["id"] == "jira_sprint_42"

    def test_state_active(self):
        data = {"id": 1, "name": "S1", "state": "active"}
        assert map_sprint(data)["status"] == "Active"

    def test_state_closed_maps_to_completed(self):
        data = {"id": 1, "name": "S1", "state": "closed"}
        assert map_sprint(data)["status"] == "Completed"

    def test_state_future_maps_to_planned(self):
        data = {"id": 1, "name": "S1", "state": "future"}
        assert map_sprint(data)["status"] == "Planned"

    def test_unknown_state_preserved(self):
        data = {"id": 1, "name": "S1", "state": "WEIRD"}
        assert map_sprint(data)["status"] == "WEIRD"

    def test_date_truncation(self):
        data = {
            "id": 1, "name": "S1", "state": "active",
            "startDate": "2024-01-01T09:00:00.000Z",
            "endDate": "2024-01-14T17:00:00.000Z",
        }
        result = map_sprint(data)
        assert result["start_date"] == "2024-01-01"
        assert result["end_date"] == "2024-01-14"

    def test_url_is_none(self):
        data = {"id": 1, "name": "S1", "state": "active"}
        assert map_sprint(data)["url"] is None


# ---------------------------------------------------------------------------
# map_issue
# ---------------------------------------------------------------------------


class TestMapIssue:
    def test_id_formula(self):
        data = _make_issue("50001", "STORY-1")
        assert map_issue(data)["id"] == "jira_issue_STORY-1"

    def test_url_construction(self):
        data = _make_issue("50001", "STORY-1")
        result = map_issue(data, "https://acme.atlassian.net")
        assert result["url"] == "https://acme.atlassian.net/browse/STORY-1"

    def test_story_points_default_field(self):
        data = _make_issue("50001", "STORY-1", extra_fields={"customfield_10016": 5.0})
        assert map_issue(data)["story_points"] == 5

    def test_story_points_fallback_field(self):
        data = _make_issue("50001", "STORY-1", extra_fields={"customfield_10026": 3})
        assert map_issue(data)["story_points"] == 3

    def test_story_points_custom_env_var(self, monkeypatch):
        monkeypatch.setenv("JIRA_STORY_POINTS_FIELD_ID", "customfield_99999")
        data = _make_issue("50001", "STORY-1", extra_fields={"customfield_99999": 8})
        assert map_issue(data)["story_points"] == 8

    def test_story_points_zero_when_absent(self):
        data = _make_issue("50001", "STORY-1")
        assert map_issue(data)["story_points"] == 0

    def test_sprint_refs_extracted(self):
        sprint = {"id": 77, "name": "Sprint 3", "state": "active"}
        data = _make_issue(
            "50001", "STORY-1",
            extra_fields={"customfield_10020": [sprint]},
        )
        result = map_issue(data)
        assert result["sprint_refs"] == [{"id": "77", "name": "Sprint 3"}]

    def test_sprint_refs_custom_field(self, monkeypatch):
        monkeypatch.setenv("JIRA_SPRINT_FIELD_ID", "customfield_99800")
        sprint = {"id": 10, "name": "Sprint X"}
        data = _make_issue(
            "50001", "STORY-1",
            extra_fields={"customfield_99800": sprint},  # single object, not list
        )
        result = map_issue(data)
        assert result["sprint_refs"] == [{"id": "10", "name": "Sprint X"}]

    def test_sprint_refs_empty_when_none(self):
        data = _make_issue("50001", "STORY-1")
        assert map_issue(data)["sprint_refs"] == []

    def test_epic_link_raw_default_field(self):
        data = _make_issue("50001", "STORY-1", extra_fields={"customfield_10014": "EPIC-5"})
        assert map_issue(data)["epic_link_raw"] == "EPIC-5"

    def test_epic_link_raw_custom_field(self, monkeypatch):
        monkeypatch.setenv("JIRA_EPIC_LINK_FIELD_ID", "customfield_20000")
        data = _make_issue("50001", "STORY-1", extra_fields={"customfield_20000": "EPIC-7"})
        assert map_issue(data)["epic_link_raw"] == "EPIC-7"

    def test_epic_link_raw_none_when_absent(self):
        data = _make_issue("50001", "STORY-1")
        assert map_issue(data)["epic_link_raw"] is None

    def test_parent_jira_id_and_type(self):
        data = _make_issue(
            "50001", "STORY-1",
            extra_fields={
                "parent": {
                    "id": "30001",
                    "key": "EPIC-1",
                    "fields": {"issuetype": {"name": "Epic"}},
                }
            },
        )
        result = map_issue(data)
        assert result["parent_jira_id"] == "30001"
        assert result["parent_type"] == "Epic"

    def test_issue_links_raw_passthrough(self):
        link = {"type": {"name": "Blocks"}, "outwardIssue": {"id": "60001"}}
        data = _make_issue("50001", "STORY-1", extra_fields={"issuelinks": [link]})
        assert map_issue(data)["issue_links_raw"] == [link]

    def test_team_value_extracted(self):
        data = _make_issue("50001", "STORY-1", extra_fields={"Team": "Infra"})
        assert map_issue(data)["team_value"] == "Infra"

    def test_team_value_none_when_absent(self):
        data = _make_issue("50001", "STORY-1")
        assert map_issue(data)["team_value"] is None


# ---------------------------------------------------------------------------
# extract_sprint_ids_from_issues
# ---------------------------------------------------------------------------


class TestExtractSprintIds:
    def test_extracts_ids_from_default_field(self):
        issues = [
            _make_issue(extra_fields={"customfield_10020": [{"id": 1}, {"id": 2}]}),
            _make_issue(extra_fields={"customfield_10020": [{"id": 2}, {"id": 3}]}),
        ]
        result = extract_sprint_ids_from_issues(issues)
        assert result == {"1", "2", "3"}

    def test_respects_custom_env_var(self, monkeypatch):
        monkeypatch.setenv("JIRA_SPRINT_FIELD_ID", "customfield_99800")
        issues = [
            _make_issue(extra_fields={"customfield_99800": [{"id": 55}]}),
        ]
        result = extract_sprint_ids_from_issues(issues)
        assert result == {"55"}

    def test_handles_single_sprint_object(self):
        issues = [_make_issue(extra_fields={"customfield_10020": {"id": 7}})]
        result = extract_sprint_ids_from_issues(issues)
        assert result == {"7"}

    def test_empty_list_returns_empty_set(self):
        assert extract_sprint_ids_from_issues([]) == set()

    def test_issues_without_sprint_field_skipped(self):
        issues = [_make_issue()]
        assert extract_sprint_ids_from_issues(issues) == set()

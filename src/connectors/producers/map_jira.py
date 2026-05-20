"""Pure mapping (transformation) functions for the Jira connector.

All functions in this module are side-effect-free: they accept raw Jira API
response dicts and return plain ``dict`` values with normalised attributes.
No network I/O and no database writes occur here.

Custom-field IDs vary across Jira Cloud instances.  The functions below
resolve configurable field names via environment variables so the caller
never needs to hard-code instance-specific IDs (see TODO.md):

  - ``JIRA_SPRINT_FIELD_ID``        (default: ``customfield_10020``)
  - ``JIRA_STORY_POINTS_FIELD_ID``  (default: tries ``customfield_10016``,
                                     ``customfield_10026``, ``story_points``)
  - ``JIRA_EPIC_LINK_FIELD_ID``     (default: ``customfield_10014``)
  - ``JIRA_EPIC_TEAM_FIELD``        (default: ``Team``)
  - ``JIRA_ISSUE_TEAM_FIELD``       (default: ``Team``)
  - ``JIRA_EPIC_START_DATE_FIELD``  (default: ``created``)
  - ``JIRA_EPIC_DUE_DATE_FIELD``    (default: ``duedate``)

Phase 3: These utilities replace inline transformation logic that was
embedded in the legacy Jira handler modules.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Private field-name helpers (resolved at call time for testability)
# ---------------------------------------------------------------------------


def _sprint_field_id() -> str:
    return os.getenv("JIRA_SPRINT_FIELD_ID", "customfield_10020")


def _story_points_field_ids() -> List[str]:
    custom = os.getenv("JIRA_STORY_POINTS_FIELD_ID", "")
    defaults = ["customfield_10016", "customfield_10026", "story_points"]
    return ([custom] + defaults) if custom else defaults


def _epic_link_field_id() -> str:
    return os.getenv("JIRA_EPIC_LINK_FIELD_ID", "customfield_10014")


def _epic_team_field() -> str:
    return os.getenv("JIRA_EPIC_TEAM_FIELD", "Team")


def _issue_team_field() -> str:
    return os.getenv("JIRA_ISSUE_TEAM_FIELD", "Team")


def _epic_start_date_field() -> str:
    return os.getenv("JIRA_EPIC_START_DATE_FIELD", "created")


def _epic_due_date_field() -> str:
    return os.getenv("JIRA_EPIC_DUE_DATE_FIELD", "duedate")


def _date(value: Optional[str]) -> str:
    """Extract the ``YYYY-MM-DD`` portion from an ISO datetime string or return
    an empty string when the value is absent."""
    return value[:10] if value else ""


def _team_from_field(field_value: Any) -> Optional[str]:
    """Normalise a Jira team field value (string, object, or None)."""
    if not field_value:
        return None
    if isinstance(field_value, dict):
        return field_value.get("value") or field_value.get("name")
    return str(field_value)


# ---------------------------------------------------------------------------
# Sprint ID extraction (shared by fetch layer — pure, no I/O)
# ---------------------------------------------------------------------------


def extract_sprint_ids_from_issues(issues: List[Dict[str, Any]]) -> Set[str]:
    """Extract the unique Jira sprint IDs referenced by a list of issues.

    Respects the ``JIRA_SPRINT_FIELD_ID`` environment variable so the correct
    custom field is checked on instances that use a non-default ID.

    Args:
        issues: List of raw Jira issue dicts.

    Returns:
        Set of sprint ID strings.
    """
    sprint_field_id = _sprint_field_id()
    sprint_ids: Set[str] = set()

    for issue_data in issues:
        fields = issue_data.get("fields", {})
        sprint_field = fields.get("sprint") or fields.get(sprint_field_id, [])
        if sprint_field:
            sprints = sprint_field if isinstance(sprint_field, list) else [sprint_field]
            for sprint in sprints:
                if isinstance(sprint, dict):
                    sid = sprint.get("id")
                    if sid:
                        sprint_ids.add(str(sid))

    return sprint_ids


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


def map_project(
    project_data: Dict[str, Any],
    jira_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract and normalise Jira project attributes.

    Args:
        project_data: Raw project dict from the Jira REST API.
        jira_base_url: Base URL of the Jira instance, used for URL generation.

    Returns:
        Dict with keys: ``id``, ``key``, ``name``, ``status``,
        ``project_type``, ``url``.
    """
    jira_project_id = project_data.get("id")
    project_key = project_data.get("key", "")
    project_name = project_data.get("name", "")
    project_type = project_data.get("projectTypeKey", "")
    style = project_data.get("style", "")
    status = "Active" if style else None

    url: Optional[str] = None
    if jira_base_url and project_key:
        url = f"{jira_base_url.rstrip('/')}/browse/{project_key}"

    return {
        "project_id": str(jira_project_id) if jira_project_id is not None else "",
        "project_key": project_key,
        "project_name": project_name,
        "status": status,
        "project_type": project_type or None,
        "url": url,
    }


# ---------------------------------------------------------------------------
# Jira user
# ---------------------------------------------------------------------------


def map_jira_user(user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and normalise a Jira user dict.

    Email is always lower-cased at the source for case-insensitive identity
    resolution downstream.

    Args:
        user_data: Raw Jira user object (``accountId``, ``displayName``,
            ``emailAddress``).

    Returns:
        Dict with keys: ``account_id``, ``display_name``, ``email``.
    """
    account_id = user_data.get("accountId", "")
    display_name = user_data.get("displayName", "")
    email = (user_data.get("emailAddress") or "").lower()

    return {
        "account_id": account_id,
        "display_name": display_name,
        "email": email,
    }


# ---------------------------------------------------------------------------
# Initiative
# ---------------------------------------------------------------------------


def map_initiative(
    issue_data: Dict[str, Any],
    jira_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract and normalise Jira initiative attributes.

    Args:
        issue_data: Raw Jira issue dict (issuetype = Initiative).
        jira_base_url: Base URL of the Jira instance.

    Returns:
        Dict with keys: ``id``, ``key``, ``summary``, ``priority``,
        ``status``, ``created_at``, ``updated_at``, ``duedate``,
        ``labels``, ``components``, ``project_key``, ``url``.
    """
    issue_id = issue_data.get("id", "")
    issue_key = issue_data.get("key", "")
    fields = issue_data.get("fields", {})

    priority_obj = fields.get("priority") or {}
    status_obj = fields.get("status") or {}
    components_obj = fields.get("components") or []
    project_obj = fields.get("project") or {}

    url: Optional[str] = None
    if jira_base_url and issue_key:
        url = f"{jira_base_url.rstrip('/')}/browse/{issue_key}"

    return {
        "key": issue_key,
        "summary": fields.get("summary", ""),
        "priority": priority_obj.get("name", "None"),
        "status": status_obj.get("name", "Unknown"),
        "created_at": _date(fields.get("created")),
        "updated_at": _date(fields.get("updated")),
        "duedate": fields.get("duedate"),
        "labels": fields.get("labels") or None,
        "components": [c.get("name", "") for c in components_obj if c.get("name")] or None,
        "project_key": project_obj.get("key"),
        "url": url,
    }


# ---------------------------------------------------------------------------
# Epic
# ---------------------------------------------------------------------------


def map_epic(
    issue_data: Dict[str, Any],
    jira_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract and normalise Jira epic attributes.

    Resolves configurable custom fields for start/due dates and team via
    environment variables (``JIRA_EPIC_START_DATE_FIELD``,
    ``JIRA_EPIC_DUE_DATE_FIELD``, ``JIRA_EPIC_TEAM_FIELD``).

    Args:
        issue_data: Raw Jira issue dict (issuetype = Epic).
        jira_base_url: Base URL of the Jira instance.

    Returns:
        Dict with keys: ``id``, ``key``, ``summary``, ``priority``,
        ``status``, ``start_date``, ``due_date``, ``created_at``,
        ``updated_at``, ``url``, ``parent_jira_id``, ``team_value``.
    """
    issue_id = issue_data.get("id", "")
    issue_key = issue_data.get("key", "")
    fields = issue_data.get("fields", {})

    priority_obj = fields.get("priority") or {}
    status_obj = fields.get("status") or {}
    created_at = _date(fields.get("created"))
    updated_at = _date(fields.get("updated"))

    start_date_field = _epic_start_date_field()
    if start_date_field == "created":
        start_date = created_at
    else:
        start_date = _date(fields.get(start_date_field)) or created_at

    due_date_field = _epic_due_date_field()
    due_date = _date(fields.get(due_date_field))

    parent_obj = fields.get("parent") or {}
    parent_jira_id = parent_obj.get("id")

    url: Optional[str] = None
    if jira_base_url and issue_key:
        url = f"{jira_base_url.rstrip('/')}/browse/{issue_key}"

    return {
        "id": f"jira_epic_{issue_id}",
        "key": issue_key,
        "summary": fields.get("summary", ""),
        "priority": priority_obj.get("name", "None"),
        "status": status_obj.get("name", "Unknown"),
        "start_date": start_date or created_at,
        "due_date": due_date or "",
        "created_at": created_at,
        "updated_at": updated_at,
        "url": url,
        "parent_jira_id": parent_jira_id,
        "team_value": _team_from_field(fields.get(_epic_team_field())),
    }


# ---------------------------------------------------------------------------
# Sprint
# ---------------------------------------------------------------------------


def map_sprint(sprint_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and normalise Jira sprint attributes.

    Args:
        sprint_data: Raw sprint dict from the Jira Agile API.

    Returns:
        Dict with keys: ``id``, ``name``, ``goal``, ``start_date``,
        ``end_date``, ``status``, ``url``.
    """
    jira_sprint_id = sprint_data.get("id")
    sprint_name = sprint_data.get("name", "")
    state = sprint_data.get("state", "Unknown")

    status_map = {
        "active": "Active",
        "closed": "Completed",
        "future": "Planned",
    }
    status = status_map.get(state.lower(), state)

    return {
        "id": f"jira_sprint_{jira_sprint_id}",
        "name": sprint_name,
        "goal": sprint_data.get("goal", ""),
        "start_date": _date(sprint_data.get("startDate")),
        "end_date": _date(sprint_data.get("endDate")),
        "status": status,
        "url": None,  # Sprint browse URLs require board ID; left for future enrichment
    }


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------


def map_issue(
    issue_data: Dict[str, Any],
    jira_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract and normalise Jira issue attributes and relationship hints.

    Resolves story-point and sprint custom fields via environment variables
    (``JIRA_STORY_POINTS_FIELD_ID``, ``JIRA_SPRINT_FIELD_ID``,
    ``JIRA_EPIC_LINK_FIELD_ID``, ``JIRA_ISSUE_TEAM_FIELD``).

    Args:
        issue_data: Raw Jira issue dict.
        jira_base_url: Base URL of the Jira instance.

    Returns:
        Dict with node attribute keys (``id``, ``key``, ``type``,
        ``summary``, ``priority``, ``status``, ``story_points``,
        ``created_at``, ``updated_at``, ``url``) plus relationship-hint
        keys consumed by the handler:

        - ``epic_link_raw`` — raw epic-link key/ID for legacy field lookup
        - ``parent_jira_id`` — parent issue Jira ID (newer Jira hierarchy)
        - ``parent_type`` — parent issue type name (e.g. ``"Epic"``)
        - ``sprint_refs`` — list of ``{"id": str, "name": str}`` dicts
        - ``issue_links_raw`` — raw ``issuelinks`` list for handler
        - ``team_value`` — team string or ``None``
    """
    jira_issue_id = issue_data.get("id", "")
    issue_key = issue_data.get("key", "")
    fields = issue_data.get("fields", {})

    issue_type_obj = fields.get("issuetype") or {}
    priority_obj = fields.get("priority") or {}
    status_obj = fields.get("status") or {}

    # Story points — try configurable + common field names
    story_points = 0
    for field_name in _story_points_field_ids():
        raw = fields.get(field_name)
        if raw is not None:
            try:
                story_points = int(float(raw))
                break
            except (ValueError, TypeError):
                pass

    url: Optional[str] = None
    if jira_base_url and issue_key:
        url = f"{jira_base_url.rstrip('/')}/browse/{issue_key}"

    # Sprint refs — resolve via configurable field ID
    sprint_field_id = _sprint_field_id()
    sprint_raw = fields.get("sprint") or fields.get(sprint_field_id, [])
    sprint_list = sprint_raw if isinstance(sprint_raw, list) else ([sprint_raw] if sprint_raw else [])
    sprint_refs = [
        {"id": str(s["id"]), "name": s.get("name", "")}
        for s in sprint_list
        if isinstance(s, dict) and s.get("id")
    ]

    # Parent info (newer Jira hierarchy)
    parent_obj = fields.get("parent") or {}
    parent_jira_id: Optional[str] = parent_obj.get("id")
    parent_type: str = (parent_obj.get("fields") or {}).get("issuetype", {}).get("name", "")

    return {
        # Node attributes
        "id": f"jira_issue_{issue_key}",
        "key": issue_key,
        "type": issue_type_obj.get("name", "Unknown"),
        "summary": fields.get("summary", ""),
        "priority": priority_obj.get("name", "None"),
        "status": status_obj.get("name", "Unknown"),
        "story_points": story_points,
        "created_at": fields.get("created", ""),
        "updated_at": fields.get("updated", ""),
        "url": url,
        # Relationship hints
        "epic_link_raw": fields.get(_epic_link_field_id()),
        "parent_jira_id": parent_jira_id,
        "parent_type": parent_type,
        "sprint_refs": sprint_refs,
        "issue_links_raw": fields.get("issuelinks", []),
        "team_value": _team_from_field(fields.get(_issue_team_field())),
    }

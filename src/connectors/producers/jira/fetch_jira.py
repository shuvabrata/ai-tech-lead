"""Pure Jira API fetching functions for the Jira connector.

All functions in this module perform network I/O against the Jira REST and
Agile APIs.  No data transformation and no database writes occur here — those
responsibilities belong to ``map_jira.py`` and the legacy handler modules
respectively.

Phase 3: These utilities replace the fetch functions that were previously
defined inside ``src/connectors/modules/jira/main.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from common.logger import logger
from connectors.producers.github.retry_with_backoff import retry_with_backoff


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def resolve_lookback_cutoff(lookback_days: int) -> str:
    """Return a ``YYYY-MM-DD`` string representing the lookback cutoff date.

    Args:
        lookback_days: Number of days to look back from today.

    Returns:
        ISO date string, e.g. ``"2024-01-15"``.
    """
    return (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")


def resolve_jql_date_field(
    lookback_days: int,
    last_synced_at: Optional[datetime],
) -> tuple[str, str]:
    """Return ``(field_name, date_string)`` for JQL date filtering.

    On the first run (no sync cursor) the function filters by ``created`` so we
    backfill existing work items within the lookback window.  On incremental
    runs it filters by ``updated`` so entities with new comments, edits, or
    transitions are re-fetched and their snapshot relationships refreshed.

    JQL accepts bare date literals (``2025-08-23``) but a date **with a time
    component** must be quoted (``"2026-08-22 04:07"``), otherwise the parser
    treats the time as a stray token.  The incremental value is therefore
    returned with surrounding double quotes.

    Args:
        lookback_days:  Number of days to look back on the first run.
        last_synced_at: Sync cursor timestamp, or ``None`` on first run.

    Returns:
        ``(field_name, date_string)`` where *date_string* is already in a
        JQL-parseable format.
    """
    if last_synced_at is None:
        return "created", resolve_lookback_cutoff(lookback_days)
    return "updated", f'"{last_synced_at.strftime("%Y-%m-%d %H:%M")}"'


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def fetch_projects(jira: Any, max_results_per_page: int = 100) -> List[Dict[str, Any]]:
    """Fetch all projects from Jira using pagination.

    Args:
        jira: Authenticated ``atlassian.Jira`` connection object.
        max_results_per_page: Page size for the search API.

    Returns:
        List of raw Jira project dicts.
    """
    try:
        logger.info("Fetching Jira projects...")

        all_projects: List[Dict[str, Any]] = []
        start_at = 0

        while True:
            params = {
                "startAt": start_at,
                "maxResults": max_results_per_page,
            }
            projects = jira.get("rest/api/3/project/search", params=params)

            if not projects or "values" not in projects:
                break

            batch = projects["values"]
            if not batch:
                break

            all_projects.extend(batch)
            logger.info(f"  Fetched {len(batch)} projects (total: {len(all_projects)})")

            total = projects.get("total", 0)
            if len(all_projects) >= total:
                break

            start_at += len(batch)

        logger.info(f"Found {len(all_projects)} total projects")
        return all_projects

    except Exception as e:
        logger.error(f"Error fetching projects: {e}")
        logger.exception(e)
        return []


# ---------------------------------------------------------------------------
# Initiatives
# ---------------------------------------------------------------------------


def fetch_initiatives(
    jira: Any,
    lookback_days: int = 90,
    max_results_per_page: int = 100,
    last_synced_at: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Fetch initiatives from Jira created (or updated, on incremental runs)
    since the lookback cutoff or the sync cursor.

    Args:
        jira: Authenticated ``atlassian.Jira`` connection object.
        lookback_days: How far back to search on the first run.
        max_results_per_page: Page size for the JQL search.
        last_synced_at: Sync cursor timestamp; when present, ``updated >=`` is
            used so entities with new comment activity are re-fetched.

    Returns:
        List of raw Jira issue dicts (issuetype = Initiative).
    """
    try:
        date_field, date_str = resolve_jql_date_field(lookback_days, last_synced_at)
        jql = f"issuetype = Initiative AND {date_field} >= {date_str} ORDER BY created DESC"

        logger.info(f"Fetching initiatives {date_field} since {date_str}...")
        logger.info(f"Executing JQL: {jql}")

        all_initiatives: List[Dict[str, Any]] = []
        next_page_token = None

        while True:
            response = jira.enhanced_jql(
                jql=jql,
                nextPageToken=next_page_token,
                limit=max_results_per_page,
            )

            if not response or "issues" not in response:
                break

            batch = response["issues"]
            if not batch:
                break

            all_initiatives.extend(batch)
            logger.info(f"  Fetched {len(batch)} initiatives (total: {len(all_initiatives)})")

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        logger.info(f"Found {len(all_initiatives)} total initiatives")
        return all_initiatives

    except Exception as e:
        logger.error(f"Error fetching initiatives: {e}")
        logger.exception(e)
        return []


# ---------------------------------------------------------------------------
# Epics
# ---------------------------------------------------------------------------


def fetch_epics(
    jira: Any,
    lookback_days: int = 90,
    max_results_per_page: int = 100,
    last_synced_at: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Fetch epics from Jira created (or updated, on incremental runs) since
    the lookback cutoff or the sync cursor.

    Args:
        jira: Authenticated ``atlassian.Jira`` connection object.
        lookback_days: How far back to search on the first run.
        max_results_per_page: Page size for the JQL search.
        last_synced_at: Sync cursor timestamp; when present, ``updated >=`` is
            used so entities with new comment activity are re-fetched.

    Returns:
        List of raw Jira issue dicts (issuetype = Epic).
    """
    try:
        date_field, date_str = resolve_jql_date_field(lookback_days, last_synced_at)
        jql = f"issuetype = Epic AND {date_field} >= {date_str} ORDER BY created DESC"

        logger.info(f"Fetching epics {date_field} since {date_str}...")
        logger.info(f"Executing JQL: {jql}")

        all_epics: List[Dict[str, Any]] = []
        next_page_token = None

        while True:
            response = jira.enhanced_jql(
                jql=jql,
                nextPageToken=next_page_token,
                limit=max_results_per_page,
            )

            if not response or "issues" not in response:
                break

            batch = response["issues"]
            if not batch:
                break

            all_epics.extend(batch)
            logger.info(f"  Fetched {len(batch)} epics (total: {len(all_epics)})")

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        logger.info(f"Found {len(all_epics)} total epics")
        return all_epics

    except Exception as e:
        logger.error(f"Error fetching epics: {e}")
        logger.exception(e)
        return []


# ---------------------------------------------------------------------------
# Sprints
# ---------------------------------------------------------------------------


def fetch_sprints_by_ids(
    jira: Any,
    sprint_ids: Set[str],
) -> List[Dict[str, Any]]:
    """Fetch specific sprints by their Jira Agile sprint IDs.

    Args:
        jira: Authenticated ``atlassian.Jira`` connection object.
        sprint_ids: Set of sprint ID strings to fetch.

    Returns:
        List of raw sprint dicts from the Agile API.
    """
    if not sprint_ids:
        logger.info("No sprint IDs to fetch")
        return []

    try:
        logger.info(f"Fetching {len(sprint_ids)} sprint(s) referenced by issues...")

        sprints: List[Dict[str, Any]] = []
        fetched_count = 0
        failed_count = 0

        for sprint_id in sprint_ids:
            try:
                sprint_response = jira.get(f"rest/agile/1.0/sprint/{sprint_id}")

                if sprint_response:
                    sprints.append(sprint_response)
                    fetched_count += 1
                    logger.debug(
                        f"  ✓ Fetched sprint {sprint_id}: {sprint_response.get('name', 'Unknown')}"
                    )
                else:
                    logger.warning(f"  ✗ Sprint {sprint_id} not found")
                    failed_count += 1

            except Exception as e:
                logger.warning(f"  ✗ Could not fetch sprint {sprint_id}: {e}")
                failed_count += 1

        logger.info(f"  ✓ Successfully fetched {fetched_count} sprint(s)")
        if failed_count > 0:
            logger.warning(f"  ✗ Failed to fetch {failed_count} sprint(s)")

        return sprints

    except Exception as e:
        logger.error(f"Error fetching sprints by IDs: {e}")
        logger.exception(e)
        return []


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


def fetch_issues(
    jira: Any,
    lookback_days: int = 90,
    max_results_per_page: int = 100,
    last_synced_at: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Fetch all issues (excluding Initiatives and Epics) created, or updated
    on incremental runs, since the lookback cutoff or the sync cursor.

    Args:
        jira: Authenticated ``atlassian.Jira`` connection object.
        lookback_days: How far back to search on the first run.
        max_results_per_page: Page size for the JQL search.
        last_synced_at: Sync cursor timestamp; when present, ``updated >=`` is
            used so entities with new comment activity are re-fetched.

    Returns:
        List of raw Jira issue dicts.
    """
    try:
        date_field, date_str = resolve_jql_date_field(lookback_days, last_synced_at)
        jql = (
            f"{date_field} >= {date_str} "
            "AND issuetype NOT IN (Initiative, Epic) "
            "ORDER BY created DESC"
        )

        logger.info(
            f"Fetching issues (excluding Initiatives and Epics) {date_field} since {date_str}..."
        )
        logger.info(f"Executing JQL: {jql}")

        all_issues: List[Dict[str, Any]] = []
        next_page_token = None

        while True:
            response = jira.enhanced_jql(
                jql=jql,
                nextPageToken=next_page_token,
                limit=max_results_per_page,
            )

            if not response or "issues" not in response:
                break

            batch = response["issues"]
            if not batch:
                break

            all_issues.extend(batch)
            logger.info(f"  Fetched {len(batch)} issues (total: {len(all_issues)})")

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        logger.info(f"Found {len(all_issues)} total issues")
        return all_issues

    except Exception as e:
        logger.error(f"Error fetching issues: {e}")
        logger.exception(e)
        return []


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def fetch_comments(
    jira: Any,
    issue_id_or_key: str,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """Fetch all comments for a Jira issue.

    Uses the cursor-based pagination provided by the ``startAt`` parameter of
    ``GET /rest/api/3/issue/{issueIdOrKey}/comment``.  Each comment dict
    contains the keys ``id``, ``author`` (a user object with ``accountId`` /
    ``displayName`` / ``emailAddress``), ``body`` (ADF JSON), ``created``, and
    ``updated``.

    Args:
        jira: Authenticated ``atlassian.Jira`` connection object.
        issue_id_or_key: Jira issue ID or key, e.g. ``"PROJ-123"``.
        max_results: Page size for the comment search API.

    Returns:
        List of raw comment dicts, or ``[]`` on error or when the issue has no
        comments.
    """
    try:
        all_comments: List[Dict[str, Any]] = []
        start_at = 0

        while True:
            params = {
                "startAt": start_at,
                "maxResults": max_results,
            }
            # Retry rate-limit (HTTP 429) responses with exponential backoff so
            # comment fetches are not silently dropped on a busy instance.
            response = retry_with_backoff(
                lambda: jira.get(
                    f"rest/api/3/issue/{issue_id_or_key}/comment", params=params
                )
            )

            if not response or "comments" not in response:
                break

            batch = response["comments"]
            if not batch:
                break

            all_comments.extend(batch)

            total = response.get("total", 0)
            if len(all_comments) >= total:
                break

            start_at += len(batch)

        logger.debug(
            "Fetched %d comments for issue %s", len(all_comments), issue_id_or_key
        )
        return all_comments

    except Exception as e:
        logger.error(f"Error fetching comments for {issue_id_or_key}: {e}")
        logger.exception(e)
        return []

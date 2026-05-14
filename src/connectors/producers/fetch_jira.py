"""Pure Jira API fetching functions for the Jira connector.

All functions in this module perform network I/O against the Jira REST and
Agile APIs.  No data transformation and no database writes occur here — those
responsibilities belong to ``map_jira.py`` and the legacy handler modules
respectively.

Phase 3: These utilities replace the fetch functions that were previously
defined inside ``src/connectors/modules/jira/main.py``.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Set

from connectors.commons.logger import logger


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
) -> List[Dict[str, Any]]:
    """Fetch initiatives from Jira created in the last *lookback_days* days.

    Args:
        jira: Authenticated ``atlassian.Jira`` connection object.
        lookback_days: How far back to search.
        max_results_per_page: Page size for the JQL search.

    Returns:
        List of raw Jira issue dicts (issuetype = Initiative).
    """
    try:
        cutoff_date_str = resolve_lookback_cutoff(lookback_days)
        jql = f"issuetype = Initiative AND created >= {cutoff_date_str} ORDER BY created DESC"

        logger.info(f"Fetching initiatives created since {cutoff_date_str}...")
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
) -> List[Dict[str, Any]]:
    """Fetch epics from Jira created in the last *lookback_days* days.

    Args:
        jira: Authenticated ``atlassian.Jira`` connection object.
        lookback_days: How far back to search.
        max_results_per_page: Page size for the JQL search.

    Returns:
        List of raw Jira issue dicts (issuetype = Epic).
    """
    try:
        cutoff_date_str = resolve_lookback_cutoff(lookback_days)
        jql = f"issuetype = Epic AND created >= {cutoff_date_str} ORDER BY created DESC"

        logger.info(f"Fetching epics created since {cutoff_date_str}...")
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
) -> List[Dict[str, Any]]:
    """Fetch all issues (excluding Initiatives and Epics) created in the last
    *lookback_days* days using cursor-based pagination.

    Args:
        jira: Authenticated ``atlassian.Jira`` connection object.
        lookback_days: How far back to search.
        max_results_per_page: Page size for the JQL search.

    Returns:
        List of raw Jira issue dicts.
    """
    try:
        cutoff_date_str = resolve_lookback_cutoff(lookback_days)
        jql = (
            f"created >= {cutoff_date_str} "
            "AND issuetype NOT IN (Initiative, Epic) "
            "ORDER BY created DESC"
        )

        logger.info(
            f"Fetching issues (excluding Initiatives and Epics) created since {cutoff_date_str}..."
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

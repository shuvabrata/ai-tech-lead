#!/usr/bin/env python3
"""Manual validation harness for Plan 018 — Phase 1 (Jira comments + mentions).

Connects to a REAL Jira instance using the same production helpers the
producer uses and exercises the Phase 1 changes:

  - ``resolve_jql_date_field``            (first-run vs incremental JQL)
  - ``fetch_initiatives/epics/issues``    (with ``last_synced_at``)
  - ``fetch_comments``                    (per-issue comment pagination)
  - ``extract_mentions_from_texts``       (ADF @mention extraction)

This is a DRY-RUN harness: it never publishes to RabbitMQ and never writes to
any database.  It only reads from Jira and prints results to stdout.

Usage:
    PYTHONPATH=src python scripts/validate_jira_comments_phase1.py [issue_key]

The optional ``issue_key`` (e.g. ``PROJ-123``) pins the comment-fetch check to
a specific issue; otherwise the most recently updated issue is used.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from connectors.producers.jira.fetch_jira import (
    fetch_comments,
    fetch_epics,
    fetch_initiatives,
    fetch_issues,
    resolve_jql_date_field,
)
from connectors.producers.jira.jira_config import create_jira_connection
from connectors.producers.jira.map_jira import (
    extract_mentions_from_adf,
    extract_mentions_from_texts,
)

# ---------------------------------------------------------------------------
# Config loading (mirrors jira_config.load_config_from_file but with a path arg)
# ---------------------------------------------------------------------------


def _find_config(path: Optional[str]) -> Path:
    """Resolve the Jira .config.json path."""
    if path:
        return Path(path)
    # Look next to the module first, then project-root level.
    candidates = [
        Path(__file__).resolve().parent.parent
        / "src"
        / "connectors"
        / "producers"
        / "jira"
        / ".config.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No .config.json found in {candidates}")


def load_config(path: Optional[str]) -> Dict[str, Any]:
    """Load the raw Jira account config (keys only — never printed)."""
    config_path = _find_config(path)
    print(f"Using config: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Human-friendly printers
# ---------------------------------------------------------------------------


def _key(item: Dict[str, Any]) -> str:
    return item.get("key", "?")


def _summary(issue: Dict[str, Any]) -> str:
    fields = issue.get("fields", {})
    return str(fields.get("summary", ""))[:60]


def _report_issue_counts(label: str, issues: List[Dict[str, Any]]) -> None:
    print(f"  {label}: {len(issues)} result(s)")
    for item in issues[:5]:
        rid = item.get("id", "?")
        print(f"    - {_key(item)} (id={rid}) {_summary(item)}")
    if len(issues) > 5:
        print(f"    ... (+{len(issues) - 5} more)")


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_resolve_jql_date_field() -> None:
    """Show the JQL date field for first-run vs incremental modes."""
    print("\n=== 1) resolve_jql_date_field ===")
    lookback = 365
    field_1st, date_1st = resolve_jql_date_field(lookback, None)
    print(f"  First run (last_synced_at=None):  field={field_1st!r} date={date_1st!r}")

    cursor = datetime.now(timezone.utc) - timedelta(hours=24)
    field_inc, date_inc = resolve_jql_date_field(lookback, cursor)
    print(f"  Incremental (cursor={cursor.isoformat(timespec='minutes')}):"
          f"  field={field_inc!r} date={date_inc!r}")


def check_fetch_work_items(
    jira: Any, lookback: int, page_size: int
) -> Dict[str, List[Dict[str, Any]]]:
    """Exercise all three fetch functions in both JQL modes."""
    print("\n=== 2) fetch_* with last_synced_at ===")
    cursor = datetime.now(timezone.utc) - timedelta(days=30)

    init_first = fetch_initiatives(jira, lookback, page_size)
    init_inc = fetch_initiatives(jira, lookback, page_size, last_synced_at=cursor)
    print("  Initiatives (first run):")
    _report_issue_counts("created>=", init_first)
    print("  Initiatives (incremental):")
    _report_issue_counts("updated>=", init_inc)

    epics_first = fetch_epics(jira, lookback, page_size)
    epics_inc = fetch_epics(jira, lookback, page_size, last_synced_at=cursor)
    print("  Epics (first run):")
    _report_issue_counts("created>=", epics_first)
    print("  Epics (incremental):")
    _report_issue_counts("updated>=", epics_inc)

    issues_first = fetch_issues(jira, lookback, page_size)
    issues_inc = fetch_issues(jira, lookback, page_size, last_synced_at=cursor)
    print("  Issues (first run):")
    _report_issue_counts("created>=", issues_first)
    print("  Issues (incremental):")
    _report_issue_counts("updated>=", issues_inc)

    return {"issues_first": issues_first, "issues_inc": issues_inc}


def _pick_target(
    issues: List[Dict[str, Any]], override: Optional[str]
) -> Optional[str]:
    """Return the explicit override, else the first issue key, else None."""
    if override:
        return override
    if issues:
        return issues[0].get("key")
    return None


def check_comments_and_mentions(
    jira: Any, issue_key: Optional[str]
) -> None:
    """Fetch comments for an issue and extract mentions from its text."""
    print("\n=== 3) fetch_comments + extract_mentions ===")
    if not issue_key:
        print("  No issue available — skipping comment/mention check.")
        return

    print(f"  Target issue: {issue_key}")
    comments = fetch_comments(jira, issue_key, max_results=100)
    print(f"  fetch_comments returned {len(comments)} comment(s).")
    for c in comments[:5]:
        author = (c.get("author") or {}).get("displayName", "?")
        print(f"    - {c.get('id', '?')} by {author} @ {c.get('created', '?')}")

    # Pull the raw issue to get its description so we can test mention parsing.
    raw = jira.get(f"rest/api/3/issue/{issue_key}")
    if not raw:
        print("  (could not fetch raw issue — mention extraction only on comments).")
        description = None
    else:
        description = raw.get("fields", {}).get("description")
    body_docs = [c.get("body") for c in comments if c.get("body")]

    mentions = extract_mentions_from_texts(description, body_docs)
    print(f"  extract_mentions_from_texts found {len(mentions)} unique mention(s): {mentions}")

    # Also dump the raw ADF for a single comment for visual confirmation.
    if body_docs:
        first_body = body_docs[0]
        adf_mentions = extract_mentions_from_adf(first_body)
        print(
            "  extract_mentions_from_adf on first comment body -> "
            f"{adf_mentions}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    config_path = os.getenv("JIRA_CONFIG_PATH")
    issue_key = sys.argv[1] if len(sys.argv) > 1 else None

    lookback = int(os.getenv("JIRA_LOOKBACK_DAYS", "365"))
    page_size = int(os.getenv("JIRA_MAX_RESULTS_PER_PAGE", "100"))

    config = load_config(config_path)
    accounts = config.get("account", [])
    if not accounts:
        print("No 'account' entries in config.")
        return 1

    account = accounts[0]
    print(f"Connecting to Jira: {account.get('url')}")

    jira = create_jira_connection({"account": [account]})

    check_resolve_jql_date_field()
    results = check_fetch_work_items(jira, lookback, page_size)
    issues = results["issues_first"]

    target = _pick_target(issues, issue_key)
    check_comments_and_mentions(jira, target)

    print("\n=== DONE — dry-run complete (no DB/RabbitMQ writes) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
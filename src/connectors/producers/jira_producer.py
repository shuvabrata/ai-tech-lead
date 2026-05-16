"""Jira ActivitySignal producer.

One-shot async script that:
1. Loads Jira connector configuration (server or file).
2. Connects to Jira and fetches Projects, Initiatives, Epics, Sprints,
   Issues, and Person nodes.
3. Maps each entity to an ``ActivitySignal`` Pydantic model.
4. Publishes valid signals to RabbitMQ (``activity_signals`` exchange).
5. Updates the Postgres sync cursor on success.

Sync cursor key: ``source="jira"``, ``resource_id=<jira_base_url>``.

Run via::

    PYTHONPATH=/app python connectors/producers/jira_producer.py

Or in Docker::

    docker compose run jira-producer
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from atlassian import Jira  # type: ignore[import-untyped]

from common.activity_signal.models import (
    ActivitySignal,
    EpicAttributes,
    InitiativeAttributes,
    IssueAttributes,
    PersonAttributes,
    ProjectAttributes,
    Relationship,
    RelationshipTarget,
    SprintAttributes,
)
from common.messaging.rabbitmq import RabbitMQPublisher
from connectors.producers.jira.jira_config import (
    create_jira_connection,
    load_config_from_file,
    load_config_from_server,
)
from connectors.producers.fetch_jira import (
    fetch_epics,
    fetch_initiatives,
    fetch_issues,
    fetch_projects,
    fetch_sprints_by_ids,
)
from connectors.producers.map_jira import (
    extract_sprint_ids_from_issues,
    map_epic,
    map_initiative,
    map_issue,
    map_jira_user,
    map_project,
    map_sprint,
)
from connectors.producers.sync_cursor import get_sync_cursor, set_sync_cursor
from connectors.commons.logger import logger

_SOURCE = "jira"
_VERSION = "1.0"
_TEXT_MAX = 2000


def _truncate(value: Any) -> str:
    """Return *value* as a string truncated to ``_TEXT_MAX`` characters."""
    return str(value)[:_TEXT_MAX]


def _connector_url() -> str:
    api_server = os.environ.get("API_SERVER", "http://localhost:8000")
    return f"{api_server.rstrip('/')}/connectors/jira"


def _event_time_from(updated_at: str, created_at: str) -> datetime:
    """Parse ``updated_at`` (or fall back to ``created_at``) into a UTC datetime."""
    raw = updated_at or created_at
    if raw:
        try:
            # Strip trailing Z or +00:00 variants handled by fromisoformat in Python 3.11+
            ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Signal builders — return None on validation failure so callers can skip
# ---------------------------------------------------------------------------


def build_project_signal(
    project_data: Dict[str, Any],
    jira_base_url: str,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a Jira Project."""
    try:
        attrs = ProjectAttributes(
            id=project_data["id"],
            key=project_data["key"],
            name=project_data["name"],
            # Extra
            status=project_data.get("status"),
            project_type=project_data.get("project_type"),
            url=project_data.get("url"),
        )
        return ActivitySignal(
            source=_SOURCE,
            external_id=project_data["id"],
            source_config=jira_base_url,
            connector_url=_connector_url(),
            event_time=datetime.now(timezone.utc),
            version=_VERSION,
            attributes=attrs,
        )
    except Exception as exc:
        logger.warning("Skipping Project signal for '%s' (validation error): %s", project_data.get("key"), exc)
        return None


def build_person_signal(
    user_data: Dict[str, Any],
    jira_base_url: str,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a Person (Jira user)."""
    account_id = user_data.get("account_id", "")
    person_id = f"jira_person_{account_id}"
    try:
        attrs = PersonAttributes(
            id=person_id,
            name=user_data.get("display_name") or account_id,
            # Extra
            account_id=account_id,
            email=user_data.get("email", ""),
        )
        return ActivitySignal(
            source=_SOURCE,
            external_id=person_id,
            source_config=jira_base_url,
            connector_url=_connector_url(),
            event_time=datetime.now(timezone.utc),
            version=_VERSION,
            attributes=attrs,
        )
    except Exception as exc:
        logger.warning("Skipping Person signal for '%s' (validation error): %s", account_id, exc)
        return None


def build_initiative_signal(
    initiative_data: Dict[str, Any],
    jira_base_url: str,
    project_id: Optional[str] = None,
    reporter_person_id: Optional[str] = None,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a Jira Initiative."""
    try:
        attrs = InitiativeAttributes(
            id=initiative_data["id"],
            key=initiative_data["key"],
            summary=_truncate(initiative_data.get("summary", "")),
            priority=initiative_data.get("priority", "None"),
            status=initiative_data.get("status", "Unknown"),
            created_at=initiative_data.get("created_at", ""),
            project_id=project_id,
            # Extra
            updated_at=initiative_data.get("updated_at", ""),
            duedate=initiative_data.get("duedate"),
            labels=initiative_data.get("labels"),
            components=initiative_data.get("components"),
            url=initiative_data.get("url"),
        )
        rels: List[Relationship] = []
        if project_id:
            rels.append(
                Relationship(
                    type="PART_OF",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Project",
                        external_id=project_id,
                    ),
                )
            )
        if reporter_person_id:
            rels.append(
                Relationship(
                    type="REPORTED_BY",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        external_id=reporter_person_id,
                    ),
                )
            )
        return ActivitySignal(
            source=_SOURCE,
            external_id=initiative_data["id"],
            source_config=jira_base_url,
            connector_url=_connector_url(),
            event_time=_event_time_from(
                initiative_data.get("updated_at", ""),
                initiative_data.get("created_at", ""),
            ),
            version=_VERSION,
            attributes=attrs,
            relationships=rels,
        )
    except Exception as exc:
        logger.warning("Skipping Initiative signal for '%s' (validation error): %s", initiative_data.get("key"), exc)
        return None


def build_epic_signal(
    epic_data: Dict[str, Any],
    jira_base_url: str,
    initiative_id: Optional[str] = None,
    project_id: Optional[str] = None,
    reporter_person_id: Optional[str] = None,
    team_id: Optional[str] = None,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a Jira Epic."""
    try:
        attrs = EpicAttributes(
            id=epic_data["id"],
            key=epic_data["key"],
            summary=_truncate(epic_data.get("summary", "")),
            priority=epic_data.get("priority", "None"),
            status=epic_data.get("status", "Unknown"),
            created_at=epic_data.get("created_at", ""),
            # Extra
            updated_at=epic_data.get("updated_at", ""),
            start_date=epic_data.get("start_date"),
            due_date=epic_data.get("due_date"),
            team_value=epic_data.get("team_value"),
            url=epic_data.get("url"),
        )
        rels: List[Relationship] = []
        if initiative_id:
            rels.append(
                Relationship(
                    type="PART_OF",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Initiative",
                        external_id=initiative_id,
                    ),
                )
            )
        elif project_id:
            # Epic without an initiative still belongs to its project
            rels.append(
                Relationship(
                    type="PART_OF",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Project",
                        external_id=project_id,
                    ),
                )
            )
        if reporter_person_id:
            rels.append(
                Relationship(
                    type="REPORTED_BY",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        external_id=reporter_person_id,
                    ),
                )
            )
        if team_id:
            rels.append(
                Relationship(
                    type="TEAM",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Team",
                        external_id=team_id,
                    ),
                )
            )
        return ActivitySignal(
            source=_SOURCE,
            external_id=epic_data["id"],
            source_config=jira_base_url,
            connector_url=_connector_url(),
            event_time=_event_time_from(
                epic_data.get("updated_at", ""),
                epic_data.get("created_at", ""),
            ),
            version=_VERSION,
            attributes=attrs,
            relationships=rels,
        )
    except Exception as exc:
        logger.warning("Skipping Epic signal for '%s' (validation error): %s", epic_data.get("key"), exc)
        return None


def build_sprint_signal(
    sprint_data: Dict[str, Any],
    jira_base_url: str,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a Jira Sprint."""
    try:
        attrs = SprintAttributes(
            id=sprint_data["id"],
            name=sprint_data["name"],
            status=sprint_data.get("status", "Unknown"),
            # Extra
            goal=sprint_data.get("goal", ""),
            start_date=sprint_data.get("start_date", ""),
            end_date=sprint_data.get("end_date", ""),
        )
        return ActivitySignal(
            source=_SOURCE,
            external_id=sprint_data["id"],
            source_config=jira_base_url,
            connector_url=_connector_url(),
            event_time=datetime.now(timezone.utc),
            version=_VERSION,
            attributes=attrs,
        )
    except Exception as exc:
        logger.warning("Skipping Sprint signal for '%s' (validation error): %s", sprint_data.get("name"), exc)
        return None


def build_issue_signal(
    issue_data: Dict[str, Any],
    jira_base_url: str,
    epic_id: Optional[str] = None,
    sprint_ids: Optional[List[str]] = None,
    assignee_person_id: Optional[str] = None,
    reporter_person_id: Optional[str] = None,
    team_id: Optional[str] = None,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a Jira Issue."""
    try:
        attrs = IssueAttributes(
            id=issue_data["id"],
            key=issue_data["key"],
            summary=_truncate(issue_data.get("summary", "")),
            priority=issue_data.get("priority", "None"),
            status=issue_data.get("status", "Unknown"),
            type=issue_data.get("type", "Unknown"),
            created_at=issue_data.get("created_at", ""),
            # Extra
            updated_at=issue_data.get("updated_at", ""),
            story_points=issue_data.get("story_points", 0),
            team_value=issue_data.get("team_value"),
            url=issue_data.get("url"),
        )
        rels: List[Relationship] = []

        # PART_OF → Epic
        if epic_id:
            rels.append(
                Relationship(
                    type="PART_OF",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Epic",
                        external_id=epic_id,
                    ),
                )
            )

        # IN_SPRINT → Sprint(s)
        for sid in (sprint_ids or []):
            rels.append(
                Relationship(
                    type="IN_SPRINT",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Sprint",
                        external_id=sid,
                    ),
                )
            )

        # ASSIGNED_TO → Person
        if assignee_person_id:
            rels.append(
                Relationship(
                    type="ASSIGNED_TO",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        external_id=assignee_person_id,
                    ),
                )
            )

        # REPORTED_BY → Person
        if reporter_person_id:
            rels.append(
                Relationship(
                    type="REPORTED_BY",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        external_id=reporter_person_id,
                    ),
                )
            )

        # TEAM → Team
        if team_id:
            rels.append(
                Relationship(
                    type="TEAM",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Team",
                        external_id=team_id,
                    ),
                )
            )

        # BLOCKS / DEPENDS_ON / RELATES_TO from Jira issue links
        for link in (issue_data.get("issue_links_raw") or []):
            link_type = link.get("type", {})
            outward_desc = link_type.get("outward", "").lower()
            inward_desc = link_type.get("inward", "").lower()
            if "outwardIssue" in link and outward_desc == "blocks":
                # This issue blocks the outward target
                target_key = link["outwardIssue"].get("key")
                if not target_key:
                    continue
                target_id = f"jira_issue_{target_key}"
                rels.append(
                    Relationship(
                        type="BLOCKS",
                        direction=None,
                        target=RelationshipTarget(
                            source=_SOURCE,
                            entity_type="Issue",
                            external_id=target_id,
                        ),
                    )
                )
            elif "inwardIssue" in link and "blocked by" in inward_desc:
                # This issue is blocked by the inward target → DEPENDS_ON
                target_key = link["inwardIssue"].get("key")
                if not target_key:
                    continue
                target_id = f"jira_issue_{target_key}"
                rels.append(
                    Relationship(
                        type="DEPENDS_ON",
                        direction=None,
                        target=RelationshipTarget(
                            source=_SOURCE,
                            entity_type="Issue",
                            external_id=target_id,
                        ),
                    )
                )
            elif "relates" in outward_desc or "relates" in inward_desc:
                # Symmetric "relates to" — use whichever side provides the target
                linked_issue = link.get("outwardIssue") or link.get("inwardIssue")
                if linked_issue:
                    target_key = linked_issue.get("key")
                    if not target_key:
                        continue
                    target_id = f"jira_issue_{target_key}"
                    rels.append(
                        Relationship(
                            type="RELATES_TO",
                            direction=None,
                            target=RelationshipTarget(
                                source=_SOURCE,
                                entity_type="Issue",
                                external_id=target_id,
                            ),
                        )
                    )

        return ActivitySignal(
            source=_SOURCE,
            external_id=issue_data["id"],
            source_config=jira_base_url,
            connector_url=_connector_url(),
            event_time=_event_time_from(
                issue_data.get("updated_at", ""),
                issue_data.get("created_at", ""),
            ),
            version=_VERSION,
            attributes=attrs,
            relationships=rels,
        )
    except Exception as exc:
        logger.warning("Skipping Issue signal for '%s' (validation error): %s", issue_data.get("key"), exc)
        return None


# ---------------------------------------------------------------------------
# Main async logic
# ---------------------------------------------------------------------------


async def publish_signals(
    publisher: RabbitMQPublisher,
    jira: Any,
    jira_base_url: str,
    lookback_days: int,
    max_results_per_page: int,
) -> Dict[str, int]:
    """Fetch all Jira entities and publish ActivitySignal events.

    Returns:
        Dict mapping entity type → count of successfully published signals.
    """
    published: Dict[str, int] = {}

    seen_persons: set[str] = set()

    def _inc(entity_type: str) -> None:
        published[entity_type] = published.get(entity_type, 0) + 1

    async def _pub(sig: Optional[ActivitySignal]) -> None:
        if sig:
            await publisher.publish(sig)
            logger.info(
                "Published signal_id=%s entity_type=%s external_id=%s routing_key=%s",
                sig.signal_id,
                sig.entity_type,
                sig.external_id,
                sig.routing_key,
            )
            _inc(sig.entity_type)

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    logger.info("Fetching projects...")
    projects_raw = await asyncio.to_thread(fetch_projects, jira, max_results_per_page)
    logger.info("Fetched %d projects", len(projects_raw))
    # key → internal id map for downstream relationship wiring
    project_key_to_id: Dict[str, str] = {}

    for p_raw in projects_raw:
        p_data = map_project(p_raw, jira_base_url)
        project_key_to_id[p_data["key"]] = p_data["id"]
        logger.debug("Processing project '%s' (%s)", p_data.get("key"), p_data.get("name"))
        await _pub(build_project_signal(p_data, jira_base_url))

    logger.info("Projects done (%d)", published.get("Project", 0))

    # ------------------------------------------------------------------
    # Initiatives
    # ------------------------------------------------------------------
    logger.info("Fetching initiatives (lookback=%d days)...", lookback_days)
    initiatives_raw = await asyncio.to_thread(fetch_initiatives, jira, lookback_days, max_results_per_page)
    logger.info("Fetched %d initiatives", len(initiatives_raw))
    # issue_id (Jira) → internal id for Epic → Initiative wiring
    initiative_jira_id_to_id: Dict[str, str] = {}

    for i_raw in initiatives_raw:
        i_data = map_initiative(i_raw, jira_base_url)
        initiative_jira_id_to_id[i_raw.get("id", "")] = i_data["id"]
        project_key = i_data.get("project_key")
        project_id = project_key_to_id.get(project_key) if project_key else None
        logger.debug("Processing initiative '%s': '%s'", i_data.get("key"), str(i_data.get("summary", ""))[:60])
        await _pub(build_initiative_signal(i_data, jira_base_url, project_id))

    logger.info("Initiatives done (%d)", published.get("Initiative", 0))

    # ------------------------------------------------------------------
    # Epics
    # ------------------------------------------------------------------
    logger.info("Fetching epics (lookback=%d days)...", lookback_days)
    epics_raw = await asyncio.to_thread(fetch_epics, jira, lookback_days, max_results_per_page)
    logger.info("Fetched %d epics", len(epics_raw))
    # jira issue id → internal epic id for Issue → Epic wiring
    epic_jira_id_to_id: Dict[str, str] = {}

    for e_raw in epics_raw:
        e_data = map_epic(e_raw, jira_base_url)
        epic_jira_id_to_id[e_raw.get("id", "")] = e_data["id"]

        # Resolve parent initiative
        parent_jira_id = e_data.get("parent_jira_id")
        initiative_id = initiative_jira_id_to_id.get(parent_jira_id) if parent_jira_id else None

        # Resolve project via epic's own project field
        project_obj = e_raw.get("fields", {}).get("project") or {}
        project_key = project_obj.get("key")
        project_id = project_key_to_id.get(project_key) if project_key else None

        reporter_raw = e_raw.get("fields", {}).get("reporter")
        reporter_person_id: Optional[str] = None
        if reporter_raw and isinstance(reporter_raw, dict):
            user_data = map_jira_user(reporter_raw)
            account_id = user_data.get("account_id", "")
            reporter_person_id = f"jira_person_{account_id}"
            if account_id and account_id not in seen_persons:
                seen_persons.add(account_id)
                await _pub(build_person_signal(user_data, jira_base_url))

        team_id = f"jira_team_{e_data['team_value']}" if e_data.get("team_value") else None

        logger.debug("Processing epic '%s': '%s'", e_data.get("key"), str(e_data.get("summary", ""))[:60])
        await _pub(build_epic_signal(e_data, jira_base_url, initiative_id, project_id, reporter_person_id, team_id))

    logger.info("Epics done (%d)", published.get("Epic", 0))

    # ------------------------------------------------------------------
    # Issues (fetch all first so we can collect sprint IDs)
    # ------------------------------------------------------------------
    logger.info("Fetching issues (lookback=%d days, page_size=%d)...", lookback_days, max_results_per_page)
    issues_raw = await asyncio.to_thread(fetch_issues, jira, lookback_days, max_results_per_page)
    sprint_ids_needed = extract_sprint_ids_from_issues(issues_raw)
    logger.info("Fetched %d issues; found %d unique sprint IDs", len(issues_raw), len(sprint_ids_needed))

    # ------------------------------------------------------------------
    # Sprints
    # ------------------------------------------------------------------
    logger.info("Fetching %d sprints by ID...", len(sprint_ids_needed))
    sprints_raw = await asyncio.to_thread(fetch_sprints_by_ids, jira, sprint_ids_needed)
    logger.info("Fetched %d sprints", len(sprints_raw))
    # jira sprint id string → internal sprint id for Issue → Sprint wiring
    sprint_jira_id_to_id: Dict[str, str] = {}

    for s_raw in sprints_raw:
        s_data = map_sprint(s_raw)
        sprint_jira_id_to_id[str(s_raw.get("id", ""))] = s_data["id"]
        logger.debug("Processing sprint '%s' (state=%s)", s_data.get("name"), s_data.get("status"))
        await _pub(build_sprint_signal(s_data, jira_base_url))

    logger.info("Sprints done (%d)", published.get("Sprint", 0))

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------
    issue_count = 0

    for raw in issues_raw:
        try:
            i_data = map_issue(raw, jira_base_url)
            fields = raw.get("fields", {})
            issue_count += 1

            logger.debug(
                "Processing issue '%s' (%s) [%d/%d]",
                i_data.get("key"),
                i_data.get("type", "?"),
                issue_count,
                len(issues_raw),
            )

            # Person: assignee
            assignee_raw = fields.get("assignee")
            assignee_person_id: Optional[str] = None
            if assignee_raw and isinstance(assignee_raw, dict):
                user_data = map_jira_user(assignee_raw)
                account_id = user_data.get("account_id", "")
                assignee_person_id = f"jira_person_{account_id}"
                if account_id and account_id not in seen_persons:
                    seen_persons.add(account_id)
                    await _pub(build_person_signal(user_data, jira_base_url))

            # Person: reporter
            reporter_raw = fields.get("reporter")
            reporter_person_id: Optional[str] = None
            if reporter_raw and isinstance(reporter_raw, dict):
                user_data = map_jira_user(reporter_raw)
                account_id = user_data.get("account_id", "")
                reporter_person_id = f"jira_person_{account_id}"
                if account_id and account_id not in seen_persons:
                    seen_persons.add(account_id)
                    await _pub(build_person_signal(user_data, jira_base_url))

            # Resolve parent epic
            parent_jira_id = i_data.get("parent_jira_id")
            epic_id = epic_jira_id_to_id.get(parent_jira_id) if parent_jira_id else None

            # Resolve sprints
            sprint_ref_ids = [
                sprint_jira_id_to_id[ref["id"]]
                for ref in i_data.get("sprint_refs", [])
                if ref.get("id") in sprint_jira_id_to_id
            ]

            team_id = f"jira_team_{i_data['team_value']}" if i_data.get("team_value") else None

            await _pub(
                build_issue_signal(
                    i_data,
                    jira_base_url,
                    epic_id=epic_id,
                    sprint_ids=sprint_ref_ids,
                    assignee_person_id=assignee_person_id,
                    reporter_person_id=reporter_person_id,
                    team_id=team_id,
                )
            )

            if issue_count % 25 == 0:
                logger.info("  ... %d/%d issues processed", issue_count, len(issues_raw))
        except Exception as exc:
            logger.warning("Issue skipped: %s", exc)

    logger.info("Issues done (%d)", published.get("Issue", 0))
    logger.info("Persons done (%d)", published.get("Person", 0))

    return published


async def main_async() -> None:
    """Entry point — load config, run producer loop."""
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    config_source = os.getenv("CONFIGURATION_SOURCE", "FILE").upper()
    lookback_days = int(os.getenv("JIRA_LOOKBACK_DAYS", "90"))
    max_results_per_page = int(os.getenv("JIRA_MAX_RESULTS_PER_PAGE", "100"))

    logger.info("Jira ActivitySignal Producer starting (config_source=%s)", config_source)

    if config_source == "SERVER":
        config = load_config_from_server()
    else:
        config = load_config_from_file()

    accounts: List[Dict[str, Any]] = config.get("account", [])
    if not accounts:
        logger.warning("No Jira accounts configured — exiting.")
        return

    async with RabbitMQPublisher(rabbitmq_url) as publisher:
        for account in accounts:
            jira_base_url: str = account.get("url", "").rstrip("/")
            if not jira_base_url:
                logger.warning("Skipping account with missing url")
                continue

            try:
                jira = create_jira_connection({"account": [account]})
            except Exception as exc:
                logger.error("Failed to connect to Jira '%s': %s", jira_base_url, exc)
                continue

            try:
                last_synced_at = await get_sync_cursor(_SOURCE, jira_base_url)
                logger.info(
                    "Processing Jira '%s' (last_synced_at=%s)",
                    jira_base_url,
                    last_synced_at,
                )

                published = await publish_signals(
                    publisher, jira, jira_base_url, lookback_days, max_results_per_page
                )

                now = datetime.now(timezone.utc)
                await set_sync_cursor(_SOURCE, jira_base_url, now)

                total = sum(published.values())
                logger.info(
                    "Jira '%s' done — %d signals published: %s",
                    jira_base_url,
                    total,
                    published,
                )
            except Exception as exc:
                logger.error("Error processing Jira '%s': %s", jira_base_url, exc, exc_info=True)

    logger.info("Jira ActivitySignal Producer finished.")


def main() -> None:
    """Synchronous entry point for Docker CMD."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

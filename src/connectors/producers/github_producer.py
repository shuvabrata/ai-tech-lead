"""GitHub ActivitySignal producer.

One-shot async script that:
1. Loads GitHub connector configuration (server or file).
2. For each configured repository:
   a. Reads the sync cursor from Postgres (``producer_sync_state``).
   b. Fetches repositories, branches, commits, pull requests, and persons.
   c. Maps each entity to an ``ActivitySignal`` Pydantic model.
   d. Publishes valid signals to RabbitMQ (``activity_signals`` exchange).
   e. Updates the sync cursor on success.

Run via::

    PYTHONPATH=/app python connectors/producers/github_producer.py

Or in Docker::

    docker compose run github-producer
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from github import Github  # type: ignore[import-untyped]

from common.activity_signal.models import (
    ActivitySignal,
    BranchAttributes,
    CommitAttributes,
    PersonAttributes,
    PullRequestAttributes,
    Relationship,
    RelationshipTarget,
    RepositoryAttributes,
    TeamAttributes,
)
from common.messaging.rabbitmq import RabbitMQPublisher
from connectors.producers.github.github_config import (
    is_wildcard_url,
    load_config_from_file,
    load_config_from_server,
    parse_repo_url,
)
from connectors.producers.github.get_all_repos_for_owner import get_all_repos_for_owner  # type: ignore[import]
from connectors.producers.fetch_github import (
    fetch_branches,
    fetch_commits,
    fetch_pr_commits,
    fetch_pr_reviews,
    fetch_pull_requests_direct,
    fetch_repo_teams,
    fetch_repo_topics,
    resolve_commits_since_date,
    resolve_prs_since_date,
)
from connectors.producers.map_github import (
    extract_issue_keys,
    extract_issue_keys_from_branch,
    map_branch,
    map_commit,
    map_commit_author,
    map_pr_reviews,
    map_pr_user,
    map_pull_request,
    map_repo,
)
from connectors.producers.sync_cursor import get_sync_cursor, set_sync_cursor
from connectors.commons.logger import logger

_SOURCE = "github"
_VERSION = "1.0"
_TEXT_MAX = 2000


def _truncate(value: Any) -> str:
    """Return *value* as a string truncated to ``_TEXT_MAX`` characters."""
    return str(value)[:_TEXT_MAX]


def _connector_url() -> str:
    api_server = os.environ.get("API_SERVER", "http://localhost:8000")
    return f"{api_server.rstrip('/')}/connectors/github"


# ---------------------------------------------------------------------------
# Signal builders — return None on validation failure so callers can skip
# ---------------------------------------------------------------------------


def build_repository_signal(repo_data: Dict[str, Any]) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub Repository."""
    try:
        attrs = RepositoryAttributes(
            id=repo_data["id"],
            full_name=repo_data["full_name"],
            name=repo_data["name"],
            created_at=repo_data["created_at"],
            updated_at=repo_data["updated_at"],
            url=repo_data["url"],
            # Extra fields (allowed by extra='allow')
            language=repo_data.get("language", ""),
            is_private=repo_data.get("is_private", False),
            topics=repo_data.get("topics", []),
        )
        return ActivitySignal(
            source=_SOURCE,
            external_id=repo_data["id"],
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=datetime.now(timezone.utc),
            version=_VERSION,
            attributes=attrs,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Skipping Repository signal (validation error): %s", exc)
        return None


def build_branch_signal(
    branch_data: Dict[str, Any],
    repo_data: Dict[str, Any],
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub Branch."""
    try:
        ts_raw = branch_data.get("last_commit_timestamp")
        event_time = (
            datetime.fromisoformat(ts_raw).replace(tzinfo=timezone.utc)
            if ts_raw
            else datetime.now(timezone.utc)
        )
        attrs = BranchAttributes(
            name=branch_data["name"],
            last_commit_sha=branch_data["last_commit_sha"],
            last_commit_timestamp=branch_data.get("last_commit_timestamp"),
            is_protected=branch_data.get("is_protected", False),
            is_deleted=branch_data.get("is_deleted", False),
            is_external=branch_data.get("is_external", False),
            # Extra
            id=branch_data["id"],
            is_default=branch_data.get("is_default", False),
            url=branch_data.get("url"),
        )
        signal = ActivitySignal(
            source=_SOURCE,
            external_id=branch_data["id"],
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=event_time,
            version=_VERSION,
            attributes=attrs,
            relationships=[
                Relationship(
                    type="BRANCH_OF",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Repository",
                        external_id=repo_data["id"],
                    ),
                )
            ],
        )
        return signal
    except Exception as exc:
        logger.warning("Skipping Branch signal for '%s' (validation error): %s", branch_data.get("name"), exc)
        return None


def build_person_signal(
    person_data: Dict[str, Any],
    extra_relationships: Optional[List[Relationship]] = None,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a Person (GitHub author/contributor)."""
    login = person_data.get("login") or person_data.get("name", "unknown")
    person_id = f"github_person_{login}"
    try:
        attrs = PersonAttributes(
            id=person_id,
            name=person_data.get("name") or login,
            # Extra
            login=login,
            email=person_data.get("email", ""),
        )
        return ActivitySignal(
            source=_SOURCE,
            external_id=person_id,
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=datetime.now(timezone.utc),
            version=_VERSION,
            attributes=attrs,
            relationships=list(extra_relationships) if extra_relationships else [],
        )
    except Exception as exc:
        logger.warning("Skipping Person signal for '%s' (validation error): %s", login, exc)
        return None


def build_team_signal(
    team_data: Dict[str, Any],
    repo_data: Dict[str, Any],
    permission: Optional[str] = None,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub Team."""
    try:
        attrs = TeamAttributes(
            id=team_data["id"],
            name=team_data["name"],
            slug=team_data["slug"],
        )
        props: Optional[Dict[str, Any]] = {"permission": permission} if permission else None
        rels: List[Relationship] = [
            Relationship(
                type="COLLABORATOR",
                direction=None,
                target=RelationshipTarget(
                    source=_SOURCE,
                    entity_type="Repository",
                    external_id=repo_data["id"],
                ),
                properties=props,
            )
        ]
        return ActivitySignal(
            source=_SOURCE,
            external_id=team_data["id"],
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=datetime.now(timezone.utc),
            version=_VERSION,
            attributes=attrs,
            relationships=rels,
        )
    except Exception as exc:
        logger.warning("Skipping Team signal for '%s' (validation error): %s", team_data.get("name"), exc)
        return None


def build_commit_signal(
    commit_data: Dict[str, Any],
    author_data: Dict[str, Any],
    branch_data: Optional[Dict[str, Any]],
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub Commit."""
    try:
        event_time = (
            datetime.fromisoformat(commit_data["created_at"]).replace(tzinfo=timezone.utc)
            if commit_data.get("created_at")
            else datetime.now(timezone.utc)
        )
        login = author_data.get("login") or author_data.get("name", "unknown")
        author_person_id = f"github_person_{login}"

        attrs = CommitAttributes(
            sha=commit_data["sha"],
            message=_truncate(commit_data.get("message", "")),
            author=author_data.get("name") or login,
            created_at=commit_data.get("created_at", ""),
            # Extra
            id=commit_data["id"],
            additions=commit_data.get("additions", 0),
            deletions=commit_data.get("deletions", 0),
            files_changed=commit_data.get("files_changed", 0),
            url=commit_data.get("url"),
        )

        rels: List[Relationship] = [
            Relationship(
                type="AUTHORED_BY",
                direction=None,
                target=RelationshipTarget(
                    source=_SOURCE,
                    entity_type="Person",
                    external_id=author_person_id,
                ),
            )
        ]
        if branch_data:
            rels.append(
                Relationship(
                    type="PART_OF",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Branch",
                        external_id=branch_data["id"],
                    ),
                )
            )  # Commit→Branch: PART_OF is correct (matches neo4j_db handler)

        # REFERENCES → Jira issues mentioned in the commit message or branch name
        issue_keys = extract_issue_keys(commit_data.get("message", ""))
        if branch_data:
            branch_keys = extract_issue_keys_from_branch(branch_data.get("name", ""))
            issue_keys = list({*issue_keys, *branch_keys})
        for issue_key in issue_keys:
            rels.append(
                Relationship(
                    type="REFERENCES",
                    direction=None,
                    target=RelationshipTarget(
                        source="jira",
                        entity_type="Issue",
                        external_id=issue_key,
                    ),
                )
            )

        return ActivitySignal(
            source=_SOURCE,
            external_id=commit_data["id"],
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=event_time,
            version=_VERSION,
            attributes=attrs,
            relationships=rels,
        )
    except Exception as exc:
        logger.warning("Skipping Commit signal for sha '%s' (validation error): %s", commit_data.get("sha"), exc)
        return None


def build_pull_request_signal(
    pr_data: Dict[str, Any],
    author_data: Dict[str, Any],
    reviewer_logins: List[str],
    repo_data: Dict[str, Any],
    requested_reviewer_logins: Optional[List[str]] = None,
    merger_login: Optional[str] = None,
    commit_shas: Optional[List[str]] = None,
) -> Optional[ActivitySignal]:
    """Build an ActivitySignal for a GitHub PullRequest."""
    try:
        event_time = (
            datetime.fromisoformat(pr_data["updated_at"]).replace(tzinfo=timezone.utc)
            if pr_data.get("updated_at")
            else datetime.now(timezone.utc)
        )
        author_login = author_data.get("login") or author_data.get("name", "unknown")
        author_person_id = f"github_person_{author_login}"

        attrs = PullRequestAttributes(
            id=str(pr_data["id"]),
            number=int(pr_data["number"]),
            title=_truncate(pr_data.get("title", "")),
            state=pr_data.get("state", ""),
            created_at=pr_data.get("created_at", ""),
            user=author_login,
            # Extra
            url=pr_data.get("url"),
            merged_at=pr_data.get("merged_at"),
            base_branch_id=pr_data.get("base_branch_id"),
            head_branch_id=pr_data.get("head_branch_id"),
        )

        rels: List[Relationship] = [
            Relationship(
                type="CREATED_BY",
                direction=None,
                target=RelationshipTarget(
                    source=_SOURCE,
                    entity_type="Person",
                    external_id=author_person_id,
                ),
            )
        ]

        # TARGETS → base branch
        base_branch_id = pr_data.get("base_branch_id")
        if base_branch_id:
            rels.append(
                Relationship(
                    type="TARGETS",
                    direction="OUT",
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Branch",
                        external_id=base_branch_id,
                    ),
                )
            )

        # FROM → head branch (the feature/source branch of this PR)
        head_branch_id = pr_data.get("head_branch_id")
        if head_branch_id:
            rels.append(
                Relationship(
                    type="FROM",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Branch",
                        external_id=head_branch_id,
                    ),
                )
            )

        # REVIEWED_BY → each reviewer
        for reviewer_login in reviewer_logins:
            reviewer_person_id = f"github_person_{reviewer_login}"
            rels.append(
                Relationship(
                    type="REVIEWED_BY",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        external_id=reviewer_person_id,
                    ),
                )
            )

        # REQUESTED_REVIEWER → each requested reviewer person
        for rr_login in (requested_reviewer_logins or []):
            rr_person_id = f"github_person_{rr_login}"
            rels.append(
                Relationship(
                    type="REQUESTED_REVIEWER",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        external_id=rr_person_id,
                    ),
                )
            )

        # MERGED_BY → merger person (only when the PR was merged)
        if pr_data.get("state") == "merged" and merger_login:
            merger_person_id = f"github_person_{merger_login}"
            rels.append(
                Relationship(
                    type="MERGED_BY",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Person",
                        external_id=merger_person_id,
                    ),
                )
            )

        # INCLUDES → each commit SHA associated with this PR
        for sha in (commit_shas or []):
            commit_id = f"commit_{sha}"
            rels.append(
                Relationship(
                    type="INCLUDES",
                    direction=None,
                    target=RelationshipTarget(
                        source=_SOURCE,
                        entity_type="Commit",
                        external_id=commit_id,
                    ),
                )
            )

        return ActivitySignal(
            source=_SOURCE,
            external_id=str(pr_data["id"]),
            source_config="https://github.com",
            connector_url=_connector_url(),
            event_time=event_time,
            version=_VERSION,
            attributes=attrs,
            relationships=rels,
        )
    except Exception as exc:
        logger.warning("Skipping PR signal for #%s (validation error): %s", pr_data.get("number"), exc)
        return None


# ---------------------------------------------------------------------------
# Repo processor
# ---------------------------------------------------------------------------


async def process_repo_signals(
    publisher: RabbitMQPublisher,
    repo: Any,
    repo_owner: str,
    last_synced_at: Optional[datetime],
    published: Dict[str, int],
) -> None:
    """Fetch all entities for *repo* and publish ActivitySignal events."""
    full_name = repo.full_name

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
            published[sig.entity_type] = published.get(sig.entity_type, 0) + 1

    # Topics
    topics = fetch_repo_topics(repo)

    # Repository signal
    try:
        repo_data = map_repo(repo, topics)
    except ValueError as exc:
        logger.warning("Skipping repo '%s': %s", full_name, exc)
        return

    await _pub(build_repository_signal(repo_data))

    # Branches
    default_branch = repo.default_branch or "main"
    logger.info("Fetching branches for '%s'...", full_name)
    branches_raw = fetch_branches(repo)
    branch_map: Dict[str, Dict[str, Any]] = {}  # branch_name -> branch_data

    branch_semaphore = asyncio.Semaphore(5)

    async def process_single_branch(branch: Any) -> None:
        async with branch_semaphore:
            try:
                b_data = await asyncio.to_thread(map_branch, repo.name, default_branch, branch, repo_owner)
                branch_map[b_data["name"]] = b_data
                logger.debug("Branch '%s' mapped (is_default=%s)", b_data["name"], b_data.get("is_default"))
                b_sig = build_branch_signal(b_data, repo_data)
                await _pub(b_sig)
            except Exception as exc:
                logger.warning("Branch '%s' skipped: %s", getattr(branch, "name", "?"), exc)

    if branches_raw:
        await asyncio.gather(*(process_single_branch(b) for b in branches_raw))

    logger.info("Branches done (%d) for '%s'", published.get("Branch", 0), full_name)

    # Default branch dict (used for commit→branch relationships)
    default_branch_data = branch_map.get(default_branch)

    # Commits
    since = resolve_commits_since_date(last_synced_at)
    logger.info("Fetching commits for '%s' since %s...", full_name, since.date())
    commits_raw = fetch_commits(repo, since)
    logger.info(f"Number of commits fetched for {full_name} = {len(commits_raw)}")
    seen_persons: set[str] = set()
    commit_count = 0

    semaphore = asyncio.Semaphore(5)  # Capped concurrency to prevent API rate limits

    async def process_single_commit(commit: Any) -> None:
        nonlocal commit_count
        async with semaphore:
            try:
                # Isolate blocking PyGithub lazy-loads in a background thread
                def extract_data() -> tuple[Dict[str, Any], Dict[str, Any]]:
                    commit_author_obj = commit.author or commit.commit.author
                    a_data = map_commit_author(commit_author_obj)
                    c_data = map_commit(repo.name, commit, repo_owner)
                    return a_data, c_data

                author_data, commit_data = await asyncio.to_thread(extract_data)

                # Back on the async event loop (thread-safe updates)
                login = author_data.get("login") or author_data.get("name", "unknown")
                if login not in seen_persons:
                    seen_persons.add(login)
                    await _pub(build_person_signal(author_data))

                sha_short = commit_data.get("sha", "?")[:8]
                logger.debug("Commit %s by '%s' processed", sha_short, login)

                await _pub(build_commit_signal(commit_data, author_data, default_branch_data))

                commit_count += 1
                if commit_count % 10 == 0:
                    logger.info("  ... %d commits processed so far for '%s'", commit_count, full_name)
            except Exception as exc:
                logger.warning("Commit skipped: %s", exc)

    if commits_raw:
        await asyncio.gather(*(process_single_commit(c) for c in commits_raw))

    logger.info("Commits done (%d) for '%s'", published.get("Commit", 0), full_name)

    # Pull Requests
    pr_since = resolve_prs_since_date(last_synced_at)
    logger.info("Fetching pull requests for '%s'...", full_name)
    prs_raw = fetch_pull_requests_direct(repo)
    for pr in prs_raw:
        try:
            # Filter by date
            pr_updated = getattr(pr, "updated_at", None)
            logger.debug(f"PR # {pr.number} updated at {pr_updated} (since={pr_since})")
            if pr_updated and pr_updated.replace(tzinfo=timezone.utc) < pr_since:
                logger.debug("PR #%s skipped (updated before since=%s)", pr.number, pr_since.date())
                # Since PRs are processed newest-first, we can stop the entire loop 
                # once we hit a PR older than our cutoff, saving massive API pagination!
                logger.info("Stopping PR fetch loop for '%s' since remaining PRs will be older than %s", full_name, pr_since.date())
                break

            pr_user_obj = pr.user
            author_data = map_pr_user(pr_user_obj)
            pr_data = map_pull_request(repo.name, pr, repo_owner)

            author_login = author_data.get("login") or author_data.get("name", "unknown")
            logger.debug("Processing PR #%s '%s' by '%s'", pr.number, str(getattr(pr, "title", ""))[:60], author_login)

            # Reviewer logins from review state dict
            reviews_raw = fetch_pr_reviews(pr)
            review_map = map_pr_reviews(reviews_raw)
            reviewer_logins = list(review_map.keys())

            # Extract merger login (only set when state == "merged")
            merger_login: Optional[str] = None
            if pr_data.get("state") == "merged":
                merged_by_obj = getattr(pr, "merged_by", None)
                if merged_by_obj:
                    merger_login = getattr(merged_by_obj, "login", None)

            # Requested reviewers (GitHub API: pr.requested_reviewers)
            requested_reviewer_logins: List[str] = [
                u.login for u in (getattr(pr, "requested_reviewers", None) or [])
                if getattr(u, "login", None)
            ]

            # Commit SHAs for INCLUDES relationships
            try:
                pr_commits_raw = fetch_pr_commits(pr)
                commit_shas = [c.sha for c in pr_commits_raw if getattr(c, "sha", None)]
            except Exception as exc:
                logger.warning("Could not fetch commits for PR #%s: %s", pr.number, exc)
                commit_shas = []

            # Emit Person signals for author + reviewers
            for person_login, _ in [(author_data.get("login") or author_data.get("name", "unknown"), None)]:
                if person_login not in seen_persons:
                    seen_persons.add(person_login)
                    p_sig = build_person_signal(author_data)
                    await _pub(p_sig)

            for r_login in reviewer_logins:
                if r_login not in seen_persons:
                    seen_persons.add(r_login)
                    r_sig = build_person_signal({"login": r_login, "name": r_login, "email": ""})
                    await _pub(r_sig)

            pr_sig = build_pull_request_signal(
                pr_data, author_data, reviewer_logins, repo_data,
                requested_reviewer_logins=requested_reviewer_logins,
                merger_login=merger_login,
                commit_shas=commit_shas,
            )
            await _pub(pr_sig)
        except Exception as exc:
            logger.warning("PR skipped: %s", exc)
    logger.info("PRs done (%d) for '%s'", published.get("PullRequest", 0), full_name)

    # Teams — emit Team signals with COLLABORATOR rel; emit MEMBER_OF on Person signals
    logger.info("Fetching teams for '%s'...", full_name)
    try:
        teams_raw = fetch_repo_teams(repo)
        for team in teams_raw:
            team_slug = getattr(team, "slug", None) or getattr(team, "name", "unknown")
            team_name = getattr(team, "name", team_slug)
            team_id = f"github_team_{team_slug}"
            permission = getattr(team, "permission", None)
            team_data_dict: Dict[str, Any] = {
                "id": team_id,
                "name": team_name,
                "slug": team_slug,
            }
            await _pub(build_team_signal(team_data_dict, repo_data, permission))

            # Emit Person signals for team members with MEMBER_OF and COLLABORATOR rels
            try:
                members = list(team.get_members())
                for member in members:
                    member_login = getattr(member, "login", None)
                    if not member_login:
                        continue
                    member_rels: List[Relationship] = [
                        Relationship(
                            type="MEMBER_OF",
                            direction=None,
                            target=RelationshipTarget(
                                source=_SOURCE,
                                entity_type="Team",
                                external_id=team_id,
                            ),
                        ),
                        Relationship(
                            type="COLLABORATOR",
                            direction=None,
                            target=RelationshipTarget(
                                source=_SOURCE,
                                entity_type="Repository",
                                external_id=repo_data["id"],
                            ),
                            properties={"permission": permission} if permission else None,
                        ),
                    ]
                    member_sig = build_person_signal(
                        {"login": member_login, "name": getattr(member, "name", None) or member_login, "email": ""},
                        extra_relationships=member_rels,
                    )
                    await _pub(member_sig)
            except Exception as exc:
                logger.warning("Could not fetch members for team '%s': %s", team_slug, exc)
    except Exception as exc:
        logger.warning("Could not fetch teams for '%s': %s", full_name, exc)
    logger.info("Teams done (%d) for '%s'", published.get("Team", 0), full_name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main_async() -> None:
    """Entry point — load config, iterate repos, publish signals."""
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    config_source = os.getenv("CONFIGURATION_SOURCE", "FILE").upper()

    logger.info("GitHub ActivitySignal Producer starting (config_source=%s)", config_source)

    if config_source == "SERVER":
        config = load_config_from_server()
    else:
        config = load_config_from_file()

    repos_cfg: List[Dict[str, Any]] = config.get("repos", [])
    if not repos_cfg:
        logger.warning("No repositories configured — exiting.")
        return

    async with RabbitMQPublisher(rabbitmq_url) as publisher:
        for repo_cfg in repos_cfg:
            url: str = repo_cfg.get("url", "")
            access_token: str = repo_cfg.get("access_token", "")
            if not url or not access_token:
                logger.warning("Skipping repo entry with missing url/access_token")
                continue

            g = Github(access_token)

            try:
                if is_wildcard_url(url):
                    owner, _ = parse_repo_url(url)
                    repo_list = get_all_repos_for_owner(g, owner)
                else:
                    owner, repo_name = parse_repo_url(url)
                    repo_list = [g.get_repo(f"{owner}/{repo_name}")]
            except Exception as exc:
                logger.error("Failed to resolve repos for '%s': %s", url, exc)
                continue

            for repo in repo_list:
                full_name = repo.full_name
                try:
                    last_synced_at = await get_sync_cursor(_SOURCE, full_name)
                    logger.info(
                        "Processing repo '%s' (last_synced_at=%s)",
                        full_name,
                        last_synced_at,
                    )

                    published: Dict[str, int] = {}
                    await process_repo_signals(publisher, repo, owner, last_synced_at, published)

                    now = datetime.now(timezone.utc)
                    await set_sync_cursor(_SOURCE, full_name, now)

                    total = sum(published.values())
                    logger.info(
                        "Repo '%s' done — %d signals published: %s",
                        full_name,
                        total,
                        published,
                    )
                except Exception as exc:
                    logger.error("Error processing repo '%s': %s", full_name, exc, exc_info=True)

    logger.info("GitHub ActivitySignal Producer finished.")


def main() -> None:
    """Synchronous entry point for Docker CMD."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

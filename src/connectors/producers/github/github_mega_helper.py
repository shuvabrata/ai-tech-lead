
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from common.logger import logger

from common.activity_signal.models import (
    ActivitySignal,
    BranchAttributes,
    Relationship,
    RelationshipTarget,
    TeamAttributes,
)
from common.messaging.rabbitmq import RabbitMQPublisher

from connectors.producers.fetch_github import (
    fetch_branches,
    fetch_commits,
    fetch_repo_topics,
    resolve_commits_since_date,
)
from connectors.producers.github.build_commit_signal import build_commit_signal
from connectors.producers.github.build_repository_signal import build_repository_signal
from connectors.producers.github.process_teams import process_teams
from connectors.producers.map_github import (
    fetch_github_user,
    map_branch,
    map_commit,
    map_repo,
)
from connectors.producers.github.process_prs import process_prs
from connectors.producers.github.pub_callback import make_pub_callback
from connectors.producers.github.constants import (
    _SOURCE,
    _VERSION,
    _connector_url,
)
from connectors.producers.github.build_person_signal import build_person_signal


# ---------------------------------------------------------------------------
# Signal builders — return None on validation failure so callers can skip
# ---------------------------------------------------------------------------

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
    _pub = make_pub_callback(publisher, published)

    # Topics — run in thread so time.sleep in retry_with_backoff never blocks the event loop
    topics = await asyncio.to_thread(fetch_repo_topics, repo)

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
    branches_raw = await asyncio.to_thread(fetch_branches, repo)
    branch_map: Dict[str, Dict[str, Any]] = {}  # branch_name -> branch_data

    branch_semaphore = asyncio.Semaphore(3)

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
    commits_raw = await asyncio.to_thread(fetch_commits, repo, since)
    logger.info(f"Number of commits fetched for {full_name} = {len(commits_raw)}")
    published_persons: set[str] = set()
    seen_commits: set[str] = set()
    commit_count = 0

    semaphore = asyncio.Semaphore(3)  # Capped concurrency to prevent API rate limits

    async def process_single_commit(commit: Any) -> None:
        nonlocal commit_count
        async with semaphore:
            try:
                # Isolate blocking PyGithub lazy-loads in a background thread.
                # fetch_github_user handles both NamedUser (triggers GET /users/{login})
                # and GitAuthor (reads git metadata directly).
                def extract_data() -> tuple[Dict[str, Any], Dict[str, Any]]:
                    a_data = fetch_github_user(commit.author or commit.commit.author)
                    c_data = map_commit(repo.name, commit, repo_owner)
                    return a_data, c_data

                author_data, commit_data = await asyncio.to_thread(extract_data)

                # Back on the async event loop (thread-safe updates)
                login = author_data.get("login") or author_data.get("name", "unknown")
                if login not in published_persons:
                    published_persons.add(login)
                    logger.debug(
                        "[person:commit_author] login=%r  name=%r  email=%r  sha=%s",
                        login,
                        author_data.get("name"),
                        author_data.get("email"),
                        commit_data.get("sha", "?")[:8],
                    )
                    await _pub(build_person_signal(author_data))

                sha_short = commit_data.get("sha", "?")[:8]
                seen_commits.add(commit_data.get("sha"))
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
    await process_prs(
        repo=repo,
        repo_data=repo_data,
        repo_owner=repo_owner,
        full_name=full_name,
        last_synced_at=last_synced_at,
        published=published,
        seen_commits=seen_commits,
        published_persons=published_persons,
        pub_callback=_pub,
    )

    # Teams — emit Team signals with COLLABORATOR rel; emit MEMBER_OF on Person signals
    await process_teams(
        repo=repo,
        repo_data=repo_data,
        full_name=full_name,
        published=published,
        pub_callback=_pub,
        build_team_signal_fn=build_team_signal,
        build_person_signal_fn=build_person_signal,
    )


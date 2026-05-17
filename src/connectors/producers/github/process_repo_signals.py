
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional

from common.logger import logger

from common.messaging.rabbitmq import RabbitMQPublisher

from connectors.producers.fetch_github import fetch_repo_topics
from connectors.producers.github.build_repository_signal import build_repository_signal
from connectors.producers.github.process_branches import process_branches
from connectors.producers.github.process_teams import process_teams
from connectors.producers.map_github import map_repo
from connectors.producers.github.process_prs import process_prs
from connectors.producers.github.process_commits import process_commits
from connectors.producers.github.pub_callback import make_pub_callback
from connectors.producers.github.build_person_signal import build_person_signal
from connectors.producers.github.build_team_signal import build_team_signal

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
    default_branch_data = await process_branches(
        repo=repo,
        repo_owner=repo_owner,
        repo_data=repo_data,
        full_name=full_name,
        published=published,
        pub_callback=_pub,
    )

    # Commits
    seen_commits, published_persons = await process_commits(
        repo=repo,
        repo_owner=repo_owner,
        full_name=full_name,
        last_synced_at=last_synced_at,
        default_branch_data=default_branch_data,
        published=published,
        pub_callback=_pub,
    )

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

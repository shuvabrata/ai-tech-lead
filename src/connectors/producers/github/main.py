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
import asyncio
import os
from typing import Any, Dict, List
from datetime import datetime, timezone

from github import Github  # type: ignore[import-untyped]

from common.logger import logger
from common.messaging.rabbitmq import RabbitMQPublisher

from connectors.producers.github.github_config import (
    is_wildcard_url,
    load_config_from_file,
    load_config_from_server,
    parse_repo_url,
)

from connectors.producers.github.get_all_repos_for_owner import get_all_repos_for_owner  # type: ignore[import]
from connectors.producers.github.github_mega_helper import (
    process_repo_signals,
    _SOURCE
)
from connectors.producers.sync_cursor import get_sync_cursor, set_sync_cursor


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
                    filters = repo_cfg.get("search_filters", {})
                    logger.info(f"Wildcard pattern detected. Fetching all repositories for: {owner} with filters: {filters} ")
                    repo_list = get_all_repos_for_owner(g, owner, filters)
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

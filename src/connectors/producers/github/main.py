"""GitHub ActivitySignal producer — unified entry point (daemon + scan).

Usage:
    python main.py                          # daemon mode (default)
    python main.py --mode scan ...          # one-shot scan mode

The daemon mode listens on the ``command_n_control`` RabbitMQ exchange for
``scan`` commands targeted at ``github-producer``.  Each accepted command
spawns a child process in ``--mode scan`` that runs the existing one-shot
scan logic (loading its own config and reporting status via HTTP PATCH).

Environment variables:
    CONTAINER_NAME         (default: "github-producer")
    RABBITMQ_URL           (default: "amqp://guest:guest@localhost:5672/")
    API_SERVER             (default: "http://localhost:8000")
    MAX_CONCURRENT_SCANS   (default: 5)

Run via::

    PYTHONPATH=/app python connectors/producers/github/main.py

Or in Docker::

    docker compose run github-producer
"""
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from github import Github, Auth  # type: ignore[import-untyped]

from common.logger import LogContext, logger
from common.messaging.rabbitmq import RabbitMQPublisher

from connectors.producers.github.github_config import (
    is_wildcard_url,
    load_config_from_file,
    load_config_from_server,
    parse_repo_url,
)

from connectors.producers.github.get_all_repos_for_owner import get_all_repos_for_owner  # type: ignore[import]
from connectors.producers.github.constants import _SOURCE
from connectors.producers.github.process_repo_signals import (
    process_repo_signals,
)
from connectors.producers.github.retry_with_backoff import WbaRetryTimeoutError
from connectors.producers.sync_cursor import get_sync_cursor, set_sync_cursor
from connectors.producers.daemon_common import ScanResult, producer_main


async def main_async() -> ScanResult:
    """Entry point — load config, iterate repos, publish signals.

    Returns a :class:`ScanResult` describing the aggregate outcome across all
    configured repositories.  A config that fails to resolve or has any repo
    processing error is recorded as a failed item, but does not abort the
    remaining configs.
    """
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    config_source = os.getenv("CONFIGURATION_SOURCE", "FILE").upper()

    logger.info("GitHub ActivitySignal Producer starting (config_source=%s)", config_source)

    if config_source == "SERVER":
        config = load_config_from_server()
    else:
        config = load_config_from_file()

    repos_cfg: List[Dict[str, Any]] = config.get("repos", [])
    result = ScanResult()
    if not repos_cfg:
        logger.warning("No repositories configured — exiting.")
        return result

    async with RabbitMQPublisher(rabbitmq_url) as publisher:
        for repo_cfg in repos_cfg:
            if not repo_cfg.get("enabled", True):
                logger.info("Skipping disabled configuration for url: %s", repo_cfg.get("url", "unknown"))
                continue

            result.items_processed += 1

            url: str = repo_cfg.get("url", "")
            access_token: str = repo_cfg.get("access_token", "")
            if not url or not access_token:
                logger.warning("Skipping repo entry with missing url/access_token")
                result.add_error(url or "unknown", "missing url/access_token")
                continue

            auth = Auth.Token(access_token)
            g = Github(auth=auth)

            try:
                if is_wildcard_url(url):
                    owner, _ = parse_repo_url(url)
                    filters = repo_cfg.get("search_filters", {})
                    logger.info(f"Wildcard pattern detected. Fetching all repositories "
                                f"for: {owner} with filters: {filters} ")
                    repo_list = get_all_repos_for_owner(g, owner, filters)
                else:
                    owner, repo_name = parse_repo_url(url)
                    repo_list = [g.get_repo(f"{owner}/{repo_name}")]
            except Exception as exc:
                logger.error("Failed to resolve repos for '%s': %s", url, exc)
                result.add_error(url, str(exc))
                continue

            config_failed = False
            first_error: str | None = None
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
                    with LogContext(request_id=repo.full_name):
                        await process_repo_signals(publisher, repo, owner, last_synced_at, published, github_obj=g)

                    now = datetime.now(timezone.utc)
                    await set_sync_cursor(_SOURCE, full_name, now)

                    total = sum(published.values())
                    logger.info(
                        "Repo '%s' done — %d signals published: %s",
                        full_name,
                        total,
                        published,
                    )
                except WbaRetryTimeoutError as exc:
                    # Retry budget exhausted — the repo is incomplete. Do NOT
                    # advance its sync cursor so the next scan re-considers it.
                    logger.error(
                        "Retry budget exhausted for repo '%s' — skipping, will retry next scan: %s",
                        full_name,
                        exc,
                    )
                    config_failed = True
                    if first_error is None:
                        first_error = str(exc)
                except Exception as exc:
                    logger.error("Error processing repo '%s': %s", full_name, exc, exc_info=True)
                    config_failed = True
                    if first_error is None:
                        first_error = str(exc)

            if config_failed:
                result.add_error(url, first_error or "unknown error")
            else:
                result.items_succeeded += 1

    logger.info("GitHub ActivitySignal Producer finished.")
    return result


def _get_test_item_id() -> int | None:
    """Read ``TEST_ITEM_ID`` from environment — set by daemon for ``--mode test``."""
    raw = os.environ.get("TEST_ITEM_ID")
    return int(raw) if raw else None


async def test_connection() -> tuple[bool, str]:
    """Test GitHub connectivity.  Loads config, authenticates, returns result.

    Returns:
        ``(True, "Authenticated as <login>")`` on success, or
        ``(False, "<error message>")`` on failure.
    """
    config_source = os.getenv("CONFIGURATION_SOURCE", "FILE").upper()
    config = load_config_from_server() if config_source == "SERVER" else load_config_from_file()
    repos_cfg: List[Dict[str, Any]] = config.get("repos", [])

    item_id = _get_test_item_id()
    if item_id is not None:
        repos_cfg = [r for r in repos_cfg if r.get("id") == item_id]
        if not repos_cfg:
            return (False, f"No repository config found with id={item_id}")

    for repo_cfg in repos_cfg:
        url: str = repo_cfg.get("url", "")
        access_token: str = repo_cfg.get("access_token", "")
        if not url or not access_token:
            continue
        try:
            auth = Auth.Token(access_token)
            g = Github(auth=auth)
            user = g.get_user()
            login = user.login  # lightweight call to verify credentials
            return (True, f"Authenticated as {login}")
        except Exception as exc:
            return (False, f"GitHub auth failed for {url}: {exc}")

    return (False, "No enabled repository configurations to test")



def main() -> None:
    """Unified CLI entry point — delegates to ``daemon_common``."""

    producer_main(
        description="GitHub Producer",
        default_container="github-producer",
        producer_main_path=__file__,
        scan_func=main_async,
        test_func=test_connection,
    )


if __name__ == "__main__":
    main()

import os
from typing import Any

from common.logger import logger
from connectors.modules.github.get_fully_synced_pr_numbers import get_fully_synced_pr_numbers
from connectors.modules.github.new_pull_request_handler import new_pull_request_handler
from connectors.modules.github.repo_last_synced_at import get__last_synced_at
from connectors.producers.fetch_github import (
    fetch_pull_requests_direct,
    fetch_pull_requests_search,
    resolve_prs_since_date,
)


def process_pull_requests(
    repo: Any,
    session: Any,
    repo_id: str,
    repo_obj: Any,
    person_cache: Any,
    github_obj=None
) -> None:
    try:
        _last_synced = get__last_synced_at(session, repo_id)
        since_date = resolve_prs_since_date(_last_synced)
        if _last_synced:
            logger.info(f"    Incremental sync: Fetching PRs updated since _last_synced_at ({since_date.strftime('%Y-%m-%d %H:%M:%S')}...")
        else:
            pr_days_limit = int(os.getenv('PULL_REQUEST_DAYS_LIMIT', '60'))
            logger.info(f"    First sync: Fetching pull requests (last {pr_days_limit} days)...")

        use_search_mode = os.getenv('PR_FETCH_MODE', 'SEARCH').upper() == 'SEARCH'
        if use_search_mode:
            logger.info(f"    [SEARCH MODE] Using GitHub Search API for CLOSED PRs updated since {since_date.date()}...")
            if github_obj is None:
                raise RuntimeError("github_obj must be provided for SEARCH mode.")
            all_prs = fetch_pull_requests_search(github_obj, repo_obj.full_name, since_date)
        else:
            all_prs = fetch_pull_requests_direct(repo_obj)

        recent_prs = [pr for pr in all_prs if pr.updated_at >= since_date]
        existing_pr_numbers = get_fully_synced_pr_numbers(session, repo_id)
        prs_to_process = [pr for pr in recent_prs if pr.number not in existing_pr_numbers]
        if existing_pr_numbers:
            logger.info(f"    Found {len(recent_prs)} recent PRs, {len(existing_pr_numbers)} already processed (closed/merged), {len(prs_to_process)} to process")
        else:
            logger.info(f"    Processing {len(prs_to_process)} pull requests...")
        prs_processed = 0
        prs_failed = 0
        for pr in prs_to_process:
            if new_pull_request_handler(session, repo_obj, pr, repo_id, repo_obj.owner.login, person_cache):
                prs_processed += 1
            else:
                prs_failed += 1
        logger.info(f"    ✓ Processed {prs_processed} pull requests")
        if prs_failed > 0:
            logger.info(f"    ✗ Failed/Skipped: {prs_failed} pull requests")
    except Exception as e:
        logger.info(f"    Warning: Could not fetch pull requests - {str(e)}")

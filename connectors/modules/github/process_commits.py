from common.logger import logger
from modules.github.get_fully_synced_commit_shas import get_fully_synced_commit_shas
from modules.github.new_commit_handler import new_commit_handler
from modules.github.repo_last_synced_at import get__last_synced_at
from modules.github.retry_with_backoff import retry_with_backoff


import os
from datetime import datetime, timedelta


from typing import Any, List

def process_commits(
    repo: Any,
    session: Any,
    repo_id: str,
    default_branch_id: str,
    branch_patterns: List[str],
    extraction_sources: List[str],
    person_cache: Any
) -> None:
    if default_branch_id:
        try:
            _last_synced = get__last_synced_at(session, repo_id)
            if _last_synced:
                since_date = _last_synced
                logger.info(f"    Incremental sync: Fetching commits since _last_synced_at ({since_date.strftime('%Y-%m-%d %H:%M:%S')}...")
            else:
                commit_days_limit = int(os.getenv('COMMIT_DAYS_LIMIT', '60'))
                since_date = datetime.now() - timedelta(days=commit_days_limit)
                logger.info(f"    First sync: Fetching commits from default branch '{repo.default_branch}' (last {commit_days_limit} days)...")
            commits = retry_with_backoff(
                lambda: list(repo.get_commits(sha=repo.default_branch, since=since_date))
            )
            existing_shas = get_fully_synced_commit_shas(session, repo_id)
            commits_to_process = [c for c in commits if c.sha not in existing_shas]
            if existing_shas:
                logger.info(f"    Found {len(commits)} commits from GitHub, {len(existing_shas)} already processed, {len(commits_to_process)} new to process")
            else:
                logger.info(f"    Processing {len(commits_to_process)} commits...")
            commits_processed = 0
            commits_failed = 0
            for commit in commits_to_process:
                if new_commit_handler(
                    session,
                    repo.name,
                    commit,
                    default_branch_id,
                    repo.owner.login,
                    repo.default_branch,
                    person_cache,
                    branch_patterns=branch_patterns,
                    extraction_sources=extraction_sources
                ):
                    commits_processed += 1
                else:
                    commits_failed += 1
            logger.info(f"    ✓ Processed {commits_processed} commits")
            if commits_failed > 0:
                logger.info(f"    ✗ Failed: {commits_failed} commits")
        except Exception as e:
            logger.info(f"    Warning: Could not fetch commits - {str(e)}")
    else:
        logger.info(f"    Warning: Default branch not encountered in this scan, skipping commit processing")

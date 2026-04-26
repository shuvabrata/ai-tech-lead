from common.logger import logger
from modules.github.new_user_handler import new_user_handler
from modules.github.process_github_user import get_users_needing_refresh


import os


from typing import Any, Optional

from typing import Any, Dict

def process_collaborators(
    repo: Any,
    session: Any,
    repo_id: str,
    repo_created_at: str,
    processed_users_cache: dict[str, Any]
) -> None:
    try:
        collaborators = repo.get_collaborators()
        logger.info(f"    Found {collaborators.totalCount} collaborators...")
        collaborator_list: list[Any] = [collab for collab in collaborators if collab.type == 'User']
        refresh_days = int(os.getenv('IDENTITY_REFRESH_DAYS', '7'))
        collaborators_to_process, skip_count = get_users_needing_refresh(
            session, collaborator_list, refresh_days
        )
        if skip_count > 0:
            logger.info(f"    Skipping {skip_count} collaborators (updated within last {refresh_days} days)")
        if not collaborators_to_process:
            logger.info(f"    All collaborators are up-to-date, skipping processing")
        else:
            bulk_threshold = int(os.getenv('BULK_PROCESSING_THRESHOLD', '100'))
            batch_size = int(os.getenv('COLLABORATOR_BATCH_SIZE', '50'))
            if len(collaborators_to_process) > bulk_threshold:
                logger.info(f"    Using bulk processing for {len(collaborators_to_process)} collaborators (threshold: {bulk_threshold})...")
                from modules.github.bulk_user_handler import bulk_user_handler
                bulk_user_handler(session, collaborators_to_process, repo_id, repo_created_at, batch_size)
            else:
                logger.info(f"    Processing {len(collaborators_to_process)} collaborators individually...")
                for collab in collaborators_to_process:
                    new_user_handler(session, collab, repo_id, repo_created_at, processed_users_cache)
    except Exception as e:
        logger.info(f"    Warning: Could not fetch collaborators - {str(e)}")
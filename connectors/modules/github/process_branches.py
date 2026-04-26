from common.logger import logger
from modules.github.new_branch_handler import new_branch_handler
from modules.github.get_existing_branch_metadata import get_existing_branch_metadata


from typing import Any, Optional

def process_branches(
    repo: Any,
    session: Any,
    repo_id: str,
    owner_login: str
) -> Optional[str]:
    default_branch_id = None
    try:
        branches = list(repo.get_branches())
        logger.info(f"    Found {len(branches)} branches...")
        existing_branches = get_existing_branch_metadata(session, repo_id)
        branches_to_process = []
        for branch in branches:
            existing = existing_branches.get(branch.name)
            if not existing or existing['last_commit_sha'] != branch.commit.sha or existing['is_deleted']:
                branches_to_process.append(branch)
        skip_count = len(branches) - len(branches_to_process)
        if skip_count > 0:
            logger.info(f"    Processing {len(branches_to_process)} branches, skipping {skip_count} unchanged...")
        else:
            logger.info(f"    Processing {len(branches_to_process)} branches...")
        for branch in branches_to_process:
            new_branch_handler(session, repo, branch, repo_id, owner_login)
            if branch.name == repo.default_branch:
                default_branch_id = f"branch_{repo.name}_{branch.name.replace('/', '_').replace('-', '_')}"
    except Exception as e:
        logger.info(f"    Warning: Could not fetch branches - {str(e)}")
    return default_branch_id
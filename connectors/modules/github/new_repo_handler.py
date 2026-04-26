from typing import Optional, Tuple
from neo4j import Session
from github.Repository import Repository as GitHubRepository
from db.models import Repository, merge_repository

from common.logger import logger

def new_repo_handler(session: Session, repo: GitHubRepository) -> Tuple[Optional[str], str]:
    """Handle a repository by creating Repository node in Neo4j.

    Args:
        session (Session): Neo4j session
        repo (GitHubRepository): GitHub repository object

    Returns:
        Tuple[Optional[str], Optional[str]]: (repo_id, repo_created_at) or (None, None) if failed
    """

    logger.info(f"    Processing repository: {repo.name}")

    # Extract repository information
    repo_id = f"repo_{repo.name.replace('-', '_')}"
    if not repo.created_at:
        raise ValueError("Repository created_at is None")
    repo_created_at = repo.created_at.strftime("%Y-%m-%d")
    logger.debug(f"      Repository details: id='{repo_id}', created_at='{repo_created_at}'")
    logger.debug(f"      Full name: '{repo.full_name}', URL: '{repo.html_url}'")
    logger.debug(f"      Language: '{repo.language}', Private: {repo.private}")

    # Create Repository node
    topics = repo.get_topics()
    logger.debug(f"      Extracted topics: {topics}")
    logger.debug(f"      Description: '{repo.description or 'No description'}'")

    repository = Repository(
        id=repo_id,
        name=repo.name,
        full_name=repo.full_name,
        url=repo.html_url,
        language=repo.language or "",
        is_private=repo.private,
        topics=topics,
        created_at=repo_created_at
    )

    # Merge into Neo4j
    logger.debug(f"      Merging Repository node: {repo_id}")
    merge_repository(session, repository)
    repository.print_cli()

    logger.info(f"    ✓ Successfully merged repository node: {repo.name}")
    logger.debug(f"      Returning: repo_id='{repo_id}', repo_created_at='{repo_created_at}'")
    return repo_id, repo_created_at

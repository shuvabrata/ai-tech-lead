from typing import Optional, Tuple
from neo4j import Session
from github.Repository import Repository as GitHubRepository
from connectors.neo4j_db.models import Repository, merge_repository

from connectors.commons.logger import logger
from connectors.producers.fetch_github import fetch_repo_topics
from connectors.producers.map_github import map_repo

def new_repo_handler(session: Session, repo: GitHubRepository) -> Tuple[Optional[str], str]:
    """Handle a repository by creating Repository node in Neo4j.

    Args:
        session (Session): Neo4j session
        repo (GitHubRepository): GitHub repository object

    Returns:
        Tuple[Optional[str], Optional[str]]: (repo_id, repo_created_at) or (None, None) if failed
    """

    logger.info(f"    Processing repository: {repo.name}")

    topics = fetch_repo_topics(repo)
    logger.debug(f"      Extracted topics: {topics}")

    repo_data = map_repo(repo, topics)
    repo_id = repo_data["id"]
    repo_created_at = repo_data["created_at"]
    logger.debug(f"      Repository details: id='{repo_id}', created_at='{repo_created_at}'")
    logger.debug(f"      Full name: '{repo_data['full_name']}', URL: '{repo_data['url']}'")
    logger.debug(f"      Language: '{repo_data['language']}', Private: {repo_data['is_private']}")
    logger.debug(f"      Description: '{repo.description or 'No description'}'")

    repository = Repository(
        id=repo_id,
        name=repo_data["name"],
        full_name=repo_data["full_name"],
        url=repo_data["url"],
        language=repo_data["language"],
        is_private=repo_data["is_private"],
        topics=repo_data["topics"],
        created_at=repo_created_at
    )

    # Merge into Neo4j
    logger.debug(f"      Merging Repository node: {repo_id}")
    merge_repository(session, repository)
    repository.print_cli()

    logger.info(f"    ✓ Successfully merged repository node: {repo.name}")
    logger.debug(f"      Returning: repo_id='{repo_id}', repo_created_at='{repo_created_at}'")
    return repo_id, repo_created_at

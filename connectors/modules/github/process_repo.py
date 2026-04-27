from modules.github.new_repo_handler import new_repo_handler
from modules.github.process_branches import process_branches
from modules.github.process_collaborators import process_collaborators
from modules.github.process_commits import process_commits
from modules.github.process_pull_requests import process_pull_requests
from modules.github.process_teams import process_teams
from commons.config_validator import get_repo_branch_patterns, get_repo_extraction_sources
from commons.person_cache import PersonCache
from neo4j import Session
from github.Repository import Repository

from typing import Optional, Dict, Any, Tuple

from commons.logger import logger, LogContext
from modules.github.repo_last_synced_at import update__last_synced_at


def flush_person_cache(person_cache: PersonCache, session: Session) -> None:
    try:
        person_cache.flush_identity_mappings(session)
        stats = person_cache.get_stats()
        logger.info(f"    📊 PersonCache stats (commits + PRs): {stats['cache_hits']} hits, {stats['cache_misses']} misses, hit rate: {stats['hit_rate']}")
    except Exception as e:
        logger.info(f"    Warning: Could not flush PersonCache - {str(e)}")


def process_repo(repo: Repository, session: Session, repo_config: Optional[Dict[str, Any]] = None, github_obj=None) -> None:
    with LogContext(request_id=repo.full_name):
        return process_repo_(repo, session, repo_config, github_obj)

def process_repo_(repo: Repository, session: Session, repo_config: Optional[Dict[str, Any]] = None, github_obj=None) -> None:
    """Process repository: create repo node, collaborators, teams, branches, and commits in Neo4j.
    
    Args:
        repo (Repository): GitHub repository object
        session (Session): Neo4j session
        repo_config (Optional[Dict[str, Any]]): Optional repository configuration dict with branch_patterns, extraction_sources, etc.
    """
    processed_users_cache: Dict[str, Any] = {}
    repo_config = repo_config or {}
    branch_patterns = get_repo_branch_patterns(repo_config)
    extraction_sources = get_repo_extraction_sources(repo_config)
    logger.debug(f"    Using extraction sources: {extraction_sources}")
    if "branch" in extraction_sources:
        logger.debug(f"    Using branch patterns: {branch_patterns}")

    repo_id, repo_created_at = new_repo_handler(session, repo)
    if repo_id is None:
        logger.info(f"    Warning: Skipping collaborators/teams due to repo creation failure")
        raise Exception("Repository node creation failed")

    process_collaborators(repo, session, repo_id, repo_created_at, processed_users_cache)
    process_teams(repo, session, repo_id, repo_created_at, processed_users_cache)
    default_branch_id = process_branches(repo, session, repo_id, repo.owner.login)
    person_cache = PersonCache()

    if default_branch_id:
        # Its possible that nothing has changed in default branch since last sync, 
        # so we should only process commits if there are new commits to process
        process_commits(repo, session, repo_id, default_branch_id, branch_patterns, extraction_sources, person_cache)
        
    process_pull_requests(repo, session, repo_id, repo, person_cache, github_obj=github_obj)
    flush_person_cache(person_cache, session)
    update__last_synced_at(session, repo_id)

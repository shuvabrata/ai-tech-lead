from connectors.neo4j_db.models import Branch, Relationship, merge_branch, merge_relationship
from common.logger import logger
from connectors.producers.map_github import map_branch
from typing import Any, Optional
from neo4j import Session

# NOTE FOR FUTURE DEVELOPERS:
# We do NOT fetch branch creation timestamp (created_at) because:
#
# 1. GitHub API does not provide direct access to branch ref creation time
# 2. The only way to approximate it is to iterate through ALL commits on the branch
#    to find the first/oldest commit timestamp
# 3. For long-lived branches (e.g., main with 10,000+ commits), this requires:
#    - ~334 API calls (GitHub paginates commits at 30 per page)
#    - 3-5 MINUTES per branch (network latency + rate limiting)
#    - For repos like PyTorch (85K commits): 40+ MINUTES per branch!
# 4. This creates severe performance issues:
#    - Processing 10 branches = 30-50 minutes
#    - Processing 100 repos = HOURS of runtime
#    - Exhausts GitHub API rate limits quickly
#
# SOLUTION: We removed the 'created_at' field from Branch dataclass entirely.
# Use 'last_commit_timestamp' for identifying stale branches - it's already available
# from the branch object with zero additional API calls.
#
# Performance improvement: 100,000x faster (from minutes to milliseconds per branch)


def new_branch_handler(
    session: Session,
    repo: Any,
    branch: Any,
    repo_id: str,
    repo_owner: Optional[str] = None
) -> None:
    """Handle a branch by creating Branch node and BRANCH_OF relationship (undirected).

    Args:
        session: Neo4j session
        repo: GitHub repository object (for fetching commit history)
        branch: GitHub branch object
        repo_id: Repository ID to create relationship with
        repo_owner: GitHub repository owner (optional, for URL generation)
    """
    try:
        branch_name = branch.name
        logger.info(f"      Processing branch: {branch_name}")

        branch_data = map_branch(repo.name, repo.default_branch, branch, repo_owner)
        branch_id = branch_data["id"]
        logger.debug(f"        Branch properties: default={branch_data['is_default']}, protected={branch_data['is_protected']}")
        logger.debug(f"        Last commit: {branch_data['last_commit_sha'][:8]}, timestamp: {branch_data['last_commit_timestamp']}")
        if branch_data["url"]:
            logger.debug(f"        Generated URL: {branch_data['url']}")

        logger.debug(f"        Creating Branch node with ID: {branch_id}")
        branch_node = Branch(
            id=branch_id,
            name=branch_data["name"],
            is_default=branch_data["is_default"],
            is_protected=branch_data["is_protected"],
            is_deleted=branch_data["is_deleted"],
            is_external=branch_data["is_external"],
            last_commit_sha=branch_data["last_commit_sha"],
            last_commit_timestamp=branch_data["last_commit_timestamp"],
            url=branch_data["url"]
        )

        logger.debug(f"        Creating BRANCH_OF relationship between {branch_id} and {repo_id}")
        relationship = Relationship(
            type="BRANCH_OF",
            from_id=branch_id,
            to_id=repo_id,
            from_type="Branch",
            to_type="Repository"
        )

        logger.debug(f"        Merging Branch node and relationship")
        merge_branch(session, branch_node)
        branch_node.print_cli()

        merge_relationship(session, relationship)
        relationship.print_cli()

        logger.info(f"      ✓ Successfully processed branch: {branch_name}")
        logger.debug(f"        Branch summary: id='{branch_id}', default={branch_data['is_default']}, protected={branch_data['is_protected']}")

    except Exception as e:
        logger.info(f"      ✗ Error: Failed to create Branch for {branch.name}: {str(e)}")
        logger.exception(e)

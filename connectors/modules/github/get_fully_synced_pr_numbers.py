from typing import Set
from neo4j import Session

def get_fully_synced_pr_numbers(
    session: Session,
    repo_id: str
) -> Set[int]:
    """Get list of PR numbers for closed/merged PRs already in Neo4j.

    Args:
        session: Neo4j session
        repo_id: Repository node ID

    Returns:
        set: Set of PR numbers for closed/merged PRs (won't change anymore)
    """
    # Optimization: Only retrieve PRs in terminal states (merged/closed)
    # These states are immutable - once a PR is merged or closed, it won't change anymore
    # This allows us to skip re-processing them on subsequent syncs
    query = """
    MATCH (pr:PullRequest)-[:TARGETS]->(b:Branch)-[:BRANCH_OF]-(r:Repository {id: $repo_id})
    WHERE pr.state IN ['merged', 'closed']
    RETURN collect(pr.number) as processed_pr_numbers
    """
    result = session.run(query, repo_id=repo_id).single()

    if result and result['processed_pr_numbers']:
        return set(result['processed_pr_numbers'])
    return set()

from datetime import datetime, timezone

from typing import Any, Optional
from connectors.neo4j_db.models import PullRequest, Branch, Relationship, merge_pull_request, merge_branch, merge_relationship
from connectors.commons.person_cache import PersonCache
from common.logger import logger
from connectors.producers.fetch_github import (
    fetch_external_branch_details,
    fetch_pr_reviews,
    fetch_pr_commits,
)
from connectors.producers.map_github import (
    map_external_branch,
    map_pr_user,
    map_pull_request,
    map_pr_reviews,
)

def create_or_get_external_branch(
    session: Any,
    repo_name: str,
    head_ref: Any,
    pr_number: int
) -> Optional[str]:
    """Create or get a Branch node for external (fork) branches.

    Args:
        session: Neo4j session
        repo_name: Repository name
        head_ref: Head reference object from PR (contains repo and ref info)
        pr_number: PR number for logging

    Returns:
        str: Branch ID if successful, None otherwise
    """
    try:
        branch_name = head_ref.ref
        logger.debug(f"        Processing external branch: {branch_name} for PR #{pr_number}")

        branch_details = fetch_external_branch_details(head_ref)
        branch_data = map_external_branch(repo_name, head_ref, branch_details)
        branch_id = branch_data["id"]
        logger.debug(f"        External branch ID: {branch_id}")

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

        merge_branch(session, branch_node)
        return branch_id

    except Exception as e:
        logger.info(f"      Warning: Could not create external branch for PR #{pr_number}: {str(e)}")
        logger.exception(e)
        return None


def get_or_create_pr_author(
    session: Any,
    pr_user: Any,
    person_cache: PersonCache
) -> str:
    """Get or create Person for PR author using PersonCache.

    Uses ``map_pr_user`` for field extraction and normalisation, then
    delegates to PersonCache for the actual DB lookup / creation.

    Args:
        session: Neo4j session
        pr_user: GitHub User object
        person_cache: PersonCache for batch operations (required for performance)

    Returns:
        str: Person ID
    """
    try:
        if pr_user is None:
            return "github::Person::unknown"

        user_data = map_pr_user(pr_user)
        github_login = user_data["login"]
        github_name = user_data["name"]
        github_email = user_data["email"]

        person_id, is_new = person_cache.get_or_create_person(
            session,
            email=github_email,
            name=github_name,
            provider="github",
            external_id=github_login
        )

        identity_id = f"identity_github_{github_login}"
        person_cache.queue_identity_mapping(
            person_id=person_id,
            identity_id=identity_id,
            provider="GitHub",
            username=github_login,
            email=github_email if github_email else "",
            last_updated_at=datetime.now(timezone.utc).isoformat()
        )

        return person_id

    except Exception as e:
        logger.info(f"      Warning: Failed to create PR author: {str(e)}")
        logger.exception(e)
        return "github::Person::unknown"


def new_pull_request_handler(
    session: Any,
    repo: Any,
    pr: Any,
    repo_id: str,
    repo_owner: str,
    person_cache: PersonCache
) -> bool:
    """
    Handle a pull request by creating PullRequest node and all relationships.
    
    Relationships created:
    - TARGETS: PR → Branch (base branch)
    - FROM: PR → Branch (head branch, may be external)
    - CREATED_BY: PR → Person
    - REVIEWED_BY: PR → Person (with state property)
    - REQUESTED_REVIEWER: PR → Person
    - MERGED_BY: PR → Person (only for merged PRs)
    - INCLUDES: PR → Commit (only for merged PRs, only commits in our DB)
    
    Args:
        session: Neo4j session
        repo: GitHub repository object
        pr: GitHub PullRequest object
        repo_id: Repository ID
        repo_owner: GitHub repository owner (for URL generation)
        person_cache: PersonCache for batch operations (required for performance)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Skip draft PRs
        if pr.draft:
            logger.info(f"      Skipping draft PR #{pr.number}")
            return False

        # Map PR attributes
        pr_data = map_pull_request(repo.name, pr, repo_owner)
        pr_id = pr_data["id"]
        state = pr_data["state"]

        # Create PullRequest node
        pull_request = PullRequest(
            id=pr_id,
            number=pr_data["number"],
            title=pr_data["title"],
            state=state,
            created_at=pr_data["created_at"],
            updated_at=pr_data["updated_at"],
            merged_at=pr_data["merged_at"],
            closed_at=pr_data["closed_at"],
            commits_count=pr_data["commits_count"],
            additions=pr_data["additions"],
            deletions=pr_data["deletions"],
            changed_files=pr_data["changed_files"],
            comments=pr_data["comments"],
            review_comments=pr_data["review_comments"],
            head_branch_name=pr_data["head_branch_name"],
            base_branch_name=pr_data["base_branch_name"],
            labels=pr_data["labels"],
            mergeable_state=pr_data["mergeable_state"],
            url=pr_data["url"]
        )

        # Merge PR node
        merge_pull_request(session, pull_request)

        # Track relationships
        relationships_created = 0

        # 1. TARGETS relationship (base branch - should always exist in our repo)
        targets_rel = Relationship(
            type="TARGETS",
            from_id=pr_id,
            to_id=pr_data["base_branch_id"],
            from_type="PullRequest",
            to_type="Branch"
        )
        merge_relationship(session, targets_rel)
        relationships_created += 1

        # 2. FROM relationship (head branch - may be external/fork)
        head_branch_id: Optional[str] = None

        # Check if head is from a fork
        if pr.head.repo is None or pr.head.repo.id != repo.id:
            # External branch (fork or deleted)
            head_branch_id = create_or_get_external_branch(session, repo.name, pr.head, pr.number)
        else:
            # Internal branch - should exist in our Branch nodes
            head_branch_id = pr_data["head_branch_id"] or f"branch_{repo.name}_{pr.head.ref.replace('/', '_').replace('-', '_')}"

        if head_branch_id:
            from_rel = Relationship(
                type="FROM",
                from_id=pr_id,
                to_id=head_branch_id,
                from_type="PullRequest",
                to_type="Branch"
            )
            merge_relationship(session, from_rel)
            relationships_created += 1

        # 3. CREATED_BY relationship (PR author)
        author_id = get_or_create_pr_author(session, pr.user, person_cache)
        created_by_rel = Relationship(
            type="CREATED_BY",
            from_id=pr_id,
            to_id=author_id,
            from_type="PullRequest",
            to_type="Person"
        )
        merge_relationship(session, created_by_rel)
        relationships_created += 1

        # 4. REVIEWED_BY relationships (reviewers with their review state)
        try:
            reviews = fetch_pr_reviews(pr)
            # map_pr_reviews returns {login: state}; resolve person IDs from login via
            # get_or_create_pr_author using the raw review user objects
            reviewer_login_to_state = map_pr_reviews(reviews)
            # Build login → raw user map for PersonCache resolution
            login_to_user = {r.user.login: r.user for r in reviews if r.user}

            for login, review_state in reviewer_login_to_state.items():
                raw_user = login_to_user.get(login)
                reviewer_id = get_or_create_pr_author(session, raw_user, person_cache)
                reviewed_by_rel = Relationship(
                    type="REVIEWED_BY",
                    from_id=pr_id,
                    to_id=reviewer_id,
                    from_type="PullRequest",
                    to_type="Person",
                    properties={"state": review_state}
                )
                merge_relationship(session, reviewed_by_rel)
                relationships_created += 1

        except Exception as e:
            logger.info(f"      Warning: Could not fetch reviews for PR #{pr.number}: {str(e)}")
            logger.exception(e)

        # 5. REQUESTED_REVIEWER relationships
        try:
            requested_reviewers = pr.requested_reviewers or []
            for reviewer in requested_reviewers:
                reviewer_id = get_or_create_pr_author(session, reviewer, person_cache)
                requested_reviewer_rel = Relationship(
                    type="REQUESTED_REVIEWER",
                    from_id=pr_id,
                    to_id=reviewer_id,
                    from_type="PullRequest",
                    to_type="Person"
                )
                merge_relationship(session, requested_reviewer_rel)
                relationships_created += 1

        except Exception as e:
            logger.info(f"      Warning: Could not fetch requested reviewers for PR #{pr.number}: {str(e)}")
            logger.exception(e)

        # 6. MERGED_BY relationship (only for merged PRs)
        if state == "merged" and pr.merged_by:
            merger_id = get_or_create_pr_author(session, pr.merged_by, person_cache)
            merged_by_rel = Relationship(
                type="MERGED_BY",
                from_id=pr_id,
                to_id=merger_id,
                from_type="PullRequest",
                to_type="Person"
            )
            merge_relationship(session, merged_by_rel)
            relationships_created += 1

        # 7. INCLUDES relationships (only for merged PRs, only commits in our DB)
        if state == "merged":
            try:
                pr_commits = fetch_pr_commits(pr)

                commits_linked = 0
                for pr_commit in pr_commits:
                    commit_sha = pr_commit.sha

                    # Check if this commit exists in our database
                    check_commit_query = """
                    MATCH (c:Commit {sha: $sha})
                    RETURN c.id as commit_id
                    LIMIT 1
                    """
                    result = session.run(check_commit_query, sha=commit_sha)
                    record = result.single()

                    if record:
                        commit_id = record["commit_id"]
                        includes_rel = Relationship(
                            type="INCLUDES",
                            from_id=pr_id,
                            to_id=commit_id,
                            from_type="PullRequest",
                            to_type="Commit"
                        )
                        merge_relationship(session, includes_rel)
                        relationships_created += 1
                        commits_linked += 1

                if commits_linked > 0:
                    logger.info(f"      Linked {commits_linked} commits to PR #{pr.number}")
                    
            except Exception as e:
                logger.info(f"      Warning: Could not fetch commits for PR #{pr.number}: {str(e)}")
                logger.exception(e)
        
        logger.info(f"      ✓ PR #{pr.number}: {pr.title[:50]} ({relationships_created} relationships)")
        return True
        
    except Exception as e:
        logger.info(f"      ✗ Failed to process PR #{pr.number}: {str(e)}")
        logger.exception(e)
        return False

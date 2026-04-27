from datetime import datetime, timezone

from typing import Any, Optional
from connectors.neo4j_db.models import PullRequest, Branch, Relationship, merge_pull_request, merge_branch, merge_relationship
from connectors.modules.github.retry_with_backoff import retry_with_backoff
from connectors.commons.person_cache import PersonCache
from connectors.commons.logger import logger

def create_or_get_external_branch(
    session: Any,
    repo_name: str,
    head_ref: Any,
    pr_number: int
) -> Optional[str]:
    """
    Create or get a Branch node for external (fork) branches.
    
    Args:
        session: Neo4j session
        repo_name: Repository name
        head_ref: Head reference object from PR (contains repo and ref info)
        pr_number: PR number for logging
        
    Returns:
        str: Branch ID if successful, None otherwise
    """
    try:
        # head_ref.ref is the branch name
        # head_ref.repo might be None for deleted forks
        branch_name = head_ref.ref
        logger.debug(f"        Processing external branch: {branch_name} for PR #{pr_number}")
        
        if head_ref.repo is None:
            # Fork has been deleted - create a placeholder branch
            logger.info(f"      Warning: Fork deleted for PR #{pr_number}, creating placeholder branch")
            branch_id = f"branch_external_{repo_name}_{branch_name.replace('/', '_').replace('-', '_')}_deleted"
            logger.debug(f"        Creating deleted fork placeholder: {branch_id}")
            
            branch_node = Branch(
                id=branch_id,
                name=branch_name,
                is_default=False,
                is_protected=False,
                is_deleted=True,
                is_external=True,
                last_commit_sha="unknown",
                last_commit_timestamp=datetime.now().isoformat(),
                url=None  # No URL available for deleted forks
            )
        else:
            # Fork still exists
            fork_repo = head_ref.repo
            fork_owner = fork_repo.owner.login
            logger.debug(f"        Processing existing fork: {fork_owner}/{fork_repo.name}")
            
            branch_id = f"branch_external_{fork_owner}_{fork_repo.name}_{branch_name.replace('/', '_').replace('-', '_')}"
            logger.debug(f"        External branch ID: {branch_id}")
            
            # Construct GitHub URL for the external branch
            github_url = f"https://github.com/{fork_owner}/{fork_repo.name}/tree/{branch_name}"
            logger.debug(f"        Generated fork branch URL: {github_url}")
            
            # Try to get the branch details from the fork
            try:
                logger.debug(f"        Fetching branch details from fork: {branch_name}")
                fork_branch = fork_repo.get_branch(branch_name)
                last_commit = fork_branch.commit
                last_commit_sha = last_commit.sha
                last_commit_timestamp = last_commit.commit.author.date.isoformat() if last_commit.commit.author.date else datetime.now().isoformat()
                is_protected = fork_branch.protected
            except Exception:
                # Branch might have been deleted from fork
                last_commit_sha = head_ref.sha if hasattr(head_ref, 'sha') else "unknown"
                last_commit_timestamp = datetime.now().isoformat()
                is_protected = False
            
            branch_node = Branch(
                id=branch_id,
                name=branch_name,
                is_default=False,
                is_protected=is_protected,
                is_deleted=False,
                is_external=True,
                last_commit_sha=last_commit_sha,
                last_commit_timestamp=last_commit_timestamp,
                url=github_url
            )
        
        # Merge the external branch into Neo4j
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
    """
    Get or create Person for PR author using PersonCache.
    
    Args:
        session: Neo4j session
        pr_user: GitHub User object
        person_cache: PersonCache for batch operations (required for performance)
        
    Returns:
        str: Person ID
    """
    try:
        if pr_user is None:
            return "person_github_unknown"
        
        # Get user details
        github_login = pr_user.login
        # Defensive: avoid triggering PyGithub API errors if user is deleted or inaccessible
        try:
            github_name = pr_user.name or github_login
        except Exception:
            logger.warning(f"      Warning: Could not fetch name for PR author {github_login}, using login as name")
            github_name = github_login
        try:
            github_email = pr_user.email if pr_user.email else None
        except Exception:
            logger.warning(f"      Warning: Could not fetch email for PR author {github_login}, using None as email")
            github_email = None
        # Normalize email to lowercase immediately at source for case-insensitive identity resolution
        github_email = github_email.lower() if github_email else None
        
        # Use PersonCache for lookup (required for performance)
        person_id, is_new = person_cache.get_or_create_person(
            session,
            email=github_email,
            name=github_name,
            provider="github",
            external_id=github_login
        )
        
        # Queue IdentityMapping creation (batched on flush)
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
        return "person_github_unknown"


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
        
        # Create PR node
        pr_id = f"pr_{repo.name}_{pr.number}"
        
        # Get state
        if pr.merged:
            state = "merged"
        elif pr.state == "closed":
            state = "closed"
        else:
            state = "open"
        
        # Handle nullable datetime fields
        merged_at = pr.merged_at.isoformat() if pr.merged_at else None
        closed_at = pr.closed_at.isoformat() if pr.closed_at else None
        
        # Get labels
        labels = [label.name for label in pr.labels] if pr.labels else []
        
        # Generate GitHub URL if owner is provided
        github_url = None
        if repo_owner:
            github_url = f"https://github.com/{repo_owner}/{repo.name}/pull/{pr.number}"
        
        # Create PullRequest node
        pull_request = PullRequest(
            id=pr_id,
            number=pr.number,
            title=pr.title or "",
            state=state,
            created_at=pr.created_at.isoformat(),
            updated_at=pr.updated_at.isoformat(),
            merged_at=merged_at,
            closed_at=closed_at,
            commits_count=pr.commits,
            additions=pr.additions,
            deletions=pr.deletions,
            changed_files=pr.changed_files,
            comments=pr.comments,
            review_comments=pr.review_comments,
            head_branch_name=pr.head.ref,
            base_branch_name=pr.base.ref,
            labels=labels,
            mergeable_state=pr.mergeable_state or "unknown",
            url=github_url
        )
        
        # Merge PR node
        merge_pull_request(session, pull_request)
        
        # Track relationships
        relationships_created = 0
        
        # 1. TARGETS relationship (base branch - should always exist in our repo)
        base_branch_id = f"branch_{repo.name}_{pr.base.ref.replace('/', '_').replace('-', '_')}"
        targets_rel = Relationship(
            type="TARGETS",
            from_id=pr_id,
            to_id=base_branch_id,
            from_type="PullRequest",
            to_type="Branch"
        )
        merge_relationship(session, targets_rel)
        relationships_created += 1
        
        # 2. FROM relationship (head branch - may be external/fork)
        head_branch_id = None
        
        # Check if head is from a fork
        if pr.head.repo is None or pr.head.repo.id != repo.id:
            # External branch (fork or deleted)
            head_branch_id = create_or_get_external_branch(session, repo.name, pr.head, pr.number)
        else:
            # Internal branch - should exist in our Branch nodes
            head_branch_id = f"branch_{repo.name}_{pr.head.ref.replace('/', '_').replace('-', '_')}"
        
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
            reviews = retry_with_backoff(lambda: list(pr.get_reviews()))
            
            # Track unique reviewers and their latest review state
            reviewer_states = {}
            for review in reviews:
                if review.user:
                    reviewer_id = get_or_create_pr_author(session, review.user, person_cache)
                    # Keep the most recent review state for each reviewer
                    # States: APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED
                    if review.state in ["APPROVED", "CHANGES_REQUESTED", "COMMENTED"]:
                        reviewer_states[reviewer_id] = review.state
            
            # Create REVIEWED_BY relationships
            for reviewer_id, review_state in reviewer_states.items():
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
            # Get requested reviewers (individuals, not teams)
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
                # Get commits from this PR
                pr_commits = retry_with_backoff(lambda: list(pr.get_commits()))
                
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

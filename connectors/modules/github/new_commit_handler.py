import re
from datetime import datetime, timezone
from typing import Optional, List

from db.models import Commit, Relationship, merge_commit, merge_relationship
from modules.github.new_file_handler import new_file_handler
from modules.github.retry_with_backoff import retry_with_backoff
from common.person_cache import PersonCache
from common.logger import logger

from typing import Any

def is_commit_fully_synced(session: Any, commit_id: str, commit_sha: str) -> bool:
    """
    Check if a commit is already fully synced (has all MODIFIES relationships).
    
    Since commits are immutable, if a commit exists with fully_synced=true,
    we can skip all processing including the expensive commit.files API call.
    
    Args:
        session: Neo4j session
        commit_id: Commit node ID
        commit_sha: Commit SHA for logging
        
    Returns:
        bool: True if commit is fully synced, False otherwise
    """
    query = """
    MATCH (c:Commit {id: $commit_id})
    WHERE c.fully_synced = true
    RETURN c.fully_synced as is_synced
    """
    result = session.run(query, commit_id=commit_id).single()
    
    if result and result['is_synced']:
        logger.debug(f"      Commit {commit_sha[:8]} is already fully synced, skipping")
        return True
    
    return False


def mark_commit_fully_synced(session: Any, commit_id: str) -> None:
    """
    Mark a commit as fully synced after all MODIFIES relationships are created.
    
    Args:
        session: Neo4j session
        commit_id: Commit node ID
    """
    query = """
    MATCH (c:Commit {id: $commit_id})
    SET c.fully_synced = true
    RETURN c
    """
    session.run(query, commit_id=commit_id)


def get_or_create_commit_author(session: Any, commit_author: Any, person_cache: PersonCache) -> str:
    """
    Get or create Person for a commit author using PersonCache.
    
    Args:
        session: Neo4j session
        commit_author: GitHub commit author object
        person_cache: PersonCache for batch operations (required for performance)
        
    Returns:
        str: Person ID for the author
    """
    try:
        logger.debug(f"      Processing commit author: {commit_author}")
        
        # Extract author information
        # GitHub commit authors can be User objects or just name/email dicts
        if hasattr(commit_author, 'login'):
            # Full user object
            github_login = commit_author.login
            
            # Safely access name property (may trigger lazy load that can fail for bots)
            try:
                github_name = commit_author.name if commit_author.name else github_login
            except Exception:
                # Lazy load failed (common for bot accounts like "Copilot")
                github_name = github_login
                logger.warning(f"        Could not load name for '{github_login}', using login as name")
            
            # Safely access email property (may trigger lazy load that can fail for bots)
            try:
                github_email = commit_author.email if commit_author.email else ""
            except Exception:
                # Lazy load failed (common for bot accounts)
                github_email = ""
                logger.warning(f"        Could not load email for '{github_login}', using empty email")
            
            # Normalize email to lowercase immediately at source
            github_email = github_email.lower() if github_email else ""
            logger.debug(f"        Full user object: login='{github_login}', name='{github_name}', email='{github_email}'")
        elif hasattr(commit_author, 'name'):
            # Name/email only (common for commits)
            github_name = commit_author.name or "Unknown"
            github_email = commit_author.email or ""
            # Normalize email to lowercase immediately at source
            github_email = github_email.lower() if github_email else ""
            # Create a sanitized login from email or name
            if github_email:
                github_login = github_email.split('@')[0]
            else:
                github_login = github_name.lower().replace(' ', '_')
            logger.debug(f"        Name/email only: derived_login='{github_login}', name='{github_name}', email='{github_email}'")
        else:
            # Fallback for unknown author format
            github_login = "unknown"
            github_name = "Unknown"
            github_email = ""
            logger.debug(f"        Unknown author format, using fallback values")
        
        logger.debug(f"        Using PersonCache for lookup: {github_login}, {github_email}")
        
        # Use PersonCache for lookup (required for performance)
        # Convert empty string email to None for proper NULL handling
        email = github_email if github_email else None
        
        person_id, is_new = person_cache.get_or_create_person(
            session,
            email=email,
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
            email=github_email,
            last_updated_at=datetime.now(timezone.utc).isoformat()
        )
        
        if is_new:
            logger.info(f"      ✓ Created commit author: {github_name} ({github_login})")
        else:
            logger.debug(f"        Reused existing person: {person_id}")
        
        logger.debug(f"        Returning person_id: {person_id}")
        
        return person_id
        
    except Exception as e:
        logger.debug(f"        Error creating commit author: {str(e)}", exc_info=True)
        logger.exception(e)
        # Return a fallback person ID
        fallback_id = "person_github_unknown"
        logger.debug(f"        Using fallback person ID: {fallback_id}")
        return fallback_id


def extract_issue_keys(message: str) -> List[str]:
    """
    Extract Jira issue keys from commit message.
    
    Supports patterns:
    - [PROJ-123]
    - PROJ-123:
    - (PROJ-123)
    - PROJ-123 at start or after space
    
    Args:
        message: Commit message string
        
    Returns:
        list: List of unique issue keys found
    """
    # Pattern: Project key (2+ uppercase letters) followed by hyphen and number
    # Matches: PROJ-123, ABC-456, STORY-789, etc.
    pattern = r'\b([A-Z]{2,}-\d+)\b'
    matches = re.findall(pattern, message)
    return list(set(matches))  # Return unique keys


def extract_issue_keys_from_branch(branch_name: str, patterns: Optional[List[str]] = None) -> List[str]:
    """
    Extract Jira issue keys from Git branch name.
    
    Supports both Git Flow conventions and direct prefix patterns:
    - feature/PROJ-123-description
    - bugfix/PROJ-123-fix-issue
    - PROJ-123-description (direct prefix)
    
    Args:
        branch_name: Git branch name string
        patterns: Optional list of regex patterns to use. Each pattern must have
                 one capture group to extract the issue key. If None, uses defaults.
        
    Returns:
        list: List of unique issue keys found
    """
    # Default patterns support both Git Flow and direct prefix
    if patterns is None:
        patterns = [
            r'(?:feature|bugfix|hotfix|release)/([A-Z]{2,}-\d+)',  # Git Flow
            r'^([A-Z]{2,}-\d+)',  # Direct prefix
        ]
    
    all_matches = []
    
    for pattern in patterns:
        try:
            matches = re.findall(pattern, branch_name)
            all_matches.extend(matches)
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{pattern}': {e}")
            continue
    
    unique_keys = list(set(all_matches))
    
    if unique_keys:
        logger.debug(f"        Extracted issue keys from branch '{branch_name}': {unique_keys}")
    
    return unique_keys


def get_or_create_issue_stub(session: Any, issue_key: str) -> str:
    """
    Get or create a stub Issue node for a Jira issue key.
    
    Creates a minimal Issue node if it doesn't exist. When the full Jira data
    is loaded later, the MERGE operation will update this stub with complete data.
    This allows commits to reference issues regardless of load order.
    
    Args:
        session: Neo4j session
        issue_key: Issue key (e.g., "PROJ-123")
        
    Returns:
        str: Issue ID (always returns a valid ID)
    """
    issue_id = f"issue_{issue_key}"
    
    query = """
    MERGE (i:Issue {id: $issue_id})
    ON CREATE SET i.key = $issue_key,
                  i.source = 'github_reference',
                  i.created_at = datetime()
    RETURN i.id as issue_id, i.source as source
    """
    result = session.run(query, issue_id=issue_id, issue_key=issue_key)
    record = result.single()
    
    if record and record['source'] == 'github_reference':
        logger.debug(f"        Created stub Issue node for {issue_key} (will be enriched when Jira loads)")
    
    return issue_id


def new_commit_handler(
    session: Any,
    repo_name: str,
    commit: Any,
    branch_id: str,
    repo_owner: str,
    branch_name: str,
    person_cache: PersonCache,
    branch_patterns: Optional[List[str]] = None,
    extraction_sources: Optional[List[str]] = None
) -> bool:
    """
    Handle a commit by creating Commit node and relationships.

    Args:
        session: Neo4j session
        repo_name: Repository name for ID generation
        commit: GitHub commit object
        branch_id: Branch ID this commit belongs to
        repo_owner: GitHub repository owner (for file URLs)
        branch_name: Branch name
        person_cache: PersonCache for batch operations (required for performance)
        branch_patterns: Optional list of regex patterns for extracting issue keys from branch names
        extraction_sources: Optional list of sources to extract from ("branch", "commit_message")

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.debug(f"      Processing commit: {commit.sha[:8]} on branch {branch_name}")
        logger.debug(f"        Repository: {repo_name}, Branch ID: {branch_id}")
        # Generate commit ID
        commit_sha = commit.sha
        commit_id = f"commit_{repo_name}_{commit_sha[:8]}"

        # Check if commit is already fully synced (optimization for subsequent runs)
        # Since commits are immutable, if fully_synced=true, we can skip entirely
        if is_commit_fully_synced(session, commit_id, commit_sha):
            logger.info(f"      ✓ Commit {commit_sha[:8]} already fully synced, skipping")
            return True

        # Check if commit already exists (but not fully synced)
        check_query = "MATCH (c:Commit {id: $commit_id}) RETURN c.id LIMIT 1"
        result = session.run(check_query, commit_id=commit_id)
        if result.single():
            # Commit exists but not fully synced - might need to process files
            logger.info(f"      Commit {commit_sha[:8]} exists but not fully synced, processing files...")
        else:
            logger.debug(f"      Creating new commit {commit_sha[:8]}")

        # Extract commit information
        commit_message = commit.commit.message or "No message"
        commit_timestamp = commit.commit.author.date.isoformat() if commit.commit.author.date else datetime.now().isoformat()

        # Get commit stats
        stats = commit.stats if hasattr(commit, 'stats') else None
        additions = stats.additions if stats else 0
        deletions = stats.deletions if stats else 0
        total_files = stats.total if stats else 0

        # Get or create commit author
        commit_author = commit.author if commit.author else commit.commit.author
        author_person_id = get_or_create_commit_author(session, commit_author, person_cache)

        # Generate GitHub URL if owner is provided
        github_url = None
        if repo_owner:
            github_url = f"https://github.com/{repo_owner}/{repo_name}/commit/{commit_sha}"

        # Create Commit node
        commit_node = Commit(
            id=commit_id,
            sha=commit_sha,
            message=commit_message,
            created_at=commit_timestamp,
            additions=additions,
            deletions=deletions,
            files_changed=total_files,
            url=github_url
        )
        logger.info(f"      Creating commit: {github_url if github_url else commit_sha[:8]}")

        # Merge commit into Neo4j
        merge_commit(session, commit_node)

        # Create PART_OF relationship (Commit → Branch)
        part_of_rel = Relationship(
            type="PART_OF",
            from_id=commit_id,
            to_id=branch_id,
            from_type="Commit",
            to_type="Branch"
        )
        merge_relationship(session, part_of_rel)

        # Create AUTHORED_BY relationship (undirected)
        authored_by_rel = Relationship(
            type="AUTHORED_BY",
            from_id=commit_id,
            to_id=author_person_id,
            from_type="Commit",
            to_type="Person"
        )
        merge_relationship(session, authored_by_rel)

        # Extract and validate Jira issue keys from configured sources
        sources = extraction_sources or ["branch", "commit_message"]
        all_issue_keys = []
        
        # Extract from branch name if enabled
        if "branch" in sources:
            branch_keys = extract_issue_keys_from_branch(branch_name, branch_patterns)
            if branch_keys:
                logger.debug(f"        Found {len(branch_keys)} issue key(s) from branch name: {branch_keys}")
                all_issue_keys.extend(branch_keys)
        
        # Extract from commit message if enabled
        if "commit_message" in sources:
            commit_keys = extract_issue_keys(commit_message)
            if commit_keys:
                logger.debug(f"        Found {len(commit_keys)} issue key(s) from commit message: {commit_keys}")
                all_issue_keys.extend(commit_keys)
        
        # Create REFERENCES relationships for all unique issue keys
        unique_issue_keys = list(set(all_issue_keys))
        
        for issue_key in unique_issue_keys:
            # Get or create Issue node (creates stub if doesn't exist)
            issue_id = get_or_create_issue_stub(session, issue_key)
            
            # Create REFERENCES relationship (Commit → Issue)
            references_rel = Relationship(
                type="REFERENCES",
                from_id=commit_id,
                to_id=issue_id,
                from_type="Commit",
                to_type="Issue"
            )
            merge_relationship(session, references_rel)
            logger.debug(f"        Created REFERENCES relationship: {commit_id} -> {issue_key}")

        # Process modified files
        try:
            files = retry_with_backoff(lambda: list(commit.files))
            for file in files:
                # Create File node
                file_id = new_file_handler(
                    session,
                    repo_name,
                    file.filename,
                    commit_timestamp,
                    file.additions + file.deletions if hasattr(file, 'additions') else 0,
                    repo_owner,
                    branch_name
                )

                if file_id:
                    # Create MODIFIES relationship (Commit → File) with per-file stats
                    modifies_rel = Relationship(
                        type="MODIFIES",
                        from_id=commit_id,
                        to_id=file_id,
                        from_type="Commit",
                        to_type="File",
                        properties={
                            "additions": file.additions if hasattr(file, 'additions') else 0,
                            "deletions": file.deletions if hasattr(file, 'deletions') else 0
                        }
                    )
                    merge_relationship(session, modifies_rel)
            
            # Mark commit as fully synced after all files processed
            mark_commit_fully_synced(session, commit_id)
            logger.debug(f"      ✓ Marked commit {commit_sha[:8]} as fully synced")
            
        except Exception as e:
            logger.info(f"      Warning: Could not fetch files for commit {commit_sha[:8]}: {str(e)}")
            logger.exception(e)
            # Don't mark as fully_synced if file processing failed

        return True

    except Exception as e:
        logger.info(f"      Warning: Failed to create commit {commit.sha[:8]}: {str(e)}")
        logger.exception(e)
        return False

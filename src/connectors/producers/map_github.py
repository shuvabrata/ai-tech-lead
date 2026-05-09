"""Pure mapping (transformation) functions for the GitHub connector.

All functions in this module are side-effect-free: they accept raw PyGithub
objects or primitive values, perform field extraction / ID generation / data
normalisation, and return plain ``dict`` values. No network I/O and no database
writes occur here.

Returning plain dicts (rather than ``ActivitySignal`` Pydantic models) keeps the
legacy write layer intact and defers model construction to the Phase 4 producers.

Phase 3: These utilities replace inline transformation logic that was embedded in
the legacy ``new_*_handler`` modules.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


def map_repo(repo: Any, topics: List[str]) -> Dict[str, Any]:
    """Extract and normalise repository attributes.

    Args:
        repo: PyGithub Repository object.
        topics: Pre-fetched list of topic strings (from ``fetch_repo_topics``).

    Returns:
        Dict with keys: ``id``, ``name``, ``full_name``, ``url``, ``language``,
        ``is_private``, ``topics``, ``created_at``, ``updated_at``.

    Raises:
        ValueError: When ``repo.created_at`` is ``None``.
    """
    if not repo.created_at:
        raise ValueError(f"Repository '{repo.name}' has no created_at timestamp.")

    repo_id = f"repo_{repo.name.replace('-', '_')}"
    updated_at = (
        repo.updated_at.strftime("%Y-%m-%d")
        if repo.updated_at
        else repo.created_at.strftime("%Y-%m-%d")
    )
    return {
        "id": repo_id,
        "name": repo.name,
        "full_name": repo.full_name,
        "url": repo.html_url,
        "language": repo.language or "",
        "is_private": repo.private,
        "topics": topics,
        "created_at": repo.created_at.strftime("%Y-%m-%d"),
        "updated_at": updated_at,
    }


# ---------------------------------------------------------------------------
# Branch
# ---------------------------------------------------------------------------


def map_branch(
    repo_name: str,
    default_branch: str,
    branch: Any,
    repo_owner: Optional[str],
) -> Dict[str, Any]:
    """Extract and normalise branch attributes.

    Args:
        repo_name: Repository name (used for ID generation and URL).
        default_branch: Name of the default branch (e.g. ``"main"``).
        branch: PyGithub Branch object.
        repo_owner: GitHub owner login; ``None`` disables URL generation.

    Returns:
        Dict with keys: ``id``, ``name``, ``is_default``, ``is_protected``,
        ``is_deleted``, ``is_external``, ``last_commit_sha``,
        ``last_commit_timestamp``, ``url``.
    """
    branch_name = branch.name
    branch_id = f"branch_{repo_name}_{branch_name.replace('/', '_').replace('-', '_')}"
    last_commit = branch.commit
    last_commit_sha = last_commit.sha
    last_commit_timestamp = last_commit.commit.author.date.isoformat()

    url: Optional[str] = None
    if repo_owner:
        url = f"https://github.com/{repo_owner}/{repo_name}/tree/{branch_name}"

    return {
        "id": branch_id,
        "name": branch_name,
        "is_default": branch_name == default_branch,
        "is_protected": branch.protected,
        "is_deleted": False,
        "is_external": False,
        "last_commit_sha": last_commit_sha,
        "last_commit_timestamp": last_commit_timestamp,
        "url": url,
    }


def map_external_branch(
    repo_name: str,
    head_ref: Any,
    branch_details: Optional[dict],
) -> Dict[str, Any]:
    """Map an external (fork) branch to a normalised attribute dict.

    ``branch_details`` should be the return value of
    ``fetch_github.fetch_external_branch_details``.  Pass ``None`` when the
    fork repo has been deleted.

    Args:
        repo_name: Name of the *target* repository (not the fork).
        head_ref: PyGithub ``PullRequestPart`` (``pr.head``).
        branch_details: Pre-fetched dict or ``None`` for deleted forks.

    Returns:
        Dict with keys: ``id``, ``name``, ``is_default``, ``is_protected``,
        ``is_deleted``, ``is_external``, ``last_commit_sha``,
        ``last_commit_timestamp``, ``url``.
    """
    branch_name = head_ref.ref
    safe_name = branch_name.replace("/", "_").replace("-", "_")

    if branch_details is None or head_ref.repo is None:
        # Fork has been deleted
        branch_id = f"branch_external_{repo_name}_{safe_name}_deleted"
        return {
            "id": branch_id,
            "name": branch_name,
            "is_default": False,
            "is_protected": False,
            "is_deleted": True,
            "is_external": True,
            "last_commit_sha": "unknown",
            "last_commit_timestamp": datetime.now().isoformat(),
            "url": None,
        }

    fork_repo = head_ref.repo
    fork_owner = fork_repo.owner.login
    branch_id = f"branch_external_{fork_owner}_{fork_repo.name}_{safe_name}"
    url = f"https://github.com/{fork_owner}/{fork_repo.name}/tree/{branch_name}"

    return {
        "id": branch_id,
        "name": branch_name,
        "is_default": False,
        "is_protected": branch_details["is_protected"],
        "is_deleted": False,
        "is_external": True,
        "last_commit_sha": branch_details["sha"],
        "last_commit_timestamp": branch_details["timestamp"],
        "url": url,
    }


# ---------------------------------------------------------------------------
# Commit
# ---------------------------------------------------------------------------


def map_commit_author(commit_author: Any) -> Dict[str, Any]:
    """Normalise a commit author object into a plain dict.

    Handles three author shapes returned by PyGithub:
    1. Full ``NamedUser`` objects with a ``login`` attribute.
    2. Lightweight objects with only ``name`` / ``email`` attributes.
    3. Unknown fallback.

    Email is always lower-cased at the source to enable case-insensitive
    identity resolution downstream.

    Args:
        commit_author: PyGithub commit author (``commit.author`` or
            ``commit.commit.author``).

    Returns:
        Dict with keys: ``login``, ``name``, ``email``.
    """
    if hasattr(commit_author, "login"):
        login = commit_author.login
        try:
            name = commit_author.name or login
        except Exception:
            name = login
        try:
            email = commit_author.email or ""
        except Exception:
            email = ""
    elif hasattr(commit_author, "name"):
        name = commit_author.name or "Unknown"
        email = commit_author.email or ""
        login = email.split("@")[0] if email else name.lower().replace(" ", "_")
    else:
        login = "unknown"
        name = "Unknown"
        email = ""

    return {
        "login": login,
        "name": name,
        "email": email.lower() if email else "",
    }


def map_commit(
    repo_name: str,
    commit: Any,
    repo_owner: Optional[str],
) -> Dict[str, Any]:
    """Extract and normalise commit attributes.

    Args:
        repo_name: Repository name (for ID and URL generation).
        commit: PyGithub Commit object.
        repo_owner: GitHub owner login; ``None`` disables URL generation.

    Returns:
        Dict with keys: ``id``, ``sha``, ``message``, ``created_at``,
        ``additions``, ``deletions``, ``files_changed``, ``url``.
    """
    sha = commit.sha
    commit_id = f"commit_{repo_name}_{sha[:8]}"
    message = commit.commit.message or "No message"
    timestamp = (
        commit.commit.author.date.isoformat()
        if commit.commit.author.date
        else datetime.now().isoformat()
    )
    stats = commit.stats if hasattr(commit, "stats") else None
    url: Optional[str] = None
    if repo_owner:
        url = f"https://github.com/{repo_owner}/{repo_name}/commit/{sha}"

    return {
        "id": commit_id,
        "sha": sha,
        "message": message,
        "created_at": timestamp,
        "additions": stats.additions if stats else 0,
        "deletions": stats.deletions if stats else 0,
        "files_changed": stats.total if stats else 0,
        "url": url,
    }


def map_commit_files(files: List[Any]) -> List[Dict[str, Any]]:
    """Normalise a list of commit file objects.

    Args:
        files: List of PyGithub File objects from a commit.

    Returns:
        List of dicts with keys: ``filename``, ``additions``, ``deletions``.
    """
    result = []
    for f in files:
        result.append(
            {
                "filename": f.filename,
                "additions": f.additions if hasattr(f, "additions") else 0,
                "deletions": f.deletions if hasattr(f, "deletions") else 0,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Pull request
# ---------------------------------------------------------------------------


def map_pr_user(pr_user: Any) -> Dict[str, Any]:
    """Normalise a GitHub user attached to a PR (author, reviewer, merger).

    Gracefully handles lazy-load failures common with bot accounts.

    Args:
        pr_user: PyGithub ``NamedUser`` object, or ``None``.

    Returns:
        Dict with keys: ``login``, ``name``, ``email``.  Falls back to
        ``"unknown"`` values when ``pr_user`` is ``None``.
    """
    if pr_user is None:
        return {"login": "unknown", "name": "Unknown", "email": None}

    login = pr_user.login
    try:
        name = pr_user.name or login
    except Exception:
        name = login
    try:
        email = pr_user.email if pr_user.email else None
    except Exception:
        email = None

    return {
        "login": login,
        "name": name,
        "email": email.lower() if email else None,
    }


def map_pull_request(
    repo_name: str,
    pr: Any,
    repo_owner: Optional[str],
) -> Dict[str, Any]:
    """Extract and normalise pull request attributes.

    Args:
        repo_name: Repository name (for ID and URL generation).
        pr: PyGithub PullRequest object.
        repo_owner: GitHub owner login; ``None`` disables URL generation.

    Returns:
        Dict with keys: ``id``, ``number``, ``title``, ``state``,
        ``created_at``, ``updated_at``, ``merged_at``, ``closed_at``,
        ``commits_count``, ``additions``, ``deletions``, ``changed_files``,
        ``comments``, ``review_comments``, ``head_branch_name``,
        ``base_branch_name``, ``labels``, ``mergeable_state``, ``url``,
        ``base_branch_id``, ``head_branch_id`` (internal only).
    """
    pr_id = f"pr_{repo_name}_{pr.number}"

    if pr.merged:
        state = "merged"
    elif pr.state == "closed":
        state = "closed"
    else:
        state = "open"

    merged_at = pr.merged_at.isoformat() if pr.merged_at else None
    closed_at = pr.closed_at.isoformat() if pr.closed_at else None
    labels = [label.name for label in pr.labels] if pr.labels else []

    url: Optional[str] = None
    if repo_owner:
        url = f"https://github.com/{repo_owner}/{repo_name}/pull/{pr.number}"

    # Pre-compute internal branch IDs for convenience
    base_branch_id = f"branch_{repo_name}_{pr.base.ref.replace('/', '_').replace('-', '_')}"
    head_branch_id: Optional[str] = None
    is_external_head = pr.head.repo is None or (
        hasattr(pr.head, "repo") and pr.head.repo is not None and pr.head.repo.id != getattr(pr, "_base_repo_id", None)
    )
    if not is_external_head and pr.head.repo is not None:
        head_branch_id = f"branch_{repo_name}_{pr.head.ref.replace('/', '_').replace('-', '_')}"

    return {
        "id": pr_id,
        "number": pr.number,
        "title": pr.title or "",
        "state": state,
        "created_at": pr.created_at.isoformat(),
        "updated_at": pr.updated_at.isoformat(),
        "merged_at": merged_at,
        "closed_at": closed_at,
        "commits_count": pr.commits,
        "additions": pr.additions,
        "deletions": pr.deletions,
        "changed_files": pr.changed_files,
        "comments": pr.comments,
        "review_comments": pr.review_comments,
        "head_branch_name": pr.head.ref,
        "base_branch_name": pr.base.ref,
        "labels": labels,
        "mergeable_state": pr.mergeable_state or "unknown",
        "url": url,
        "base_branch_id": base_branch_id,
        "head_branch_id": head_branch_id,
        "is_external_head": pr.head.repo is None or pr.head.repo.id != (pr.base.repo.id if pr.base.repo else None),
    }


def map_pr_reviews(reviews: List[Any]) -> Dict[str, str]:
    """Collapse a list of reviews into a ``{reviewer_login: latest_state}`` map.

    Only the latest non-``DISMISSED`` state per reviewer is retained.
    Supported states: ``APPROVED``, ``CHANGES_REQUESTED``, ``COMMENTED``.

    Args:
        reviews: List of PyGithub PullRequestReview objects.

    Returns:
        Dict mapping reviewer login → review state string.
    """
    reviewer_states: Dict[str, str] = {}
    for review in reviews:
        if review.user and review.state in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED"}:
            reviewer_states[review.user.login] = review.state
    return reviewer_states


# ---------------------------------------------------------------------------
# Issue key extraction (shared by commit and branch mapping)
# ---------------------------------------------------------------------------


def extract_issue_keys(message: str) -> List[str]:
    """Extract unique Jira issue keys from a commit message.

    Matches patterns like ``PROJ-123``, ``[ABC-456]``, ``(STORY-789)``.

    Args:
        message: Commit message string.

    Returns:
        Deduplicated list of issue key strings.
    """
    pattern = r"\b([A-Z]{2,}-\d+)\b"
    return list(set(re.findall(pattern, message)))


def extract_issue_keys_from_branch(
    branch_name: str,
    patterns: Optional[List[str]] = None,
) -> List[str]:
    """Extract unique Jira issue keys from a Git branch name.

    Supports both Git Flow conventions (``feature/PROJ-123-desc``) and direct
    prefix patterns (``PROJ-123-desc``).

    Args:
        branch_name: Git branch name string.
        patterns: Optional list of regex patterns.  Each must contain exactly
            one capture group that yields the issue key.  Defaults to the
            standard Git Flow and direct-prefix patterns.

    Returns:
        Deduplicated list of issue key strings.
    """
    if patterns is None:
        patterns = [
            r"(?:feature|bugfix|hotfix|release)/([A-Z]{2,}-\d+)",
            r"^([A-Z]{2,}-\d+)",
        ]

    all_matches: List[str] = []
    for pattern in patterns:
        try:
            all_matches.extend(re.findall(pattern, branch_name))
        except re.error:
            pass  # invalid user-supplied regex; skip silently

    return list(set(all_matches))

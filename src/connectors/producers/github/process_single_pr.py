from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Awaitable, Callable


from connectors.producers.fetch_github import (
    fetch_pr_commits,
    fetch_pr_reviews,
)

from connectors.producers.github.build_commit_signal import build_commit_signal
from connectors.producers.github.build_person_signal import build_person_signal
from connectors.producers.github.build_pull_request_signal import build_pull_request_signal
from connectors.producers.map_github import (
    fetch_github_user,
    map_commit,
    map_pr_reviews,
    map_pull_request,
)

from common.logger import logger
from common.activity_signal.models import ActivitySignal

async def process_single_pr(pr: Any, 
                            pr_since: datetime,
                            repo: Any,
                            repo_data:Dict[str, Any],
                            repo_owner: str,
                            seen_commits: set[str],
                            published_persons: set[str],
                            _pub: Callable[[Optional[ActivitySignal]], Awaitable[None]]) -> bool:
    """Process a single PR and publish its signals.

    Returns True if the PR loop should stop (PR is older than pr_since).
    """
    # Filter by date
    pr_updated = getattr(pr, "updated_at", None)
    logger.debug(f"PR # {pr.number} updated at {pr_updated} (since={pr_since})")
    if pr_updated and pr_updated.replace(tzinfo=timezone.utc) < pr_since:
        logger.debug("PR #%s skipped (updated before since=%s)", pr.number, pr_since.date())
        # Since PRs are processed newest-first, we can stop the entire loop
        # once we hit a PR older than our cutoff, saving massive API pagination!
        logger.info(
            "Stopping PR fetch loop for '%s' since remaining PRs will be older than %s",
            repo.full_name,
            pr_since.date(),
        )
        return True

    # fetch_github_user accesses .email and .name on PyGithub NamedUser stubs,
    # which triggers a blocking GET /users/{login} API call per user.
    # Run in a worker thread to avoid blocking the event loop.
    def get_pr_author_and_data() -> tuple[Dict[str, Any], Dict[str, Any]]:
        return fetch_github_user(pr.user), map_pull_request(repo.name, pr, repo_owner)

    author_data, pr_data = await asyncio.to_thread(get_pr_author_and_data)

    author_login = author_data.get("login") or author_data.get("name", "unknown")
    logger.debug(
        "Processing PR #%s '%s' by '%s'",
        pr.number,
        str(getattr(pr, "title", ""))[:60],
        author_login,
    )

    # Reviewer logins from review state dict
    reviews_raw = await asyncio.to_thread(fetch_pr_reviews, pr)
    review_map = map_pr_reviews(reviews_raw)
    reviewer_logins = list(review_map.keys())
    # Build reviewer enriched data in a thread — same lazy-load concern as PR author.
    def build_reviewer_user_data() -> Dict[str, Dict[str, Any]]:
        return {
            review.user.login: fetch_github_user(review.user)
            for review in reviews_raw
            if review.user and review.user.login
        }

    reviewer_user_data: Dict[str, Dict[str, Any]] = await asyncio.to_thread(
        build_reviewer_user_data
    )

    # Extract merger details — fetch full user data so a proper Person signal
    # is emitted (not just a stub node created by merge_relationship).
    merger_login: Optional[str] = None
    merger_data: Optional[Dict[str, Any]] = None
    if pr_data.get("state") == "merged":
        merged_by_obj = getattr(pr, "merged_by", None)
        if merged_by_obj and getattr(merged_by_obj, "login", None):
            merger_data = await asyncio.to_thread(fetch_github_user, merged_by_obj)
            merger_login = merger_data["login"]

    # Requested reviewers — fetch full user data via fetch_github_user so
    # these users get dedicated Person signals, not just stub nodes.
    requested_reviewers_raw = getattr(pr, "requested_reviewers", None) or []

    def fetch_requested_reviewer_data() -> Dict[str, Dict[str, Any]]:
        return {
            u.login: fetch_github_user(u)
            for u in requested_reviewers_raw
            if getattr(u, "login", None)
        }

    requested_reviewer_user_data: Dict[str, Dict[str, Any]] = await asyncio.to_thread(
        fetch_requested_reviewer_data
    )
    requested_reviewer_logins: List[str] = list(requested_reviewer_user_data.keys())

    # Commit SHAs for INCLUDES relationships
    try:
        pr_commits_raw = await asyncio.to_thread(fetch_pr_commits, pr)
        commit_shas = []
        for pr_c in pr_commits_raw:
            c_sha = getattr(pr_c, "sha", None)
            if not c_sha:
                continue
            commit_shas.append(c_sha)

            # If we haven't emitted this commit in the main loop, emit it now!
            if c_sha not in seen_commits:
                try:
                    # fetch_github_user handles NamedUser stubs (triggers GET /users/{login})
                    # and GitAuthor objects (git metadata, no API call) uniformly.
                    # Run in a worker thread to avoid blocking the event loop.
                    def extract_pr_commit_data() -> tuple[Dict[str, Any], Dict[str, Any]]:
                        return (
                            fetch_github_user(pr_c.author or pr_c.commit.author),
                            map_commit(repo.name, pr_c, repo_owner),
                        )

                    pr_a_data, pr_c_data = await asyncio.to_thread(extract_pr_commit_data)

                    pr_login = pr_a_data.get("login") or pr_a_data.get("name", "unknown")
                    if pr_login not in published_persons:
                        published_persons.add(pr_login)
                        logger.debug(
                            "[person:pr_commit_author] login=%r  name=%r  email=%r  pr=#%s  sha=%s",
                            pr_login,
                            pr_a_data.get("name"),
                            pr_a_data.get("email"),
                            pr.number,
                            c_sha[:8],
                        )
                        await _pub(build_person_signal(pr_a_data))

                    # Note: branch_name is set to None because we aren't certain which branch it belongs to here
                    # After PR is merged, the commit will be associated with the default branch in process_commits, 
                    # which is sufficient for our use cases and avoids extra API calls to check branch membership.
                    await _pub(build_commit_signal(pr_c_data, pr_a_data, repo_name=repo.name, branch_name=None))
                    seen_commits.add(c_sha)
                except Exception as inner_exc:
                    logger.warning("Failed to emit PR commit '%s': %s", c_sha, inner_exc)
    except Exception as exc:
        logger.warning("Could not fetch commits for PR #%s: %s", pr.number, exc)
        commit_shas = []

    # Emit Person signals for author + reviewers
    for person_login, _ in [(author_data.get("login") or author_data.get("name", "unknown"), None)]:
        if person_login not in published_persons:
            published_persons.add(person_login)
            logger.debug(
                "[person:pr_author] login=%r  name=%r  email=%r  pr=#%s",
                person_login,
                author_data.get("name"),
                author_data.get("email"),
                pr.number,
            )
            p_sig = build_person_signal(author_data)
            await _pub(p_sig)

    for r_login in reviewer_logins:
        if r_login not in published_persons:
            published_persons.add(r_login)
            r_data = reviewer_user_data.get(r_login, {"login": r_login, "name": r_login, "email": ""})
            logger.debug(
                "[person:pr_reviewer] login=%r  name=%r  email=%r  pr=#%s",
                r_login,
                r_data.get("name"),
                r_data.get("email"),
                pr.number,
            )
            r_sig = build_person_signal(r_data)
            await _pub(r_sig)

    for rr_login, rr_data in requested_reviewer_user_data.items():
        if rr_login not in published_persons:
            published_persons.add(rr_login)
            logger.debug(
                "[person:requested_reviewer] login=%r  name=%r  email=%r  pr=#%s",
                rr_login,
                rr_data.get("name"),
                rr_data.get("email"),
                pr.number,
            )
            await _pub(build_person_signal(rr_data))

    if merger_login and merger_data and merger_login not in published_persons:
        published_persons.add(merger_login)
        logger.debug(
            "[person:merger] login=%r  name=%r  email=%r  pr=#%s",
            merger_login,
            merger_data.get("name"),
            merger_data.get("email"),
            pr.number,
        )
        await _pub(build_person_signal(merger_data))

    pr_sig = build_pull_request_signal(
        pr_data,
        author_data,
        reviewer_logins,
        repo_data,
        requested_reviewer_logins=requested_reviewer_logins,
        merger_login=merger_login,
        commit_shas=commit_shas,
    )
    await _pub(pr_sig)
    return False
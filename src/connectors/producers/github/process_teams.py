from __future__ import annotations

import asyncio
import os
from typing import Any, Callable, Coroutine, Dict, List, Optional

from common.activity_signal.models import (
    ActivitySignal,
    Relationship,
    RelationshipTarget,
)
from connectors.producers.fetch_github import fetch_repo_teams
from connectors.producers.map_github import fetch_github_user
from common.logger import logger

_SOURCE = "github"


async def process_teams(
    repo: Any,
    repo_data: Dict[str, Any],
    full_name: str,
    published: Dict[str, int],
    pub_callback: Callable[[Optional[ActivitySignal]], Coroutine[Any, Any, None]],
    build_team_signal_fn: Callable[..., Optional[ActivitySignal]],
    build_person_signal_fn: Callable[..., Optional[ActivitySignal]],
) -> None:
    """Fetch teams for *repo* and publish Team and Person signals.

    Emits a Team signal with a COLLABORATOR relationship for each team,
    then emits Person signals with MEMBER_OF and COLLABORATOR relationships
    for each team member. Teams exceeding MAX_TEAM_SIZE are skipped entirely.
    """
    max_team_size = int(os.environ.get("MAX_TEAM_SIZE", "100"))
    logger.info("Fetching teams for '%s'...", full_name)
    try:
        teams_raw = await asyncio.to_thread(fetch_repo_teams, repo)
        for team in teams_raw:
            team_slug = getattr(team, "slug", None) or getattr(team, "name", "unknown")
            team_name = getattr(team, "name", team_slug)
            team_id = f"github_team_{team_slug}"
            permission = getattr(team, "permission", None)
            team_data_dict: Dict[str, Any] = {
                "id": team_id,
                "name": team_name,
                "slug": team_slug,
            }
            # Fetch members first — gate on MAX_TEAM_SIZE before emitting anything
            try:
                logger.info(f"Fetching members for team '{team_slug}' in '{full_name}'...")
                members_raw = await asyncio.to_thread(lambda: list(team.get_members()))
            except Exception as exc:
                logger.warning("Could not fetch members for team '%s': %s", team_slug, exc)
                members_raw = []

            if len(members_raw) > max_team_size:
                logger.warning(
                    "Skipping team '%s' entirely (%d members exceeds MAX_TEAM_SIZE=%d)",
                    team_slug,
                    len(members_raw),
                    max_team_size,
                )
                continue
            logger.info(
                f"Team '{team_slug}' has {len(members_raw)} members "
                f"(within MAX_TEAM_SIZE={max_team_size}), processing..."
            )

            await pub_callback(build_team_signal_fn(team_data_dict, repo_data, permission))

            # Fetch member details (name + email) in a worker thread.
            # The team members API returns NamedUser stubs — fetch_github_user
            # accesses .name and .email, triggering GET /users/{login} per member.
            def fetch_member_details() -> List[Dict[str, Any]]:
                return [
                    fetch_github_user(m)
                    for m in members_raw
                    if getattr(m, "login", None)
                ]

            # Emit Person signals for team members with MEMBER_OF and COLLABORATOR rels
            try:
                member_details = await asyncio.to_thread(fetch_member_details)
                for member_info in member_details:
                    member_login = member_info["login"]
                    member_rels: List[Relationship] = [
                        Relationship(
                            type="MEMBER_OF",
                            direction=None,
                            target=RelationshipTarget(
                                source=_SOURCE,
                                entity_type="Team",
                                id=team_slug,
                            ),
                        ),
                        Relationship(
                            type="COLLABORATOR",
                            direction=None,
                            target=RelationshipTarget(
                                source=_SOURCE,
                                entity_type="Repository",
                                id=repo_data["full_name"],
                            ),
                            properties={"permission": permission} if permission else None,
                        ),
                    ]
                    member_name = member_info["name"]
                    member_email = member_info["email"]
                    logger.debug(
                        "[person:team_member] login=%r  name=%r  email=%r  team=%s",
                        member_login,
                        member_name,
                        member_email,
                        team_slug,
                    )
                    member_sig = build_person_signal_fn(
                        {
                            "login": member_login,
                            "name": member_name,
                            "email": member_email,
                        },
                        extra_relationships=member_rels,
                    )
                    await pub_callback(member_sig)
            except Exception as exc:
                logger.warning("Could not fetch members for team '%s': %s", team_slug, exc)
    except Exception as exc:
        logger.warning("Could not fetch teams for '%s': %s", full_name, exc)
    logger.info("Teams done (%d) for '%s'", published.get("Team", 0), full_name)

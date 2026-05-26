from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine, Dict, List, Optional

from common.activity_signal.models import (
    ActivitySignal,
    Relationship,
    RelationshipTarget,
)
from common.logger import logger
from connectors.producers.fetch_github import fetch_repo_collaborators
from connectors.producers.map_github import fetch_github_user

_SOURCE = "github"


def _map_permission_and_role(collaborator: Any) -> tuple[str, Optional[str]]:
    """Map GitHub permission flags to legacy-style permission and role."""
    permissions = getattr(collaborator, "permissions", None)
    if not permissions:
        return "READ", None

    is_admin = bool(getattr(permissions, "admin", False))
    is_maintain = bool(getattr(permissions, "maintain", False))
    is_push = bool(getattr(permissions, "push", False))

    permission = "WRITE" if (is_admin or is_maintain or is_push) else "READ"

    role: Optional[str] = None
    if is_admin:
        role = "admin"
    elif is_maintain:
        role = "maintainer"
    elif is_push:
        role = "contributor"

    return permission, role


async def process_collaborators(
    repo: Any,
    repo_data: Dict[str, Any],
    full_name: str,
    published: Dict[str, int],
    pub_callback: Callable[[Optional[ActivitySignal]], Coroutine[Any, Any, None]],
    build_person_signal_fn: Callable[..., Optional[ActivitySignal]],
) -> None:
    """Fetch direct repository collaborators and publish Person collaborator signals.

    This preserves legacy semantics: direct collaborators emit a Person signal
    carrying a COLLABORATOR relationship to the repository with permission,
    optional role, and granted_at properties.
    """
    logger.info("Fetching collaborators for '%s'...", full_name)
    try:
        collaborators = await asyncio.to_thread(fetch_repo_collaborators, repo)
    except Exception as exc:
        logger.warning("Could not fetch collaborators for '%s': %s", full_name, exc)
        return

    repo_created_at = repo_data.get("created_at")

    for collaborator in collaborators:
        try:
            collaborator_data = await asyncio.to_thread(fetch_github_user, collaborator)
            login = collaborator_data.get("login") or "unknown"
            permission, role = _map_permission_and_role(collaborator)

            rel_props: Dict[str, Any] = {"permission": permission}
            if repo_created_at:
                rel_props["granted_at"] = repo_created_at
            if role:
                rel_props["role"] = role

            collaborator_rel = Relationship(
                type="COLLABORATOR",
                direction=None,
                target=RelationshipTarget(
                    source=_SOURCE,
                    entity_type="Repository",
                    id=repo_data["full_name"],
                ),
                properties=rel_props,
            )

            logger.debug(
                "[person:collaborator] login=%r permission=%r role=%r repo=%s",
                login,
                permission,
                role,
                repo_data.get("full_name", "?"),
            )

            sig = build_person_signal_fn(
                collaborator_data,
                extra_relationships=[collaborator_rel],
            )
            await pub_callback(sig)
        except Exception as exc:
            logger.warning(
                "Could not process collaborator '%s' in '%s': %s",
                getattr(collaborator, "login", "unknown"),
                full_name,
                exc,
            )

    logger.info("Collaborators done (%d) for '%s'", published.get("Person", 0), full_name)

"""Unit tests for connectors/producers/github/process_teams.py.

Tests call process_teams() directly, injecting real signal-builder callbacks
from github_mega_helper and patching only the I/O boundaries
(fetch_repo_teams, fetch_github_user, os.environ).

Coverage goals
--------------
- Happy path: single team + single member
- MAX_TEAM_SIZE exceeded: entire team skipped (no Team, no Person signals)
- MAX_TEAM_SIZE boundary: exactly at limit is allowed
- Mixed teams: one over limit, one within — only the within-limit team published
- Multiple teams: all within-limit teams published independently
- Team with zero members: Team signal emitted, no Person signals
- get_members() raises: members_raw falls back to [], Team signal still emitted
- fetch_repo_teams raises: swallowed gracefully, nothing published
- Member without login: excluded from Person signals
"""

from __future__ import annotations

import os
from contextlib import ExitStack
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.activity_signal.models import ActivitySignal
from connectors.producers.github.process_repo_signals import build_person_signal, build_team_signal
from connectors.producers.github.process_teams import process_teams

# ---------------------------------------------------------------------------
# Shared fixtures / factories
# ---------------------------------------------------------------------------

_PATCH_FETCH_TEAMS = "connectors.producers.github.process_teams.fetch_repo_teams"
_PATCH_FETCH_USER = "connectors.producers.github.process_teams.fetch_github_user"


def _repo_data(**overrides: Any) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": "repo_myrepo",
        "name": "myrepo",
        "full_name": "org/myrepo",
        "url": "https://github.com/org/myrepo",
        "language": "Python",
        "is_private": False,
        "topics": [],
        "created_at": "2023-01-01",
        "updated_at": "2024-06-01",
    }
    data.update(overrides)
    return data


def _mock_member(login: str, name: str = "Test User", email: str = "") -> MagicMock:
    m = MagicMock()
    m.login = login
    m.name = name
    m.email = email
    return m


def _mock_team(
    slug: str,
    members: List[MagicMock],
    permission: str = "push",
    name: Optional[str] = None,
) -> MagicMock:
    team = MagicMock()
    team.slug = slug
    team.name = name or slug.capitalize()
    team.permission = permission
    team.get_members = MagicMock(return_value=members)
    return team


async def _run_process_teams(
    teams: List[Any],
    max_team_size: str = "100",
    fetch_user_side_effect: Any = None,
    fetch_user_return_value: Any = None,
) -> tuple[List[ActivitySignal], Dict[str, int]]:
    """Run process_teams with fetch_repo_teams mocked to *teams*.

    Returns (published_signals, published_counts).
    """
    repo = MagicMock()
    repo.full_name = "org/myrepo"
    published: Dict[str, int] = {}
    published_sigs: List[ActivitySignal] = []

    async def pub(sig: Optional[ActivitySignal]) -> None:
        if sig:
            published_sigs.append(sig)
            published[sig.entity_type] = published.get(sig.entity_type, 0) + 1

    patches: List[Any] = [
        patch(_PATCH_FETCH_TEAMS, return_value=teams),
        patch.dict(os.environ, {"MAX_TEAM_SIZE": max_team_size}),
    ]
    if fetch_user_side_effect is not None:
        patches.append(patch(_PATCH_FETCH_USER, side_effect=fetch_user_side_effect))
    elif fetch_user_return_value is not None:
        patches.append(patch(_PATCH_FETCH_USER, return_value=fetch_user_return_value))

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        await process_teams(
            repo=repo,
            repo_data=_repo_data(),
            full_name="org/myrepo",
            published=published,
            pub_callback=pub,
            build_team_signal_fn=build_team_signal,
            build_person_signal_fn=build_person_signal,
        )

    return published_sigs, published


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProcessTeamsHappyPath:
    @pytest.mark.asyncio
    async def test_single_team_single_member_emits_team_and_person(self) -> None:
        """One team with one member → one Team signal and one Person signal."""
        member = _mock_member("alice", "Alice", "alice@example.com")
        team = _mock_team("eng", [member], permission="push")

        sigs, published = await _run_process_teams(
            [team],
            fetch_user_return_value={"login": "alice", "name": "Alice", "email": "alice@example.com"},
        )

        assert published.get("Team", 0) == 1
        assert published.get("Person", 0) == 1

    @pytest.mark.asyncio
    async def test_team_signal_has_collaborator_rel_to_repo(self) -> None:
        team = _mock_team("eng", [])

        sigs, _ = await _run_process_teams([team])

        team_sig = next(s for s in sigs if s.entity_type == "Team")
        collab_rels = [r for r in team_sig.relationships if r.type == "COLLABORATOR"]
        assert len(collab_rels) == 1
        assert collab_rels[0].target.entity_type == "Repository"
        assert collab_rels[0].target.external_id == "repo_myrepo"

    @pytest.mark.asyncio
    async def test_team_id_derived_from_slug(self) -> None:
        team = _mock_team("frontend", [])

        sigs, _ = await _run_process_teams([team])

        team_sig = next(s for s in sigs if s.entity_type == "Team")
        assert team_sig.external_id == "github_team_frontend"

    @pytest.mark.asyncio
    async def test_person_signal_has_member_of_rel_to_team(self) -> None:
        member = _mock_member("bob", "Bob", "bob@example.com")
        team = _mock_team("eng", [member])

        sigs, _ = await _run_process_teams(
            [team],
            fetch_user_return_value={"login": "bob", "name": "Bob", "email": "bob@example.com"},
        )

        person_sig = next(s for s in sigs if s.entity_type == "Person")
        member_of_rels = [r for r in person_sig.relationships if r.type == "MEMBER_OF"]
        assert len(member_of_rels) == 1
        assert member_of_rels[0].target.entity_type == "Team"
        assert member_of_rels[0].target.external_id == "github_team_eng"

    @pytest.mark.asyncio
    async def test_person_signal_has_collaborator_rel_with_permission(self) -> None:
        member = _mock_member("carol", "Carol", "carol@example.com")
        team = _mock_team("eng", [member], permission="admin")

        sigs, _ = await _run_process_teams(
            [team],
            fetch_user_return_value={"login": "carol", "name": "Carol", "email": "carol@example.com"},
        )

        person_sig = next(s for s in sigs if s.entity_type == "Person")
        collab_rels = [r for r in person_sig.relationships if r.type == "COLLABORATOR"]
        assert len(collab_rels) == 1
        assert collab_rels[0].properties is not None
        assert collab_rels[0].properties["permission"] == "admin"

    @pytest.mark.asyncio
    async def test_multiple_teams_all_published(self) -> None:
        """All within-limit teams are processed independently."""
        member_a = _mock_member("alice", "Alice", "alice@example.com")
        member_b = _mock_member("bob", "Bob", "bob@example.com")
        teams = [
            _mock_team("frontend", [member_a]),
            _mock_team("backend", [member_b]),
        ]

        user_data = [
            {"login": "alice", "name": "Alice", "email": "alice@example.com"},
            {"login": "bob", "name": "Bob", "email": "bob@example.com"},
        ]

        sigs, published = await _run_process_teams([teams[0], teams[1]], fetch_user_side_effect=user_data)

        assert published.get("Team", 0) == 2
        assert published.get("Person", 0) == 2
        team_ids = {s.external_id for s in sigs if s.entity_type == "Team"}
        assert team_ids == {"github_team_frontend", "github_team_backend"}

    @pytest.mark.asyncio
    async def test_team_with_zero_members_emits_team_signal_only(self) -> None:
        """A team returning an empty member list still emits the Team signal."""
        team = _mock_team("empty-team", [])

        sigs, published = await _run_process_teams([team])

        assert published.get("Team", 0) == 1
        assert published.get("Person", 0) == 0

    @pytest.mark.asyncio
    async def test_member_without_login_is_excluded(self) -> None:
        """Members with no login are silently skipped."""
        no_login_member = MagicMock()
        no_login_member.login = None
        ok_member = _mock_member("dave", "Dave", "dave@example.com")
        team = _mock_team("mixed", [no_login_member, ok_member])

        sigs, published = await _run_process_teams(
            [team],
            fetch_user_return_value={"login": "dave", "name": "Dave", "email": "dave@example.com"},
        )

        assert published.get("Person", 0) == 1
        person_sig = next(s for s in sigs if s.entity_type == "Person")
        assert person_sig.external_id == "person_github_dave"


class TestProcessTeamsMaxTeamSize:
    @pytest.mark.asyncio
    async def test_team_exceeding_max_size_emits_no_signals(self) -> None:
        """A team with more members than MAX_TEAM_SIZE must be skipped entirely."""
        members = [_mock_member(f"user{i}") for i in range(5)]
        team = _mock_team("big-team", members)

        sigs, published = await _run_process_teams([team], max_team_size="3")

        assert published.get("Team", 0) == 0
        assert published.get("Person", 0) == 0
        assert sigs == []

    @pytest.mark.asyncio
    async def test_team_exactly_at_max_size_is_allowed(self) -> None:
        """A team with exactly MAX_TEAM_SIZE members must be processed (boundary is inclusive)."""
        members = [_mock_member(f"user{i}") for i in range(3)]
        team = _mock_team("exact-team", members)

        user_data = [{"login": f"user{i}", "name": f"User {i}", "email": ""} for i in range(3)]

        sigs, published = await _run_process_teams([team], max_team_size="3", fetch_user_side_effect=user_data)

        assert published.get("Team", 0) == 1
        assert published.get("Person", 0) == 3

    @pytest.mark.asyncio
    async def test_mixed_teams_only_within_limit_published(self) -> None:
        """One team over limit is skipped; the other within limit is published."""
        big_members = [_mock_member(f"u{i}") for i in range(10)]
        small_member = _mock_member("solo", "Solo", "solo@example.com")
        teams = [
            _mock_team("giants", big_members),
            _mock_team("solo-team", [small_member]),
        ]

        sigs, published = await _run_process_teams(
            teams,
            max_team_size="5",
            fetch_user_return_value={"login": "solo", "name": "Solo", "email": "solo@example.com"},
        )

        assert published.get("Team", 0) == 1
        assert published.get("Person", 0) == 1
        team_sig = next(s for s in sigs if s.entity_type == "Team")
        assert team_sig.external_id == "github_team_solo-team"


class TestProcessTeamsErrorHandling:
    @pytest.mark.asyncio
    async def test_fetch_repo_teams_raises_does_not_crash(self) -> None:
        """An exception from fetch_repo_teams is swallowed and nothing is published."""
        repo = MagicMock()
        repo.full_name = "org/myrepo"
        published: Dict[str, int] = {}
        pub = AsyncMock()

        with patch(_PATCH_FETCH_TEAMS, side_effect=RuntimeError("API rate limit")):
            await process_teams(
                repo=repo,
                repo_data=_repo_data(),
                full_name="org/myrepo",
                published=published,
                pub_callback=pub,
                build_team_signal_fn=build_team_signal,
                build_person_signal_fn=build_person_signal,
            )

        pub.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_members_raises_team_signal_still_emitted(self) -> None:
        """If get_members() throws, members_raw falls back to [] and the Team signal is still emitted."""
        team = MagicMock()
        team.slug = "ops"
        team.name = "Ops"
        team.permission = "push"
        team.get_members = MagicMock(side_effect=RuntimeError("forbidden"))

        sigs, published = await _run_process_teams([team])

        assert published.get("Team", 0) == 1
        assert published.get("Person", 0) == 0

    @pytest.mark.asyncio
    async def test_no_teams_publishes_nothing(self) -> None:
        sigs, published = await _run_process_teams([])

        assert published == {}
        assert sigs == []

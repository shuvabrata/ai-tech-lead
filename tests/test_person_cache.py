from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from connectors.commons.person_cache import PersonCache
from connectors.neo4j_db.models import Person, _is_account_id_stub, merge_person


pytestmark = pytest.mark.unit


class _SingleResult:
    def __init__(self, row):
        self._row = row

    def single(self):
        return self._row


def test_get_or_create_person_reuses_existing_person_by_atlassian_account() -> None:
    session = MagicMock()

    def run_side_effect(query: str, **_kwargs):
        if "WHERE im.id IN $identity_ids" in query:
            return _SingleResult({"id": "jira::Person::acc123"})
        raise AssertionError(f"Unexpected query: {query}")

    session.run.side_effect = run_side_effect
    cache = PersonCache()

    with patch("connectors.commons.person_cache.merge_person") as mock_merge_person:
        person_id, is_new = cache.get_or_create_person(
            session,
            email=None,
            name="Alice Dev",
            provider="confluence",
            external_id="acc123",
            account_id="acc123",
        )

    assert person_id == "jira::Person::acc123"
    assert is_new is False
    mock_merge_person.assert_called_once()
    person = mock_merge_person.call_args.args[1]
    assert person.id == "jira::Person::acc123"
    assert person.name == "Alice Dev"


def test_get_or_create_person_prefers_email_before_atlassian_account() -> None:
    session = MagicMock()

    def run_side_effect(query: str, **_kwargs):
        if "WHERE p.email = $email" in query:
            return _SingleResult({"id": "github::Person::alice"})
        raise AssertionError(f"Unexpected query: {query}")

    session.run.side_effect = run_side_effect
    cache = PersonCache()

    with patch("connectors.commons.person_cache.merge_person") as mock_merge_person:
        person_id, is_new = cache.get_or_create_person(
            session,
            email="alice@example.com",
            name="Alice Dev",
            provider="confluence",
            external_id="acc123",
            account_id="acc123",
        )

    assert person_id == "github::Person::alice"
    assert is_new is False
    assert session.run.call_count == 1
    mock_merge_person.assert_called_once()
    person = mock_merge_person.call_args.args[1]
    assert person.id == "github::Person::alice"
    assert person.email == "alice@example.com"


# ---------------------------------------------------------------------------
# Merge guard: account-id shaped names must not clobber a real name
# ---------------------------------------------------------------------------


def test_is_account_id_stub_recognises_atlassian_ids() -> None:
    assert _is_account_id_stub("712020:cc7f7515-d137-44a0-9858-22b270a86387") is True
    assert _is_account_id_stub("557058:62105664-0fbe-4128-ab5c-3b0071e8f7f5") is True


def test_is_account_id_stub_treats_empty_blank_as_stub() -> None:
    assert _is_account_id_stub(None) is True
    assert _is_account_id_stub("") is True
    assert _is_account_id_stub("   ") is True


def test_is_account_id_stub_does_not_match_real_names() -> None:
    assert _is_account_id_stub("Alice Dev") is False
    assert _is_account_id_stub("Shuva Brata Deb") is False
    assert _is_account_id_stub("alice@example.com") is False


def test_merge_person_skips_name_when_incoming_is_account_id_stub() -> None:
    """A stub named by account id must NOT overwrite an existing real name."""
    session = MagicMock()
    person = Person(
        id="confluence::Person::712020:cc7f7515-d137-44a0-9858-22b270a86387",
        name="712020:cc7f7515-d137-44a0-9858-22b270a86387",
        email=None,
        url=None,
    )
    merge_person(session, person)
    # ``name`` must never be written to a raw account id, so it cannot clobber
    # a previously-resolved real name. The display props ARE coalesce-filled so
    # the node is never left blank, but a plain overwrite is forbidden.
    all_queries = " ".join(call.args[0] for call in session.run.call_args_list)
    assert "p.name = $name" not in all_queries
    assert "p._display_name = $_display_name" not in all_queries
    assert "p._on_hover_name = $_on_hover_name" not in all_queries
    # fill-only guards are present for the display props
    assert "coalesce(p._display_name, $_display_name)" in all_queries
    assert "coalesce(p._on_hover_name, $_on_hover_name)" in all_queries


def test_merge_person_fills_display_name_when_name_empty() -> None:
    """An empty name still coalesce-fills _display_name so the node is not blank."""
    session = MagicMock()
    person = Person(
        id="jira::Person::712020:23da340e-0000-0000-0000-000000000000",
        name="",
        email=None,
        url=None,
    )
    merge_person(session, person)
    # ``name`` is not written (empty), but _display_name is coalesce-filled so
    # the node renders a label (the account id, derived from the node id).
    all_queries = " ".join(call.args[0] for call in session.run.call_args_list)
    assert "p.name = $name" not in all_queries
    assert "p._display_name = $_display_name" not in all_queries
    assert "coalesce(p._display_name, $_display_name)" in all_queries
    assert "coalesce(p._on_hover_name, $_on_hover_name)" in all_queries


def test_merge_person_sets_display_name_when_real_name() -> None:
    session = MagicMock()
    person = Person(
        id="jira::Person::acc123",
        name="Alice Dev",
        email="alice@example.com",
        url=None,
    )
    merge_person(session, person)
    all_queries = " ".join(call.args[0] for call in session.run.call_args_list)
    assert "p.name = $name" in all_queries
    assert "p._display_name = $_display_name" in all_queries


def test_merge_person_sets_name_when_real_name() -> None:
    session = MagicMock()
    person = Person(
        id="jira::Person::acc123",
        name="Alice Dev",
        email="alice@example.com",
        url=None,
    )
    merge_person(session, person)
    all_queries = " ".join(call.args[0] for call in session.run.call_args_list)
    assert "p.name = $name" in all_queries


# ---------------------------------------------------------------------------
# Cache-hit re-merge: a richer name should upgrade an earlier stub
# ---------------------------------------------------------------------------


def test_cache_hit_upgrades_person_with_real_name() -> None:
    """On a provider-cache hit, the incoming richer name should be merged."""
    session = MagicMock()
    cache = PersonCache()
    cache._provider_cache[("jira", "acc123")] = "confluence::Person::acc123"

    with patch("connectors.commons.person_cache.merge_person") as mock_merge_person:
        person_id, is_new = cache.get_or_create_person(
            session,
            email="lalika@example.com",
            name="Lalika Doe",
            provider="jira",
            external_id="acc123",
            account_id="acc123",
        )

    assert person_id == "confluence::Person::acc123"
    assert is_new is False
    mock_merge_person.assert_called_once()
    person = mock_merge_person.call_args.args[1]
    assert person.id == "confluence::Person::acc123"
    assert person.name == "Lalika Doe"


def test_cache_hit_merge_skips_account_id_stub_name() -> None:
    """A cache-hit stub (name == account id) must not overwrite the real name."""
    session = MagicMock()
    cache = PersonCache()
    cache._provider_cache[("jira", "acc123")] = "confluence::Person::acc123"

    with patch("connectors.commons.person_cache.merge_person") as mock_merge_person:
        person_id, _ = cache.get_or_create_person(
            session,
            email=None,
            name="712020:cc7f7515-d137-44a0-9858-22b270a86387",
            provider="jira",
            external_id="acc123",
            account_id="acc123",
        )

    assert person_id == "confluence::Person::acc123"
    mock_merge_person.assert_called_once()
    person = mock_merge_person.call_args.args[1]
    # merge_person itself guards the name; the Person passed still carries it,
    # but the underlying merge query will skip it via the stub guard.
    assert person.name == "712020:cc7f7515-d137-44a0-9858-22b270a86387"


def test_atlassian_account_cache_hit_remerges_richer_person() -> None:
    """An atlassian-account cache hit should also upgrade an earlier stub."""
    session = MagicMock()
    cache = PersonCache()
    cache._atlassian_account_cache["acc123"] = "confluence::Person::acc123"

    with patch("connectors.commons.person_cache.merge_person") as mock_merge_person:
        person_id, is_new = cache.get_or_create_person(
            session,
            email=None,
            name="Lalika Doe",
            provider="jira",
            external_id="acc123",
            account_id="acc123",
        )

    assert person_id == "confluence::Person::acc123"
    assert is_new is False
    mock_merge_person.assert_called_once()
    person = mock_merge_person.call_args.args[1]
    assert person.name == "Lalika Doe"
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from connectors.commons.person_cache import PersonCache


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
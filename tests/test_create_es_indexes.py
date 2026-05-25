"""Unit tests for src/app/scripts/create_es_indexes.py.

Verifies:
- MANAGED_INDEXES covers every entity type in SUPPORTED_ENTITY_TYPES
- Field mapping helpers (_full_text_field, _standard_text_field) produce the
  correct structure (type, analyzer, keyword sub-field)
- _SHARED_MAPPINGS applies the correct Elasticsearch type/analyser to each
  field category (free-text, standard, keyword, date, numeric)
- _index_name() follows the {source}_{entity_type_lower}_index pattern
- create_indexes() issues exactly one indices.create call per MANAGED_INDEXES entry

Run with:
    pytest -m unit tests/test_create_es_indexes.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.scripts.create_es_indexes import (
    MANAGED_INDEXES,
    _SHARED_MAPPINGS,
    _full_text_field,
    _index_name,
    _standard_text_field,
    create_indexes,
)
from common.activity_signal.models import SUPPORTED_ENTITY_TYPES

pytestmark = [pytest.mark.unit]

# Convenience alias — resolved once at import time to avoid repeated dict look-ups
_props: dict = _SHARED_MAPPINGS["properties"]


# ---------------------------------------------------------------------------
# MANAGED_INDEXES — coverage and uniqueness
# ---------------------------------------------------------------------------


def test_managed_indexes_covers_all_supported_entity_types() -> None:
    """Regression guard: every SUPPORTED_ENTITY_TYPES entry must appear in MANAGED_INDEXES.

    Failing here means create_es_indexes.py was not updated after adding a new
    entity type to the ActivitySignal schema.
    """
    covered = {entity_type for _, entity_type in MANAGED_INDEXES}
    missing = SUPPORTED_ENTITY_TYPES - covered
    assert not missing, (
        f"Entity types in SUPPORTED_ENTITY_TYPES not covered by MANAGED_INDEXES: {missing}\n"
        "Add the missing (source, entity_type) pairs to MANAGED_INDEXES in "
        "src/app/scripts/create_es_indexes.py."
    )


def test_managed_indexes_has_no_duplicate_pairs() -> None:
    seen: set[tuple[str, str]] = set()
    for pair in MANAGED_INDEXES:
        assert pair not in seen, f"Duplicate entry in MANAGED_INDEXES: {pair}"
        seen.add(pair)


# ---------------------------------------------------------------------------
# Field mapping helper functions
# ---------------------------------------------------------------------------


def test_full_text_field_type_is_text() -> None:
    assert _full_text_field()["type"] == "text"


def test_full_text_field_uses_english_analyser() -> None:
    assert _full_text_field()["analyzer"] == "english"


def test_full_text_field_has_keyword_subfield() -> None:
    field = _full_text_field()
    assert "keyword" in field["fields"]
    assert field["fields"]["keyword"]["type"] == "keyword"


def test_standard_text_field_type_is_text() -> None:
    assert _standard_text_field()["type"] == "text"


def test_standard_text_field_uses_standard_analyser() -> None:
    assert _standard_text_field()["analyzer"] == "standard"


def test_standard_text_field_has_keyword_subfield() -> None:
    field = _standard_text_field()
    assert "keyword" in field["fields"]
    assert field["fields"]["keyword"]["type"] == "keyword"


def test_full_text_field_custom_ignore_above() -> None:
    field = _full_text_field(ignore_above=256)
    assert field["fields"]["keyword"]["ignore_above"] == 256


def test_standard_text_field_custom_ignore_above() -> None:
    field = _standard_text_field(ignore_above=128)
    assert field["fields"]["keyword"]["ignore_above"] == 128


# ---------------------------------------------------------------------------
# _SHARED_MAPPINGS — free-text fields (english analyser)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name",
    ["summary", "title", "message", "description", "name", "full_name", "path"],
)
def test_free_text_fields_use_english_analyser(field_name: str) -> None:
    assert _props[field_name]["type"] == "text", f"{field_name}: expected type=text"
    assert _props[field_name]["analyzer"] == "english", f"{field_name}: expected analyzer=english"
    assert "keyword" in _props[field_name]["fields"], f"{field_name}: missing keyword sub-field"


# ---------------------------------------------------------------------------
# _SHARED_MAPPINGS — standard analyser fields (partial-match identifiers)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field_name", ["key", "login", "email"])
def test_standard_analyser_fields(field_name: str) -> None:
    assert _props[field_name]["type"] == "text", f"{field_name}: expected type=text"
    assert _props[field_name]["analyzer"] == "standard", f"{field_name}: expected analyzer=standard"
    assert "keyword" in _props[field_name]["fields"], f"{field_name}: missing keyword sub-field"


# ---------------------------------------------------------------------------
# _SHARED_MAPPINGS — keyword fields (exact-match categoricals)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field_name", ["status", "priority", "entity_type", "source"])
def test_categorical_fields_are_keyword(field_name: str) -> None:
    assert _props[field_name]["type"] == "keyword", f"{field_name}: expected type=keyword"


def test_wba_id_is_keyword() -> None:
    assert _props["wba_id"]["type"] == "keyword"


def test_relationship_ids_is_keyword() -> None:
    assert _props["relationship_ids"]["type"] == "keyword"


# ---------------------------------------------------------------------------
# _SHARED_MAPPINGS — date fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field_name", ["event_time", "created_at", "updated_at"])
def test_temporal_fields_are_date(field_name: str) -> None:
    assert _props[field_name]["type"] == "date", f"{field_name}: expected type=date"


# ---------------------------------------------------------------------------
# _SHARED_MAPPINGS — numeric fields
# ---------------------------------------------------------------------------


def test_story_points_is_float() -> None:
    assert _props["story_points"]["type"] == "float"


@pytest.mark.parametrize("field_name", ["additions", "deletions", "commits_count"])
def test_integer_numeric_fields(field_name: str) -> None:
    assert _props[field_name]["type"] == "integer", f"{field_name}: expected type=integer"


# ---------------------------------------------------------------------------
# _index_name helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, entity_type, expected",
    [
        ("github", "Repository", "github_repository_index"),
        ("jira", "Issue", "jira_issue_index"),
        ("github", "PullRequest", "github_pullrequest_index"),
        ("jira", "Person", "jira_person_index"),
        ("github", "Commit", "github_commit_index"),
    ],
)
def test_index_name_pattern(source: str, entity_type: str, expected: str) -> None:
    assert _index_name(source, entity_type) == expected


# ---------------------------------------------------------------------------
# create_indexes — client call count
# ---------------------------------------------------------------------------


def test_create_indexes_calls_create_for_each_managed_index() -> None:
    """create_indexes() must issue exactly one indices.create call per MANAGED_INDEXES entry."""
    client = MagicMock()
    # Return empty dict so indexes_already_aliased = set() and update_aliases runs normally
    client.indices.get_alias.return_value = {}

    create_indexes(client)

    assert client.indices.create.call_count == len(MANAGED_INDEXES)


def test_create_indexes_uses_correct_index_names() -> None:
    """Each indices.create call must use the expected index name."""
    client = MagicMock()
    client.indices.get_alias.return_value = {}

    create_indexes(client)

    created_indexes = {
        call.kwargs.get("index") or call.args[0]
        for call in client.indices.create.call_args_list
    }
    expected_indexes = {_index_name(source, et) for source, et in MANAGED_INDEXES}
    assert created_indexes == expected_indexes

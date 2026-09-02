"""Unit tests for catalog query Cypher parameter substitution."""

import pytest

from app.dash_app.pages.graph.utils.cypher_substitution import (
    cypher_literal,
    substitute_catalog_query_parameters,
)


pytestmark = pytest.mark.unit


def _person_query() -> dict:
    """A minimal catalog query dict mirroring the person_to_person shape."""
    return {
        "id": "person_to_person/shortest_path_collaboration",
        "parameters": [
            {"name": "person1_id", "required": True},
            {"name": "person2_id", "required": True},
        ],
        "queries": {
            "graph": (
                "MATCH (p1:Person {id: $person1_id}), "
                "(p2:Person {id: $person2_id})\n"
                "MATCH path = allShortestPaths((p1)-[*..6]-(p2))\n"
                "RETURN path\nLIMIT 10"
            )
        },
    }


def test_cypher_literal_wraps_in_single_quotes():
    assert cypher_literal("github::Person::alice") == "'github::Person::alice'"


def test_cypher_literal_escapes_single_quotes():
    assert cypher_literal("o'brien") == "'o\\'brien'"


def test_cypher_literal_escapes_backslashes():
    assert cypher_literal("a\\b") == "'a\\\\b'"


def test_substitute_replaces_declared_params_with_values():
    query = _person_query()
    params = {
        "person1_id": "github::Person::alice",
        "person2_id": "jira::Person::557058:abc",
    }
    result = substitute_catalog_query_parameters(
        query["queries"]["graph"], query, params
    )
    assert "{id: 'github::Person::alice'}" in result
    assert "{id: 'jira::Person::557058:abc'}" in result
    assert "$person1_id" not in result
    assert "$person2_id" not in result


def test_substitute_renders_empty_string_for_missing_params():
    query = _person_query()
    result = substitute_catalog_query_parameters(query["queries"]["graph"], query, {})
    assert "{id: ''}" in result
    assert "$person1_id" not in result
    assert "$person2_id" not in result


def test_substitute_renders_empty_string_for_whitespace_value():
    query = _person_query()
    params = {"person1_id": "   ", "person2_id": ""}
    result = substitute_catalog_query_parameters(
        query["queries"]["graph"], query, params
    )
    assert "{id: ''}" in result


def test_substitute_unwraps_person_picker_dict_value():
    query = _person_query()
    params = {
        "person1_id": {"wba": "github::Person::alice", "display": "Alice"},
        "person2_id": {"wba": "jira::Person::557058:abc", "display": "Bob"},
    }
    result = substitute_catalog_query_parameters(
        query["queries"]["graph"], query, params
    )
    assert "{id: 'github::Person::alice'}" in result
    assert "{id: 'jira::Person::557058:abc'}" in result


def test_substitute_unwraps_person_picker_dict_with_empty_wba():
    query = _person_query()
    params = {
        "person1_id": {"wba": "", "display": "Alice"},
        "person2_id": {"wba": "github::Person::bob", "display": "Bob"},
    }
    result = substitute_catalog_query_parameters(
        query["queries"]["graph"], query, params
    )
    assert "{id: ''}" in result
    assert "{id: 'github::Person::bob'}" in result


def test_substitute_leaves_undeclared_dollar_tokens_untouched():
    query = _person_query()
    cypher = "MATCH (n {id: $person1_id}) WHERE n.x = $undeclared RETURN n"
    result = substitute_catalog_query_parameters(cypher, query, {"person1_id": "abc"})
    assert "{id: 'abc'}" in result
    assert "$undeclared" in result


def test_substitute_handles_query_without_parameters():
    query = {"id": "github/top_contributors", "parameters": [], "queries": {"graph": "MATCH (n) RETURN n"}}
    result = substitute_catalog_query_parameters(
        query["queries"]["graph"], query, {"person1_id": "abc"}
    )
    assert result == "MATCH (n) RETURN n"


def test_substitute_handles_none_params():
    query = _person_query()
    result = substitute_catalog_query_parameters(query["queries"]["graph"], query, None)
    assert "{id: ''}" in result
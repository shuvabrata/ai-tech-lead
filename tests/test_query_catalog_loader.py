"""Unit tests for the query catalog loader."""

from pathlib import Path

import pytest
import yaml

from app.query_catalog import CatalogLoadError, get_catalog_query, load_catalog, load_namespaces


pytestmark = pytest.mark.unit


CATALOG_DIR = Path(__file__).resolve().parent.parent / "queries_catalog"


def test_load_namespaces_from_master_catalog():
    namespaces = load_namespaces(CATALOG_DIR)

    assert [namespace.directory for namespace in namespaces] == [
        "schema",
        "cross_domain",
        "github",
        "jira",
        "people_and_identity",
        "person_to_person",
    ]
    assert namespaces[0].name == "Schema"
    assert namespaces[0].order == 0


def test_load_catalog_normalizes_all_existing_entries():
    queries = load_catalog(CATALOG_DIR)

    assert len(queries) == 64
    assert len({query.id for query in queries}) == len(queries)
    assert all(query.available_views for query in queries)
    assert all(query.namespace.name for query in queries)
    assert all(query.source_path.startswith("queries_catalog/") for query in queries)
    assert all(query.summary for query in queries)
    assert all(query.default_view in {"tabular", "graph"} for query in queries)
    assert all(query.owner for query in queries)
    assert all(query.status == "active" for query in queries)


def test_get_catalog_query_by_stable_id():
    query = get_catalog_query("github/top_contributors", CATALOG_DIR)

    assert query.name == "Top Contributors"
    assert query.namespace.directory == "github"
    assert query.slug == "top_contributors"
    assert query.available_views == ["tabular", "graph"]
    assert "LIMIT 10" in query.queries["tabular"]


def test_parameterized_queries_are_detected():
    queries = load_catalog(CATALOG_DIR)
    parameterized = [query for query in queries if query.parameters]

    assert len(parameterized) == 11
    direct_reviews = get_catalog_query("person_to_person/direct_code_reviews", CATALOG_DIR)
    assert [parameter.name for parameter in direct_reviews.parameters] == ["person1_id", "person2_id"]
    assert all(parameter.required for parameter in direct_reviews.parameters)
    assert direct_reviews.summary == "Compare two people by direct code review activity."
    assert direct_reviews.default_view == "tabular"
    assert direct_reviews.owner == "graph-team"
    assert direct_reviews.status == "active"
    assert direct_reviews.parameters[0].label == "First person"
    assert direct_reviews.parameters[0].type == "person_id"
    assert direct_reviews.parameters[0].placeholder == "e.g. github::Person::alice or jira::Person::557058:abc"
    assert direct_reviews.parameters[0].description == "WBA canonical Person ID. Format: github::Person::<login> or jira::Person::<account_id>"


def test_rejects_invalid_query_shape(tmp_path):
    catalog_dir = tmp_path / "queries_catalog"
    namespace_dir = catalog_dir / "bad"
    namespace_dir.mkdir(parents=True)
    _write_yaml(
        catalog_dir / "catalog.yaml",
        {"namespaces": [{"name": "Bad", "directory": "bad"}]},
    )
    _write_yaml(
        namespace_dir / "missing_queries.yaml",
        {"name": "Missing Queries", "description": "No query variants."},
    )

    with pytest.raises(CatalogLoadError, match="queries mapping"):
        load_catalog(catalog_dir)


def test_rejects_non_read_only_catalog_query(tmp_path):
    catalog_dir = tmp_path / "queries_catalog"
    namespace_dir = catalog_dir / "bad"
    namespace_dir.mkdir(parents=True)
    _write_yaml(
        catalog_dir / "catalog.yaml",
        {"namespaces": [{"name": "Bad", "directory": "bad"}]},
    )
    _write_yaml(
        namespace_dir / "write_query.yaml",
        {
            "name": "Write Query",
            "description": "Should be rejected.",
            "queries": {"tabular": "MATCH (n) DELETE n"},
        },
    )

    with pytest.raises(CatalogLoadError, match="non-read-only tabular query"):
        load_catalog(catalog_dir)


def test_rejects_default_view_for_missing_variant(tmp_path):
    catalog_dir = tmp_path / "queries_catalog"
    namespace_dir = catalog_dir / "bad"
    namespace_dir.mkdir(parents=True)
    _write_yaml(
        catalog_dir / "catalog.yaml",
        {"namespaces": [{"name": "Bad", "directory": "bad"}]},
    )
    _write_yaml(
        namespace_dir / "invalid_default_view.yaml",
        {
            "name": "Invalid Default View",
            "description": "Should be rejected.",
            "default_view": "graph",
            "queries": {"tabular": "MATCH (n) RETURN n LIMIT 1"},
        },
    )

    with pytest.raises(CatalogLoadError, match="default_view must match an available query variant"):
        load_catalog(catalog_dir)


def test_rejects_invalid_status_value(tmp_path):
    catalog_dir = tmp_path / "queries_catalog"
    namespace_dir = catalog_dir / "bad"
    namespace_dir.mkdir(parents=True)
    _write_yaml(
        catalog_dir / "catalog.yaml",
        {"namespaces": [{"name": "Bad", "directory": "bad"}]},
    )
    _write_yaml(
        namespace_dir / "invalid_status.yaml",
        {
            "name": "Invalid Status",
            "description": "Should be rejected.",
            "status": "retired",
            "queries": {"tabular": "MATCH (n) RETURN n LIMIT 1"},
        },
    )

    with pytest.raises(CatalogLoadError, match="status"):
        load_catalog(catalog_dir)


def _write_yaml(path: Path, data: dict):
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

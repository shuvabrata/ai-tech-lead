"""Elasticsearch index coverage tests.

Split into two test groups:

Schema coverage (unit — no live Elasticsearch required)
--------------------------------------------------------
Asserts that every entity type in SUPPORTED_ENTITY_TYPES is covered by at
least one entry in MANAGED_INDEXES, and that every MANAGED_INDEXES entry
produces the expected ``{source}_{entity_type_lower}_index`` name pattern.
These tests run without any external services.

Index existence (integration + elasticsearch)
---------------------------------------------
Connects to a live Elasticsearch cluster and asserts that every managed index
actually exists.  Automatically skipped when ``ELASTICSEARCH_ENABLED=false``.

Run schema coverage only:
    pytest -m unit tests/test_es_index_coverage.py -v

Run index existence checks (requires live ES):
    pytest -m "integration and elasticsearch" tests/test_es_index_coverage.py -v
"""

from __future__ import annotations

import pytest

from app.scripts.create_es_indexes import MANAGED_INDEXES, _index_name
from app.settings import settings
from common.activity_signal.models import SUPPORTED_ENTITY_TYPES

# ---------------------------------------------------------------------------
# Schema coverage — no live Elasticsearch required (unit)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_every_supported_entity_type_is_covered_by_managed_indexes() -> None:
    """Regression guard: adding a new entity type without updating MANAGED_INDEXES fails here.

    This catches the 'I added a new entity type to the schema but forgot to create
    its ES index' mistake before it reaches production.
    """
    covered = {entity_type for _, entity_type in MANAGED_INDEXES}
    uncovered = SUPPORTED_ENTITY_TYPES - covered
    assert not uncovered, (
        f"SUPPORTED_ENTITY_TYPES contains entity types with no corresponding ES index "
        f"definition in MANAGED_INDEXES: {uncovered}\n"
        "Add the missing (source, entity_type) pairs to MANAGED_INDEXES in "
        "src/app/scripts/create_es_indexes.py."
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "source, entity_type",
    MANAGED_INDEXES,
    ids=[f"{s}_{et.lower()}" for s, et in MANAGED_INDEXES],
)
def test_managed_index_name_follows_pattern(source: str, entity_type: str) -> None:
    """Every managed index name must follow the {source}_{entity_type_lower}_index pattern."""
    expected = f"{source}_{entity_type.lower()}_index"
    assert _index_name(source, entity_type) == expected, (
        f"_index_name({source!r}, {entity_type!r}) should return {expected!r}"
    )


# ---------------------------------------------------------------------------
# Index existence — requires live Elasticsearch (integration + elasticsearch)
# ---------------------------------------------------------------------------

_es_enabled: bool = settings.ELASTICSEARCH_ENABLED


def _build_es_client():
    """Return a connected Elasticsearch client using application settings."""
    from elasticsearch import Elasticsearch  # pylint: disable=import-outside-toplevel

    if settings.ELASTIC_PASSWORD:
        return Elasticsearch(
            settings.ELASTICSEARCH_URL,
            basic_auth=("elastic", settings.ELASTIC_PASSWORD),
        )
    return Elasticsearch(settings.ELASTICSEARCH_URL)


@pytest.mark.parametrize(
    "source, entity_type",
    MANAGED_INDEXES,
    ids=[f"{s}_{et.lower()}" for s, et in MANAGED_INDEXES],
)
@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.skipif(
    not _es_enabled,
    reason="Elasticsearch is not enabled (ELASTICSEARCH_ENABLED=false)",
)
def test_managed_index_exists_in_elasticsearch(source: str, entity_type: str) -> None:
    """Each managed index must exist in the live Elasticsearch cluster.

    If this fails, run ``python src/app/scripts/create_es_indexes.py`` (or the
    app entrypoint) to create the missing indexes.
    """
    idx = _index_name(source, entity_type)
    client = _build_es_client()
    assert client.indices.exists(index=idx), (
        f"Index '{idx}' does not exist in Elasticsearch at {settings.ELASTICSEARCH_URL}. "
        "Run the index-creation script to initialise it."
    )


@pytest.mark.integration
@pytest.mark.elasticsearch
@pytest.mark.skipif(
    not _es_enabled,
    reason="Elasticsearch is not enabled (ELASTICSEARCH_ENABLED=false)",
)
def test_wba_all_alias_exists_and_covers_all_managed_indexes() -> None:
    """The 'wba_all' alias must exist and point to every managed index."""
    client = _build_es_client()
    try:
        alias_info = client.indices.get_alias(name="wba_all")
    except Exception as exc:
        pytest.fail(f"'wba_all' alias does not exist in Elasticsearch: {exc}")

    aliased_indexes = set(alias_info.keys())
    expected_indexes = {_index_name(s, et) for s, et in MANAGED_INDEXES}
    missing_from_alias = expected_indexes - aliased_indexes
    assert not missing_from_alias, (
        f"The following indexes are not covered by the 'wba_all' alias: {missing_from_alias}"
    )

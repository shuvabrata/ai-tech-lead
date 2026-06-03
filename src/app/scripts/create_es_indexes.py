#!/usr/bin/env python3
"""Create all Elasticsearch indexes for the WBA search capability.

Run automatically from ``src/app/entrypoint.sh`` when
``ELASTICSEARCH_ENABLED=true``.  Safe to re-run on every startup —
all ``indices.create`` calls use ``ignore=400`` so existing indexes are
left untouched.

After creating the per-entity indexes the script (re-)registers the
``wba_all`` alias that points to all managed indexes so unfiltered search
queries can fan out in a single request.

Environment variables
---------------------
ELASTICSEARCH_URL   Base URL of the Elasticsearch cluster.
                    Default: ``http://localhost:9200``
ELASTIC_PASSWORD    Password for the ``elastic`` built-in user.
                    Leave empty when security is disabled (local dev).
"""

from __future__ import annotations

import os
import sys

from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError, RequestError

# ---------------------------------------------------------------------------
# Registry of all managed (source, entity_type) pairs.
# ---------------------------------------------------------------------------
# This constant is the authoritative list used by:
#   • this script to create indexes
#   • tests/test_es_index_coverage.py to verify every SUPPORTED_ENTITY_TYPE
#     is covered
#
# CRITICAL: Any new entity type OR new source for an existing entity type MUST
# be added here AND to SUPPORTED_ENTITY_TYPES in src/common/activity_signal/models.py.
# If you miss adding a (source, entity_type) pair here:
#   1. Elasticsearch will dynamically create the index without proper text analyzers
#      (e.g., partial searches on email/name won't work).
#   2. The unmanaged index will NOT be included in the `wba_all` global search alias,
#      meaning cross-domain searches will silently fail to find these entities.

MANAGED_INDEXES: list[tuple[str, str]] = [
    ("github", "Repository"),
    ("github", "Commit"),
    ("github", "PullRequest"),
    ("github", "Person"),
    ("github", "Team"),
    ("github", "File"),
    ("jira", "Project"),
    ("jira", "Issue"),
    ("jira", "Epic"),
    ("jira", "Initiative"),
    ("jira", "Sprint"),
    ("jira", "Person"),
    ("confluence", "Space"),
    ("confluence", "Page"),
    ("confluence", "Blogpost"),
    ("confluence", "Person"),
]


def _index_name(source: str, entity_type: str) -> str:
    """Return the ES index name for a (source, entity_type) pair."""
    return f"{source}_{entity_type.lower()}_index"


# ---------------------------------------------------------------------------
# Shared field mappings
# ---------------------------------------------------------------------------

# text (english analyser) + .keyword sub-field for sort/aggregation
def _full_text_field(ignore_above: int = 512) -> dict:
    return {
        "type": "text",
        "analyzer": "english",
        "fields": {"keyword": {"type": "keyword", "ignore_above": ignore_above}},
    }


# text (standard analyser) + .keyword sub-field
def _standard_text_field(ignore_above: int = 512) -> dict:
    return {
        "type": "text",
        "analyzer": "standard",
        "fields": {"keyword": {"type": "keyword", "ignore_above": ignore_above}},
    }


_SHARED_MAPPINGS: dict = {
    "properties": {
        # --- Envelope fields ---
        "wba_id":        {"type": "keyword"},
        "source":        {"type": "keyword"},
        "entity_type":   {"type": "keyword"},
        "source_config": {"type": "keyword"},
        "event_time":    {"type": "date"},

        # --- Relationship identifiers ---
        "relationship_ids": {"type": "keyword"},

        # --- Free-text descriptive fields (english analyser) ---
        "summary":       _full_text_field(),
        "title":         _full_text_field(),
        "message":       _full_text_field(),
        "description":   _full_text_field(),
        "name":          _full_text_field(),
        "project_name":  _full_text_field(),
        "full_name":     _full_text_field(),
        "path":          _full_text_field(),
        "goal":          _full_text_field(),

        # --- Issue / entity keys (standard analyser: tokenises PROJ-123 → proj, 123) ---
        "key":           _standard_text_field(),

        # --- Person identifiers (standard analyser for partial match) ---
        "login":         _standard_text_field(),
        "email":         _standard_text_field(),

        # --- Opaque identifiers (exact match only) ---
        "sha":           {"type": "keyword"},
        "branch_name":   {"type": "keyword"},
        "id":            {"type": "keyword"},
        "repo_name":     {"type": "keyword"},
        "project_id":    {"type": "keyword"},
        "project_key":   {"type": "keyword"},
        "account_id":    {"type": "keyword"},
        "url":           {"type": "keyword"},
        "avatar_url":    {"type": "keyword"},

        # --- Categorical fields ---
        "status":        {"type": "keyword"},
        "priority":      {"type": "keyword"},
        "type":          {"type": "keyword"},
        "state":         {"type": "keyword"},
        "language":      {"type": "keyword"},
        "extension":     {"type": "keyword"},
        "project_type":  {"type": "keyword"},
        "mergeable_state": {"type": "keyword"},
        "head_branch_name": {"type": "keyword"},
        "base_branch_name": {"type": "keyword"},
        "last_commit_sha": {"type": "keyword"},

        # --- Temporal fields ---
        "created_at":    {"type": "date", "ignore_malformed": True},
        "updated_at":    {"type": "date", "ignore_malformed": True},
        "merged_at":     {"type": "date", "ignore_malformed": True},
        "closed_at":     {"type": "date", "ignore_malformed": True},
        "start_date":    {"type": "date", "ignore_malformed": True},
        "end_date":      {"type": "date", "ignore_malformed": True},
        "due_date":      {"type": "date", "ignore_malformed": True},
        "duedate":       {"type": "date", "ignore_malformed": True},
        "complete_date": {"type": "date", "ignore_malformed": True},
        "last_commit_timestamp": {"type": "date", "ignore_malformed": True},
        "last_updated_at": {"type": "date", "ignore_malformed": True},

        # --- Numeric fields ---
        "story_points":      {"type": "float"},
        "additions":         {"type": "integer"},
        "deletions":         {"type": "integer"},
        "files_changed":     {"type": "integer"},
        "commits_count":     {"type": "integer"},
        "changed_files":     {"type": "integer"},
        "comments":          {"type": "integer"},
        "review_comments":   {"type": "integer"},
        "pull_request_number": {"type": "integer"},
        "version":           {"type": "integer"},

        # --- Boolean fields ---
        "is_private":    {"type": "boolean"},
        "is_default":    {"type": "boolean"},
        "is_protected":  {"type": "boolean"},
        "is_deleted":    {"type": "boolean"},
        "is_external":   {"type": "boolean"},
        "is_test":       {"type": "boolean"},
    }
}

_INDEX_SETTINGS: dict = {
    "number_of_shards": 1,
    "number_of_replicas": 0,
}


def create_indexes(client: Elasticsearch) -> None:
    """Create all managed indexes and register the ``wba_all`` alias."""
    index_names: list[str] = []

    for source, entity_type in MANAGED_INDEXES:
        idx = _index_name(source, entity_type)
        index_names.append(idx)
        try:
            client.indices.create(
                index=idx,
                body={
                    "settings": _INDEX_SETTINGS,
                    "mappings": _SHARED_MAPPINGS,
                },
            )
            print(f"  Created index: {idx}")
        except RequestError as exc:
            if exc.error == "resource_already_exists_exception":
                print(f"  Index already exists (skipped): {idx}")
            else:
                raise

    # Register / update the wba_all alias to cover all managed indexes.
    try:
        existing_aliases = client.indices.get_alias(name="wba_all")
        indexes_already_aliased: set[str] = set(existing_aliases.keys())
    except NotFoundError:
        indexes_already_aliased = set()

    indexes_to_add = [n for n in index_names if n not in indexes_already_aliased]
    if indexes_to_add:
        alias_actions = [
            {"add": {"index": idx, "alias": "wba_all"}} for idx in indexes_to_add
        ]
        client.indices.update_aliases(body={"actions": alias_actions})
        print(f"  Alias 'wba_all' updated — added {len(indexes_to_add)} index(es).")
    else:
        print("  Alias 'wba_all' already up to date.")


def _build_client() -> Elasticsearch:
    url = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    password = os.getenv("ELASTIC_PASSWORD", "")
    if password:
        return Elasticsearch(url, basic_auth=("elastic", password))
    return Elasticsearch(url)


def main() -> None:
    """Entry point: create all ES indexes."""
    print("Creating Elasticsearch indexes...")
    client = _build_client()
    try:
        info = client.info()
        print(f"  Connected to Elasticsearch {info['version']['number']}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"ERROR: Cannot connect to Elasticsearch: {exc}", file=sys.stderr)
        sys.exit(1)

    create_indexes(client)
    print("Elasticsearch index creation complete.")


if __name__ == "__main__":
    main()

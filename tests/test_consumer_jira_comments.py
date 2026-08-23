"""Unit tests for the consumer snapshot pattern on Jira Initiative/Epic nodes.

These tests verify that ``merge_initiative`` and ``merge_epic`` route
``COMMENTED_ON``/``REACTED_TO`` relationships through
``replace_snapshot_interaction_relationships`` (mirroring ``merge_issue`` and
``merge_pull_request``), while all other relationship types continue to use the
standard ``merge_relationship`` path.

The snapshot functions are mocked at the module level so the tests stay pure
unit (no Neo4j connection required).  The aggregation and idempotency of
``replace_snapshot_interaction_relationships`` are verified directly against
mocked ``session.run`` calls.

All tests are marked ``unit``.
"""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from connectors.neo4j_db.models import Epic, Initiative


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INITIATIVE_ID = "jira::Initiative::init_1"
_EPIC_ID = "jira::Epic::epic_1"


def _make_initiative() -> Initiative:
    """Build a minimal Initiative dataclass instance."""
    return Initiative(
        id=_INITIATIVE_ID,
        key="INIT-1",
        summary="Platform Modernization",
        priority="High",
        status="In Progress",
        created_at="2025-12-01",
        updated_at="2026-01-15",
        duedate="2026-06-30",
        project_id="project_eng_2026",
        labels=["platform"],
        components=["Infrastructure"],
        url="https://myorg.atlassian.net/browse/INIT-1",
    )


def _make_epic() -> Epic:
    """Build a minimal Epic dataclass instance."""
    return Epic(
        id=_EPIC_ID,
        key="PLAT-1",
        summary="Migrate to Kubernetes",
        priority="High",
        status="In Progress",
        start_date="2025-12-09",
        due_date="2026-03-01",
        created_at="2025-12-09",
        updated_at="2026-01-15",
        url="https://myorg.atlassian.net/browse/PLAT-1",
    )


def _commented_on_rel(
    from_id: str, timestamp: str = "2026-01-03T10:00:00+00:00"
) -> MagicMock:
    """Build a mock COMMENTED_ON relationship with snapshot-relevant fields."""
    rel = MagicMock()
    rel.type = "COMMENTED_ON"
    rel.from_id = from_id
    rel.from_type = "Person"
    rel.properties = {"timestamp": timestamp}
    return rel


def _reacted_to_rel(from_id: str, timestamp: str) -> MagicMock:
    """Build a mock REACTED_TO relationship."""
    rel = MagicMock()
    rel.type = "REACTED_TO"
    rel.from_id = from_id
    rel.from_type = "Person"
    rel.properties = {"timestamp": timestamp}
    return rel


def _other_rel() -> MagicMock:
    """Build a mock non-interaction relationship (e.g. PART_OF)."""
    rel = MagicMock()
    rel.type = "PART_OF"
    rel.from_id = "jira::Initiative::proj-9"
    rel.from_type = "Initiative"
    rel.properties = {}
    return rel


def _group_forward_writes(session: MagicMock) -> Dict[str, Dict[str, Any]]:
    """Group aggregated forward-edge write params by from_id."""
    groups: Dict[str, Dict[str, Any]] = {}
    for call in session.run.call_args_list:
        query = call.args[0] or ""
        merged_params = call.kwargs
        if "MERGE (from" in query and "from_id" in merged_params:
            groups[merged_params["from_id"]] = merged_params
    return groups


# ---------------------------------------------------------------------------
# Tests — merge_initiative snapshot routing
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_merge_initiative_routes_commented_on_to_snapshot():
    """COMMENTED_ON relationships should be passed to the snapshot function."""
    from connectors.neo4j_db import models as db_models

    session = MagicMock()
    initiative = _make_initiative()

    commented = _commented_on_rel("jira::Person::charlie")
    other = _other_rel()

    with (
        patch.object(db_models, "replace_snapshot_interaction_relationships") as snap_mock,
        patch.object(db_models, "merge_relationship") as merge_rel_mock,
    ):
        db_models.merge_initiative(session, initiative, relationships=[commented, other])

    snap_mock.assert_called_once()
    # Args: (session, initiative.id, "Initiative", interaction_rels)
    assert snap_mock.call_args.args[1] == _INITIATIVE_ID
    assert snap_mock.call_args.args[2] == "Initiative"
    snap_rels = snap_mock.call_args.args[3]
    assert len(snap_rels) == 1
    assert snap_rels[0].type == "COMMENTED_ON"

    # merge_relationship should only receive the non-interaction rel
    merge_rel_mock.assert_called_once_with(session, other)


@pytest.mark.unit
def test_merge_initiative_routes_reacted_to_to_snapshot():
    """REACTED_TO should also be routed through the snapshot function."""
    from connectors.neo4j_db import models as db_models

    session = MagicMock()
    initiative = _make_initiative()

    reacted = _reacted_to_rel("jira::Person::dave", "2026-01-04T11:00:00+00:00")

    with (
        patch.object(db_models, "replace_snapshot_interaction_relationships") as snap_mock,
        patch.object(db_models, "merge_relationship") as merge_rel_mock,
    ):
        db_models.merge_initiative(session, initiative, relationships=[reacted])

    snap_mock.assert_called_once()
    snap_rels = snap_mock.call_args.args[3]
    assert len(snap_rels) == 1
    assert snap_rels[0].type == "REACTED_TO"
    merge_rel_mock.assert_not_called()


@pytest.mark.unit
def test_merge_initiative_other_rels_use_merge_relationship():
    """Non-interaction relationships should use the standard merge path."""
    from connectors.neo4j_db import models as db_models

    session = MagicMock()
    initiative = _make_initiative()

    other = _other_rel()

    with (
        patch.object(db_models, "replace_snapshot_interaction_relationships") as snap_mock,
        patch.object(db_models, "merge_relationship") as merge_rel_mock,
    ):
        db_models.merge_initiative(session, initiative, relationships=[other])

    snap_mock.assert_called_once()
    assert snap_mock.call_args.args[3] == []
    merge_rel_mock.assert_called_once_with(session, other)


@pytest.mark.unit
def test_merge_initiative_no_relationships():
    """An empty relationships list should not crash."""
    from connectors.neo4j_db import models as db_models

    session = MagicMock()
    initiative = _make_initiative()

    with (
        patch.object(db_models, "replace_snapshot_interaction_relationships") as snap_mock,
        patch.object(db_models, "merge_relationship") as merge_rel_mock,
    ):
        db_models.merge_initiative(session, initiative, relationships=None)

    snap_mock.assert_not_called()
    merge_rel_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for merge_epic delegation
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_merge_epic_routes_commented_on_to_snapshot():
    """COMMENTED_ON relationships should pass to snapshot for Epics."""
    from connectors.neo4j_db import models as db_models

    session = MagicMock()
    epic = _make_epic()

    commented = _commented_on_rel("jira::Person::charlie")
    other = _other_rel()

    with (
        patch.object(db_models, "replace_snapshot_interaction_relationships") as snap_mock,
        patch.object(db_models, "merge_relationship") as merge_rel_mock,
    ):
        db_models.merge_epic(session, epic, relationships=[commented, other])

    snap_mock.assert_called_once()
    assert snap_mock.call_args.args[1] == _EPIC_ID
    assert snap_mock.call_args.args[2] == "Epic"
    snap_rels = snap_mock.call_args.args[3]
    assert len(snap_rels) == 1
    assert snap_rels[0].type == "COMMENTED_ON"

    merge_rel_mock.assert_called_once_with(session, other)


@pytest.mark.unit
def test_merge_epic_routes_reacted_to_to_snapshot():
    """REACTED_TO relationships should be routed to snapshot on Epics."""
    from connectors.neo4j_db import models as db_models

    session = MagicMock()
    epic = _make_epic()

    reacted = _reacted_to_rel("jira::Person::dave", "2026-01-04T11:00:00+00:00")

    with (
        patch.object(db_models, "replace_snapshot_interaction_relationships") as snap_mock,
        patch.object(db_models, "merge_relationship") as merge_rel_mock,
    ):
        db_models.merge_epic(session, epic, relationships=[reacted])

    snap_mock.assert_called_once()
    snap_rels = snap_mock.call_args.args[3]
    assert len(snap_rels) == 1
    assert snap_rels[0].type == "REACTED_TO"
    merge_rel_mock.assert_not_called()


@pytest.mark.unit
def test_merge_epic_other_rels_use_merge_relationship():
    """Non-interaction relationships should use the standard merge path."""
    from connectors.neo4j_db import models as db_models

    session = MagicMock()
    epic = _make_epic()

    other = _other_rel()

    with (
        patch.object(db_models, "replace_snapshot_interaction_relationships") as snap_mock,
        patch.object(db_models, "merge_relationship") as merge_rel_mock,
    ):
        db_models.merge_epic(session, epic, relationships=[other])

    snap_mock.assert_called_once()
    assert snap_mock.call_args.args[3] == []
    merge_rel_mock.assert_called_once_with(session, other)


@pytest.mark.unit
def test_merge_epic_no_relationships():
    """An empty relationships list on an Epic should not crash."""
    from connectors.neo4j_db import models as db_models

    session = MagicMock()
    epic = _make_epic()

    with (
        patch.object(db_models, "replace_snapshot_interaction_relationships") as snap_mock,
        patch.object(db_models, "merge_relationship") as merge_rel_mock,
    ):
        db_models.merge_epic(session, epic, relationships=None)

    snap_mock.assert_not_called()
    merge_rel_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Tests for snapshot aggregation
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_snapshot_aggregates_count_and_timestamps():
    """Multiple comment rels from the same person are grouped and aggregated."""
    from connectors.neo4j_db import models as db_models

    session = MagicMock()

    rels = [
        _commented_on_rel("jira::Person::charlie", "2026-01-03T10:00:00+00:00"),
        _commented_on_rel("jira::Person::charlie", "2026-01-05T09:00:00+00:00"),
        _commented_on_rel("jira::Person::dave", "2026-01-04T11:00:00+00:00"),
    ]

    db_models.replace_snapshot_interaction_relationships(
        session, _INITIATIVE_ID, "Initiative", rels)

    aggregated = _group_forward_writes(session)
    assert len(aggregated) == 2

    charlie = aggregated["jira::Person::charlie"]
    assert charlie["count"] == 2
    assert charlie["first_at"] == "2026-01-03T10:00:00+00:00"
    assert charlie["last_at"] == "2026-01-05T09:00:00+00:00"

    dave = aggregated["jira::Person::dave"]
    assert dave["count"] == 1
    assert dave["first_at"] == "2026-01-04T11:00:00+00:00"
    assert dave["last_at"] == "2026-01-04T11:00:00+00:00"


@pytest.mark.unit
def test_snapshot_idempotent():
    """Re-processing the same signal yields the same aggregated counts."""
    from connectors.neo4j_db import models as db_models

    rels = [
        _commented_on_rel("jira::Person::charlie", "2026-01-03T10:00:00+00:00"),
        _commented_on_rel("jira::Person::dave", "2026-01-04T11:00:00+00:00"),
    ]

    edge_counts = []
    for _ in range(2):
        session = MagicMock()
        db_models.replace_snapshot_interaction_relationships(
            session, _INITIATIVE_ID, "Initiative", rels)
        # Count distinct forward edges written (one per unique commenter).
        edge_counts.append(len(_group_forward_writes(session)))

    # Both runs write the same set of forward edges → idempotent.
    assert edge_counts[0] == edge_counts[1]
    assert edge_counts[0] == 2  # one aggregated edge per unique commenter
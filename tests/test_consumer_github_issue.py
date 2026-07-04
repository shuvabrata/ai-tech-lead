"""Unit tests for the consumer handling of GitHub-source Issue signals (Phase 4).

These tests verify that ``_handle_issue`` in ``neo4j_sink.py`` correctly:

1. Populates ``source=signal.source`` on the ``Issue`` dataclass (so GitHub
   issues get ``source='github'`` and Jira issues keep ``source='jira'``).
2. Produces a canonical WBA node id ``github::Issue::<repo>#<number>``.
3. Routes ``COMMENTED_ON`` relationships through the snapshot interaction
   aggregation path (``replace_snapshot_interaction_relationships``).
4. Routes other relationships (``ASSIGNED_TO``, ``REPORTED_BY``, etc.) through
   the standard ``merge_relationship`` path.

The ``merge_issue`` and ``replace_snapshot_interaction_relationships``
functions are mocked at the module level so the tests stay pure-unit (no
Neo4j connection required).  The ``Issue`` dataclass is inspected after the
handler runs to assert the ``source`` field is set correctly.

All tests are marked ``unit``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest

from common.activity_signal.models import (
    ActivitySignal,
    IssueAttributes,
    Relationship,
    RelationshipTarget,
)
from connectors.consumers.sinks import neo4j_sink
from connectors.neo4j_db.models import Issue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_FULL = "owner/repo"
_ISSUE_ID = f"{_REPO_FULL}#42"
_WBA_ID = f"github::Issue::{_ISSUE_ID}"


def _make_github_issue_signal(
    relationships: List[Relationship] | None = None,
) -> ActivitySignal:
    """Build a minimal GitHub-source Issue ActivitySignal."""
    return ActivitySignal(
        source="github",
        id=_ISSUE_ID,
        source_config="https://github.com",
        connector_url="https://wba-ai/connectors/github/1",
        event_time=datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
        version="1.0",
        attributes=IssueAttributes(
            entity_type="Issue",
            key=_ISSUE_ID,
            summary="Fix login bug",
            priority="None",
            status="open",
            type="Issue",
            created_at="2026-01-01T09:00:00+00:00",
            updated_at="2026-01-02T12:00:00+00:00",
            story_points=None,
            assignee="bob",
            reporter="alice",
            labels=["bug"],
            url=f"https://github.com/{_REPO_FULL}/issues/42",
            custom=None,
        ),
        relationships=relationships or [],
    )


def _make_jira_issue_signal() -> ActivitySignal:
    """Build a minimal Jira-source Issue ActivitySignal (regression check)."""
    return ActivitySignal(
        source="jira",
        id="PROJ-123",
        source_config="https://myorg.atlassian.net",
        connector_url="https://wba-ai/connectors/jira/1",
        event_time=datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc),
        version="1.0",
        attributes=IssueAttributes(
            entity_type="Issue",
            key="PROJ-123",
            summary="Jira story",
            priority="Medium",
            status="In Progress",
            type="Story",
            created_at="2026-01-01T09:00:00+00:00",
            updated_at="2026-01-02T12:00:00+00:00",
            story_points=5,
            assignee="bob",
            reporter="alice",
            labels=None,
            url="https://myorg.atlassian.net/browse/PROJ-123",
            custom=None,
        ),
        relationships=[],
    )


def _commented_on_rel(login: str, timestamp: str = "2026-01-03T10:00:00+00:00") -> Relationship:
    """Build a COMMENTED_ON relationship (direction='IN')."""
    return Relationship(
        type="COMMENTED_ON",
        direction="IN",
        target=RelationshipTarget(source="github", entity_type="Person", id=login),
        properties={"timestamp": timestamp},
    )


def _assigned_to_rel(login: str) -> Relationship:
    return Relationship(
        type="ASSIGNED_TO",
        direction=None,
        target=RelationshipTarget(source="github", entity_type="Person", id=login),
    )


# ---------------------------------------------------------------------------
# Tests — source field
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_handle_issue_github_signal_sets_source_github():
    """``_handle_issue`` should set ``source='github'`` on the Issue dataclass."""
    signal = _make_github_issue_signal()
    captured: dict[str, Any] = {}

    def _capture_merge(session, issue, relationships=None):
        captured["issue"] = issue

    session = MagicMock()
    with (
        patch.object(neo4j_sink, "merge_issue", side_effect=_capture_merge),
        patch.object(neo4j_sink, "_to_db_relationships", return_value=[]),
    ):
        neo4j_sink._handle_issue(session, signal)

    assert "issue" in captured
    assert isinstance(captured["issue"], Issue)
    assert captured["issue"].source == "github"


@pytest.mark.unit
def test_handle_issue_jira_signal_keeps_source_jira():
    """Jira-source Issue signals should still get ``source='jira'`` (regression)."""
    signal = _make_jira_issue_signal()
    captured: dict[str, Any] = {}

    def _capture_merge(session, issue, relationships=None):
        captured["issue"] = issue

    session = MagicMock()
    with (
        patch.object(neo4j_sink, "merge_issue", side_effect=_capture_merge),
        patch.object(neo4j_sink, "_to_db_relationships", return_value=[]),
    ):
        neo4j_sink._handle_issue(session, signal)

    assert captured["issue"].source == "jira"


# ---------------------------------------------------------------------------
# Tests — canonical WBA node id
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_handle_issue_github_signal_uses_wba_canonical_id():
    """The Issue node id should be the WBA canonical key ``github::Issue::<id>``."""
    signal = _make_github_issue_signal()
    captured: dict[str, Any] = {}

    def _capture_merge(session, issue, relationships=None):
        captured["issue"] = issue

    session = MagicMock()
    with (
        patch.object(neo4j_sink, "merge_issue", side_effect=_capture_merge),
        patch.object(neo4j_sink, "_to_db_relationships", return_value=[]),
    ):
        neo4j_sink._handle_issue(session, signal)

    assert captured["issue"].id == _WBA_ID


# ---------------------------------------------------------------------------
# Tests — COMMENTED_ON snapshot aggregation
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_handle_issue_routes_commented_on_to_snapshot_aggregation():
    """COMMENTED_ON relationships should be passed to ``merge_issue`` which
    routes them through ``replace_snapshot_interaction_relationships``."""
    comments = [
        _commented_on_rel("charlie", "2026-01-03T10:00:00+00:00"),
        _commented_on_rel("dave", "2026-01-04T11:00:00+00:00"),
    ]
    signal = _make_github_issue_signal(relationships=comments)

    captured: dict[str, Any] = {}

    def _capture_merge(session, issue, relationships=None):
        captured["relationships"] = relationships or []

    session = MagicMock()
    with (
        patch.object(neo4j_sink, "merge_issue", side_effect=_capture_merge),
        patch.object(neo4j_sink, "_to_db_relationships", return_value=[
            # Simulate the DB-relationship conversion output
            MagicMock(type="COMMENTED_ON", from_id="github::Person::charlie",
                      from_type="Person", to_id=_WBA_ID, to_type="Issue",
                      properties={"timestamp": "2026-01-03T10:00:00+00:00"}),
            MagicMock(type="COMMENTED_ON", from_id="github::Person::dave",
                      from_type="Person", to_id=_WBA_ID, to_type="Issue",
                      properties={"timestamp": "2026-01-04T11:00:00+00:00"}),
        ]),
    ):
        neo4j_sink._handle_issue(session, signal)

    rels = captured["relationships"]
    commented = [r for r in rels if r.type == "COMMENTED_ON"]
    assert len(commented) == 2


@pytest.mark.unit
def test_handle_issue_routes_other_rels_to_merge_relationship():
    """Non-interaction relationships (ASSIGNED_TO) should be passed through."""
    rels_in = [_assigned_to_rel("bob")]
    signal = _make_github_issue_signal(relationships=rels_in)

    captured: dict[str, Any] = {}

    def _capture_merge(session, issue, relationships=None):
        captured["relationships"] = relationships or []

    session = MagicMock()
    with (
        patch.object(neo4j_sink, "merge_issue", side_effect=_capture_merge),
        patch.object(neo4j_sink, "_to_db_relationships", return_value=[
            MagicMock(type="ASSIGNED_TO", from_id=_WBA_ID, from_type="Issue",
                      to_id="github::Person::bob", to_type="Person"),
        ]),
    ):
        neo4j_sink._handle_issue(session, signal)

    other_rels = [r for r in captured["relationships"] if r.type != "COMMENTED_ON"]
    assert len(other_rels) == 1
    assert other_rels[0].type == "ASSIGNED_TO"


# ---------------------------------------------------------------------------
# Tests — merge_issue integration (verify snapshot path is invoked)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_merge_issue_uses_snapshot_for_commented_on():
    """``merge_issue`` should call ``replace_snapshot_interaction_relationships``
    for COMMENTED_ON relationships (mirrors ``merge_pull_request``)."""
    from connectors.neo4j_db import models as db_models

    session = MagicMock()
    issue = Issue(
        id=_WBA_ID,
        key=_ISSUE_ID,
        type="Issue",
        summary="Test",
        priority="None",
        status="open",
        story_points=0,
        source="github",
        created_at="2026-01-01T09:00:00+00:00",
        updated_at="2026-01-02T12:00:00+00:00",
        url="https://github.com/owner/repo/issues/42",
    )

    commented_rel = MagicMock()
    commented_rel.type = "COMMENTED_ON"
    commented_rel.from_id = "github::Person::charlie"
    commented_rel.from_type = "Person"
    commented_rel.properties = {"timestamp": "2026-01-03T10:00:00+00:00"}

    assigned_rel = MagicMock()
    assigned_rel.type = "ASSIGNED_TO"

    with (
        patch.object(db_models, "replace_snapshot_interaction_relationships") as snap_mock,
        patch.object(db_models, "merge_relationship") as merge_rel_mock,
    ):
        db_models.merge_issue(session, issue, relationships=[commented_rel, assigned_rel])

    snap_mock.assert_called_once()
    # The snapshot function should receive only the COMMENTED_ON rel
    snap_rels = snap_mock.call_args.args[3]
    assert len(snap_rels) == 1
    assert snap_rels[0].type == "COMMENTED_ON"

    # merge_relationship should be called once for the ASSIGNED_TO rel
    merge_rel_mock.assert_called_once_with(session, assigned_rel)


@pytest.mark.unit
def test_merge_issue_sets_source_from_props():
    """``merge_issue`` should set ``i.source = $source`` (not hardcoded 'jira')."""
    from connectors.neo4j_db import models as db_models

    session = MagicMock()
    issue = Issue(
        id=_WBA_ID,
        key=_ISSUE_ID,
        type="Issue",
        summary="Test",
        priority="None",
        status="open",
        story_points=0,
        source="github",
        created_at="2026-01-01T09:00:00+00:00",
    )

    with patch.object(db_models, "replace_snapshot_interaction_relationships"):
        db_models.merge_issue(session, issue, relationships=None)

    # The MERGE query should have been run with source='github' in props
    assert session.run.called
    call_kwargs = session.run.call_args
    # The props are passed as **kwargs to session.run
    assert call_kwargs.kwargs.get("source") == "github"


# ---------------------------------------------------------------------------
# Tests — no regression for Jira path
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_handle_issue_jira_signal_uses_jira_wba_id():
    """Jira Issue signals should produce ``jira::Issue::<key>`` node id."""
    signal = _make_jira_issue_signal()
    captured: dict[str, Any] = {}

    def _capture_merge(session, issue, relationships=None):
        captured["issue"] = issue

    session = MagicMock()
    with (
        patch.object(neo4j_sink, "merge_issue", side_effect=_capture_merge),
        patch.object(neo4j_sink, "_to_db_relationships", return_value=[]),
    ):
        neo4j_sink._handle_issue(session, signal)

    assert captured["issue"].id == "jira::Issue::PROJ-123"
    assert captured["issue"].source == "jira"

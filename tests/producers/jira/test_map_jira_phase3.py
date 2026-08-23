"""Unit tests for Jira mapper timestamp normalization (Phase 3).

Tests ``src/connectors/producers/jira/map_jira.py``:

- ``map_initiative`` / ``map_epic`` preserve the full ISO ``created_at`` /
  ``updated_at`` datetime (matching ``map_issue``) instead of truncating to
  ``YYYY-MM-DD``.
- Genuine date-only fields (``start_date``, ``due_date``, ``duedate``) still
  truncate to ``YYYY-MM-DD`` via ``_date()``.
"""

import pytest

from connectors.producers.jira.map_jira import (
    map_epic,
    map_initiative,
    map_issue,
)

_ISO_CREATED = "2024-03-10T09:30:00.000+0000"
_ISO_UPDATED = "2024-03-11T14:45:00.000+0000"


def _fields(**overrides):
    fields = {
        "created": _ISO_CREATED,
        "updated": _ISO_UPDATED,
        "summary": "Some summary",
        "priority": {"name": "High"},
        "status": {"name": "In Progress"},
    }
    fields.update(overrides)
    return fields


@pytest.mark.unit
class TestInitiativeTimestamps:
    def test_created_at_preserves_full_iso(self):
        """``map_initiative`` keeps the full ISO datetime for ``created_at``."""
        result = map_initiative({"key": "INI-1", "fields": _fields()})
        assert result["created_at"] == _ISO_CREATED

    def test_updated_at_preserves_full_iso(self):
        """``map_initiative`` keeps the full ISO datetime for ``updated_at``."""
        result = map_initiative({"key": "INI-1", "fields": _fields()})
        assert result["updated_at"] == _ISO_UPDATED


@pytest.mark.unit
class TestEpicTimestamps:
    def test_created_at_preserves_full_iso(self):
        """``map_epic`` keeps the full ISO datetime for ``created_at``."""
        result = map_epic({"key": "EPIC-1", "fields": _fields()})
        assert result["created_at"] == _ISO_CREATED

    def test_updated_at_preserves_full_iso(self):
        """``map_epic`` keeps the full ISO datetime for ``updated_at``."""
        result = map_epic({"key": "EPIC-1", "fields": _fields()})
        assert result["updated_at"] == _ISO_UPDATED

    def test_due_date_still_truncates(self, monkeypatch):
        """``due_date`` reads the ``duedate`` field and truncates to ``YYYY-MM-DD``."""
        monkeypatch.setenv("JIRA_EPIC_DUE_DATE_FIELD", "duedate")
        result = map_epic(
            {"key": "EPIC-1", "fields": _fields(duedate="2024-12-31T00:00:00.000+0000")}
        )
        assert result["due_date"] == "2024-12-31"

    def test_start_date_still_truncates(self, monkeypatch):
        """``start_date`` reads a custom field and truncates to ``YYYY-MM-DD``."""
        monkeypatch.setenv("JIRA_EPIC_START_DATE_FIELD", "customfield_start")
        result = map_epic(
            {
                "key": "EPIC-1",
                "fields": _fields(customfield_start="2024-01-15T00:00:00.000+0000"),
            }
        )
        assert result["start_date"] == "2024-01-15"


@pytest.mark.unit
class TestTimestampConsistency:
    def test_issue_and_initiative_same_shape(self):
        """``map_issue`` and ``map_initiative`` produce identical ``created_at``
        for identical raw input."""
        issue = map_issue({"key": "PROJ-1", "fields": _fields()})
        initiative = map_initiative({"key": "INI-1", "fields": _fields()})
        assert issue["created_at"] == initiative["created_at"] == _ISO_CREATED
        assert issue["updated_at"] == initiative["updated_at"] == _ISO_UPDATED
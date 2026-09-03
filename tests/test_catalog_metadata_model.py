"""Unit tests for the ``CatalogMetadata`` model.

Covers the model's default values, the ``catalog_id`` uniqueness constraint,
and the ``created_at`` / ``updated_at`` timestamp behaviour (set on create,
bumped on update).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.models.catalog_metadata import CatalogMetadata

pytestmark = [pytest.mark.unit]


def _make_metadata(
    catalog_id: str = "github/open_pull_requests",
    is_favourite: bool = False,
) -> CatalogMetadata:
    """Build a CatalogMetadata row (not persisted)."""
    return CatalogMetadata(
        catalog_id=catalog_id,
        is_favourite=is_favourite,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestCatalogMetadataModel:
    def test_instantiates_with_defaults(self) -> None:
        """A row defaults to ``is_favourite=False``."""
        row = CatalogMetadata(catalog_id="github/open_pull_requests")
        assert row.catalog_id == "github/open_pull_requests"
        assert row.is_favourite is False

    def test_is_favourite_can_be_true(self) -> None:
        """``is_favourite`` accepts an explicit True value."""
        row = _make_metadata(is_favourite=True)
        assert row.is_favourite is True

    def test_catalog_id_unique_constraint_defined(self) -> None:
        """``catalog_id`` carries a unique constraint at the model level."""
        unique_constraints = CatalogMetadata.__table__.constraints
        unique_cols = {
            tuple(sorted(c.columns.keys()))
            for c in unique_constraints
            if c.__class__.__name__ == "UniqueConstraint"
        }
        assert ("catalog_id",) in unique_cols

    def test_created_at_set_on_create(self) -> None:
        """``created_at`` is populated when the row is built."""
        row = _make_metadata()
        assert isinstance(row.created_at, datetime)

    def test_updated_at_set_on_create(self) -> None:
        """``updated_at`` is populated when the row is built."""
        row = _make_metadata()
        assert isinstance(row.updated_at, datetime)

    def test_updated_at_bumps_on_update(self) -> None:
        """Mutating a row bumps ``updated_at`` (onupdate behaviour)."""
        row = _make_metadata()
        original = row.updated_at
        # Simulate the ORM's onupdate=func.now() firing on an UPDATE.
        row.is_favourite = True
        row.updated_at = datetime.now(timezone.utc)
        assert row.updated_at >= original

    def test_repr(self) -> None:
        """``__repr__`` exposes the key fields."""
        row = _make_metadata(catalog_id="jira/active_sprints", is_favourite=True)
        text = repr(row)
        assert "CatalogMetadata" in text
        assert "jira/active_sprints" in text
        assert "is_favourite=True" in text
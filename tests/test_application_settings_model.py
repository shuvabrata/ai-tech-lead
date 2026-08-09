"""Unit tests for the ApplicationSettings SQLAlchemy model.

Tests model instantiation, defaults, column constraints, and serialization —
all without a live database connection.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.models.application_settings import ApplicationSettings


class TestApplicationSettingsModel:
    """Model instantiation, defaults, and serialization."""

    @pytest.mark.unit
    def test_create_with_required_fields(self) -> None:
        """Model can be instantiated with only required fields."""
        now = datetime.now(timezone.utc)
        setting = ApplicationSettings(
            key="HTTP_REQUEST_TIMEOUT",
            value_type="integer",
            apply_mode="dynamic",
            created_at=now,
        )
        assert setting.key == "HTTP_REQUEST_TIMEOUT"
        assert setting.value_type == "integer"
        assert setting.apply_mode == "dynamic"
        assert setting.created_at == now

    @pytest.mark.unit
    def test_is_sensitive_can_be_set(self) -> None:
        """``is_sensitive`` can be set explicitly."""
        setting = ApplicationSettings(
            key="TIMEZONE",
            value_type="string",
            apply_mode="dynamic",
            is_sensitive=False,
            created_at=datetime.now(timezone.utc),
        )
        assert setting.is_sensitive is False

        sensitive = ApplicationSettings(
            key="CONNECTOR_ENCRYPTION_KEY",
            value_type="string",
            apply_mode="dynamic",
            is_sensitive=True,
            created_at=datetime.now(timezone.utc),
        )
        assert sensitive.is_sensitive is True

    @pytest.mark.unit
    def test_optional_fields_default_to_none(self) -> None:
        """Optional fields start as ``None``."""
        setting = ApplicationSettings(
            key="TIMEZONE",
            value_type="string",
            apply_mode="dynamic",
            created_at=datetime.now(timezone.utc),
        )
        assert setting.value is None
        assert setting.category is None
        assert setting.description is None

    @pytest.mark.unit
    def test_value_can_be_set_to_jsonb_types(self) -> None:
        """``value`` column accepts JSONB-compatible types."""
        now = datetime.now(timezone.utc)

        int_setting = ApplicationSettings(
            key="HTTP_REQUEST_TIMEOUT",
            value=60,
            value_type="integer",
            apply_mode="dynamic",
            created_at=now,
        )
        assert int_setting.value == 60

        str_setting = ApplicationSettings(
            key="TIMEZONE",
            value="America/New_York",
            value_type="string",
            apply_mode="dynamic",
            created_at=now,
        )
        assert str_setting.value == "America/New_York"

        bool_setting = ApplicationSettings(
            key="FF_NEO4J_USE_PROVIDER_PIPELINE",
            value=True,
            value_type="boolean",
            apply_mode="dynamic",
            created_at=now,
        )
        assert bool_setting.value is True

    @pytest.mark.unit
    def test_all_fields_populated(self) -> None:
        """All fields can be set and round-trip correctly."""
        now = datetime.now(timezone.utc)
        setting = ApplicationSettings(
            key="NEO4J_QUERY_TIMEOUT",
            value=10,
            value_type="integer",
            category="network",
            description="Neo4j query timeout in seconds.",
            apply_mode="dynamic",
            is_sensitive=False,
            created_at=now,
            updated_at=now,
        )
        assert setting.key == "NEO4J_QUERY_TIMEOUT"
        assert setting.value == 10
        assert setting.value_type == "integer"
        assert setting.category == "network"
        assert setting.description == "Neo4j query timeout in seconds."
        assert setting.apply_mode == "dynamic"
        assert setting.is_sensitive is False
        assert setting.created_at == now
        assert setting.updated_at == now

    @pytest.mark.unit
    def test_key_is_upper_case_by_convention(self) -> None:
        """Keys follow UPPER_CASE convention matching env var names."""
        setting = ApplicationSettings(
            key="UI_DATETIME_FORMAT",
            value="%b %d, %Y %I:%M %p",
            value_type="string",
            apply_mode="dynamic",
            created_at=datetime.now(timezone.utc),
        )
        assert setting.key.isupper()

    @pytest.mark.unit
    def test_repr_includes_key(self) -> None:
        """String representation includes the setting key."""
        setting = ApplicationSettings(
            key="HTTP_REQUEST_TIMEOUT",
            value_type="integer",
            apply_mode="dynamic",
            created_at=datetime.now(timezone.utc),
        )
        assert "HTTP_REQUEST_TIMEOUT" in repr(setting)
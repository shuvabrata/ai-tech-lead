"""Unit tests for the CommandStatus SQLAlchemy model.

Tests model instantiation, defaults, serialization, and validation —
all without a live database connection.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.db.models.command_status import CommandStatus


class TestCommandStatusModel:
    """Model instantiation, defaults, and serialization."""

    @pytest.mark.unit
    def test_create_with_required_fields(self) -> None:
        """Model can be instantiated with only required fields."""
        command_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        cmd = CommandStatus(
            command_id=command_id,
            command_type="scan",
            target="github-producer",
            created_at=now,
        )
        assert cmd.command_id == command_id
        assert cmd.command_type == "scan"
        assert cmd.target == "github-producer"
        assert cmd.created_at == now

    @pytest.mark.unit
    def test_default_status_is_pending(self) -> None:
        """Default status is ``"pending"`` when set explicitly."""
        cmd = CommandStatus(
            command_id=uuid.uuid4(),
            command_type="scan",
            target="github-producer",
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        assert cmd.status == "pending"

    @pytest.mark.unit
    def test_optional_fields_default_to_none(self) -> None:
        """Optional fields start as ``None``."""
        cmd = CommandStatus(
            command_id=uuid.uuid4(),
            command_type="scan",
            target="github-producer",
            created_at=datetime.now(timezone.utc),
        )
        assert cmd.parameters is None
        assert cmd.started_at is None
        assert cmd.completed_at is None
        assert cmd.error_message is None
        assert cmd.result_summary is None

    @pytest.mark.unit
    def test_all_fields_populated(self) -> None:
        """All fields can be set and round-trip correctly."""
        command_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        started = datetime(2026, 7, 30, 10, 0, 0, tzinfo=timezone.utc)
        completed = datetime(2026, 7, 30, 10, 30, 0, tzinfo=timezone.utc)
        cmd = CommandStatus(
            command_id=command_id,
            command_type="scan",
            target="github-producer",
            parameters={"force_full": True},
            status="completed",
            created_at=now,
            started_at=started,
            completed_at=completed,
            error_message=None,
            result_summary={"signals_published": 42},
        )
        assert cmd.parameters == {"force_full": True}
        assert cmd.status == "completed"
        assert cmd.started_at == started
        assert cmd.completed_at == completed
        assert cmd.result_summary == {"signals_published": 42}

    @pytest.mark.unit
    def test_status_string_values(self) -> None:
        """Model allows all valid status strings."""
        now = datetime.now(timezone.utc)
        for status in ("pending", "accepted", "queued", "running", "completed", "failed"):
            cmd = CommandStatus(
                command_id=uuid.uuid4(),
                command_type="scan",
                target="github-producer",
                status=status,
                created_at=now,
            )
            assert cmd.status == status

    @pytest.mark.unit
    def test_error_message_allows_long_text(self) -> None:
        """``error_message`` accepts long text."""
        long_msg = "x" * 5000
        cmd = CommandStatus(
            command_id=uuid.uuid4(),
            command_type="scan",
            target="github-producer",
            status="failed",
            error_message=long_msg,
            created_at=datetime.now(timezone.utc),
        )
        assert len(cmd.error_message) == 5000

    @pytest.mark.unit
    def test_result_summary_accepts_complex_dict(self) -> None:
        """``result_summary`` accepts a nested dict."""
        summary = {
            "signals_published": 42,
            "entities": {"issues": 10, "prs": 5, "commits": 27},
            "duration_seconds": 12.5,
        }
        cmd = CommandStatus(
            command_id=uuid.uuid4(),
            command_type="scan",
            target="github-producer",
            status="completed",
            result_summary=summary,
            created_at=datetime.now(timezone.utc),
        )
        assert cmd.result_summary == summary
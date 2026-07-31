"""Unit tests for the command-and-control shared library.

Tests the Pydantic models and publisher routing logic — all without a live
RabbitMQ broker.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from common.command_n_control.models import CommandEnvelope, CommandStatusUpdate
from common.command_n_control.publisher import CommandPublisher


# ===========================================================================
# CommandEnvelope model tests
# ===========================================================================


class TestCommandEnvelope:
    """Serialization, validation, and round-trip behaviour."""

    @pytest.mark.unit
    def test_round_trip(self) -> None:
        """dict → model → json → model preserves all fields."""
        command_id = uuid.uuid4()
        issued_at = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
        original = CommandEnvelope(
            command_id=command_id,
            command_type="scan",
            target="github-producer",
            parameters={"force_full": True, "since": "2026-01-01"},
            issued_at=issued_at,
        )
        raw = json.loads(original.model_dump_json())
        restored = CommandEnvelope.model_validate(raw)
        assert restored.command_id == command_id
        assert restored.command_type == "scan"
        assert restored.target == "github-producer"
        assert restored.parameters == {"force_full": True, "since": "2026-01-01"}
        assert restored.issued_at == issued_at

    @pytest.mark.unit
    def test_round_trip_minimal(self) -> None:
        """All required fields only (no optional parameters)."""
        command_id = uuid.uuid4()
        issued_at = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
        original = CommandEnvelope(
            command_id=command_id,
            command_type="scan",
            target="github-producer",
            issued_at=issued_at,
        )
        raw = json.loads(original.model_dump_json())
        restored = CommandEnvelope.model_validate(raw)
        assert restored.parameters is None
        assert restored.command_id == command_id

    @pytest.mark.unit
    def test_missing_command_id_raises(self) -> None:
        """Omitting ``command_id`` raises a ValidationError."""
        with pytest.raises(ValidationError):
            CommandEnvelope(
                command_type="scan",
                target="github-producer",
                issued_at=datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc),
            )  # type: ignore[call-arg]

    @pytest.mark.unit
    def test_missing_command_type_raises(self) -> None:
        """Omitting ``command_type`` raises a ValidationError."""
        with pytest.raises(ValidationError):
            CommandEnvelope(
                command_id=uuid.uuid4(),
                target="github-producer",
                issued_at=datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc),
            )  # type: ignore[call-arg]

    @pytest.mark.unit
    def test_invalid_uuid_raises(self) -> None:
        """A non-UUID string in ``command_id`` raises a ValidationError."""
        with pytest.raises(ValidationError):
            CommandEnvelope.model_validate(
                {
                    "command_id": "not-a-uuid",
                    "command_type": "scan",
                    "target": "github-producer",
                    "issued_at": "2026-07-29T12:00:00Z",
                }
            )


# ===========================================================================
# CommandStatusUpdate model tests
# ===========================================================================


class TestCommandStatusUpdate:
    """Status lifecycle values and serialization."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "status",
        ["accepted", "queued", "running", "completed", "failed"],
    )
    def test_valid_status_values(self, status: str) -> None:
        """All five canonical status values are accepted."""
        update = CommandStatusUpdate(status=status)  # type: ignore[arg-type]
        assert update.status == status

    @pytest.mark.unit
    def test_unknown_status_rejected(self) -> None:
        """An unrecognised status string raises a ValidationError."""
        with pytest.raises(ValidationError):
            CommandStatusUpdate(status="unknown_status")  # type: ignore[arg-type]

    @pytest.mark.unit
    def test_optional_fields_omitted_from_json(self) -> None:
        """Fields set to ``None`` are excluded from the serialized output."""
        update = CommandStatusUpdate(status="running")
        raw = json.loads(update.model_dump_json(exclude_none=True))
        assert "error_message" not in raw
        assert "started_at" not in raw
        assert "completed_at" not in raw
        assert "result_summary" not in raw

    @pytest.mark.unit
    def test_result_summary_serialized(self) -> None:
        """``result_summary`` is included when populated."""
        update = CommandStatusUpdate(
            status="completed",
            started_at=datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 7, 29, 12, 30, 0, tzinfo=timezone.utc),
            result_summary={"signals_published": 42},
        )
        raw = json.loads(update.model_dump_json(exclude_none=True))
        assert raw["result_summary"] == {"signals_published": 42}

    @pytest.mark.unit
    def test_error_message_on_failed(self) -> None:
        """``error_message`` is accepted and round-tripped when status is failed."""
        update = CommandStatusUpdate(
            status="failed",
            error_message="scan already in progress",
        )
        raw = json.loads(update.model_dump_json(exclude_none=True))
        assert raw["error_message"] == "scan already in progress"


# ===========================================================================
# CommandPublisher unit tests
# ===========================================================================


class TestCommandPublisher:
    """Routing key logic and channel management (mocked)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_publish_with_target(self) -> None:
        """Routing key is ``command_n_control.<target>``."""
        envelope = CommandEnvelope(
            command_id=uuid.uuid4(),
            command_type="scan",
            target="github-producer",
            issued_at=datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc),
        )

        mock_exchange = AsyncMock()
        mock_channel = AsyncMock()
        mock_channel.get_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.is_closed = False

        publisher = CommandPublisher("amqp://fake:5672/")
        publisher._connection = MagicMock()
        publisher._connection.is_closed = False
        publisher._channel = mock_channel

        await publisher.publish(envelope)

        mock_exchange.publish.assert_awaited_once()
        _call_routing_key = mock_exchange.publish.await_args_list[0].kwargs[
            "routing_key"
        ]
        assert _call_routing_key == "command_n_control.github-producer"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_publish_wildcard(self) -> None:
        """Target ``"*"`` publishes to all known targets."""
        envelope = CommandEnvelope(
            command_id=uuid.uuid4(),
            command_type="scan",
            target="*",
            issued_at=datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc),
        )

        known = ["github-producer", "jira-producer", "confluence-producer"]
        mock_exchange = AsyncMock()
        mock_channel = AsyncMock()
        mock_channel.get_exchange = AsyncMock(return_value=mock_exchange)
        mock_channel.is_closed = False

        publisher = CommandPublisher(
            "amqp://fake:5672/",
            known_targets=known,
        )
        publisher._connection = MagicMock()
        publisher._connection.is_closed = False
        publisher._channel = mock_channel

        await publisher.publish(envelope)

        assert mock_exchange.publish.await_count == len(known)
        actual_keys = [
            call.kwargs["routing_key"]
            for call in mock_exchange.publish.await_args_list
        ]
        assert "command_n_control.github-producer" in actual_keys
        assert "command_n_control.jira-producer" in actual_keys
        assert "command_n_control.confluence-producer" in actual_keys

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_publish_outside_context_manager_raises(self) -> None:
        """Calling ``publish()`` without entering the context manager raises."""
        envelope = CommandEnvelope(
            command_id=uuid.uuid4(),
            command_type="scan",
            target="github-producer",
            issued_at=datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc),
        )
        publisher = CommandPublisher("amqp://fake:5672/")
        with pytest.raises(RuntimeError, match="must be used as an async context"):
            await publisher.publish(envelope)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ensure_channel_reconnects(self) -> None:
        """``_ensure_channel`` reconnects when the connection is closed."""
        envelope = CommandEnvelope(
            command_id=uuid.uuid4(),
            command_type="scan",
            target="github-producer",
            issued_at=datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc),
        )

        # Simulate a closed connection that gets reconnected.
        closed_conn = MagicMock()
        closed_conn.is_closed = True

        new_conn = MagicMock()
        new_conn.is_closed = False
        new_channel = AsyncMock()
        new_channel.is_closed = False
        new_channel.declare_exchange = AsyncMock()
        new_conn.channel = AsyncMock(return_value=new_channel)

        mock_exchange = AsyncMock()
        new_channel.get_exchange = AsyncMock(return_value=mock_exchange)

        with patch(
            "common.command_n_control.publisher.aio_pika.connect_robust",
            AsyncMock(return_value=new_conn),
        ):
            publisher = CommandPublisher("amqp://fake:5672/")
            publisher._connection = closed_conn
            publisher._channel = None  # Force reconnection path.

            await publisher.publish(envelope)

        mock_exchange.publish.assert_awaited_once()


# ===========================================================================
# CommandListener unit tests
# ===========================================================================
# NOTE: CommandListener was removed as dead code (finding 1 from branch audit).
# The async listener class is unused in production — the daemon uses a sync
# pika loop.  If a future async listener is needed, refer to git history.
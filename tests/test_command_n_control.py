"""Unit tests for the command-and-control shared library.

Tests the Pydantic models, publisher routing logic, and listener message
parsing — all without a live RabbitMQ broker.
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
from common.command_n_control.listener import CommandListener


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


class TestCommandListener:
    """Queue declaration, topology, and message parsing (mocked)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_queue_name_and_binding(self) -> None:
        """Queue is named ``cnc.<container_name>`` and bound with correct routing key."""
        mock_channel = AsyncMock()
        mock_queue = AsyncMock()
        mock_channel.declare_queue = AsyncMock(return_value=mock_queue)

        await CommandListener.declare_topology(mock_channel)

        # Verify DLX, DLQ, and exchange were declared.
        declare_exchange_calls = mock_channel.declare_exchange.await_args_list
        exchange_names = [call.args[0] for call in declare_exchange_calls]
        assert "command_n_control" in exchange_names
        assert "command_n_control_dlx" in exchange_names

        mock_channel.declare_queue.assert_awaited_once_with(
            "command_n_control_dlq",
            durable=True,
        )

    @pytest.mark.unit
    def test_listener_queue_naming(self) -> None:
        """Queue name follows the ``cnc.<container_name>`` convention."""
        for container_name, expected in [
            ("github-producer", "cnc.github-producer"),
            ("jira-producer", "cnc.jira-producer"),
            ("confluence-producer", "cnc.confluence-producer"),
        ]:
            listener = CommandListener("amqp://fake:5672/", container_name)
            assert listener._queue_name == expected

    @pytest.mark.unit
    def test_listener_routing_key_convention(self) -> None:
        """Routing key follows the ``command_n_control.<container_name>`` convention."""
        for container_name, expected in [
            ("github-producer", "command_n_control.github-producer"),
            ("jira-producer", "command_n_control.jira-producer"),
            ("confluence-producer", "command_n_control.confluence-producer"),
        ]:
            routing_key = f"command_n_control.{container_name}"
            assert routing_key == expected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_valid_message(self) -> None:
        """Valid JSON yields a ``CommandEnvelope``."""
        command_id = uuid.uuid4()
        payload = {
            "command_id": str(command_id),
            "command_type": "scan",
            "target": "github-producer",
            "parameters": None,
            "issued_at": "2026-07-29T12:00:00Z",
        }
        mock_message = MagicMock()
        mock_message.body = json.dumps(payload).encode()
        mock_message.nack = AsyncMock()

        result = await CommandListener._parse_message(mock_message)
        assert result is not None
        assert isinstance(result, CommandEnvelope)
        assert result.command_id == command_id
        assert result.command_type == "scan"
        mock_message.nack.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_invalid_message_nacks(self) -> None:
        """Invalid JSON nacks with ``requeue=False``."""
        mock_message = MagicMock()
        mock_message.body = b"not valid json"
        mock_message.nack = AsyncMock()

        result = await CommandListener._parse_message(mock_message)
        assert result is None
        mock_message.nack.assert_awaited_once_with(requeue=False)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_invalid_schema_nacks(self) -> None:
        """Valid JSON but missing required fields nacks with ``requeue=False``."""
        payload = {"command_type": "scan"}  # missing command_id, target, issued_at
        mock_message = MagicMock()
        mock_message.body = json.dumps(payload).encode()
        mock_message.nack = AsyncMock()

        result = await CommandListener._parse_message(mock_message)
        assert result is None
        mock_message.nack.assert_awaited_once_with(requeue=False)
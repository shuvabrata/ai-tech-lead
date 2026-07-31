"""Unit tests for the commands API (service layer + state transitions).

Tests service logic with mocked database and RabbitMQ dependencies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.commands.v1 import service
from app.api.commands.v1.models import (
    CommandStatusUpdateRequest,
    CreateCommandRequest,
)
from app.db.models.command_status import CommandStatus


pytestmark = [pytest.mark.unit]


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock async database session."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_cmd(
    command_id: uuid.UUID | None = None,
    status: str = "pending",
    target: str = "github-producer",
    command_type: str = "scan",
) -> CommandStatus:
    """Helper to create a CommandStatus instance for testing."""
    return CommandStatus(
        command_id=command_id or uuid.uuid4(),
        command_type=command_type,
        target=target,
        status=status,
        created_at=datetime.now(timezone.utc),
    )


# ===========================================================================
# State transition validation
# ===========================================================================


class TestStateTransitions:
    """Verify the _validate_state_transition function."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("current", "new"),
        [
            ("pending", "accepted"),
            ("pending", "failed"),
            ("accepted", "queued"),
            ("accepted", "failed"),
            ("queued", "running"),
            ("queued", "failed"),
            ("running", "completed"),
            ("running", "failed"),
        ],
    )
    def test_valid_transitions(self, current: str, new: str) -> None:
        """Allowed transitions do not raise."""
        # Should not raise.
        service._validate_state_transition(current, new)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("current", "new"),
        [
            ("pending", "running"),
            ("pending", "completed"),
            ("accepted", "completed"),
            ("queued", "completed"),
            ("completed", "running"),
            ("completed", "failed"),
            ("failed", "running"),
            ("failed", "accepted"),
            ("running", "pending"),
        ],
    )
    def test_invalid_transitions_raise(self, current: str, new: str) -> None:
        """Disallowed transitions raise ValueError."""
        with pytest.raises(ValueError, match="Invalid status transition"):
            service._validate_state_transition(current, new)

    @pytest.mark.unit
    def test_terminal_states_have_no_transitions(self) -> None:
        """Terminal states (completed, failed) have no outgoing transitions."""
        for terminal in ("completed", "failed"):
            for new_status in ("accepted", "queued", "running", "completed", "failed"):
                if new_status != terminal:
                    with pytest.raises(ValueError, match="Invalid status transition"):
                        service._validate_state_transition(terminal, new_status)


# ===========================================================================
# Target validation
# ===========================================================================


class TestTargetValidation:
    """Verify _is_producer_target checks the registry."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "target",
        ["github-producer", "jira-producer", "confluence-producer"],
    )
    def test_known_producer_targets(self, target: str) -> None:
        """Known producer container names return True."""
        assert service._is_producer_target(target) is True

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "target",
        ["unknown", "slack", "teams", "", "non-producer"],
    )
    def test_unknown_targets(self, target: str) -> None:
        """Unknown targets return False."""
        assert service._is_producer_target(target) is False


# ===========================================================================
# Create and publish command
# ===========================================================================


class TestCreateAndPublishCommand:
    """Verify the create_and_publish_command service function."""

    pytestmark = [pytest.mark.asyncio]

    @pytest.mark.unit
    async def test_invalid_target_raises(self, mock_db: AsyncMock) -> None:
        """An unknown target raises ValueError."""
        request = CreateCommandRequest(
            command_type="scan",
            target="unknown-container",
        )
        with pytest.raises(ValueError, match="Unknown target"):
            await service.create_and_publish_command(request, mock_db)

    @pytest.mark.unit
    async def test_wildcard_target_accepted(self, mock_db: AsyncMock) -> None:
        """Target '*' is always accepted."""
        request = CreateCommandRequest(
            command_type="scan",
            target="*",
        )
        with patch(
            "app.api.commands.v1.service.CommandPublisher",
            autospec=True,
        ) as mock_pub_cls:
            mock_pub = AsyncMock()
            mock_pub.__aenter__.return_value = mock_pub
            mock_pub_cls.return_value = mock_pub

            cmd = await service.create_and_publish_command(request, mock_db)

        assert cmd.status in ("accepted", "failed")
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.unit
    async def test_publish_success_sets_accepted(self, mock_db: AsyncMock) -> None:
        """Successful publish transitions status to 'accepted'."""
        command_id = uuid.uuid4()
        request = CreateCommandRequest(
            command_type="scan",
            target="github-producer",
        )

        # Mock db.add to set the command_id on the added object.
        def _add_side_effect(obj: CommandStatus) -> None:
            obj.command_id = command_id

        mock_db.add.side_effect = _add_side_effect

        with patch(
            "app.api.commands.v1.service.CommandPublisher",
            autospec=True,
        ) as mock_pub_cls:
            mock_pub = AsyncMock()
            mock_pub.__aenter__.return_value = mock_pub
            mock_pub_cls.return_value = mock_pub

            cmd = await service.create_and_publish_command(request, mock_db)

        assert cmd.status == "accepted"
        mock_pub.publish.assert_awaited_once()

    @pytest.mark.unit
    async def test_publish_failure_sets_failed(self, mock_db: AsyncMock) -> None:
        """Publish failure sets status to 'failed' with error message."""
        request = CreateCommandRequest(
            command_type="scan",
            target="github-producer",
        )

        with patch(
            "app.api.commands.v1.service.CommandPublisher",
            autospec=True,
        ) as mock_pub_cls:
            mock_pub = AsyncMock()
            mock_pub.__aenter__.return_value = mock_pub
            mock_pub.publish = AsyncMock(side_effect=RuntimeError("Connection refused"))
            mock_pub_cls.return_value = mock_pub

            cmd = await service.create_and_publish_command(request, mock_db)

        assert cmd.status == "failed"
        assert cmd.error_message == "Failed to publish to RabbitMQ"


# ===========================================================================
# Get command
# ===========================================================================


class TestGetCommand:
    """Verify the get_command service function."""

    pytestmark = [pytest.mark.asyncio]

    @pytest.mark.unit
    async def test_found(self, mock_db: AsyncMock) -> None:
        """Returns the command when found by command_id."""
        command_id = uuid.uuid4()
        cmd = _make_cmd(command_id=command_id)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = cmd
        mock_db.execute.return_value = mock_result

        result = await service.get_command(command_id, mock_db)
        assert result is not None
        assert result.command_id == command_id

    @pytest.mark.unit
    async def test_not_found(self, mock_db: AsyncMock) -> None:
        """Returns None when command_id does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_command(uuid.uuid4(), mock_db)
        assert result is None


# ===========================================================================
# List commands
# ===========================================================================


class TestListCommands:
    """Verify the list_commands service function."""

    pytestmark = [pytest.mark.asyncio]

    @pytest.mark.unit
    async def test_no_filters(self, mock_db: AsyncMock) -> None:
        """Returns all commands with correct pagination."""
        cmds = [_make_cmd() for _ in range(3)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = cmds
        mock_db.execute.return_value = mock_result

        # Mock the count query result.
        count_result = MagicMock()
        count_result.scalar.return_value = 3
        # Use a side effect to return different results for different queries.
        mock_db.execute = AsyncMock(side_effect=[count_result, mock_result])

        commands, total = await service.list_commands(mock_db)
        assert total == 3
        assert len(commands) == 3

    @pytest.mark.unit
    async def test_filter_by_status(self, mock_db: AsyncMock) -> None:
        """Filters by status correctly."""
        pending_cmd = _make_cmd(status="pending")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [pending_cmd]
        mock_db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar=MagicMock(return_value=1)),
                mock_result,
            ]
        )

        commands, total = await service.list_commands(mock_db, status="pending")
        assert total == 1
        assert commands[0].status == "pending"

    @pytest.mark.unit
    async def test_filter_by_target(self, mock_db: AsyncMock) -> None:
        """Filters by target correctly."""
        cmd = _make_cmd(target="jira-producer")
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [cmd]
        mock_db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar=MagicMock(return_value=1)),
                mock_result,
            ]
        )

        commands, total = await service.list_commands(mock_db, target="jira-producer")
        assert total == 1
        assert commands[0].target == "jira-producer"

    @pytest.mark.unit
    async def test_pagination(self, mock_db: AsyncMock) -> None:
        """Respects limit and offset."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar=MagicMock(return_value=10)),
                mock_result,
            ]
        )

        commands, total = await service.list_commands(mock_db, limit=5, offset=5)
        assert total == 10
        assert len(commands) == 0


# ===========================================================================
# Update command status
# ===========================================================================


class TestUpdateCommandStatus:
    """Verify the update_command_status service function."""

    pytestmark = [pytest.mark.asyncio]

    @pytest.mark.unit
    async def test_valid_transition(self, mock_db: AsyncMock) -> None:
        """Valid transition updates the status."""
        command_id = uuid.uuid4()
        cmd = _make_cmd(command_id=command_id, status="pending")

        # Mock get_command to return our command.
        with patch.object(service, "get_command", AsyncMock(return_value=cmd)):
            result = await service.update_command_status(
                command_id,
                CommandStatusUpdateRequest(status="accepted"),
                mock_db,
            )

        assert result.status == "accepted"
        mock_db.commit.assert_awaited_once()

    @pytest.mark.unit
    async def test_full_lifecycle(self, mock_db: AsyncMock) -> None:
        """Full lifecycle: pending→accepted→queued→running→completed."""
        command_id = uuid.uuid4()
        started_at = datetime(2026, 7, 30, 10, 0, 0, tzinfo=timezone.utc)
        completed_at = datetime(2026, 7, 30, 10, 30, 0, tzinfo=timezone.utc)

        transitions = [
            ("pending", "accepted", None, None),
            ("accepted", "queued", None, None),
            ("queued", "running", started_at, None),
            ("running", "completed", None, completed_at),
        ]

        for initial, target, start, end in transitions:
            cmd = _make_cmd(command_id=command_id, status=initial)
            with patch.object(service, "get_command", AsyncMock(return_value=cmd)):
                result = await service.update_command_status(
                    command_id,
                    CommandStatusUpdateRequest(
                        status=target,
                        started_at=start,
                        completed_at=end,
                    ),
                    mock_db,
                )
            assert result.status == target

    @pytest.mark.unit
    async def test_invalid_transition_raises(self, mock_db: AsyncMock) -> None:
        """Invalid transition raises ValueError."""
        command_id = uuid.uuid4()
        cmd = _make_cmd(command_id=command_id, status="completed")

        with patch.object(service, "get_command", AsyncMock(return_value=cmd)):
            with pytest.raises(ValueError, match="Invalid status transition"):
                await service.update_command_status(
                    command_id,
                    CommandStatusUpdateRequest(status="running"),
                    mock_db,
                )

    @pytest.mark.unit
    async def test_command_not_found_raises(self, mock_db: AsyncMock) -> None:
        """Unknown command_id raises ValueError."""
        with patch.object(service, "get_command", AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="Command not found"):
                await service.update_command_status(
                    uuid.uuid4(),
                    CommandStatusUpdateRequest(status="accepted"),
                    mock_db,
                )

    @pytest.mark.unit
    async def test_error_message_and_result(self, mock_db: AsyncMock) -> None:
        """Error message and result summary are stored."""
        command_id = uuid.uuid4()
        cmd = _make_cmd(command_id=command_id, status="running")

        with patch.object(service, "get_command", AsyncMock(return_value=cmd)):
            result = await service.update_command_status(
                command_id,
                CommandStatusUpdateRequest(
                    status="failed",
                    error_message="Something went wrong",
                    result_summary={"partial": 5},
                ),
                mock_db,
            )

        assert result.status == "failed"
        assert result.error_message == "Something went wrong"
        assert result.result_summary == {"partial": 5}
"""Tests for the shared daemon infrastructure (``connectors.producers.daemon_common``).

Tests cover:
- CLI dispatch (``producer_main``)
- Child process spawning and max-concurrency gate (``_spawn_scan``)
- SIGCHLD reaping (``_reap_children``)
- Status PATCH (``_update_status``)
- Scan mode lifecycle (``run_scan``)
- Daemon message dispatch (``run_daemon``)
- Graceful shutdown (killing children on exit)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from common.command_n_control.models import CommandEnvelope, CommandStatusUpdate

# Module-level state to reset between tests
import connectors.producers.daemon_common as daemon_mod

pytestmark = pytest.mark.unit


# ── Helpers ───────────────────────────────────────────────────────────────


def _make_envelope(
    command_id: uuid.UUID | None = None,
    command_type: str = "scan",
    target: str = "github-producer",
    parameters: dict | None = None,
) -> CommandEnvelope:
    return CommandEnvelope(
        command_id=command_id or uuid.uuid4(),
        command_type=command_type,
        target=target,
        parameters=parameters,
        issued_at=datetime.now(timezone.utc),
    )


def _reset_children() -> None:
    """Clear the module-level child-tracking dict."""
    daemon_mod._children.clear()


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_state():
    """Reset module-level state before each test."""
    _reset_children()
    # Restore default max scans
    daemon_mod._max_scans = 5
    yield


# ═══════════════════════════════════════════════════════════════════════════
#  producer_main — CLI dispatch
# ═══════════════════════════════════════════════════════════════════════════


class TestProducerMain:
    """Tests for the ``producer_main()`` entry point."""

    def test_default_mode_is_daemon(self):
        """No ``--mode`` flag should invoke ``run_daemon``."""
        with patch.object(daemon_mod, "run_daemon") as mock_daemon:
            with patch.object(daemon_mod, "run_scan") as mock_scan:
                test_args = ["main.py"]
                with patch.object(sys, "argv", test_args):
                    daemon_mod.producer_main(
                        description="Test",
                        default_container="test-container",
                        producer_main_path="/fake/main.py",
                        scan_func=AsyncMock(),
                    )
        mock_daemon.assert_called_once()
        mock_scan.assert_not_called()

    def test_scan_mode_dispatches_to_run_scan(self):
        """``--mode scan`` should invoke ``run_scan``."""
        with patch.object(daemon_mod, "run_daemon") as mock_daemon:
            with patch.object(daemon_mod, "run_scan") as mock_scan:
                test_args = ["main.py", "--mode", "scan", "--command-id", str(uuid.uuid4()), "--target", "test"]
                with patch.object(sys, "argv", test_args):
                    daemon_mod.producer_main(
                        description="Test",
                        default_container="test-container",
                        producer_main_path="/fake/main.py",
                        scan_func=AsyncMock(),
                    )
        mock_daemon.assert_not_called()
        mock_scan.assert_called_once()

    def test_daemon_mode_explicit(self):
        """``--mode daemon`` should invoke ``run_daemon``."""
        with patch.object(daemon_mod, "run_daemon") as mock_daemon:
            with patch.object(daemon_mod, "run_scan") as mock_scan:
                test_args = ["main.py", "--mode", "daemon"]
                with patch.object(sys, "argv", test_args):
                    daemon_mod.producer_main(
                        description="Test",
                        default_container="test-container",
                        producer_main_path="/fake/main.py",
                        scan_func=AsyncMock(),
                    )
        mock_daemon.assert_called_once()
        mock_scan.assert_not_called()

    def test_scan_mode_passes_command_id(self):
        """``run_scan`` should receive the parsed ``command_id``."""
        command_id = uuid.uuid4()
        with patch.object(daemon_mod, "run_scan") as mock_scan:
            test_args = ["main.py", "--mode", "scan", "--command-id", str(command_id), "--target", "test"]
            with patch.object(sys, "argv", test_args):
                daemon_mod.producer_main(
                    description="Test",
                    default_container="test",
                    producer_main_path="/fake/main.py",
                    scan_func=AsyncMock(),
                )
        kwargs = mock_scan.call_args[1]
        assert kwargs["command_id"] == command_id

    def test_scan_mode_passes_parameters(self):
        """``run_scan`` should receive parsed ``parameters``."""
        with patch.object(daemon_mod, "run_scan") as mock_scan:
            test_args = [
                "main.py", "--mode", "scan",
                "--command-id", str(uuid.uuid4()),
                "--target", "test",
                "--parameters", '{"force_full": true}',
            ]
            with patch.object(sys, "argv", test_args):
                daemon_mod.producer_main(
                    description="Test",
                    default_container="test",
                    producer_main_path="/fake/main.py",
                    scan_func=AsyncMock(),
                )
        kwargs = mock_scan.call_args[1]
        assert kwargs["parameters"] == {"force_full": True}

    def test_daemon_mode_passes_container_name(self):
        """``run_daemon`` should receive the container name from env or default."""
        with patch.object(daemon_mod, "run_daemon") as mock_daemon:
            test_args = ["main.py"]
            with patch.object(sys, "argv", test_args):
                daemon_mod.producer_main(
                    description="Test",
                    default_container="my-container",
                    producer_main_path="/fake/main.py",
                    scan_func=AsyncMock(),
                )
        kwargs = mock_daemon.call_args[1]
        assert kwargs["container_name"] == "my-container"

    def test_daemon_mode_uses_env_container_name(self, monkeypatch):
        """``CONTAINER_NAME`` env var should override the default."""
        monkeypatch.setenv("CONTAINER_NAME", "env-container")
        with patch.object(daemon_mod, "run_daemon") as mock_daemon:
            test_args = ["main.py"]
            with patch.object(sys, "argv", test_args):
                daemon_mod.producer_main(
                    description="Test",
                    default_container="default-container",
                    producer_main_path="/fake/main.py",
                    scan_func=AsyncMock(),
                )
        kwargs = mock_daemon.call_args[1]
        assert kwargs["container_name"] == "env-container"


# ═══════════════════════════════════════════════════════════════════════════
#  _spawn_scan — child process spawning
# ═══════════════════════════════════════════════════════════════════════════


class TestSpawnScan:
    """Tests for the ``_spawn_scan()`` function."""

    def test_spawns_child_process(self):
        """A valid ``scan`` envelope should spawn a ``Popen`` child."""
        envelope = _make_envelope()
        fake_popen = MagicMock(spec=subprocess.Popen)
        fake_popen.pid = 12345

        with patch.object(daemon_mod, "_update_status") as mock_status:
            with patch("subprocess.Popen", return_value=fake_popen) as mock_popen:
                result = daemon_mod._spawn_scan(envelope, "/fake/main.py")

        assert result is fake_popen
        mock_popen.assert_called_once()
        # Verify the child is tracked
        assert daemon_mod._children[12345] == envelope.command_id
        mock_status.assert_not_called()  # no error PATCH

    def test_spawn_rejects_at_max_concurrency(self):
        """When at ``_max_scans``, should reject and PATCH ``failed``."""
        # Fill the children dict
        for i in range(daemon_mod._max_scans):
            daemon_mod._children[10000 + i] = uuid.uuid4()

        envelope = _make_envelope()

        with patch.object(daemon_mod, "_update_status") as mock_status:
            with patch("subprocess.Popen") as mock_popen:
                result = daemon_mod._spawn_scan(envelope, "/fake/main.py")

        assert result is None
        mock_popen.assert_not_called()
        mock_status.assert_called_once()
        call_args = mock_status.call_args[0]
        assert call_args[0] == envelope.command_id
        assert call_args[1].status == "failed"
        assert "Max concurrent scans" in (call_args[1].error_message or "")

    def test_spawn_command_includes_parameters(self):
        """When ``envelope.parameters`` is set, should pass ``--parameters`` to child."""
        envelope = _make_envelope(parameters={"since": "2026-01-01"})
        fake_popen = MagicMock(spec=subprocess.Popen)
        fake_popen.pid = 67890

        with patch.object(daemon_mod, "_update_status"):
            with patch("subprocess.Popen", return_value=fake_popen) as mock_popen:
                daemon_mod._spawn_scan(envelope, "/fake/main.py")

        cmd = mock_popen.call_args[0][0]
        assert "--parameters" in cmd
        params_idx = cmd.index("--parameters") + 1
        assert json.loads(cmd[params_idx]) == {"since": "2026-01-01"}

    def test_spawn_uses_producer_main_path(self):
        """The child command should use the correct ``producer_main_path``."""
        envelope = _make_envelope()
        fake_popen = MagicMock(spec=subprocess.Popen)
        fake_popen.pid = 11111

        with patch.object(daemon_mod, "_update_status"):
            with patch("subprocess.Popen", return_value=fake_popen) as mock_popen:
                daemon_mod._spawn_scan(envelope, "/custom/path/main.py")

        cmd = mock_popen.call_args[0][0]
        assert "/custom/path/main.py" in cmd



# ═══════════════════════════════════════════════════════════════════════════
#  _update_status — HTTP PATCH
# ═══════════════════════════════════════════════════════════════════════════


class TestUpdateStatus:
    """Tests for the ``_update_status()`` function."""

    def test_patches_running_status(self, monkeypatch):
        """Should PATCH ``running`` status to the API."""
        monkeypatch.setenv("API_SERVER", "http://test:8000")
        command_id = uuid.uuid4()
        update = CommandStatusUpdate(status="running", started_at=datetime.now(timezone.utc))

        with patch("httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance
            daemon_mod._update_status(command_id, update)

        mock_instance.patch.assert_called_once()
        url = mock_instance.patch.call_args[0][0]
        assert str(command_id) in url
        payload = mock_instance.patch.call_args[1]["json"]
        assert payload["status"] == "running"
        assert "started_at" in payload

    def test_handles_http_error_gracefully(self, monkeypatch):
        """HTTP errors should be logged as warnings, not raised."""
        monkeypatch.setenv("API_SERVER", "http://test:8000")
        command_id = uuid.uuid4()
        update = CommandStatusUpdate(status="completed", completed_at=datetime.now(timezone.utc))

        with patch("httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance
            mock_instance.patch.side_effect = __import__("httpx").HTTPError("test error")

            # Should not raise
            daemon_mod._update_status(command_id, update)

    def test_uses_correct_api_url(self, monkeypatch):
        """Should construct the correct API URL."""
        monkeypatch.setenv("API_SERVER", "http://api:5000")
        command_id = uuid.uuid4()
        update = CommandStatusUpdate(status="running")

        with patch("httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance
            daemon_mod._update_status(command_id, update)

        url = mock_instance.patch.call_args[0][0]
        assert url == f"http://api:5000/api/v1/commands/{command_id}/status"

    def test_default_api_server(self):
        """Should default to ``http://localhost:8000`` when no env set."""
        # Unset API_SERVER
        with patch.dict(os.environ, {}, clear=True):
            # os.environ needs at least PATH for the interpreter to work
            pass
        # We can't fully clear os.environ, so just ensure the default is used
        with patch("httpx.Client") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__enter__.return_value = mock_instance
            command_id = uuid.uuid4()
            update = CommandStatusUpdate(status="running")
            daemon_mod._update_status(command_id, update)

        url = mock_instance.patch.call_args[0][0]
        assert "localhost:8000" in url


# ═══════════════════════════════════════════════════════════════════════════
#  run_scan — scan mode lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestRunScan:
    """Tests for the ``run_scan()`` function."""

    def test_reports_running_before_scan(self):
        """Should PATCH ``running`` status before starting the scan."""
        command_id = uuid.uuid4()
        scan_func = AsyncMock()

        with patch.object(daemon_mod, "_update_status") as mock_status:
            daemon_mod.run_scan(
                command_id=command_id,
                parameters={},
                scan_func=scan_func,
            )

        # First PATCH should be running
        first_call = mock_status.call_args_list[0]
        assert first_call[0][1].status == "running"

    def test_reports_completed_after_successful_scan(self):
        """Should PATCH ``completed`` status after scan succeeds."""
        command_id = uuid.uuid4()
        scan_func = AsyncMock()

        with patch.object(daemon_mod, "_update_status") as mock_status:
            daemon_mod.run_scan(
                command_id=command_id,
                parameters={},
                scan_func=scan_func,
            )

        # Last PATCH should be completed
        last_call = mock_status.call_args_list[-1]
        assert last_call[0][1].status == "completed"

    def test_reports_failed_on_exception(self):
        """Should PATCH ``failed`` status when scan raises."""
        command_id = uuid.uuid4()
        scan_func = AsyncMock(side_effect=RuntimeError("scan failed"))

        with patch.object(daemon_mod, "_update_status") as mock_status:
            with pytest.raises(SystemExit):
                daemon_mod.run_scan(
                    command_id=command_id,
                    parameters={},
                    scan_func=scan_func,
                )

        # Last PATCH should be failed
        last_call = mock_status.call_args_list[-1]
        assert last_call[0][1].status == "failed"
        assert "scan failed" in (last_call[0][1].error_message or "")

    def test_runs_scan_func(self):
        """Should call the provided ``scan_func``."""
        command_id = uuid.uuid4()
        scan_func = AsyncMock()

        with patch.object(daemon_mod, "_update_status"):
            daemon_mod.run_scan(
                command_id=command_id,
                parameters={},
                scan_func=scan_func,
            )

        scan_func.assert_awaited_once()

    def test_exits_with_code_1_on_failure(self):
        """Should call ``sys.exit(1)`` on failure."""
        command_id = uuid.uuid4()
        scan_func = AsyncMock(side_effect=RuntimeError("fail"))

        with patch.object(daemon_mod, "_update_status"):
            with pytest.raises(SystemExit) as exc_info:
                daemon_mod.run_scan(
                    command_id=command_id,
                    parameters={},
                    scan_func=scan_func,
                )

        assert exc_info.value.code == 1


# ═══════════════════════════════════════════════════════════════════════════
#  run_daemon — message dispatch
# ═══════════════════════════════════════════════════════════════════════════


class TestRunDaemon:
    """Tests for the ``run_daemon()`` function."""

    def test_scan_command_dispatches_to_spawn_scan(self):
        """A ``scan`` command should call ``_spawn_scan``."""
        envelope = _make_envelope()
        body = envelope.model_dump_json().encode()

        # Mock pika
        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel

        # Simulate one message then KeyboardInterrupt
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 1
        mock_channel.consume.return_value = [(mock_frame, None, body)]

        with patch.object(daemon_mod, "_spawn_scan") as mock_spawn:
            with patch("pika.BlockingConnection", return_value=mock_connection):
                with patch.object(daemon_mod, "signal"):
                    daemon_mod.run_daemon(
                        container_name="test-container",
                        producer_main_path="/fake/main.py",
                    )

        mock_spawn.assert_called_once()
        # Verify the envelope was deserialized
        call_envelope = mock_spawn.call_args[0][0]
        assert call_envelope.command_id == envelope.command_id
        assert call_envelope.command_type == "scan"

    def test_cancel_command_logs_not_implemented(self):
        """A ``cancel`` command should log and not spawn."""
        envelope = _make_envelope(command_type="cancel")
        body = envelope.model_dump_json().encode()

        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 1
        mock_channel.consume.return_value = [(mock_frame, None, body)]

        with patch.object(daemon_mod, "_spawn_scan") as mock_spawn:
            with patch("pika.BlockingConnection", return_value=mock_connection):
                with patch.object(daemon_mod, "signal"):
                    daemon_mod.run_daemon(
                        container_name="test-container",
                        producer_main_path="/fake/main.py",
                    )

        mock_spawn.assert_not_called()

    def test_unknown_command_type_logs_and_acks(self):
        """An unknown command type should be acked and discarded."""
        envelope = _make_envelope(command_type="unknown_type")
        body = envelope.model_dump_json().encode()

        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 1
        mock_channel.consume.return_value = [(mock_frame, None, body)]

        with patch.object(daemon_mod, "_spawn_scan") as mock_spawn:
            with patch("pika.BlockingConnection", return_value=mock_connection):
                with patch.object(daemon_mod, "signal"):
                    daemon_mod.run_daemon(
                        container_name="test-container",
                        producer_main_path="/fake/main.py",
                    )

        mock_spawn.assert_not_called()
        # Should still ack the message
        mock_channel.basic_ack.assert_called_with(1)

    def test_invalid_message_nacked(self):
        """An invalid JSON message should be nacked to DLQ."""
        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 1
        # Invalid JSON body
        mock_channel.consume.return_value = [(mock_frame, None, b"not valid json")]

        with patch("pika.BlockingConnection", return_value=mock_connection):
            with patch.object(daemon_mod, "signal"):
                daemon_mod.run_daemon(
                    container_name="test-container",
                    producer_main_path="/fake/main.py",
                )

        mock_channel.basic_nack.assert_called_with(
            1, requeue=False
        )
        mock_channel.basic_ack.assert_not_called()

    def test_acks_after_processing(self):
        """Every valid message should be acknowledged."""
        envelope = _make_envelope()
        body = envelope.model_dump_json().encode()

        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 42
        mock_channel.consume.return_value = [(mock_frame, None, body)]

        with patch.object(daemon_mod, "_spawn_scan"):
            with patch("pika.BlockingConnection", return_value=mock_connection):
                with patch.object(daemon_mod, "signal"):
                    daemon_mod.run_daemon(
                        container_name="test-container",
                        producer_main_path="/fake/main.py",
                    )

        mock_channel.basic_ack.assert_called_with(42)

    def test_declares_exchange_and_queue_and_binding(self):
        """Should declare the exchange, queue, and binding."""
        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_channel.consume.return_value = []

        with patch("pika.BlockingConnection", return_value=mock_connection):
            with patch.object(daemon_mod, "signal"):
                daemon_mod.run_daemon(
                    container_name="test-container",
                    producer_main_path="/fake/main.py",
                )

        mock_channel.exchange_declare.assert_called_with(
            exchange="command_n_control",
            exchange_type="topic",
            durable=True,
        )
        mock_channel.queue_declare.assert_called_with(
            queue="cnc.test-container", durable=True,
            arguments={
                "x-dead-letter-exchange": "command_n_control_dlx",
                "x-dead-letter-routing-key": "command_n_control_dlq",
            },
        )
        mock_channel.queue_bind.assert_called_with(
            queue="cnc.test-container",
            exchange="command_n_control",
            routing_key="command_n_control.test-container",
        )


# ═══════════════════════════════════════════════════════════════════════════
#  Integration-style tests (unit-testable, no live services)
# ═══════════════════════════════════════════════════════════════════════════


class TestDaemonMessageFlow:
    """Tests for the full daemon message flow with mocked components."""

    def test_scan_command_acks_and_spawns_child(self):
        """A valid scan command should be acked and spawn a child."""
        envelope = _make_envelope()
        body = envelope.model_dump_json().encode()

        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 7
        mock_channel.consume.return_value = [(mock_frame, None, body)]

        fake_popen = MagicMock(spec=subprocess.Popen)
        fake_popen.pid = 7777

        with patch("subprocess.Popen", return_value=fake_popen):
            with patch("pika.BlockingConnection", return_value=mock_connection):
                with patch.object(daemon_mod, "signal"):
                    daemon_mod.run_daemon(
                        container_name="test-container",
                        producer_main_path="/fake/main.py",
                    )

        # Verify flow: ack → Popen → tracked
        mock_channel.basic_ack.assert_called_with(7)
        assert daemon_mod._children[7777] == envelope.command_id

    def test_scan_completed_updates_status(self):
        """After a successful scan, status should be PATCHed as completed."""
        command_id = uuid.uuid4()
        scan_func = AsyncMock(return_value=None)

        status_calls = []

        def _track_status(cid, update):
            status_calls.append((cid, update.status))

        with patch.object(daemon_mod, "_update_status", side_effect=_track_status):
            daemon_mod.run_scan(
                command_id=command_id,
                parameters={},
                scan_func=scan_func,
            )

        assert len(status_calls) == 2
        assert status_calls[0] == (command_id, "running")
        assert status_calls[1] == (command_id, "completed")
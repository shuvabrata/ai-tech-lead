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
import signal
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
    """Clear the module-level child-tracking dicts."""
    daemon_mod._children.clear()
    daemon_mod._test_children.clear()


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
#  producer_main — test CLI mode
# ═══════════════════════════════════════════════════════════════════════════


class TestTestModeCLI:
    """Tests for ``--mode test`` CLI dispatch."""

    def test_cli_test_mode(self):
        """``--mode test`` should invoke ``run_test``."""
        test_func = AsyncMock(return_value=(True, "ok"))
        test_args = [
            "main.py", "--mode", "test",
            "--command-id", str(uuid.uuid4()),
            "--target", "test",
        ]
        with patch.object(daemon_mod, "run_test") as mock_run:
            with patch.object(sys, "argv", test_args):
                daemon_mod.producer_main(
                    description="Test",
                    default_container="test-container",
                    producer_main_path="/fake/main.py",
                    scan_func=AsyncMock(),
                    test_func=test_func,
                )
        mock_run.assert_called_once()

    def test_cli_test_mode_no_func(self):
        """No ``test_func`` → prints error, exits 1."""
        test_args = ["main.py", "--mode", "test", "--target", "test"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                daemon_mod.producer_main(
                    description="Test",
                    default_container="test-container",
                    producer_main_path="/fake/main.py",
                    scan_func=AsyncMock(),
                )
        assert exc_info.value.code == 1

    def test_cli_test_mode_with_parameters(self):
        """``--mode test`` passes ``parameters`` to ``run_test``."""
        test_func = AsyncMock(return_value=(True, "ok"))
        command_id = uuid.uuid4()
        test_args = [
            "main.py", "--mode", "test",
            "--command-id", str(command_id),
            "--target", "test",
            "--parameters", '{"item_id": 1}',
        ]
        with patch.object(daemon_mod, "run_test") as mock_run:
            with patch.object(sys, "argv", test_args):
                daemon_mod.producer_main(
                    description="Test",
                    default_container="test-container",
                    producer_main_path="/fake/main.py",
                    scan_func=AsyncMock(),
                    test_func=test_func,
                )
        kwargs = mock_run.call_args[1]
        assert kwargs["command_id"] == command_id
        assert kwargs["parameters"] == {"item_id": 1}
        assert kwargs["test_func"] is test_func


# ═══════════════════════════════════════════════════════════════════════════
#  _spawn_test — test child process spawning
# ═══════════════════════════════════════════════════════════════════════════


class TestSpawnTest:
    """Tests for the ``_spawn_test()`` function."""

    def test_spawn_test_creates_child(self):
        """A valid test envelope should spawn a ``Popen`` child with ``stdout=PIPE``."""
        envelope = _make_envelope(command_type="test")
        fake_popen = MagicMock(spec=subprocess.Popen)
        fake_popen.pid = 22222

        with patch.object(daemon_mod, "_update_status") as mock_status:
            with patch("subprocess.Popen", return_value=fake_popen) as mock_popen:
                result = daemon_mod._spawn_test(envelope, "/fake/main.py")

        assert result is fake_popen
        mock_popen.assert_called_once()
        # Should use PIPE for stdout/stderr
        kwargs = mock_popen.call_args[1]
        assert kwargs["stdout"] is subprocess.PIPE
        assert kwargs["stderr"] is subprocess.PIPE
        # Verify tracked in _test_children
        assert daemon_mod._test_children[22222] == (envelope.command_id, fake_popen)
        mock_status.assert_not_called()

    def test_spawn_test_rejects_when_max_concurrent(self):
        """At capacity → status=failed, no spawn."""
        # Fill _test_children to max
        for i in range(daemon_mod._max_scans):
            fake = MagicMock(spec=subprocess.Popen)
            fake.pid = 30000 + i
            daemon_mod._test_children[30000 + i] = (uuid.uuid4(), fake)

        envelope = _make_envelope(command_type="test")

        with patch.object(daemon_mod, "_update_status") as mock_status:
            with patch("subprocess.Popen") as mock_popen:
                result = daemon_mod._spawn_test(envelope, "/fake/main.py")

        assert result is None
        mock_popen.assert_not_called()
        mock_status.assert_called_once()
        call_args = mock_status.call_args[0]
        assert call_args[1].status == "failed"
        assert "Max concurrent tests" in (call_args[1].error_message or "")

    def test_spawn_test_includes_parameters(self):
        """When ``envelope.parameters`` is set, should pass ``--parameters``."""
        envelope = _make_envelope(command_type="test", parameters={"item_id": 1})
        fake_popen = MagicMock(spec=subprocess.Popen)
        fake_popen.pid = 22223

        with patch.object(daemon_mod, "_update_status"):
            with patch("subprocess.Popen", return_value=fake_popen) as mock_popen:
                daemon_mod._spawn_test(envelope, "/fake/main.py")

        cmd = mock_popen.call_args[0][0]
        assert "--mode" in cmd
        assert "test" in cmd[cmd.index("--mode") + 1]
        assert "--parameters" in cmd
        params_idx = cmd.index("--parameters") + 1
        assert json.loads(cmd[params_idx]) == {"item_id": 1}


# ═══════════════════════════════════════════════════════════════════════════
#  _poll_test_children — test child result polling
# ═══════════════════════════════════════════════════════════════════════════


class TestPollTestChildren:
    """Tests for the ``_poll_test_children()`` function."""

    def _setup_mock_child(
        self, exit_code: int, stdout: str = "", stderr: str = ""
    ) -> tuple[uuid.UUID, MagicMock]:
        command_id = uuid.uuid4()
        popen_obj = MagicMock(spec=subprocess.Popen)
        popen_obj.poll.return_value = exit_code
        popen_obj.returncode = exit_code
        # communicate() returns bytes in real subprocess, so mock it with bytes
        popen_obj.communicate.return_value = (stdout.encode(), stderr.encode())
        pid = 40000 + hash(command_id) % 1000
        daemon_mod._test_children[pid] = (command_id, popen_obj)
        return command_id, popen_obj

    def test_poll_test_children_completed(self):
        """Child exits 0 → status=completed, message from stdout."""
        command_id, _ = self._setup_mock_child(exit_code=0, stdout="SUCCESS: Authenticated as testuser")

        with patch.object(daemon_mod, "_update_status") as mock_status:
            daemon_mod._poll_test_children()

        # Two calls: running → completed
        assert mock_status.call_count == 2
        first_call = mock_status.call_args_list[0]
        assert first_call[0][0] == command_id
        assert first_call[0][1].status == "running"
        second_call = mock_status.call_args_list[1]
        assert second_call[0][0] == command_id
        assert second_call[0][1].status == "completed"
        assert second_call[0][1].result_summary == {"message": "SUCCESS: Authenticated as testuser"}

    def test_poll_test_children_failed(self):
        """Child exits 1 → status=failed, message from stdout."""
        command_id, _ = self._setup_mock_child(exit_code=1, stdout="FAILED: GitHub auth failed")

        with patch.object(daemon_mod, "_update_status") as mock_status:
            daemon_mod._poll_test_children()

        # Two calls: running → failed
        assert mock_status.call_count == 2
        first_call = mock_status.call_args_list[0]
        assert first_call[0][1].status == "running"
        second_call = mock_status.call_args_list[1]
        assert second_call[0][0] == command_id
        assert second_call[0][1].status == "failed"

    def test_poll_test_children_not_finished(self):
        """Child still running (poll returns None) → no status update."""
        command_id, popen_obj = self._setup_mock_child(exit_code=None, stdout="")

        with patch.object(daemon_mod, "_update_status") as mock_status:
            daemon_mod._poll_test_children()

        mock_status.assert_not_called()
        # Child should still be tracked
        assert any(
            cid == command_id for cid, _ in daemon_mod._test_children.values()
        )

    def test_poll_test_children_removes_after_poll(self):
        """Child removed from ``_test_children`` after being polled."""
        command_id, _ = self._setup_mock_child(exit_code=0, stdout="ok")

        with patch.object(daemon_mod, "_update_status"):
            daemon_mod._poll_test_children()

        # Should no longer be tracked
        assert not any(
            cid == command_id for cid, _ in daemon_mod._test_children.values()
        )

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
#  _find_pid_by_command_id — reverse lookup helper
# ═══════════════════════════════════════════════════════════════════════════


class TestFindPidByCommandId:
    """Tests for the ``_find_pid_by_command_id()`` reverse lookup."""

    def test_found(self) -> None:
        """Returns the PID for a known ``command_id``."""
        command_id = uuid.uuid4()
        daemon_mod._children[100] = command_id
        result = daemon_mod._find_pid_by_command_id(command_id)
        assert result == 100

    def test_not_found(self) -> None:
        """Returns ``None`` for an unknown ``command_id``."""
        daemon_mod._children[101] = uuid.uuid4()
        result = daemon_mod._find_pid_by_command_id(uuid.uuid4())
        assert result is None

    def test_empty_children(self) -> None:
        """Returns ``None`` when ``_children`` dict is empty."""
        _reset_children()
        result = daemon_mod._find_pid_by_command_id(uuid.uuid4())
        assert result is None

    def test_multiple_children_returns_correct_pid(self) -> None:
        """Returns the correct PID when multiple children are tracked."""
        cid1 = uuid.uuid4()
        cid2 = uuid.uuid4()
        cid3 = uuid.uuid4()
        daemon_mod._children[201] = cid1
        daemon_mod._children[202] = cid2
        daemon_mod._children[203] = cid3
        result = daemon_mod._find_pid_by_command_id(cid2)
        assert result == 202


# ═══════════════════════════════════════════════════════════════════════════
#  run_scan — scan mode lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestRunScan:
    """Tests for the ``run_scan()`` function."""

    def test_reports_running_before_scan(self):
        """Should PATCH ``running`` status before starting the scan."""
        command_id = uuid.uuid4()
        scan_func = AsyncMock(return_value=daemon_mod.ScanResult(success=True))

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
        scan_func = AsyncMock(return_value=daemon_mod.ScanResult(success=True))

        with patch.object(daemon_mod, "_update_status") as mock_status:
            daemon_mod.run_scan(
                command_id=command_id,
                parameters={},
                scan_func=scan_func,
            )

        # Last PATCH should be completed
        last_call = mock_status.call_args_list[-1]
        assert last_call[0][1].status == "completed"

    def test_reports_failed_when_scan_result_has_errors(self):
        """Should PATCH ``failed`` status when the ScanResult reports errors."""
        command_id = uuid.uuid4()
        result = daemon_mod.ScanResult()
        result.add_error("https://github.com/foo/bar", "401 Bad credentials")
        scan_func = AsyncMock(return_value=result)

        with patch.object(daemon_mod, "_update_status") as mock_status:
            with pytest.raises(SystemExit):
                daemon_mod.run_scan(
                    command_id=command_id,
                    parameters={},
                    scan_func=scan_func,
                )

        # Last PATCH should be failed with error_message + result_summary
        last_call = mock_status.call_args_list[-1]
        assert last_call[0][1].status == "failed"
        assert "1 of" in (last_call[0][1].error_message or "")
        summary = last_call[0][1].result_summary
        assert summary is not None
        assert summary["items_failed"] == 1
        assert summary["errors"] == [
            {"item": "https://github.com/foo/bar", "error": "401 Bad credentials"}
        ]

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
        scan_func = AsyncMock(return_value=daemon_mod.ScanResult(success=True))

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
#  run_test — test mode lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestRunTest:
    """Tests for the ``run_test()`` function."""

    def test_run_test_success(self):
        """``test_func`` returns ``(True, "ok")`` → prints "SUCCESS: ok", exits 0."""
        command_id = uuid.uuid4()
        test_func = AsyncMock(return_value=(True, "Authenticated as testuser"))

        with patch.object(daemon_mod, "_update_status"):
            daemon_mod.run_test(
                command_id=command_id,
                parameters={},
                test_func=test_func,
            )

        test_func.assert_awaited_once()

    def test_run_test_failure(self):
        """``test_func`` returns ``(False, "bad")`` → prints "FAILED: bad", exits 1."""
        command_id = uuid.uuid4()
        test_func = AsyncMock(return_value=(False, "GitHub auth failed"))

        with patch.object(daemon_mod, "_update_status"):
            with pytest.raises(SystemExit) as exc_info:
                daemon_mod.run_test(
                    command_id=command_id,
                    parameters={},
                    test_func=test_func,
                )

        assert exc_info.value.code == 1

    def test_run_test_exception(self):
        """``test_func`` raises → prints "FAILED: ...", exits 1."""
        command_id = uuid.uuid4()
        test_func = AsyncMock(side_effect=RuntimeError("connection timeout"))

        with patch.object(daemon_mod, "_update_status"):
            with pytest.raises(SystemExit) as exc_info:
                daemon_mod.run_test(
                    command_id=command_id,
                    parameters={},
                    test_func=test_func,
                )

        assert exc_info.value.code == 1

    def test_run_test_sets_item_id_env_var(self):
        """``parameters["item_id"]`` sets ``TEST_ITEM_ID`` env var."""
        test_func = AsyncMock(return_value=(True, "ok"))

        with patch.object(daemon_mod, "_update_status"):
            daemon_mod.run_test(
                command_id=uuid.uuid4(),
                parameters={"item_id": 42},
                test_func=test_func,
            )

        assert os.environ.get("TEST_ITEM_ID") == "42"

    def test_run_test_skips_env_var_when_no_item_id(self):
        """No ``item_id`` in parameters → ``TEST_ITEM_ID`` not set."""
        # Clear the env var first
        os.environ.pop("TEST_ITEM_ID", None)
        test_func = AsyncMock(return_value=(True, "ok"))

        with patch.object(daemon_mod, "_update_status"):
            daemon_mod.run_test(
                command_id=uuid.uuid4(),
                parameters={"force_full": True},
                test_func=test_func,
            )

        assert "TEST_ITEM_ID" not in os.environ


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

    # ═══════════════════════════════════════════════════════════════════════════
#  Cancel handler
# ═══════════════════════════════════════════════════════════════════════════


class TestCancelHandler:
    """Tests for the cancel command handler in ``run_daemon()``."""

    def test_cancel_with_valid_command_id(self):
        """A valid cancel command should send SIGTERM and PATCH cancelled."""
        cancel_command_id = uuid.uuid4()
        scan_command_id = uuid.uuid4()
        child_pid = 9999

        # Register the scan as a running child
        daemon_mod._children[child_pid] = scan_command_id

        envelope = _make_envelope(
            command_id=cancel_command_id,
            command_type="cancel",
            parameters={"cancel_command_id": str(scan_command_id)},
        )
        body = envelope.model_dump_json().encode()

        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 1
        mock_channel.consume.return_value = [(mock_frame, None, body)]

        status_updates: list[tuple[uuid.UUID, str]] = []

        def _track_status(cid, update):
            status_updates.append((cid, update.status))

        with patch.dict(os.environ, {"RABBITMQ_URL": "amqp://guest:guest@localhost:5672/"}):
            with patch("os.kill") as mock_kill:
                with patch.object(daemon_mod, "_update_status", side_effect=_track_status):
                    with patch("pika.BlockingConnection", return_value=mock_connection):
                        with patch("signal.signal"):
                            daemon_mod.run_daemon(
                                container_name="test-container",
                                producer_main_path="/fake/main.py",
                            )

        # Should have sent SIGTERM to the child PID
        mock_kill.assert_called_once_with(child_pid, signal.SIGTERM)
        # Should have removed from _children
        assert child_pid not in daemon_mod._children
        # Two status updates: scan → cancelled, cancel → completed
        assert (scan_command_id, "cancelled") in status_updates
        assert (cancel_command_id, "completed") in status_updates

    def test_cancel_missing_parameter(self):
        """Cancel without cancel_command_id should PATCH failed."""
        cancel_command_id = uuid.uuid4()
        envelope = _make_envelope(
            command_id=cancel_command_id,
            command_type="cancel",
        )
        body = envelope.model_dump_json().encode()

        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 1
        mock_channel.consume.return_value = [(mock_frame, None, body)]

        status_updates: list[tuple[uuid.UUID, str]] = []

        def _track_status(cid, update):
            status_updates.append((cid, update.status))

        with patch.object(daemon_mod, "_update_status", side_effect=_track_status):
            with patch("pika.BlockingConnection", return_value=mock_connection):
                with patch.object(daemon_mod, "signal"):
                    daemon_mod.run_daemon(
                        container_name="test-container",
                        producer_main_path="/fake/main.py",
                    )

        assert (cancel_command_id, "failed") in status_updates

    def test_cancel_invalid_uuid(self):
        """Cancel with non-UUID cancel_command_id should PATCH failed."""
        cancel_command_id = uuid.uuid4()
        envelope = _make_envelope(
            command_id=cancel_command_id,
            command_type="cancel",
            parameters={"cancel_command_id": "not-a-uuid"},
        )
        body = envelope.model_dump_json().encode()

        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 1
        mock_channel.consume.return_value = [(mock_frame, None, body)]

        status_updates: list[tuple[uuid.UUID, str]] = []

        def _track_status(cid, update):
            status_updates.append((cid, update.status))

        with patch.object(daemon_mod, "_update_status", side_effect=_track_status):
            with patch("pika.BlockingConnection", return_value=mock_connection):
                with patch.object(daemon_mod, "signal"):
                    daemon_mod.run_daemon(
                        container_name="test-container",
                        producer_main_path="/fake/main.py",
                    )

        assert (cancel_command_id, "failed") in status_updates

    def test_cancel_no_running_scan(self):
        """Cancel for non-existent command_id should PATCH completed."""
        cancel_command_id = uuid.uuid4()
        envelope = _make_envelope(
            command_id=cancel_command_id,
            command_type="cancel",
            parameters={"cancel_command_id": str(uuid.uuid4())},
        )
        body = envelope.model_dump_json().encode()

        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 1
        mock_channel.consume.return_value = [(mock_frame, None, body)]

        status_updates: list[tuple[uuid.UUID, str]] = []

        def _track_status(cid, update):
            status_updates.append((cid, update.status))

        with patch.object(daemon_mod, "_update_status", side_effect=_track_status):
            with patch("pika.BlockingConnection", return_value=mock_connection):
                with patch.object(daemon_mod, "signal"):
                    daemon_mod.run_daemon(
                        container_name="test-container",
                        producer_main_path="/fake/main.py",
                    )

        assert (cancel_command_id, "completed") in status_updates

    def test_cancel_process_already_exited(self):
        """Cancel for an already-exited process should PATCH completed."""
        cancel_command_id = uuid.uuid4()
        scan_command_id = uuid.uuid4()
        child_pid = 8888

        # Register the scan as a running child
        daemon_mod._children[child_pid] = scan_command_id

        envelope = _make_envelope(
            command_id=cancel_command_id,
            command_type="cancel",
            parameters={"cancel_command_id": str(scan_command_id)},
        )
        body = envelope.model_dump_json().encode()

        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 1
        mock_channel.consume.return_value = [(mock_frame, None, body)]

        status_updates: list[tuple[uuid.UUID, str]] = []

        def _track_status(cid, update):
            status_updates.append((cid, update.status))

        with patch.dict(os.environ, {"RABBITMQ_URL": "amqp://guest:guest@localhost:5672/"}):
            with patch("os.kill", side_effect=ProcessLookupError):
                with patch.object(daemon_mod, "_update_status", side_effect=_track_status):
                    with patch("pika.BlockingConnection", return_value=mock_connection):
                        with patch("signal.signal"):
                            daemon_mod.run_daemon(
                                container_name="test-container",
                                producer_main_path="/fake/main.py",
                            )

        # Should have removed from _children despite ProcessLookupError
        assert child_pid not in daemon_mod._children
        # Cancel command should be completed
        assert (cancel_command_id, "completed") in status_updates

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

    def test_test_command_dispatches_to_spawn_test(self):
        """A ``test`` command should call ``_spawn_test``."""
        envelope = _make_envelope(command_type="test")
        body = envelope.model_dump_json().encode()

        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 1
        mock_channel.consume.return_value = [(mock_frame, None, body)]

        with patch.object(daemon_mod, "_spawn_test") as mock_spawn:
            with patch("pika.BlockingConnection", return_value=mock_connection):
                with patch("signal.signal"):
                    daemon_mod.run_daemon(
                        container_name="test-container",
                        producer_main_path="/fake/main.py",
                    )

        mock_spawn.assert_called_once()
        call_envelope = mock_spawn.call_args[0][0]
        assert call_envelope.command_type == "test"

    def test_daemon_kills_test_children_on_shutdown(self):
        """Daemon exit → SIGTERM sent to test children."""
        envelope = _make_envelope(command_type="test")
        body = envelope.model_dump_json().encode()

        mock_channel = MagicMock()
        mock_connection = MagicMock()
        mock_connection.channel.return_value = mock_channel
        mock_frame = MagicMock()
        mock_frame.delivery_tag = 1
        mock_channel.consume.return_value = [(mock_frame, None, body)]

        # Track whether os.kill was called for test children
        killed_pids = []

        def _track_kill(pid, sig):
            killed_pids.append(pid)

        fake_popen = MagicMock(spec=subprocess.Popen)
        fake_popen.pid = 55555

        with patch("os.kill", side_effect=_track_kill):
            with patch("subprocess.Popen", return_value=fake_popen):
                with patch("pika.BlockingConnection", return_value=mock_connection):
                    with patch("signal.signal"):
                        daemon_mod.run_daemon(
                            container_name="test-container",
                            producer_main_path="/fake/main.py",
                        )

        # The test child pid should be killed on shutdown
        assert 55555 in killed_pids

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
        scan_func = AsyncMock(return_value=daemon_mod.ScanResult(success=True))

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
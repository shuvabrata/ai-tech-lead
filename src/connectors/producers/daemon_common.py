"""Shared daemon infrastructure for producer containers.

Provides the ``producer_main()`` entry point that handles ``--mode daemon``
(default), ``--mode scan``, and ``--mode test`` CLI dispatch.  The daemon
mode uses a sync ``pika`` loop to consume commands from the
``command_n_control`` exchange and spawns child processes via
``subprocess.Popen``.  Children are reaped by a ``SIGCHLD`` handler.  The
scan mode parses the command arguments and runs the producer's async scan
logic.  The test mode runs a lightweight connectivity check (same config
loading, no data publishing).

Usage in a producer's ``main.py``::

    from connectors.producers.daemon_common import producer_main

    def main():
        producer_main(
            description="GitHub Producer",
            default_container="github-producer",
            producer_main_path=__file__,
            scan_func=main_async,
            test_func=test_connection,
        )
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import uuid
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
import pika

from common.command_n_control.models import CommandEnvelope, CommandStatusUpdate
from common.logger import logger

# ── Module-level state (shared across daemon functions) ───────────────────
_children: Dict[int, uuid.UUID] = {}  # pid → command_id
_test_children: Dict[int, tuple[uuid.UUID, subprocess.Popen]] = {}  # pid → (command_id, Popen)
_max_scans: int = int(os.environ.get("MAX_CONCURRENT_SCANS", "5"))


def _reap_children(signum: int, frame: Any) -> None:  # pylint: disable=unused-argument
    """SIGCHLD handler — reap finished children and log their exit."""
    while True:
        try:
            pid, exit_code = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
            command_id = _children.pop(pid, None)
            if command_id:
                logger.info(
                    "Child reaped pid=%d command_id=%s exit_code=%d",
                    pid, command_id, exit_code,
                )
        except ChildProcessError:
            break


def _find_pid_by_command_id(command_id: uuid.UUID) -> int | None:
    """Linear scan of ``_children`` — max 5 entries, trivially cheap."""
    for pid, cid in _children.items():
        if cid == command_id:
            return pid
    return None


def _poll_test_children() -> None:
    """Poll all test child processes and PATCH status when they finish."""
    for pid in list(_test_children.keys()):
        command_id, popen_obj = _test_children[pid]
        if popen_obj.poll() is not None:
            stdout_bytes, stderr_bytes = popen_obj.communicate()
            message = (stdout_bytes or stderr_bytes or b"").decode("utf-8", errors="replace").strip()
            success = popen_obj.returncode == 0
            # Advance through running first so the terminal-status PATCH
            # has a valid transition path from accepted (if the child
            # already set it, the 422 is harmless — logged at DEBUG).
            _update_status(command_id, CommandStatusUpdate(
                status="running", started_at=datetime.now(timezone.utc),
            ))
            _update_status(command_id, CommandStatusUpdate(
                status="completed" if success else "failed",
                completed_at=datetime.now(timezone.utc),
                result_summary={"message": message},
            ))
            del _test_children[pid]


def _update_status(command_id: uuid.UUID, update: CommandStatusUpdate) -> None:
    """PATCH a status update to the app's API (sync)."""
    api_base = os.environ.get("API_SERVER", "http://localhost:8000").rstrip("/")
    url = f"{api_base}/api/v1/commands/{command_id}/status"
    payload = update.model_dump(mode="json", exclude_none=True)
    logger.debug("PATCH %s %s", url, payload)
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.patch(url, json=payload)
            logger.debug("Response status=%d body=%s", resp.status_code, resp.text)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Failed to update command status (%s → %s): %s", url, payload.get("status"), exc)


def _spawn_scan(
    envelope: CommandEnvelope,
    producer_main_path: str,
) -> Optional[subprocess.Popen]:  # type: ignore[type-arg]
    """Spawn a child process to run the scan (or reject if at capacity)."""
    if len(_children) >= _max_scans:
        logger.warning(
            "Max concurrent scans reached (%d) — rejecting command_id=%s",
            _max_scans, envelope.command_id,
        )
        _update_status(envelope.command_id, CommandStatusUpdate(
            status="failed", completed_at=datetime.now(timezone.utc),
            error_message=f"Max concurrent scans reached ({_max_scans})",
        ))
        return None

    cmd = [
        sys.executable, producer_main_path,
        "--mode", "scan",
        "--command-id", str(envelope.command_id),
        "--target", envelope.target,
    ]
    if envelope.parameters:
        cmd += ["--parameters", json.dumps(envelope.parameters)]

    logger.info("Spawning scan child command_id=%s pid=%d", envelope.command_id, len(_children) + 1)
    child = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)  # pylint: disable=consider-using-with
    _children[child.pid] = envelope.command_id
    return child


def _spawn_test(
    envelope: CommandEnvelope,
    producer_main_path: str,
) -> Optional[subprocess.Popen]:  # type: ignore[type-arg]
    """Spawn a child process to run the test (or reject if at capacity)."""
    if len(_test_children) >= _max_scans:
        logger.warning(
            "Max concurrent tests reached (%d) — rejecting command_id=%s",
            _max_scans, envelope.command_id,
        )
        _update_status(envelope.command_id, CommandStatusUpdate(
            status="failed", completed_at=datetime.now(timezone.utc),
            error_message=f"Max concurrent tests reached ({_max_scans})",
        ))
        return None

    cmd = [
        sys.executable, producer_main_path,
        "--mode", "test",
        "--command-id", str(envelope.command_id),
        "--target", envelope.target,
    ]
    if envelope.parameters:
        cmd += ["--parameters", json.dumps(envelope.parameters)]

    logger.info("Spawning test child command_id=%s", envelope.command_id)
    child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)  # pylint: disable=consider-using-with
    _test_children[child.pid] = (envelope.command_id, child)
    return child


def _cancel_scan(envelope: CommandEnvelope) -> None:
    """Handle a cancel command — find the child PID, send SIGTERM, PATCH statuses.

    Looks up the target scan via ``parameters.cancel_command_id``, sends
    SIGTERM to the child process, and PATCHes both the scan and the cancel
    command to their terminal statuses.
    """
    cancel_command_id = envelope.command_id
    target_command_id_str = (envelope.parameters or {}).get("cancel_command_id")

    # Mark the cancel command as running first so the eventual
    # completed/failed PATCH is a valid transition.
    _update_status(cancel_command_id, CommandStatusUpdate(
        status="running", started_at=datetime.now(timezone.utc),
    ))

    if not target_command_id_str:
        logger.warning("Cancel command missing cancel_command_id parameter")
        _update_status(cancel_command_id, CommandStatusUpdate(
            status="failed", completed_at=datetime.now(timezone.utc),
            error_message="Missing cancel_command_id parameter",
        ))
        return

    try:
        target_command_id = uuid.UUID(str(target_command_id_str))
    except ValueError:
        logger.warning("Invalid cancel_command_id: %s", target_command_id_str)
        _update_status(cancel_command_id, CommandStatusUpdate(
            status="failed", completed_at=datetime.now(timezone.utc),
            error_message=f"Invalid cancel_command_id: {target_command_id_str}",
        ))
        return

    pid = _find_pid_by_command_id(target_command_id)
    if pid is None:
        logger.info("No running scan found for command_id=%s", target_command_id)
        _update_status(cancel_command_id, CommandStatusUpdate(
            status="completed", completed_at=datetime.now(timezone.utc),
            result_summary={"message": f"No running scan found for {target_command_id}"},
        ))
        return

    try:
        os.kill(pid, signal.SIGTERM)
        logger.info(
            "Sent SIGTERM to pid=%d for command_id=%s",
            pid, target_command_id,
        )
        # Remove from _children so reaper doesn't double-log
        _children.pop(pid, None)
        # Mark the scan as cancelled
        _update_status(target_command_id, CommandStatusUpdate(
            status="cancelled", completed_at=datetime.now(timezone.utc),
        ))
        # Mark the cancel command as completed
        _update_status(cancel_command_id, CommandStatusUpdate(
            status="completed", completed_at=datetime.now(timezone.utc),
            result_summary={"cancelled_command_id": str(target_command_id)},
        ))
    except ProcessLookupError:
        logger.warning(
            "Process pid=%d already exited for command_id=%s",
            pid, target_command_id,
        )
        _children.pop(pid, None)
        _update_status(cancel_command_id, CommandStatusUpdate(
            status="completed", completed_at=datetime.now(timezone.utc),
            result_summary={"message": f"Process already exited for {target_command_id}"},
        ))


def run_daemon(
    *,
    container_name: str,
    producer_main_path: str,
) -> None:
    """Daemon entry point — sync pika loop + subprocess children + SIGCHLD."""
    signal.signal(signal.SIGCHLD, _reap_children)  # reap child processes when they exit
    signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(0))  # trigger finally block to kill children + close connection

    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    queue_name = f"cnc.{container_name}"

    logger.info(
        "Daemon started container=%s max_concurrent_scans=%d",
        container_name, _max_scans,
    )

    connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
    channel = connection.channel()
    channel.basic_qos(prefetch_count=1)

    # Declare exchange + queue + binding (idempotent)
    channel.exchange_declare(
        exchange="command_n_control",
        exchange_type="topic",
        durable=True,
    )
    channel.queue_declare(
        queue=queue_name,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "command_n_control_dlx",
            "x-dead-letter-routing-key": "command_n_control_dlq",
        },
    )
    channel.queue_bind(
        queue=queue_name,
        exchange="command_n_control",
        routing_key=f"command_n_control.{container_name}",
    )

    logger.info("Consuming from queue=%s", queue_name)

    try:
        for method_frame, properties, body in channel.consume(
            queue_name, inactivity_timeout=1
        ):
            if method_frame is None:
                _poll_test_children()  # poll test children on idle ticks
                continue  # timeout, loop back

            try:
                envelope = CommandEnvelope.model_validate_json(body)
            except Exception:
                logger.warning("Invalid command message — nacking to DLQ")
                channel.basic_nack(method_frame.delivery_tag, requeue=False)
                continue

            logger.info(
                "Received command command_id=%s type=%s",
                envelope.command_id, envelope.command_type,
            )

            if envelope.command_type == "scan":
                _spawn_scan(envelope, producer_main_path)
            elif envelope.command_type == "test":
                _spawn_test(envelope, producer_main_path)
            elif envelope.command_type == "cancel":
                _cancel_scan(envelope)
            else:
                logger.warning("Unknown command type=%s — discarding", envelope.command_type)

            channel.basic_ack(method_frame.delivery_tag)

    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt — shutting down")
    finally:
        for pid in list(_children.keys()):
            try:
                os.kill(pid, signal.SIGTERM)
                logger.info("Sent SIGTERM to child pid=%d", pid)
            except ProcessLookupError:
                pass
        for pid in list(_test_children.keys()):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        connection.close()
        logger.info("Daemon stopped")


def run_scan(
    *,
    command_id: uuid.UUID,
    parameters: dict[str, Any],
    scan_func: Callable[[], Coroutine[Any, Any, None]],
) -> None:
    """Scan mode entry point — run scan and report status."""
    logger.info("Scan started command_id=%s", command_id)

    _update_status(command_id, CommandStatusUpdate(
        status="running", started_at=datetime.now(timezone.utc),
    ))

    try:
        asyncio.run(scan_func())
        logger.info("Scan completed command_id=%s", command_id)
        _update_status(command_id, CommandStatusUpdate(
            status="completed", completed_at=datetime.now(timezone.utc),
        ))
    except Exception as exc:
        logger.error("Scan failed command_id=%s: %s", command_id, exc, exc_info=True)
        _update_status(command_id, CommandStatusUpdate(
            status="failed", completed_at=datetime.now(timezone.utc),
            error_message=str(exc),
        ))
        sys.exit(1)


def run_test(
    *,
    command_id: uuid.UUID,
    parameters: dict[str, Any],
    test_func: Callable[[], Coroutine[Any, Any, tuple[bool, str]]],
) -> None:
    """Test mode entry point — run test and print result to stdout.

    The daemon parent process captures stdout/stderr via ``PIPE`` and
    PATCHes the terminal status in ``_poll_test_children()`` based on
    the exit code and printed message.  This function only needs to
    print the result and exit with the appropriate code.
    """
    logger.info("Test started command_id=%s", command_id)

    # Forward item_id to the test function via environment variable
    # (Option A from design: keeps test_func signature clean)
    if "item_id" in parameters:
        os.environ["TEST_ITEM_ID"] = str(parameters["item_id"])

    # Mark the test as running so the parent's terminal-status PATCH
    # (completed/failed) has a valid transition path.
    _update_status(command_id, CommandStatusUpdate(
        status="running", started_at=datetime.now(timezone.utc),
    ))

    try:
        success, message = asyncio.run(test_func())
        if success:
            print(f"SUCCESS: {message}")
        else:
            print(f"FAILED: {message}")
            sys.exit(1)
    except Exception as exc:
        print(f"FAILED: {exc}")
        sys.exit(1)


def producer_main(
    *,
    description: str,
    default_container: str,
    producer_main_path: str,
    scan_func: Callable[[], Coroutine[Any, Any, None]],
    test_func: Callable[[], Coroutine[Any, Any, tuple[bool, str]]] | None = None,
) -> None:
    """Unified CLI entry point — dispatch to daemon, scan, or test mode.

    Args:
        description: Human-readable description for ``argparse`` help.
        default_container: Default ``CONTAINER_NAME`` (e.g. ``"github-producer"``).
        producer_main_path: ``__file__`` from the caller's module — used to
            spawn child processes.
        scan_func: The producer's async scan function (e.g. ``main_async``).
        test_func: Optional async function returning ``(success, message)``
            for connectivity testing.  Required for ``--mode test``.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--mode", choices=["daemon", "scan", "test"], default="daemon")
    parser.add_argument("--command-id")
    parser.add_argument("--target")
    parser.add_argument("--parameters")

    args = parser.parse_args()

    if args.mode == "daemon":
        run_daemon(
            container_name=os.environ.get("CONTAINER_NAME", default_container),
            producer_main_path=producer_main_path,
        )
    elif args.mode == "test":
        if test_func is None:
            print("ERROR: No test function provided for this producer.")
            sys.exit(1)
        command_id = uuid.UUID(args.command_id) if args.command_id else uuid.uuid4()
        parameters = json.loads(args.parameters) if args.parameters else {}
        run_test(
            command_id=command_id,
            parameters=parameters,
            test_func=test_func,
        )
    else:
        command_id = uuid.UUID(args.command_id) if args.command_id else uuid.uuid4()
        parameters = json.loads(args.parameters) if args.parameters else {}
        run_scan(
            command_id=command_id,
            parameters=parameters,
            scan_func=scan_func,
        )
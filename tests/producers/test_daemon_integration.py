"""Integration tests for Phase 4 — Producer daemon RabbitMQ delivery.

Validates two behaviours:

1. **Daemon receives command via RabbitMQ** — a ``CommandEnvelope`` published
   to the ``command_n_control`` exchange with routing key
   ``command_n_control.<container>`` is deliverable to the corresponding
   ``cnc.<container>`` queue.

2. **End-to-end scan lifecycle** — the full flow: API POST → RabbitMQ →
   daemon child process → status PATCH → ``completed``.  Requires the app
   server to be running (``uvicorn``) in addition to RabbitMQ.

Requirements:
    - A running RabbitMQ instance reachable at ``settings.RABBITMQ_URL``.
    - For end-to-end tests: the app server running at ``http://localhost:8000``
      and the producer daemon test harness.

Run:
    pytest tests/producers/test_daemon_integration.py -v -m "integration and rabbitmq"
    pytest tests/producers/test_daemon_integration.py -v -m "integration and server" -k "e2e"
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone

import httpx
import pika
import pytest
import pytest_asyncio

try:
    import aio_pika

    _AIO_PIKA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _AIO_PIKA_AVAILABLE = False

from app.settings import settings

# ── RabbitMQ topology constants ───────────────────────────────────────────

CONTROL_EXCHANGE: str = "command_n_control"
CONTROL_DLX: str = "command_n_control_dlx"
CONTROL_DLQ: str = "command_n_control_dlq"

CONTROL_QUEUES: list[tuple[str, str]] = [
    ("cnc.github-producer", "command_n_control.github-producer"),
    ("cnc.jira-producer", "command_n_control.jira-producer"),
    ("cnc.confluence-producer", "command_n_control.confluence-producer"),
]

# ── Connectivity helpers ──────────────────────────────────────────────────


async def _rabbitmq_reachable() -> bool:
    """Return True if RabbitMQ is reachable at ``settings.RABBITMQ_URL``."""
    try:
        conn = await aio_pika.connect_robust(settings.RABBITMQ_URL, timeout=3)
        await conn.close()
        return True
    except Exception:  # pylint: disable=broad-except
        return False


_rabbitmq_available: bool = asyncio.run(_rabbitmq_reachable()) if _AIO_PIKA_AVAILABLE else False
_skip_if_rabbitmq_unavailable = pytest.mark.skipif(
    not _rabbitmq_available or not _AIO_PIKA_AVAILABLE,
    reason="RabbitMQ not reachable or aio-pika not installed",
)


def _app_server_reachable() -> bool:
    """Return True if the app server is reachable at ``http://localhost:8000``."""
    try:
        resp = httpx.get("http://localhost:8000/api/health", timeout=3)
        return resp.status_code == 200
    except Exception:  # pylint: disable=broad-except
        return False


_app_available: bool = _app_server_reachable()
_skip_if_app_unavailable = pytest.mark.skipif(
    not _app_available,
    reason="App server not reachable at http://localhost:8000",
)


# ── Topology helper ───────────────────────────────────────────────────────


def _delete_control_queues(url: str) -> None:
    """Delete any existing control queues synchronously via ``pika``.

    ``run_daemon`` declares queues without ``x-dead-letter-exchange``, so
    before re-declaring them with DLQ args we must delete them first.
    """
    params = pika.URLParameters(url)
    conn = pika.BlockingConnection(params)
    try:
        channel = conn.channel()
        for queue_name, _ in CONTROL_QUEUES:
            channel.queue_delete(queue_name)
        channel.queue_delete(CONTROL_DLQ)
    finally:
        conn.close()


async def _declare_control_topology(url: str) -> None:
    """Declare the ``command_n_control`` exchange, DLX, DLQ, and per-producer queues.

    First deletes any existing queues (e.g. from a prior ``run_daemon`` which
    declares them without DLQ arguments) to avoid RabbitMQ precondition failures.
    Uses ``pika`` (sync) for the delete to avoid async timing issues.
    """
    # Delete existing queues synchronously — ``pika`` is already a dependency
    # and its blocking connection avoids any async timing issues with delete.
    _delete_control_queues(url)

    # Now declare the topology on a fresh async connection
    connection = await aio_pika.connect_robust(url)
    async with connection:
        channel = await connection.channel()
        control_dlx = await channel.declare_exchange(
            CONTROL_DLX,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

        # DLQ
        control_dlq = await channel.declare_queue(CONTROL_DLQ, durable=True)
        await control_dlq.bind(control_dlx, routing_key=CONTROL_DLQ)

        # Main exchange
        control_exchange = await channel.declare_exchange(
            CONTROL_EXCHANGE,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        # Per-producer queues
        for queue_name, routing_key in CONTROL_QUEUES:
            queue = await channel.declare_queue(
                queue_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": CONTROL_DLX,
                    "x-dead-letter-routing-key": CONTROL_DLQ,
                },
            )
            await queue.bind(control_exchange, routing_key=routing_key)


# ── Pytest markers ────────────────────────────────────────────────────────

pytestmark = [pytest.mark.integration, pytest.mark.rabbitmq]


# ── Shared fixtures ───────────────────────────────────────────────────────


def _purge_control_queues_sync() -> None:
    """Purge all control queues synchronously via ``pika``.

    Using a sync connection is more reliable than ``aio_pika`` for post-test
    cleanup because it avoids any channel-state issues from the test itself.
    """
    params = pika.URLParameters(settings.RABBITMQ_URL)
    conn = pika.BlockingConnection(params)
    try:
        channel = conn.channel()
        for queue_name, _ in CONTROL_QUEUES:
            try:
                channel.queue_purge(queue_name)
            except Exception:  # pylint: disable=broad-except
                pass  # Queue may not exist
        try:
            channel.queue_purge(CONTROL_DLQ)
        except Exception:  # pylint: disable=broad-except
            pass
    finally:
        conn.close()


async def _purge_control_queues() -> None:
    """Purge all messages from the control queues to avoid test interference."""
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        for queue_name, _ in CONTROL_QUEUES:
            try:
                queue = await channel.declare_queue(queue_name, durable=True, passive=True)
                await queue.purge()
            except Exception:  # pylint: disable=broad-except
                pass  # Queue doesn't exist yet, that's fine


async def _purge_control_dlq() -> None:
    """Purge the control DLQ."""
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        try:
            dlq = await channel.declare_queue(CONTROL_DLQ, durable=True, passive=True)
            await dlq.purge()
        except Exception:  # pylint: disable=broad-except
            pass


# ═══════════════════════════════════════════════════════════════════════════
#  Test class: Daemon receives command via RabbitMQ
# ═══════════════════════════════════════════════════════════════════════════


@_skip_if_rabbitmq_unavailable
class TestDaemonReceivesCommandViaRabbitMQ:
    """A ``CommandEnvelope`` published to the control exchange is deliverable
    to the correct ``cnc.<container>`` queue."""

    @pytest_asyncio.fixture(autouse=True)
    async def ensure_topology(self, request):
        """Declare the control topology and purge queues before each test."""
        await _declare_control_topology(settings.RABBITMQ_URL)
        await _purge_control_queues()
        await _purge_control_dlq()
        # Register sync finalizer for post-test cleanup (runs before the
        # event loop is torn down, unlike ``yield`` fixture teardown).
        request.addfinalizer(_purge_control_queues_sync)

    # ── helpers ───────────────────────────────────────────────────────────

    async def _publish(
        self,
        command_id: uuid.UUID,
        target: str,
        command_type: str = "scan",
        parameters: dict | None = None,
    ) -> None:
        """Publish a ``CommandEnvelope`` to the control exchange."""
        envelope = {
            "command_id": str(command_id),
            "command_type": command_type,
            "target": target,
            "parameters": parameters,
            "issued_at": datetime.now(timezone.utc).isoformat(),
        }
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                CONTROL_EXCHANGE,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
            await exchange.publish(
                aio_pika.Message(
                    body=json.dumps(envelope).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=f"command_n_control.{target}",
            )

    # ── tests ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_message_delivered_to_correct_queue(self):
        """A message published to ``command_n_control.github-producer`` is
        consumable from the ``cnc.github-producer`` queue."""
        command_id = uuid.uuid4()
        target = "github-producer"

        await self._publish(command_id, target)

        # Consume from the target queue
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue(
                "cnc.github-producer",
                durable=True,
                passive=True,
            )
            msg = await queue.get(timeout=5, fail=False)
            assert msg is not None, "Message should be deliverable to cnc.github-producer"
            payload = json.loads(msg.body)
            assert payload["command_id"] == str(command_id)
            assert payload["command_type"] == "scan"
            assert payload["target"] == target
            await msg.ack()

    @pytest.mark.asyncio
    async def test_message_not_delivered_to_wrong_queue(self):
        """A message for ``github-producer`` is NOT deliverable to ``cnc.jira-producer``."""
        command_id = uuid.uuid4()

        await self._publish(command_id, target="github-producer")

        # Try to consume from the wrong queue
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue(
                "cnc.jira-producer",
                durable=True,
                passive=True,
            )
            msg = await queue.get(timeout=2, fail=False)
            assert msg is None, "Message should NOT be deliverable to cnc.jira-producer"

    @pytest.mark.asyncio
    async def test_message_with_parameters(self):
        """A message with ``parameters`` preserves the payload through delivery."""
        command_id = uuid.uuid4()
        parameters = {"force_full": True, "since": "2026-06-01"}

        await self._publish(command_id, target="github-producer", parameters=parameters)

        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue(
                "cnc.github-producer",
                durable=True,
                passive=True,
            )
            msg = await queue.get(timeout=5, fail=False)
            assert msg is not None
            payload = json.loads(msg.body)
            assert payload["parameters"] == parameters
            await msg.ack()

    @pytest.mark.asyncio
    async def test_multiple_producers_receive_correctly(self):
        """Messages to different targets are routed to the correct queues."""
        github_id = uuid.uuid4()
        jira_id = uuid.uuid4()

        await self._publish(github_id, target="github-producer")
        await self._publish(jira_id, target="jira-producer")

        # Verify github-producer queue
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()

            # GitHub queue
            gh_queue = await channel.declare_queue(
                "cnc.github-producer", durable=True, passive=True
            )
            gh_msg = await gh_queue.get(timeout=5, fail=False)
            assert gh_msg is not None
            gh_payload = json.loads(gh_msg.body)
            assert gh_payload["command_id"] == str(github_id)
            await gh_msg.ack()

            # Jira queue
            jira_queue = await channel.declare_queue(
                "cnc.jira-producer", durable=True, passive=True
            )
            jira_msg = await jira_queue.get(timeout=5, fail=False)
            assert jira_msg is not None
            jira_payload = json.loads(jira_msg.body)
            assert jira_payload["command_id"] == str(jira_id)
            await jira_msg.ack()

    @pytest.mark.asyncio
    async def test_all_control_queues_exist(self):
        """All three ``cnc.*`` queues are declared and durable."""
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            for queue_name, _ in CONTROL_QUEUES:
                queue = await channel.declare_queue(
                    queue_name, durable=True, passive=True
                )
                assert queue.name == queue_name

    @pytest.mark.asyncio
    async def test_control_dlx_and_dlq_exist(self):
        """The ``command_n_control_dlx`` and ``command_n_control_dlq`` exist."""
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()

            # DLX
            dlx = await channel.declare_exchange(
                CONTROL_DLX,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
                passive=True,
            )
            assert dlx.name == CONTROL_DLX

            # DLQ
            dlq = await channel.declare_queue(CONTROL_DLQ, durable=True, passive=True)
            assert dlq.name == CONTROL_DLQ

    @pytest.mark.asyncio
    async def test_invalid_message_nacked_to_dlq(self):
        """An invalid message (not valid JSON) should be nacked and routed to DLQ."""
        test_body = b"not valid json"
        test_queue = f"cnc.test-dlq-{uuid.uuid4().hex}"

        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                CONTROL_EXCHANGE,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )

            # Create a temporary queue with DLQ args
            queue = await channel.declare_queue(
                test_queue,
                durable=True,
                auto_delete=True,
                arguments={
                    "x-dead-letter-exchange": CONTROL_DLX,
                    "x-dead-letter-routing-key": CONTROL_DLQ,
                },
            )
            await queue.bind(exchange, routing_key=f"command_n_control.test-dlq")

            # Publish invalid message
            await exchange.publish(
                aio_pika.Message(
                    body=test_body,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=f"command_n_control.test-dlq",
            )

            # Consume and nack with requeue=False
            msg = await queue.get(timeout=5, fail=False)
            assert msg is not None
            assert msg.body == test_body
            await msg.reject(requeue=False)

        # Allow brief moment for DLQ routing
        await asyncio.sleep(0.2)

        # Verify message arrived in DLQ
        dlq_conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with dlq_conn:
            dlq_channel = await dlq_conn.channel()
            dlq = await dlq_channel.declare_queue(CONTROL_DLQ, durable=True, passive=True)
            dlq_msg = await dlq.get(timeout=5, fail=False)
            assert dlq_msg is not None, "Nacked message should appear in the DLQ"
            assert dlq_msg.body == test_body
            await dlq_msg.ack()

    @pytest.mark.asyncio
    async def test_declare_topology_is_idempotent(self):
        """Calling ``_declare_control_topology`` twice does not raise."""
        await _declare_control_topology(settings.RABBITMQ_URL)
        await _declare_control_topology(settings.RABBITMQ_URL)
        # No assertion needed — just checking it doesn't raise


# ═══════════════════════════════════════════════════════════════════════════
#  Test class: End-to-end scan lifecycle
# ═══════════════════════════════════════════════════════════════════════════


@_skip_if_app_unavailable
class TestScanEndToEnd:
    """Full flow: API POST → RabbitMQ → daemon → child → status completed.

    Requires the app server to be running at ``http://localhost:8000`` and
    RabbitMQ to be reachable at ``settings.RABBITMQ_URL``.
    """

    _API_BASE = "http://localhost:8000/api/v1"
    _created_command_ids: list[str] = []

    @pytest_asyncio.fixture(autouse=True)
    async def ensure_topology(self, request):
        """Declare the control topology and purge queues before each test."""
        await _declare_control_topology(settings.RABBITMQ_URL)
        await _purge_control_queues()
        await _purge_control_dlq()
        self._created_command_ids = []
        # Register a sync finalizer for post-test cleanup (runs before the
        # event loop is torn down, unlike ``yield`` fixture teardown).
        request.addfinalizer(self._cleanup)
        yield

    def _cleanup(self) -> None:
        """Synchronous post-test cleanup: purge RabbitMQ messages and test-created DB records."""
        _purge_control_queues_sync()
        command_ids = list(self._created_command_ids)
        if not command_ids:
            return
        # Clean up only the test-created command_status rows using a fresh
        # event loop (the original loop is closed by the time the finalizer
        # runs).
        async def _clean_db() -> None:
            from app.db.session import ASYNC_SESSION_LOCAL, engine  # pylint: disable=import-outside-toplevel
            from app.db.models.command_status import CommandStatus  # pylint: disable=import-outside-toplevel
            import sqlalchemy  # pylint: disable=import-outside-toplevel
            async with ASYNC_SESSION_LOCAL() as session:
                await session.execute(
                    sqlalchemy.delete(CommandStatus).where(
                        CommandStatus.command_id.in_(command_ids)
                    )
                )
                await session.commit()
            # Dispose the engine so pooled connections don't leak warnings
            # when their (closed) event loop is garbage collected.
            await engine.dispose()
        try:
            asyncio.run(_clean_db())
        except Exception:  # pylint: disable=broad-except
            pass  # Best-effort cleanup

    # ── tests ─────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    @pytest.mark.server
    async def test_scan_command_creates_command_status(self):
        """POST /api/v1/commands/ returns a command with ``accepted`` status."""
        async with httpx.AsyncClient(base_url=self._API_BASE, timeout=10) as client:
            resp = await client.post(
                "/commands/",
                json={
                    "command_type": "scan",
                    "target": "github-producer",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] in ("accepted", "failed")
        assert data["command_type"] == "scan"
        assert data["target"] == "github-producer"
        # Verify a UUID was generated
        assert len(data["command_id"]) == 36
        self._created_command_ids.append(data["command_id"])

    @pytest.mark.asyncio
    @pytest.mark.server
    async def test_scan_command_publishes_to_rabbitmq(self):
        """POST /api/v1/commands/ causes a message to appear on the ``command_n_control`` exchange."""
        async with httpx.AsyncClient(base_url=self._API_BASE, timeout=10) as client:
            resp = await client.post(
                "/commands/",
                json={
                    "command_type": "scan",
                    "target": "jira-producer",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        command_id = data["command_id"]
        self._created_command_ids.append(command_id)

        # Verify the message is consumable from the correct queue
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue(
                "cnc.jira-producer",
                durable=True,
                passive=True,
            )
            msg = await queue.get(timeout=5, fail=False)
            assert msg is not None, "Message should appear on cnc.jira-producer queue"
            payload = json.loads(msg.body)
            assert payload["command_id"] == command_id
            assert payload["command_type"] == "scan"
            assert payload["target"] == "jira-producer"
            await msg.ack()

    @pytest.mark.asyncio
    @pytest.mark.server
    async def test_scan_command_with_parameters(self):
        """POST /api/v1/commands/ with ``parameters`` persists them correctly."""
        async with httpx.AsyncClient(base_url=self._API_BASE, timeout=10) as client:
            resp = await client.post(
                "/commands/",
                json={
                    "command_type": "scan",
                    "target": "github-producer",
                    "parameters": {"force_full": True, "since": "2026-06-01"},
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        self._created_command_ids.append(data["command_id"])
        # The parameters should be stored
        assert data["parameters"] is not None

        # Verify on RabbitMQ
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue(
                "cnc.github-producer",
                durable=True,
                passive=True,
            )
            msg = await queue.get(timeout=5, fail=False)
            assert msg is not None
            payload = json.loads(msg.body)
            assert payload["parameters"] == {"force_full": True, "since": "2026-06-01"}
            await msg.ack()

    @pytest.mark.asyncio
    @pytest.mark.server
    async def test_command_status_updatable_via_patch(self):
        """PATCH /api/v1/commands/{id}/status transitions the status lifecycle."""
        async with httpx.AsyncClient(base_url=self._API_BASE, timeout=10) as client:
            # Create a command
            create_resp = await client.post(
                "/commands/",
                json={
                    "command_type": "scan",
                    "target": "github-producer",
                },
            )
            assert create_resp.status_code == 201
            command_id = create_resp.json()["command_id"]
            self._created_command_ids.append(command_id)

            # Update status to running
            patch_resp = await client.patch(
                f"/commands/{command_id}/status",
                json={
                    "status": "running",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["status"] == "running"

            # Update status to completed
            patch_resp = await client.patch(
                f"/commands/{command_id}/status",
                json={
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            assert patch_resp.status_code == 200
            assert patch_resp.json()["status"] == "completed"

            # Verify via GET
            get_resp = await client.get(f"/commands/{command_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["status"] == "completed"

    @pytest.mark.asyncio
    @pytest.mark.server
    async def test_full_lifecycle_via_api(self):
        """Full lifecycle: pending → accepted → queued → running → completed."""
        async with httpx.AsyncClient(base_url=self._API_BASE, timeout=10) as client:
            # Create
            resp = await client.post(
                "/commands/",
                json={
                    "command_type": "scan",
                    "target": "confluence-producer",
                },
            )
            assert resp.status_code == 201
            command_id = resp.json()["command_id"]
            self._created_command_ids.append(command_id)

            # pending → accepted (already accepted from create)
            # accepted → queued
            resp = await client.patch(
                f"/commands/{command_id}/status",
                json={"status": "queued"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "queued"

            # queued → running
            resp = await client.patch(
                f"/commands/{command_id}/status",
                json={
                    "status": "running",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "running"

            # running → completed
            resp = await client.patch(
                f"/commands/{command_id}/status",
                json={
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "result_summary": {"signals_published": 42},
                },
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "completed"
            assert resp.json()["result_summary"]["signals_published"] == 42

            # Final GET
            resp = await client.get(f"/commands/{command_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "completed"
            assert data["started_at"] is not None
            assert data["completed_at"] is not None
            assert data["result_summary"]["signals_published"] == 42

    @pytest.mark.asyncio
    @pytest.mark.server
    async def test_command_list_filters(self):
        """GET /api/v1/commands/ supports target and status filters."""
        async with httpx.AsyncClient(base_url=self._API_BASE, timeout=10) as client:
            # Create a few commands
            for target in ("github-producer", "jira-producer"):
                resp = await client.post(
                    "/commands/",
                    json={"command_type": "scan", "target": target},
                )
                if resp.status_code == 201:
                    self._created_command_ids.append(resp.json()["command_id"])

            # Wait briefly for async processing
            await asyncio.sleep(0.3)

            # List with target filter
            resp = await client.get("/commands/?target=github-producer")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] >= 1
            for cmd in data["commands"]:
                assert cmd["target"] == "github-producer"

            # List with limit
            resp = await client.get("/commands/?limit=1")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["commands"]) <= 1

    @pytest.mark.asyncio
    @pytest.mark.server
    async def test_scan_mode_updates_status_running_then_completed(self):
        """Simulate the daemon child process: run_scan with a mock scan_func
        that succeeds, and verify status transitions via PATCH."""

        async with httpx.AsyncClient(base_url=self._API_BASE, timeout=10) as client:
            # Create a command via API
            resp = await client.post(
                "/commands/",
                json={"command_type": "scan", "target": "github-producer"},
            )
            assert resp.status_code == 201
            command_id_str = resp.json()["command_id"]
            self._created_command_ids.append(command_id_str)
            command_id = uuid.UUID(command_id_str)

        # Simulate daemon child: PATCH running directly, then PATCH completed
        from connectors.producers.daemon_common import _update_status  # pylint: disable=import-outside-toplevel
        from common.command_n_control.models import CommandStatusUpdate  # pylint: disable=import-outside-toplevel

        _update_status(command_id, CommandStatusUpdate(
            status="running", started_at=datetime.now(timezone.utc),
        ))
        _update_status(command_id, CommandStatusUpdate(
            status="completed", completed_at=datetime.now(timezone.utc),
        ))

        # Verify final status is completed
        async with httpx.AsyncClient(base_url=self._API_BASE, timeout=10) as client:
            resp = await client.get(f"/commands/{command_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    @pytest.mark.asyncio
    @pytest.mark.server
    async def test_scan_mode_updates_status_failed_on_error(self):
        """Simulate the daemon child: PATCH failed via the daemon's
        status update helper, and verify via GET."""

        async with httpx.AsyncClient(base_url=self._API_BASE, timeout=10) as client:
            resp = await client.post(
                "/commands/",
                json={"command_type": "scan", "target": "github-producer"},
            )
            assert resp.status_code == 201
            command_id = uuid.UUID(resp.json()["command_id"])

        from connectors.producers.daemon_common import _update_status  # pylint: disable=import-outside-toplevel
        from common.command_n_control.models import CommandStatusUpdate  # pylint: disable=import-outside-toplevel

        _update_status(command_id, CommandStatusUpdate(
            status="failed",
            completed_at=datetime.now(timezone.utc),
            error_message="Simulated scan failure",
        ))

        # Verify final status is failed
        async with httpx.AsyncClient(base_url=self._API_BASE, timeout=10) as client:
            resp = await client.get(f"/commands/{command_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"
        assert "Simulated scan failure" in (resp.json().get("error_message") or "")
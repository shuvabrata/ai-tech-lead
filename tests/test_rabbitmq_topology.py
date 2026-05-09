"""Integration tests for Phase 1: RabbitMQ infrastructure setup.

Validates three behaviours required by the ActivitySignal ingestion plan:

1. **Connectivity & topology** — ``init_rabbitmq`` successfully declares the
   main exchange, dead-letter exchange, DLQ, and all per-entity-type queues.
2. **Message visibility** — an unacknowledged message is invisible to a second
   consumer and is automatically requeued when the holding connection closes.
3. **DLQ routing** — a message rejected with ``requeue=False`` is routed to
   the dead-letter queue.

   .. note::
       The plan called for testing ``x-delivery-limit`` (a Quorum Queue
       feature).  Because classic durable queues were chosen, DLQ routing is
       verified via an immediate ``nack(requeue=False)`` — the equivalent
       poison-message handling mechanism for classic queues.

Requirements:
    - A running RabbitMQ instance reachable at ``settings.RABBITMQ_URL``.

Run:
    pytest tests/test_rabbitmq_phase1.py -v -m "integration and rabbitmq"
"""

import asyncio
import base64
import json
import urllib.request
import uuid

import pytest
import pytest_asyncio

try:
    import aio_pika

    _AIO_PIKA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _AIO_PIKA_AVAILABLE = False

from app.scripts.init_rabbitmq import (
    DLQ_NAME,
    DLX_NAME,
    ENTITY_QUEUES,
    EXCHANGE_NAME,
    init_rabbitmq,
)
from app.settings import settings

# ---------------------------------------------------------------------------
# Management API helpers
# ---------------------------------------------------------------------------

_MGMT_BASE = "http://localhost:15672/api"


def _mgmt_auth() -> str:
    """Return the Basic-auth header value derived from RABBITMQ_URL."""
    url = settings.RABBITMQ_URL  # amqp://user:pass@host:port/
    try:
        credentials = url.split("://")[1].split("@")[0]  # user:pass
    except IndexError:
        credentials = "guest:guest"
    return base64.b64encode(credentials.encode()).decode()


def _mgmt_get(path: str) -> dict | list:
    """Perform a GET against the RabbitMQ Management HTTP API."""
    req = urllib.request.Request(
        f"{_MGMT_BASE}{path}",
        headers={"Authorization": f"Basic {_mgmt_auth()}"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def _mgmt_reachable() -> bool:
    try:
        _mgmt_get("/overview")
        return True
    except Exception:  # pylint: disable=broad-except
        return False


_mgmt_available = _mgmt_reachable()
_skip_if_mgmt_unavailable = pytest.mark.skipif(
    not _mgmt_available,
    reason="RabbitMQ Management API not reachable at http://localhost:15672",
)

pytestmark = [pytest.mark.integration, pytest.mark.rabbitmq]

# ---------------------------------------------------------------------------
# Module-level skip guards
# ---------------------------------------------------------------------------

if not _AIO_PIKA_AVAILABLE:
    pytest.skip("aio-pika is not installed", allow_module_level=True)


def _rabbitmq_reachable() -> bool:
    """Return True if RabbitMQ is reachable at settings.RABBITMQ_URL."""
    async def _check() -> bool:
        try:
            conn = await aio_pika.connect_robust(settings.RABBITMQ_URL, timeout=3)
            await conn.close()
            return True
        except Exception:  # pylint: disable=broad-except
            return False

    return asyncio.run(_check())


_rabbitmq_available = _rabbitmq_reachable()
_skip_if_unavailable = pytest.mark.skipif(
    not _rabbitmq_available,
    reason=f"RabbitMQ not reachable at {settings.RABBITMQ_URL}",
)


@_skip_if_unavailable
class TestRabbitMQConnectivity:
    """Phase 1 — Connectivity and topology initialization tests."""

    @pytest_asyncio.fixture(autouse=True)
    async def ensure_topology(self):
        """Run init_rabbitmq once before each test in this class."""
        await init_rabbitmq(settings.RABBITMQ_URL)

    @pytest.mark.asyncio
    async def test_main_exchange_exists(self):
        """``activity_signals`` topic exchange is declared and durable."""
        conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with conn:
            channel = await conn.channel()
            # Passive re-declare: succeeds only if exchange exists with matching params
            exchange = await channel.declare_exchange(
                EXCHANGE_NAME,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
                passive=True,
            )
            assert exchange.name == EXCHANGE_NAME

    @pytest.mark.asyncio
    async def test_dlx_exists(self):
        """``activity_signals_dlx`` direct exchange is declared and durable."""
        conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with conn:
            channel = await conn.channel()
            dlx = await channel.declare_exchange(
                DLX_NAME,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
                passive=True,
            )
            assert dlx.name == DLX_NAME

    @pytest.mark.asyncio
    async def test_dlq_exists(self):
        """``activity_signals_dlq`` queue is declared and durable."""
        conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with conn:
            channel = await conn.channel()
            dlq = await channel.declare_queue(DLQ_NAME, durable=True, passive=True)
            assert dlq.name == DLQ_NAME

    @pytest.mark.asyncio
    async def test_all_entity_queues_exist(self):
        """All 12 per-entity-type queues are declared and durable."""
        conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with conn:
            channel = await conn.channel()
            for queue_name, _ in ENTITY_QUEUES:
                queue = await channel.declare_queue(
                    queue_name, durable=True, passive=True
                )
                assert queue.name == queue_name

    @pytest.mark.asyncio
    async def test_init_is_idempotent(self):
        """Calling init_rabbitmq a second time raises no errors."""
        # First call is in the autouse fixture; this is the second call.
        await init_rabbitmq(settings.RABBITMQ_URL)


@_skip_if_unavailable
class TestMessageVisibility:
    """Phase 1 — Unacknowledged messages are invisible to competing consumers.

    Verifies standard AMQP semantics: a message held unacknowledged by
    Consumer A is not returned by ``basic.get`` to Consumer B.  Once Consumer
    A's connection closes (without acking), the broker requeues the message and
    Consumer C can retrieve it.
    """

    _ROUTING_KEY = "github.Commit"

    @pytest_asyncio.fixture(autouse=True)
    async def topology(self):
        await init_rabbitmq(settings.RABBITMQ_URL)

    @pytest.mark.asyncio
    async def test_unacked_message_invisible_to_second_consumer(self):
        """Unacked message is not returned to a competing ``basic.get`` call."""
        test_body = f"visibility-test-{uuid.uuid4()}".encode()
        test_queue = f"test_visibility_queue_{uuid.uuid4().hex}"

        # ── Create an isolated queue bound to the tested routing key ───────
        setup_conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with setup_conn:
            setup_channel = await setup_conn.channel()
            exchange = await setup_channel.declare_exchange(
                EXCHANGE_NAME,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
            queue = await setup_channel.declare_queue(
                test_queue,
                durable=True,
                auto_delete=True,
            )
            await queue.bind(exchange, routing_key=self._ROUTING_KEY)

            # ── Publish to isolated queue ───────────────────────────────────
            await exchange.publish(
                aio_pika.Message(
                    body=test_body,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=self._ROUTING_KEY,
            )

        # ── Consumer A: receive but do NOT acknowledge ────────────────────────
        conn_a = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        channel_a = await conn_a.channel()
        queue_a = await channel_a.declare_queue(test_queue, durable=True, passive=True)
        msg_a = await queue_a.get(timeout=5)
        assert msg_a is not None, "Consumer A should receive the published message"
        assert msg_a.body == test_body
        # Intentionally NOT acking — message is now in "unacknowledged" state.

        # ── Consumer B: basic.get should return nothing ───────────────────────
        conn_b = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with conn_b:
            channel_b = await conn_b.channel()
            queue_b = await channel_b.declare_queue(
                test_queue, durable=True, passive=True
            )
            msg_b = await queue_b.get(fail=False)
            assert msg_b is None, (
                "Unacknowledged message must not be visible to a second consumer"
            )

        # ── Close Consumer A without acking → broker requeues the message ────
        await conn_a.close()
        # Allow a brief moment for the broker to requeue
        await asyncio.sleep(0.3)

        # ── Consumer C: should now retrieve the requeued message ──────────────
        conn_c = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with conn_c:
            channel_c = await conn_c.channel()
            queue_c = await channel_c.declare_queue(
                test_queue, durable=True, passive=True
            )
            msg_c = await queue_c.get(timeout=5)
            assert msg_c is not None, "Requeued message must be available after Consumer A disconnects"
            assert msg_c.body == test_body
            await msg_c.ack()  # Clean up
            await queue_c.unbind(EXCHANGE_NAME, routing_key=self._ROUTING_KEY)
            await queue_c.delete(if_unused=False, if_empty=False)


@_skip_if_unavailable
class TestDLQRouting:
    """Phase 1 — Dead-letter queue routing on message rejection.

    Verifies that a message rejected with ``requeue=False`` is routed to
    ``activity_signals_dlq`` via the ``activity_signals_dlx`` dead-letter
    exchange.

    .. note::
        Classic durable queues do not support ``x-delivery-limit`` (a Quorum
        Queue feature).  This test exercises the equivalent behaviour: a single
        explicit ``nack(requeue=False)`` routes the message to the DLQ.
    """

    _ROUTING_KEY = "jira.Issue"

    @pytest_asyncio.fixture(autouse=True)
    async def topology(self):
        await init_rabbitmq(settings.RABBITMQ_URL)

    @pytest.mark.asyncio
    async def test_nacked_message_routes_to_dlq(self):
        """Nack with requeue=False sends the message to the DLQ."""
        test_body = f"dlq-test-{uuid.uuid4()}".encode()
        test_queue = f"test_dlq_queue_{uuid.uuid4().hex}"

        # ── Create an isolated queue with DLQ args and bind to routing key ─
        setup_conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with setup_conn:
            setup_channel = await setup_conn.channel()
            exchange = await setup_channel.declare_exchange(
                EXCHANGE_NAME,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
            queue = await setup_channel.declare_queue(
                test_queue,
                durable=True,
                auto_delete=True,
                arguments={
                    "x-dead-letter-exchange": DLX_NAME,
                    "x-dead-letter-routing-key": DLQ_NAME,
                },
            )
            await queue.bind(exchange, routing_key=self._ROUTING_KEY)

            # ── Publish to isolated queue ───────────────────────────────────
            await exchange.publish(
                aio_pika.Message(
                    body=test_body,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=self._ROUTING_KEY,
            )

        # ── Consume and reject (dead-letter) ─────────────────────────────────
        rej_conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with rej_conn:
            channel = await rej_conn.channel()
            queue = await channel.declare_queue(test_queue, durable=True, passive=True)
            msg = await queue.get(timeout=5)
            assert msg is not None, "Entity queue should have the published message"
            assert msg.body == test_body
            await msg.reject(requeue=False)  # → routes to DLX → DLQ
            await queue.unbind(EXCHANGE_NAME, routing_key=self._ROUTING_KEY)
            await queue.delete(if_unused=False, if_empty=False)

        # Allow a brief moment for dead-letter routing to complete
        await asyncio.sleep(0.2)

        # ── Verify message arrived in DLQ ────────────────────────────────────
        dlq_conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with dlq_conn:
            channel = await dlq_conn.channel()
            dlq = await channel.declare_queue(DLQ_NAME, durable=True, passive=True)
            dlq_msg = await _drain_until(dlq, test_body, timeout=5.0)
            assert dlq_msg is not None, (
                "Rejected message must appear in the DLQ"
            )
            await dlq_msg.ack()  # Clean up


# ---------------------------------------------------------------------------
# Topology + bindings verification (via Management HTTP API)
# ---------------------------------------------------------------------------


@_skip_if_mgmt_unavailable
class TestTopologyBindings:
    """Verify exchange/queue topology and binding properties via Management API.

    Uses the RabbitMQ Management HTTP API (port 15672) so that binding details
    and queue arguments are inspectable without consuming messages.
    """

    @pytest_asyncio.fixture(autouse=True)
    async def ensure_topology(self):
        """Idempotently declare topology before each test."""
        await init_rabbitmq(settings.RABBITMQ_URL)

    def test_main_exchange_is_topic_and_durable(self):
        """``activity_signals`` exchange is a durable topic exchange."""
        data = _mgmt_get(f"/exchanges/%2F/{EXCHANGE_NAME}")
        assert data["type"] == "topic", f"Expected topic, got {data['type']}"
        assert data["durable"] is True
        assert data["auto_delete"] is False

    def test_dlx_is_direct_and_durable(self):
        """``activity_signals_dlx`` exchange is a durable direct exchange."""
        data = _mgmt_get(f"/exchanges/%2F/{DLX_NAME}")
        assert data["type"] == "direct", f"Expected direct, got {data['type']}"
        assert data["durable"] is True
        assert data["auto_delete"] is False

    def test_dlq_is_durable(self):
        """``activity_signals_dlq`` queue is durable."""
        data = _mgmt_get(f"/queues/%2F/{DLQ_NAME}")
        assert data["durable"] is True

    def test_dlq_is_bound_to_dlx(self):
        """``activity_signals_dlq`` has a binding from the DLX."""
        bindings = _mgmt_get(f"/queues/%2F/{DLQ_NAME}/bindings")
        dlx_bindings = [b for b in bindings if b.get("source") == DLX_NAME]
        assert dlx_bindings, f"No binding found from {DLX_NAME} to {DLQ_NAME}"

    @pytest.mark.parametrize("queue_name,routing_key", ENTITY_QUEUES)
    def test_entity_queue_is_durable(self, queue_name: str, routing_key: str):
        """Each entity queue is durable."""
        data = _mgmt_get(f"/queues/%2F/{queue_name}")
        assert data["durable"] is True, f"{queue_name} is not durable"

    @pytest.mark.parametrize("queue_name,routing_key", ENTITY_QUEUES)
    def test_entity_queue_has_dead_letter_exchange(self, queue_name: str, routing_key: str):
        """Each entity queue has ``x-dead-letter-exchange`` pointing to the DLX."""
        data = _mgmt_get(f"/queues/%2F/{queue_name}")
        args = data.get("arguments", {})
        assert args.get("x-dead-letter-exchange") == DLX_NAME, (
            f"{queue_name} missing x-dead-letter-exchange={DLX_NAME}, got: {args}"
        )

    @pytest.mark.parametrize("queue_name,routing_key", ENTITY_QUEUES)
    def test_entity_queue_has_dead_letter_routing_key(self, queue_name: str, routing_key: str):
        """Each entity queue routes dead-lettered messages to the DLQ name."""
        data = _mgmt_get(f"/queues/%2F/{queue_name}")
        args = data.get("arguments", {})
        assert args.get("x-dead-letter-routing-key") == DLQ_NAME, (
            f"{queue_name} missing x-dead-letter-routing-key={DLQ_NAME}, got: {args}"
        )

    @pytest.mark.parametrize("queue_name,routing_key", ENTITY_QUEUES)
    def test_entity_queue_is_bound_to_main_exchange_with_correct_routing_key(
        self, queue_name: str, routing_key: str
    ):
        """Each entity queue has a binding from ``activity_signals`` with its expected routing key."""
        bindings = _mgmt_get(f"/queues/%2F/{queue_name}/bindings")
        matching = [
            b for b in bindings
            if b.get("source") == EXCHANGE_NAME and b.get("routing_key") == routing_key
        ]
        assert matching, (
            f"{queue_name} has no binding from exchange '{EXCHANGE_NAME}' "
            f"with routing_key='{routing_key}'. "
            f"Found bindings: {[(b.get('source'), b.get('routing_key')) for b in bindings]}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _drain_until(
    queue: "aio_pika.Queue",
    target_body: bytes,
    timeout: float = 5.0,
) -> "aio_pika.IncomingMessage | None":
    """Consume messages until ``target_body`` is found or ``timeout`` expires.

    Messages that do not match are requeued so they are not accidentally
    discarded by the test.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        msg = await queue.get(fail=False)
        if msg is None:
            await asyncio.sleep(0.1)
            continue
        if msg.body == target_body:
            return msg
        # Not our message — put it back
        await msg.reject(requeue=True)
        await asyncio.sleep(0.05)
    return None

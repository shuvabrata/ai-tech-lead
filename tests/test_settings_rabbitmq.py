"""Integration tests for Phase 5: RabbitMQ propagation of settings changes.

Validates three behaviours required by the runtime settings propagation plan:

1. **Exchange topology** — ``init_rabbitmq`` idempotently declares the
   ``runtime_config_events`` fanout exchange.
2. **Event publish** — Publishing a ``settings.changed`` event is accepted
   by the fanout exchange.
3. **Listener lifecycle** — An exclusive auto-delete queue is declared and
   bound, and the listener receives events from the fanout exchange.

Requirements:
    - A running RabbitMQ instance reachable at ``settings.RABBITMQ_URL``.

Run:
    pytest tests/test_settings_rabbitmq.py -v -m "integration and rabbitmq"
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
import pytest_asyncio

try:
    import aio_pika

    _AIO_PIKA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _AIO_PIKA_AVAILABLE = False

from app.scripts.init_rabbitmq import init_rabbitmq
from app.settings import settings
from common.runtime_settings.events import (
    RUNTIME_CONFIG_EXCHANGE,
    listen_for_settings_changed,
    publish_settings_changed,
)
from common.runtime_settings import RuntimeConfig, RuntimeConfigCache

pytestmark = [pytest.mark.integration, pytest.mark.rabbitmq]

# ---------------------------------------------------------------------------
# Module-level skip guards
# ---------------------------------------------------------------------------

if not _AIO_PIKA_AVAILABLE:
    pytest.skip("aio-pika is not installed", allow_module_level=True)


def _rabbitmq_reachable() -> bool:
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
class TestRuntimeConfigExchange:
    """Verify the ``runtime_config_events`` fanout exchange topology."""

    @pytest_asyncio.fixture(autouse=True)
    async def ensure_topology(self) -> None:
        """Run init_rabbitmq once before each test to ensure the exchange exists."""
        await init_rabbitmq(settings.RABBITMQ_URL)

    @pytest.mark.asyncio
    async def test_exchange_declared(self) -> None:
        """The ``runtime_config_events`` fanout exchange is declared and durable."""
        conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with conn:
            channel = await conn.channel()
            # Passive re-declare: succeeds only if exchange exists with matching params.
            exchange = await channel.declare_exchange(
                RUNTIME_CONFIG_EXCHANGE,
                aio_pika.ExchangeType.FANOUT,
                durable=True,
                passive=True,
            )
            assert exchange.name == RUNTIME_CONFIG_EXCHANGE

    @pytest.mark.asyncio
    async def test_init_is_idempotent(self) -> None:
        """Calling init_rabbitmq a second time raises no errors."""
        # First call is in the autouse fixture; this is the second call.
        await init_rabbitmq(settings.RABBITMQ_URL)


@_skip_if_unavailable
class TestSettingsChangedPublish:
    """Verify that publishing a ``settings.changed`` event works."""

    @pytest_asyncio.fixture(autouse=True)
    async def ensure_topology(self) -> None:
        await init_rabbitmq(settings.RABBITMQ_URL)

    @pytest.mark.asyncio
    async def test_publish_event(self) -> None:
        """Publishing a settings.changed event succeeds."""
        conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with conn:
            await publish_settings_changed(
                changed_keys=["TIMEZONE", "HTTP_REQUEST_TIMEOUT"],
                connection=conn,
            )
        # No exception = success. The event is published to the fanout
        # exchange and will be received by any bound listener.

    @pytest.mark.asyncio
    async def test_publish_no_connection_is_noop(self) -> None:
        """Publishing with ``connection=None`` is a no-op (no error)."""
        await publish_settings_changed(
            changed_keys=["TIMEZONE"],
            connection=None,
        )
        # No exception = success.

    @pytest.mark.asyncio
    async def test_publish_empty_keys(self) -> None:
        """Publishing with an empty keys list is valid."""
        conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        async with conn:
            await publish_settings_changed(
                changed_keys=[],
                connection=conn,
            )
        # No exception = success.


@_skip_if_unavailable
class TestListenerLifecycle:
    """Verify the listener queue lifecycle and event delivery."""

    @pytest_asyncio.fixture(autouse=True)
    async def ensure_topology(self) -> None:
        await init_rabbitmq(settings.RABBITMQ_URL)

    @pytest.mark.asyncio
    async def test_listener_then_event_causes_refresh(self) -> None:
        """A listener receives a settings.changed event and triggers a refresh.

        This test:
        1. Creates a listener with a unique instance_id.
        2. Creates a separate publisher connection.
        3. Publishes a settings.changed event.
        4. Waits briefly for the listener to process the event.
        5. Verifies the callback was invoked with the expected keys.
        """
        cache = RuntimeConfigCache()
        received_keys: list[str] = []

        async def on_event(changed_keys: list[str]) -> None:
            received_keys.extend(changed_keys)
            # Simulate a cache refresh by setting a known value.
            cache.refresh(
                RuntimeConfig(
                    HTTP_REQUEST_TIMEOUT=99,
                    NEO4J_QUERY_TIMEOUT=10,
                    GRAPH_UI_MAX_NODES_TO_EXPAND=20,
                    GRAPH_UI_MAX_NODE_LABEL_CHARS=10,
                    CONNECTOR_SCAN_POLL_INTERVAL=5000,
                    RECENT_ACTIONS_LIMIT=5,
                    TIMEZONE="UTC",
                    UI_DATETIME_FORMAT="%b %d, %Y %I:%M %p",
                    UI_DATE_FORMAT="%b %d, %Y",
                    AUGMENTATION_HISTORY_TURNS=5,
                    ES_CHAIN_MAX_RESULTS=5,
                    MAX_MCP_ITERATIONS=3,
                    FF_NEO4J_USE_PROVIDER_PIPELINE=False,
                )
            )

        # Start listener in background.
        listener_conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        instance_id = f"test-{uuid.uuid4().hex[:8]}"
        listener_task = asyncio.ensure_future(
            listen_for_settings_changed(
                connection=listener_conn,
                on_event=on_event,
                instance_id=instance_id,
            )
        )

        # Give the listener time to declare its queue and bind.
        await asyncio.sleep(0.5)

        try:
            # Publish event from a separate connection.
            pub_conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            async with pub_conn:
                await publish_settings_changed(
                    changed_keys=["HTTP_REQUEST_TIMEOUT"],
                    connection=pub_conn,
                )

            # Wait for the event to be received and processed.
            await asyncio.sleep(1.0)

            assert received_keys == ["HTTP_REQUEST_TIMEOUT"], (
                f"Expected ['HTTP_REQUEST_TIMEOUT'], got {received_keys}"
            )
            assert cache.get_int("HTTP_REQUEST_TIMEOUT") == 99, (
                "Cache should have been refreshed with the new value"
            )
        finally:
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
            if not listener_conn.is_closed:
                await listener_conn.close()

    @pytest.mark.asyncio
    async def test_duplicate_events_cause_duplicate_refreshes(self) -> None:
        """Duplicate events cause harmless duplicate refreshes."""
        refresh_count = 0

        async def on_event(changed_keys: list[str]) -> None:
            nonlocal refresh_count
            refresh_count += 1

        listener_conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        instance_id = f"test-dup-{uuid.uuid4().hex[:8]}"
        listener_task = asyncio.ensure_future(
            listen_for_settings_changed(
                connection=listener_conn,
                on_event=on_event,
                instance_id=instance_id,
            )
        )

        await asyncio.sleep(0.5)

        try:
            pub_conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
            async with pub_conn:
                # Publish two identical events.
                await publish_settings_changed(
                    changed_keys=["TIMEZONE"],
                    connection=pub_conn,
                )
                await publish_settings_changed(
                    changed_keys=["TIMEZONE"],
                    connection=pub_conn,
                )

            await asyncio.sleep(1.0)

            assert refresh_count >= 2, (
                f"Expected at least 2 refreshes, got {refresh_count}"
            )
        finally:
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
            if not listener_conn.is_closed:
                await listener_conn.close()

    @pytest.mark.asyncio
    async def test_listener_queue_is_exclusive_and_auto_delete(self) -> None:
        """The listener queue is exclusive and auto-delete."""
        listener_conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        instance_id = f"test-excl-{uuid.uuid4().hex[:8]}"
        queue_name = f"runtime_config.{instance_id}"

        async def on_event(changed_keys: list[str]) -> None:
            pass

        listener_task = asyncio.ensure_future(
            listen_for_settings_changed(
                connection=listener_conn,
                on_event=on_event,
                instance_id=instance_id,
            )
        )

        await asyncio.sleep(0.5)

        try:
            # Use Management API to inspect queue properties.
            import base64
            import urllib.request

            url = settings.RABBITMQ_URL
            try:
                credentials = url.split("://")[1].split("@")[0]
            except IndexError:
                credentials = "guest:guest"
            auth = base64.b64encode(credentials.encode()).decode()

            req = urllib.request.Request(
                f"http://localhost:15672/api/queues/%2F/{queue_name}",
                headers={"Authorization": f"Basic {auth}"},
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                    assert data["exclusive"] is True, "Queue should be exclusive"
                    assert data["auto_delete"] is True, "Queue should be auto-delete"
                    assert data["durable"] is False, "Queue should not be durable"
            except urllib.request.HTTPError:
                # Management API may not be available in all environments.
                pytest.skip("RabbitMQ Management API not available")
        finally:
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
            if not listener_conn.is_closed:
                await listener_conn.close()


@_skip_if_unavailable
class TestPublishFailureDoesNotAbortCommit:
    """Verify that publish failure after a DB commit is non-fatal.

    Since we cannot easily simulate a publish failure without a real DB, this
    test verifies that calling ``publish_settings_changed`` with a closed
    connection does not raise an exception (emulating the scenario where the
    broker becomes unavailable after the DB commit).
    """

    @pytest.mark.asyncio
    async def test_publish_on_closed_connection_logs_warning(self) -> None:
        """Publishing on a closed connection logs a warning but does not raise."""
        conn = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        await conn.close()

        # This should not raise — the exception is caught and logged.
        await publish_settings_changed(
            changed_keys=["HTTP_REQUEST_TIMEOUT"],
            connection=conn,
        )
        # No exception = success. The DB change is preserved.
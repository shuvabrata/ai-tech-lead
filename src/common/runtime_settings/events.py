"""RabbitMQ fanout event publisher and listener for runtime settings changes.

Exchange topology
-----------------
- ``runtime_config_events`` — durable fanout exchange.
  All invalidation events are broadcast to every bound queue.

Event body
----------
.. code-block:: json

    {
      "event_type": "settings.changed",
      "changed_keys": ["TIMEZONE", "HTTP_REQUEST_TIMEOUT"],
      "issued_at": "2026-08-03T00:00:00Z"
    }

The event is an **invalidation signal only** — it carries no setting values.
Receivers fetch the latest full snapshot from the authoritative source
(Postgres).

Reliability model
-----------------
- Postgres is the durable source of truth.
- RabbitMQ fanout provides live invalidation for currently running processes.
- Startup refresh recovers from missed events.
- Publish failure after DB commit is non-fatal (DB change is preserved).
- Listener startup failure is non-fatal (process continues with env/default).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Awaitable, Callable

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from common.logger import logger

# ── Exchange name ──────────────────────────────────────────────────────

RUNTIME_CONFIG_EXCHANGE = "runtime_config_events"


# ── Publisher ──────────────────────────────────────────────────────────


async def publish_settings_changed(
    changed_keys: list[str],
    connection: aio_pika.RobustConnection | None,
) -> bool:
    """Publish a ``settings.changed`` invalidation event to the fanout exchange.

    This is a **best-effort** publish.  If *connection* is ``None`` or the
    publish fails, a warning is logged but no exception is raised — the DB
    commit has already succeeded and the local cache has already been
    refreshed.

    Args:
        changed_keys: The setting keys that were modified.
        connection: An open RabbitMQ connection, or ``None`` to no-op.

    Returns:
        ``True`` if the event was published successfully, ``False`` otherwise.
    """
    if connection is None:
        logger.debug("No RabbitMQ connection — skipping settings.changed publish")
        return False

    try:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            RUNTIME_CONFIG_EXCHANGE,
            ExchangeType.FANOUT,
            durable=True,
        )

        body = json.dumps({
            "event_type": "settings.changed",
            "changed_keys": sorted(changed_keys),
            "issued_at": datetime.now(timezone.utc).isoformat(),
        })

        await exchange.publish(
            Message(
                body=body.encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
            ),
            routing_key="",  # fanout ignores routing key
        )
        logger.info(
            "Published settings.changed event: keys=%s",
            sorted(changed_keys),
        )
        return True
    except Exception:  # pylint: disable=broad-except
        logger.warning(
            "Failed to publish settings.changed event (DB change preserved): "
            "keys=%s",
            sorted(changed_keys),
            exc_info=True,
        )
        return False


# ── Listener ───────────────────────────────────────────────────────────


async def listen_for_settings_changed(
    connection: aio_pika.RobustConnection,
    on_event: Callable[[list[str]], Awaitable[None]],
    instance_id: str | None = None,
) -> None:
    """Declare an exclusive auto-delete queue and listen for invalidation events.

    Each call creates a new queue bound to the ``runtime_config_events``
    fanout exchange.  The queue is exclusive to this connection and
    auto-deletes when the connection closes.

    Args:
        connection: An open RabbitMQ connection.
        on_event: Async callback invoked with the list of changed keys
            whenever a ``settings.changed`` event is received.
        instance_id: Optional identifier for the listener queue name.
            Defaults to ``"app"``.
    """
    if instance_id is None:
        instance_id = "app"

    channel = await connection.channel()
    exchange = await channel.declare_exchange(
        RUNTIME_CONFIG_EXCHANGE,
        ExchangeType.FANOUT,
        durable=True,
    )

    # Exclusive, auto-delete queue — one per process instance.
    queue_name = f"runtime_config.{instance_id}"
    queue = await channel.declare_queue(
        queue_name,
        durable=False,
        exclusive=True,
        auto_delete=True,
    )
    await queue.bind(exchange, routing_key="")

    logger.info(
        "Listening for runtime config events on queue %s",
        queue_name,
    )

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process(requeue=False):
                try:
                    payload = json.loads(message.body.decode())
                    event_type = payload.get("event_type")
                    if event_type != "settings.changed":
                        logger.debug(
                            "Ignoring unknown runtime config event: %s",
                            event_type,
                        )
                        continue

                    changed_keys: list[str] = payload.get("changed_keys", [])
                    logger.info(
                        "Received settings.changed event: keys=%s",
                        changed_keys,
                    )
                    await on_event(changed_keys)
                except Exception:  # pylint: disable=broad-except
                    logger.warning(
                        "Failed to process runtime config event",
                        exc_info=True,
                    )
"""RabbitMQ initialization script.

Declares the exchanges, dead-letter queue, and per-entity-type queues required
by the ActivitySignal event-driven ingestion pipeline.

Exchange topology
-----------------
- ``activity_signals``     — durable topic exchange; all producers publish here.
- ``activity_signals_dlx`` — durable direct exchange; receives dead-lettered messages.
- ``activity_signals_dlq`` — durable classic queue bound to the DLX; holds poison messages.

Queue naming convention
-----------------------
``<source>_queue``, e.g. ``github_queue``.

Routing key convention
----------------------
``<source>.#``, e.g. ``github.#``.

This script is designed to be run at container startup (before Uvicorn) via
``src/app/entrypoint.sh``.  It is idempotent: re-running it is safe because
RabbitMQ ignores re-declarations that match the existing topology exactly.
"""

import asyncio
import logging
import os
import sys

import aio_pika

logger = logging.getLogger(__name__)

EXCHANGE_NAME: str = "activity_signals"
DLX_NAME: str = "activity_signals_dlx"
DLQ_NAME: str = "activity_signals_dlq"

# (queue_name, routing_key) — one queue per source.
# Routing keys follow the format: <source>.#
SOURCE_QUEUES: list[tuple[str, str]] = [
    ("github_queue", "github.#"),
    ("jira_queue", "jira.#"),
    ("confluence_queue", "confluence.#"),
]


async def init_rabbitmq(url: str) -> None:
    """Initialize RabbitMQ topology for the ActivitySignal pipeline.

    Declares (idempotently):
    - ``activity_signals``  — durable topic exchange
    - ``activity_signals_dlx`` — durable direct dead-letter exchange
    - ``activity_signals_dlq`` — durable DLQ bound to the DLX
    - One durable classic queue per source, bound to ``activity_signals``
      with ``x-dead-letter-exchange`` pointing to the DLX

    Args:
        url: AMQP connection URL, e.g. ``amqp://guest:guest@localhost:5672/``.
    """
    logger.info("Connecting to RabbitMQ: %s", url)
    connection = await aio_pika.connect_robust(url)

    async with connection:
        channel = await connection.channel()

        # 1. Dead-letter exchange (direct) ───────────────────────────────────
        dlx = await channel.declare_exchange(
            DLX_NAME,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )
        logger.info("Exchange ready: %s (direct, durable)", DLX_NAME)

        # 2. Dead-letter queue bound to DLX ──────────────────────────────────
        dlq = await channel.declare_queue(DLQ_NAME, durable=True)
        await dlq.bind(dlx, routing_key=DLQ_NAME)
        logger.info("Queue ready: %s, bound to exchange %s", DLQ_NAME, DLX_NAME)

        # 3. Main topic exchange ──────────────────────────────────────────────
        exchange = await channel.declare_exchange(
            EXCHANGE_NAME,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        logger.info("Exchange ready: %s (topic, durable)", EXCHANGE_NAME)

        # 4. Source queues ────────────────────────────────────────────────────
        # Classic durable queues with dead-letter routing on rejection.
        # Note: x-delivery-limit is a Quorum Queue feature and is intentionally
        # omitted here. Poison-message handling relies on consumer-side nack
        # with requeue=False, which routes the message to the DLQ immediately.
        for queue_name, routing_key in SOURCE_QUEUES:
            queue = await channel.declare_queue(
                queue_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": DLX_NAME,
                    "x-dead-letter-routing-key": DLQ_NAME,
                },
            )
            await queue.bind(exchange, routing_key=routing_key)
            logger.info(
                "Queue ready: %s  ← routing key: %s", queue_name, routing_key
            )

    logger.info("RabbitMQ initialization complete.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    rabbitmq_url: str = os.environ.get(
        "RABBITMQ_URL", "amqp://guest:guest@localhost:5672/"
    )

    try:
        asyncio.run(init_rabbitmq(rabbitmq_url))
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("RabbitMQ initialization failed: %s", exc)
        sys.exit(1)

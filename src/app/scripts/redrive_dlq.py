"""DLQ Remediation Script — redrive_dlq.py

Inspects messages in ``activity_signals_dlq`` and republishes them to the
main ``activity_signals`` topic exchange so they can be reprocessed by the
appropriate consumer.

Usage
-----
Run after deploying a consumer bug-fix to drain the DLQ:

    # Dry-run: inspect only, do not republish
    PYTHONPATH=src python src/app/scripts/redrive_dlq.py --dry-run

    # Redrive all messages
    PYTHONPATH=src python src/app/scripts/redrive_dlq.py

    # Redrive up to N messages
    PYTHONPATH=src python src/app/scripts/redrive_dlq.py --limit 10

Environment
-----------
Reads ``RABBITMQ_URL`` from the environment (falls back to
``amqp://guest:guest@localhost:5672/``).

How it works
------------
For each message in the DLQ:
  1. Peek at the ``x-death`` header to recover the original routing key.
  2. Republish the raw body to ``activity_signals`` with that routing key and
     ``delivery_mode=PERSISTENT``.
  3. Acknowledge the DLQ message so it is removed from the DLQ.

If ``--dry-run`` is specified, messages are printed but not acknowledged or
republished.

Safety
------
The script uses ``basic_get`` (pull, not push) so it processes exactly the
messages present at start time and exits cleanly when the DLQ is empty or
``--limit`` is reached.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Optional

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("redrive_dlq")

DLQ_NAME = "activity_signals_dlq"
EXCHANGE_NAME = "activity_signals"
DLX_NAME = "activity_signals_dlx"


def _extract_routing_key(message: aio_pika.abc.AbstractIncomingMessage) -> Optional[str]:
    """Recover the original routing key from the ``x-death`` header.

    RabbitMQ automatically appends an ``x-death`` array header when a message
    is dead-lettered.  The first element contains the original exchange and
    routing-key.

    Falls back to the message's current ``routing_key`` if the header is absent.
    """
    headers = message.headers or {}
    x_death = headers.get("x-death")
    if x_death and isinstance(x_death, list) and len(x_death) > 0:
        original_routing_key = x_death[0].get("routing-keys")
        if original_routing_key and len(original_routing_key) > 0:
            return str(original_routing_key[0])
    # Fall back to whatever routing key the DLQ message carries
    return message.routing_key or None


async def redrive(url: str, limit: Optional[int], dry_run: bool) -> None:
    """Pull messages from the DLQ and republish them to the main exchange.

    Args:
        url: AMQP connection URL.
        limit: Maximum number of messages to process.  ``None`` means drain
            all messages currently in the DLQ.
        dry_run: If ``True``, print messages but do not republish or ack.
    """
    logger.info("Connecting to RabbitMQ: %s", url)
    connection = await aio_pika.connect_robust(url)

    async with connection:
        channel = await connection.channel()

        # Declare the main exchange (idempotent — safe to call if it exists).
        exchange = await channel.declare_exchange(
            EXCHANGE_NAME,
            ExchangeType.TOPIC,
            durable=True,
        )

        # Declare the DLQ (idempotent) so the script works even if the app
        # container hasn't started yet.
        dlx = await channel.declare_exchange(
            DLX_NAME,
            ExchangeType.DIRECT,
            durable=True,
        )
        queue = await channel.declare_queue(
            DLQ_NAME,
            durable=True,
        )
        await queue.bind(dlx, routing_key=DLQ_NAME)

        processed = 0
        skipped = 0

        logger.info(
            "Starting DLQ redrive (dry_run=%s, limit=%s) from queue '%s'",
            dry_run,
            limit,
            DLQ_NAME,
        )

        while True:
            if limit is not None and processed >= limit:
                logger.info("Reached --limit %d, stopping.", limit)
                break

            # basic_get: pull one message without blocking.
            message = await queue.get(fail=False)
            if message is None:
                logger.info("DLQ is empty — done.")
                break

            async with message.process(requeue=True, ignore_processed=True):
                routing_key = _extract_routing_key(message)

                if not routing_key:
                    logger.warning(
                        "Cannot determine routing key for message — skipping. "
                        "body_preview=%s",
                        message.body[:200],
                    )
                    skipped += 1
                    await message.nack(requeue=False)
                    continue

                # Log a preview of the payload for observability.
                try:
                    payload_preview = json.loads(message.body)
                    signal_id = payload_preview.get("signal_id", "<unknown>")
                    entity_type = payload_preview.get("entity_type", "<unknown>")
                except (json.JSONDecodeError, AttributeError):
                    signal_id = "<invalid-json>"
                    entity_type = "<invalid-json>"

                logger.info(
                    "DLQ message signal_id=%s entity_type=%s routing_key=%s",
                    signal_id,
                    entity_type,
                    routing_key,
                )

                if dry_run:
                    logger.info(
                        "[DRY-RUN] Would republish signal_id=%s to routing_key=%s",
                        signal_id,
                        routing_key,
                    )
                    # In dry-run: nack with requeue=True to leave message in DLQ.
                    await message.nack(requeue=True)
                    processed += 1
                    continue

                # Republish to the main exchange with original routing key.
                republish_msg = Message(
                    body=message.body,
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type=message.content_type or "application/json",
                    headers={
                        k: v
                        for k, v in (message.headers or {}).items()
                        if k != "x-death"  # strip x-death to reset retry history
                    },
                )
                await exchange.publish(republish_msg, routing_key=routing_key)
                await message.ack()

                logger.info(
                    "Redriven signal_id=%s to routing_key=%s",
                    signal_id,
                    routing_key,
                )
                processed += 1

        logger.info(
            "Redrive complete. processed=%d skipped=%d dry_run=%s",
            processed,
            skipped,
            dry_run,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Redrive messages from activity_signals_dlq back to the main exchange."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Inspect and log messages without republishing or acknowledging them.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of messages to process (default: drain all).",
    )
    args = parser.parse_args()

    url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

    try:
        asyncio.run(redrive(url=url, limit=args.limit, dry_run=args.dry_run))
    except KeyboardInterrupt:
        logger.info("Interrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()

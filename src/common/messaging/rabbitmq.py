"""Async RabbitMQ publisher and consumer utilities.

Uses ``aio-pika`` for async AMQP communication.

Publisher
---------
``RabbitMQPublisher`` publishes individual ``ActivitySignal`` Pydantic models as
persistent JSON messages to a topic exchange.  Batching is intentionally NOT
supported (per spec) to keep payloads small and broker throughput high.

Consumer
--------
``RabbitMQConsumer`` is an async generator that yields ``(ActivitySignal, message)``
tuples from a named queue.  The caller is responsible for:
  - Setting ``ingestion_time`` on the signal via ``signal.with_ingestion_time()``.
  - Acknowledging (``await message.ack()``) on success.
  - Nacking (``await message.nack(requeue=False)``) on validation failure or
    processing error so the message routes to the Dead Letter Queue (DLQ).

Example usage::

    async with RabbitMQPublisher(settings.RABBITMQ_URL, exchange="activity_signals") as pub:
        await pub.publish(signal)

    consumer = RabbitMQConsumer(settings.RABBITMQ_URL, queue="github_pullrequest_queue")
    async for signal, message in consumer.consume():
        signal = signal.with_ingestion_time()
        try:
            await process(signal)
            await message.ack()
        except Exception:
            await message.nack(requeue=False)
"""

from __future__ import annotations

import json
from types import TracebackType
from typing import AsyncGenerator, Optional, Type

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractIncomingMessage

from common.activity_signal.models import ActivitySignal

from common.logger import logger

_DEFAULT_EXCHANGE = "activity_signals"


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------


class RabbitMQPublisher:
    """Async context manager that publishes ActivitySignal events to RabbitMQ.

    Args:
        url: AMQP connection URL (e.g. ``amqp://guest:guest@localhost:5672/``).
        exchange: Name of the topic exchange.  Defaults to ``activity_signals``.
    """

    def __init__(self, url: str, exchange: str = _DEFAULT_EXCHANGE) -> None:
        self._url = url
        self._exchange_name = exchange
        self._connection: Optional[AbstractConnection] = None
        self._channel: Optional[AbstractChannel] = None

    async def __aenter__(self) -> "RabbitMQPublisher":
        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        # Declare the exchange (idempotent — safe to call even if it exists).
        await self._channel.declare_exchange(
            self._exchange_name,
            ExchangeType.TOPIC,
            durable=True,
        )
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()

    async def _ensure_channel(self) -> None:
        """Recreate the channel if it has been closed (e.g. after a heartbeat timeout)."""
        if self._connection is None or self._connection.is_closed:
            logger.warning("RabbitMQ connection lost — reconnecting...")
            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = None

        if self._channel is None or self._channel.is_closed:
            logger.warning("RabbitMQ channel closed — reopening...")
            self._channel = await self._connection.channel()
            await self._channel.declare_exchange(
                self._exchange_name,
                ExchangeType.TOPIC,
                durable=True,
            )

    async def publish(self, signal: ActivitySignal) -> None:
        """Publish a single ActivitySignal to the exchange.

        The routing key is derived from the signal itself:
        ``<source>.<entity_type>`` (e.g. ``github.PullRequest``).

        The message is marked as *persistent* (``delivery_mode=PERSISTENT``)
        so it survives broker restarts.

        Args:
            signal: The ActivitySignal to publish.  ``ingestion_time`` should
                be ``None`` (producer convention).

        Raises:
            RuntimeError: If called outside the async context manager.
        """
        if self._connection is None:
            raise RuntimeError(
                "RabbitMQPublisher must be used as an async context manager."
            )

        await self._ensure_channel()

        if self._channel is None:
            raise RuntimeError(
                "RabbitMQPublisher failed to initialize a channel for publishing."
            )

        exchange = await self._channel.get_exchange(self._exchange_name)
        body = signal.model_dump_json(exclude_none=False).encode()
        message = Message(
            body=body,
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        await exchange.publish(message, routing_key=f"{signal.source}.{signal.entity_type}")
        logger.debug(
            "Published signal signal_id=%s routing_key=%s",
            signal.signal_id,
            f"{signal.source}.{signal.entity_type}",
        )


# ---------------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------------


class RabbitMQConsumer:
    """Async generator consumer for a single RabbitMQ queue.

    Yields ``(ActivitySignal, message)`` tuples.  The caller must ack/nack
    each message to maintain proper flow control.

    Invalid messages (Pydantic validation failures) are automatically nacked
    with ``requeue=False`` so they route to the Dead Letter Queue (DLQ).

    Args:
        url: AMQP connection URL.
        queue: Name of the queue to consume from.
        prefetch_count: Number of unacknowledged messages to hold in-flight.
            Defaults to 1 for simple sequential processing.
    """

    def __init__(
        self, url: str, queue: str, prefetch_count: int = 1
    ) -> None:
        self._url = url
        self._queue_name = queue
        self._prefetch_count = prefetch_count

    async def consume(
        self,
    ) -> AsyncGenerator[tuple[ActivitySignal, AbstractIncomingMessage], None]:
        """Async generator yielding ``(ActivitySignal, raw_message)`` pairs.

        The consumer connects, sets QoS, and listens indefinitely.  Stop
        iteration by breaking from the loop or cancelling the enclosing task.

        Yields:
            Tuples of ``(ActivitySignal, aio_pika.IncomingMessage)``.

        Example::

            consumer = RabbitMQConsumer(url, "github_pullrequest_queue")
            async for signal, msg in consumer.consume():
                signal = signal.with_ingestion_time()
                await process(signal)
                await msg.ack()
        """
        connection: AbstractConnection = await aio_pika.connect_robust(self._url)
        try:
            channel: AbstractChannel = await connection.channel()
            await channel.set_qos(prefetch_count=self._prefetch_count)

            queue = await channel.declare_queue(self._queue_name, passive=True)

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    signal = await self._parse_message(message)
                    if signal is None:
                        # Validation failed; already nacked inside _parse_message.
                        continue
                    yield signal, message
        finally:
            if not connection.is_closed:
                await connection.close()

    @staticmethod
    async def _parse_message(
        message: AbstractIncomingMessage,
    ) -> Optional[ActivitySignal]:
        """Attempt to parse an incoming message as an ActivitySignal.

        Returns the model on success, or ``None`` after nacking on failure.
        """
        try:
            payload = json.loads(message.body)
            return ActivitySignal.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to parse ActivitySignal — routing to DLQ. error=%s body=%r",
                exc,
                message.body[:200],
            )
            await message.nack(requeue=False)
            return None

"""Async RabbitMQ listener for the command-and-control exchange.

Yields ``(CommandEnvelope, aio_pika.IncomingMessage)`` tuples from a
container-specific queue bound to the ``command_n_control`` topic exchange.

Usage::

    listener = CommandListener("amqp://guest:guest@localhost:5672/", "github-producer")
    async for envelope, message in listener.listen():
        try:
            await handle(envelope)
            await message.ack()
        except Exception:
            await message.nack(requeue=False)
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Optional

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractChannel, AbstractConnection, AbstractIncomingMessage

from common.command_n_control.models import CommandEnvelope
from common.logger import logger

_EXCHANGE_NAME = "command_n_control"
_DLX_NAME = "command_n_control_dlx"
_DLQ_NAME = "command_n_control_dlq"


class CommandListener:
    """Async generator that yields ``(CommandEnvelope, raw_message)`` pairs.

    The listener connects, declares the topology, sets QoS, and listens
    indefinitely.  Stop iteration by breaking from the loop or cancelling the
    enclosing task.

    Args:
        rabbitmq_url: AMQP connection URL.
        container_name: Name of the container/daemon (e.g. ``"github-producer"``).
            The queue is named ``cnc.<container_name>``.
        prefetch_count: Number of unacknowledged messages to hold in-flight.
            Defaults to 1 for simple sequential processing.
    """

    def __init__(
        self,
        rabbitmq_url: str,
        container_name: str,
        prefetch_count: int = 1,
    ) -> None:
        self._url = rabbitmq_url
        self._container_name = container_name
        self._queue_name = f"cnc.{container_name}"
        self._prefetch_count = prefetch_count

    @staticmethod
    async def declare_topology(channel: AbstractChannel) -> None:
        """Declare the exchange, DLX, DLQ, and binding.

        Idempotent — safe to call even if the objects already exist.

        Args:
            channel: An open aio_pika channel.
        """
        # Main exchange
        await channel.declare_exchange(
            _EXCHANGE_NAME,
            ExchangeType.TOPIC,
            durable=True,
        )

        # Dead-letter exchange
        dlx = await channel.declare_exchange(
            _DLX_NAME,
            ExchangeType.DIRECT,
            durable=True,
        )

        # Dead-letter queue
        dlq = await channel.declare_queue(
            _DLQ_NAME,
            durable=True,
        )
        await dlq.bind(dlx, routing_key=_DLQ_NAME)

    async def listen(
        self,
    ) -> AsyncGenerator[tuple[CommandEnvelope, AbstractIncomingMessage], None]:
        """Async generator yielding ``(CommandEnvelope, raw_message)`` pairs.

        Yields:
            Tuples of ``(CommandEnvelope, aio_pika.IncomingMessage)``.

        The caller **must** ack or nack each message to maintain flow control.
        Invalid messages (JSON parse failures, Pydantic validation errors) are
        automatically nacked with ``requeue=False`` so they route to the DLQ.
        """
        connection: AbstractConnection = await aio_pika.connect_robust(self._url)
        try:
            channel: AbstractChannel = await connection.channel()
            await channel.set_qos(prefetch_count=self._prefetch_count)

            # Declare topology (idempotent).
            await self.declare_topology(channel)

            # Declare and bind this container's queue.
            queue = await channel.declare_queue(
                self._queue_name,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": _DLX_NAME,
                    "x-dead-letter-routing-key": _DLQ_NAME,
                },
            )
            routing_key = f"command_n_control.{self._container_name}"
            await queue.bind(
                exchange=_EXCHANGE_NAME,
                routing_key=routing_key,
            )

            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    envelope = await self._parse_message(message)
                    if envelope is None:
                        # Validation failed; already nacked inside _parse_message.
                        continue
                    yield envelope, message
        finally:
            if not connection.is_closed:
                await connection.close()

    @staticmethod
    async def _parse_message(
        message: AbstractIncomingMessage,
    ) -> Optional[CommandEnvelope]:
        """Attempt to parse an incoming message as a CommandEnvelope.

        Returns the model on success, or ``None`` after nacking on failure.
        """
        try:
            payload = json.loads(message.body)
            return CommandEnvelope.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to parse CommandEnvelope — routing to DLQ. error=%s body=%r",
                exc,
                message.body[:200],
            )
            await message.nack(requeue=False)
            return None
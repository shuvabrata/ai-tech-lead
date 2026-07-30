"""Async RabbitMQ publisher for the command-and-control exchange.

Publishes ``CommandEnvelope`` Pydantic models as persistent JSON messages
to the ``command_n_control`` topic exchange.

Usage::

    async with CommandPublisher("amqp://guest:guest@localhost:5672/") as pub:
        envelope = CommandEnvelope(
            command_id=uuid4(),
            command_type="scan",
            target="github-producer",
            parameters={"force_full": True},
            issued_at=datetime.now(timezone.utc),
        )
        await pub.publish(envelope)
"""

from __future__ import annotations

from types import TracebackType
from typing import Optional, Type

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractChannel, AbstractConnection

from common.command_n_control.models import CommandEnvelope
from common.logger import logger

_EXCHANGE_NAME = "command_n_control"


class CommandPublisher:
    """Async context manager that publishes CommandEnvelope messages to RabbitMQ.

    Args:
        url: AMQP connection URL (e.g. ``amqp://guest:guest@localhost:5672/``).
        exchange: Name of the topic exchange.  Defaults to ``command_n_control``.
        known_targets: Optional list of all known routing-key targets.  Used
            when ``target == "*"`` to broadcast to every known container.
    """

    def __init__(
        self,
        url: str,
        exchange: str = _EXCHANGE_NAME,
        known_targets: Optional[list[str]] = None,
    ) -> None:
        self._url = url
        self._exchange_name = exchange
        self._known_targets = known_targets or []
        self._connection: Optional[AbstractConnection] = None
        self._channel: Optional[AbstractChannel] = None

    async def __aenter__(self) -> "CommandPublisher":
        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
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

    async def publish(self, envelope: CommandEnvelope) -> None:
        """Publish a single CommandEnvelope to the exchange.

        The routing key is ``command_n_control.<target>``.  When ``target`` is
        ``"*"``, one message is published per known target.

        The message is marked as *persistent* (``delivery_mode=PERSISTENT``)
        so it survives broker restarts.

        Args:
            envelope: The command envelope to publish.

        Raises:
            RuntimeError: If called outside the async context manager.
        """
        if self._connection is None:
            raise RuntimeError(
                "CommandPublisher must be used as an async context manager."
            )

        await self._ensure_channel()

        if self._channel is None:
            raise RuntimeError(
                "CommandPublisher failed to initialize a channel for publishing."
            )

        exchange = await self._channel.get_exchange(self._exchange_name)
        body = envelope.model_dump_json().encode()
        message = Message(
            body=body,
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
        )

        targets = self._known_targets if envelope.target == "*" else [envelope.target]

        for target in targets:
            routing_key = f"command_n_control.{target}"
            await exchange.publish(message, routing_key=routing_key)
            logger.debug(
                "Published command command_id=%s routing_key=%s",
                envelope.command_id,
                routing_key,
            )
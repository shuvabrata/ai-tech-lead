from __future__ import annotations

from typing import Awaitable, Callable, Dict, Optional

from common.activity_signal.models import ActivitySignal
from common.messaging.rabbitmq import RabbitMQPublisher
from common.logger import logger


def make_pub_callback(
    publisher: RabbitMQPublisher,
    published: Dict[str, int],
) -> Callable[[Optional[ActivitySignal]], Awaitable[None]]:
    """Return an async publish callback that wraps *publisher* and *published*.

    The returned coroutine:
    - Skips ``None`` signals silently.
    - Publishes the signal to RabbitMQ via *publisher*.
    - Logs each published signal at INFO level.
    - Increments the *published* counter keyed by ``entity_type``.
    """

    async def _pub(sig: Optional[ActivitySignal]) -> None:
        if sig:
            await publisher.publish(sig)
            logger.info(
                "Published signal_id=%s entity_type=%s external_id=%s routing_key=%s",
                sig.signal_id,
                sig.entity_type,
                sig.external_id,
                sig.routing_key,
            )
            published[sig.entity_type] = published.get(sig.entity_type, 0) + 1

    return _pub

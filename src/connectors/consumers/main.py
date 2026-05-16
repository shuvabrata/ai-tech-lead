"""ActivitySignal consumer entry point.

Reads the ``LISTEN_QUEUES`` environment variable (comma-separated queue names)
and starts one async consumer task per queue.  All tasks run concurrently via
``asyncio.gather``.

Environment variables
---------------------
LISTEN_QUEUES   Comma-separated list of RabbitMQ queue names to consume.
                e.g. ``github_repository_queue,github_branch_queue``
RABBITMQ_URL    AMQP connection URL (default: ``amqp://guest:guest@localhost:5672/``)
NEO4J_URI       Neo4j Bolt URI (default: ``bolt://localhost:7687``)
NEO4J_USERNAME  Neo4j username (default: ``neo4j``)
NEO4J_PASSWORD  Neo4j password (default: ``password``)

Deployment
----------
Run directly::

    PYTHONPATH=/app python connectors/consumers/main.py

Or in Docker::

    docker compose run github-consumer

Horizontal scaling: start multiple container instances — RabbitMQ will
automatically round-robin messages across all running consumers.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from neo4j import GraphDatabase

from common.messaging.rabbitmq import RabbitMQConsumer
from connectors.commons.person_cache import PersonCache
from connectors.consumers.sinks.neo4j_sink import upsert_signal
from app.common.logger import logger


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _sync_upsert(driver: Any, signal: Any, person_cache: PersonCache) -> None:
    """Execute the synchronous Neo4j upsert blocking operations safely in a thread."""
    with driver.session() as session:
        upsert_signal(session, signal, person_cache=person_cache)


async def consume_queue(
    queue_name: str,
    rabbitmq_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> None:
    """Consume all messages from *queue_name* and upsert them into Neo4j.

    Each message is processed synchronously inside a Neo4j session so that
    ack/nack happens only after the write completes.  The Neo4j driver is
    opened once per queue task and reused for all messages.

    Args:
        queue_name:     RabbitMQ queue to listen on.
        rabbitmq_url:   AMQP connection URL.
        neo4j_uri:      Bolt URI for Neo4j.
        neo4j_user:     Neo4j username.
        neo4j_password: Neo4j password.
    """
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    logger.info("Consumer started: queue=%s", queue_name)

    try:
        consumer = RabbitMQConsumer(rabbitmq_url, queue=queue_name)
        person_cache = PersonCache()
        async for signal, message in consumer.consume():
            signal = signal.with_ingestion_time()
            try:
                await asyncio.to_thread(_sync_upsert, driver, signal, person_cache)
                await message.ack()
                logger.info(
                    "Processed signal_id=%s entity_type=%s id=%s queue=%s",
                    signal.signal_id,
                    signal.entity_type,
                    signal.external_id,
                    queue_name,
                )
            except Exception as exc:
                logger.error(
                    "Failed to upsert signal_id=%s: %s — nacking to DLQ",
                    signal.signal_id,
                    exc,
                    exc_info=True,
                )
                await message.nack(requeue=False)
    finally:
        driver.close()
        logger.info("Consumer stopped: queue=%s", queue_name)


async def main() -> None:
    """Parse configuration and launch one consumer task per queue."""
    listen_queues_raw = _env("LISTEN_QUEUES", "")
    if not listen_queues_raw.strip():
        logger.error(
            "LISTEN_QUEUES env var is not set or empty. "
            "Provide a comma-separated list of queue names."
        )
        sys.exit(1)

    queues = [q.strip() for q in listen_queues_raw.split(",") if q.strip()]
    logger.info("Starting consumers for queues: %s", queues)

    rabbitmq_url = _env("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    neo4j_uri = _env("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user = _env("NEO4J_USERNAME", "neo4j")
    neo4j_password = _env("NEO4J_PASSWORD", "password")

    tasks = [
        consume_queue(q, rabbitmq_url, neo4j_uri, neo4j_user, neo4j_password)
        for q in queues
    ]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    # Process-level restart control is handled by docker-compose restart policy.
    asyncio.run(main())

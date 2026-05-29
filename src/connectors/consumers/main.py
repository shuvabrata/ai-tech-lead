"""ActivitySignal consumer entry point.

Reads the ``LISTEN_QUEUES`` environment variable (comma-separated queue names)
and starts one async consumer task per queue.  All tasks run concurrently via
``asyncio.gather``.

Environment variables
---------------------
LISTEN_QUEUES        Comma-separated list of RabbitMQ queue names to consume.
                     e.g. ``github_repository_queue,github_pullrequest_queue``
RABBITMQ_URL         AMQP connection URL (default: ``amqp://guest:guest@localhost:5672/``)
NEO4J_URI            Neo4j Bolt URI (default: ``bolt://localhost:7687``)
NEO4J_USERNAME       Neo4j username (default: ``neo4j``)
NEO4J_PASSWORD       Neo4j password (default: ``password``)
ELASTICSEARCH_ENABLED  Set to ``true`` to enable the Elasticsearch sink.
ELASTICSEARCH_URL    Elasticsearch base URL (default: ``http://localhost:9200``)
ELASTIC_PASSWORD     Elasticsearch password (leave empty when security is off).

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
import contextlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from common.messaging.rabbitmq import RabbitMQConsumer
from connectors.commons.person_cache import PersonCache
from connectors.consumers.sinks.neo4j_sink import upsert_signal
from connectors.consumers.sinks.elasticsearch_sink import (
    build_es_client,
    index_signal_with_canonical_id,
)
from common.logger import logger


def _signal_dump_path(queue_name: str) -> Path:
    """Return the JSONL path for this queue's session, creating the directory if needed.

    Uses LOG_DIR env var (set by docker-compose to the mounted log volume, e.g.
    /var/log/github-consumer) so that dumps are visible on the host under logs/signals/.
    Falls back to 'logs' for local development.
    """
    log_dir = os.environ.get("LOG_DIR", "logs")
    dump_dir = Path(log_dir) / "signals"
    dump_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return dump_dir / f"{queue_name}_{ts}.jsonl"


def _dump_signal(f: Any, signal: Any) -> None:
    """Append one signal as a JSON line to an open file handle."""
    try:
        line = signal.model_dump_json()
    except AttributeError:
        line = json.dumps(signal.dict(), default=str)
    f.write(line + "\n")
    f.flush()


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _sync_upsert(driver: Any, signal: Any, person_cache: PersonCache) -> str:
    """Execute the synchronous Neo4j upsert and return the canonical wba_id.

    The canonical wba_id may differ from ``wba_node_id(signal)`` when
    cross-provider Person dedup occurs (see ``neo4j_sink.upsert_signal``).
    The caller must pass this value to ``_sync_es_index`` so the ES sink
    can index under the correct id.
    """
    with driver.session() as session:
        return upsert_signal(session, signal, person_cache=person_cache)


def _sync_es_index(es_client: Any, signal: Any, canonical_wba_id: str) -> None:
    """Index *signal* into Elasticsearch using the canonical wba_id from Neo4j.

    Delegates to ``index_signal_with_canonical_id`` which handles the
    cross-provider Person dedup case transparently.
    """
    index_signal_with_canonical_id(es_client, signal, canonical_wba_id)


async def consume_queue(
    queue_name: str,
    rabbitmq_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> None:
    """Consume all messages from *queue_name* and upsert them into Neo4j and Elasticsearch.

    Each message is processed synchronously inside a Neo4j session so that
    ack/nack happens only after the write completes.  The Neo4j driver is
    opened once per queue task and reused for all messages.

    The Elasticsearch write is non-fatal: failures are logged at WARNING level
    and do not cause the message to be nacked.

    Args:
        queue_name:     RabbitMQ queue to listen on.
        rabbitmq_url:   AMQP connection URL.
        neo4j_uri:      Bolt URI for Neo4j.
        neo4j_user:     Neo4j username.
        neo4j_password: Neo4j password.
    """
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    es_client = build_es_client()
    if es_client is not None:
        logger.info("Elasticsearch sink enabled for queue=%s", queue_name)
    else:
        logger.info("Elasticsearch sink disabled for queue=%s", queue_name)
    signal_dumps_enabled = os.environ.get("LOG_SIGNAL_DUMPS", "").strip().lower() in ("1", "true", "yes")
    dump_path = _signal_dump_path(queue_name) if signal_dumps_enabled else None
    if dump_path:
        logger.info(f"Signal dumps enabled and will dump at: {dump_path}")
    logger.info(
        "Consumer started: queue=%s  signal_dump=%s",
        queue_name,
        dump_path if signal_dumps_enabled else "disabled",
    )

    def _open_dump():
        return dump_path.open("w", encoding="utf-8") if signal_dumps_enabled else contextlib.nullcontext()

    try:
        consumer = RabbitMQConsumer(rabbitmq_url, queue=queue_name)
        person_cache = PersonCache()
        with _open_dump() as dump_file:
            async for signal, message in consumer.consume():
                signal = signal.with_ingestion_time()
                if signal_dumps_enabled:
                    _dump_signal(dump_file, signal)
                try:
                    canonical_wba_id = await asyncio.to_thread(_sync_upsert, driver, signal, person_cache)
                    await message.ack()
                    logger.info(
                        "Upserted to neo4j signal_id=%s entity_type=%s id=%s queue=%s",
                        signal.signal_id,
                        signal.entity_type,
                        signal.id,
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
                    continue

                # Elasticsearch write — non-fatal; never nack on ES failure.
                # canonical_wba_id is passed so the sink can detect and handle
                # cross-provider Person dedup (signal wba_id != Neo4j node id).
                if es_client is not None:
                    try:
                        await asyncio.to_thread(_sync_es_index, es_client, signal, canonical_wba_id)
                        logger.info(f"Indexed to Elasticsearch signal_id={signal.signal_id} queue={queue_name}")
                    except Exception as es_exc:  # pylint: disable=broad-except
                        logger.warning(
                            "Elasticsearch index failed for wba_id=%s::%s::%s — %s",
                            signal.source,
                            signal.entity_type,
                            signal.id,
                            es_exc,
                        )
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

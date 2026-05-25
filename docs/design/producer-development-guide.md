# ActivitySignal Producer Development Guide

> **Certification checklist** for building a new ActivitySignal producer from scratch.
> A producer is a one-shot service that fetches data from a source system (GitHub, Jira,
> Confluence, Slack, etc.) and publishes `ActivitySignal` events to RabbitMQ.
>
> **Reference implementations:**
> - `src/connectors/producers/github/` (multi-file, one builder per entity)
> - `src/connectors/producers/jira_producer.py` (single-file producer)

---

## How to use this checklist

Work through each phase in order. Mark items `[x]` as you go.
Do not skip phases — later phases depend on earlier ones.

---

## Phase 1 — Pre-flight: Understand the Contract

- [ ] Read `src/common/activity_signal/models.py` — the single source of truth for the schema
- [ ] Understand the canonical identity tuple: `(source, entity_type, id)`
- [ ] Understand the WBA canonical key: `{source}::{entity_type}::{id}`
  (stored as the `id` property on every Neo4j node)
- [ ] Understand `wba_format(source, entity_type, raw_id)` in `src/common/activity_signal/wba_node_id.py`
  — this is used **in the consumer**, not the producer; the producer sets `id=<raw_id>` only
- [ ] Confirm your entity types are in `SUPPORTED_ENTITY_TYPES` in `models.py`
  — if not, add them before writing any producers
- [ ] Confirm your relationship types are in `SUPPORTED_RELATIONSHIP_TYPES`
  — if not, add them before writing any signal builders
- [ ] Read `docs/design/spec-activity-signal.md` for the full schema reference

---

## Phase 2 — Constants Module

Create `src/connectors/producers/<source>/constants.py`.
Copy the GitHub pattern at `src/connectors/producers/github/constants.py`.

```python
import os
from typing import Any

_SOURCE = "<your-source>"   # e.g. "slack", "confluence" — lowercase, no spaces
_VERSION = "1.0"
_TEXT_MAX = 2000


def _connector_url() -> str:
    api_server = os.environ.get("API_SERVER", "http://localhost:8000")
    return f"{api_server.rstrip('/')}/connectors/<source>"


def _truncate(value: Any) -> str:
    """Truncate free-text fields to prevent oversized signals."""
    return str(value)[:_TEXT_MAX]
```

Checklist:
- [ ] `_SOURCE` is lowercase with no spaces (must match what the consumer expects in node IDs)
- [ ] `_connector_url()` reads `API_SERVER` from env with a localhost fallback
- [ ] `_truncate()` is imported and used for all free-text fields (summary, title, message, description)

---

## Phase 3 — Fetch Layer

Create `src/connectors/producers/fetch_<source>.py`.

- [ ] Each function fetches one entity type from the source API and returns raw dicts (no Pydantic yet)
- [ ] Pagination is handled inside the fetch function — callers receive a flat list
- [ ] Authentication credentials come from environment variables (never hardcoded)
- [ ] Network errors are raised, not silently swallowed — the caller handles them
- [ ] Use `from common.logger import logger` — never `print()`

---

## Phase 4 — Map Layer

Create `src/connectors/producers/map_<source>.py`.

- [ ] Each `map_<entity>()` function takes a raw API dict and returns a normalised dict
- [ ] Field names are consistent where possible: `created_at`, `updated_at`, `url`, `name`, `id`
- [ ] IDs are extracted and returned as plain strings (not prefixed, not formatted with `wba_format`)
- [ ] No Pydantic construction here — that happens in signal builders

---

## Phase 5 — Signal Builders

Create one `build_<entity>_signal()` function per entity type.
Reference: `src/connectors/producers/github/build_commit_signal.py`.

### The two most critical rules

**Rule 1 — `id` is the raw identifier, never the WBA key:**

```python
# CORRECT
ActivitySignal(source=_SOURCE, id="org/my-repo", ...)           # Repository
ActivitySignal(source=_SOURCE, id="my-repo::main", ...)         # Branch
ActivitySignal(source=_SOURCE, id="my-repo::42", ...)           # PullRequest
ActivitySignal(source=_SOURCE, id="alice", ...)                  # Person (GitHub login)
ActivitySignal(source=_SOURCE, id="557058:abc123", ...)          # Person (Jira account_id)
ActivitySignal(source=_SOURCE, id="AB-42", ...)                  # Issue/Epic/Initiative

# WRONG — do not pass wba_format() output as the id
ActivitySignal(source=_SOURCE, id=wba_format(_SOURCE, "Person", "alice"), ...)
```

**Rule 2 — `RelationshipTarget.id` follows the same raw-id rule:**

```python
# CORRECT — raw id on RelationshipTarget
RelationshipTarget(source="jira", entity_type="Issue", id="AB-42")
RelationshipTarget(source="github", entity_type="Person", id="alice")

# WRONG — full canonical key on RelationshipTarget
RelationshipTarget(source="github", entity_type="Person", id="github::Person::alice")
```

### Direction

```python
# Default: direction=None (undirected edge, stored once, queryable from either end)
Relationship(type="ASSIGNED_TO", direction=None, target=...)

# Use direction="OUT" only when edge direction is semantically required
Relationship(type="TARGETS", direction="OUT", target=...)   # PR → base branch
```

### Error handling

Every signal builder must follow this pattern:

```python
def build_<entity>_signal(data: Dict[str, Any], ...) -> Optional[ActivitySignal]:
    try:
        attrs = <Entity>Attributes(
            required_field=data["required_field"],
            optional_field=data.get("optional_field"),
        )
        return ActivitySignal(
            source=_SOURCE,
            id=data["<raw_id_field>"],
            source_config=...,
            connector_url=_connector_url(),
            event_time=...,
            version=_VERSION,
            attributes=attrs,
            relationships=[...],
        )
    except Exception as exc:
        logger.warning(
            "Skipping <Entity> signal for '%s' (validation error): %s",
            data.get("<id_field>"), exc,
        )
        return None
```

### Checklist per entity type

For **each** entity type your producer covers:

- [ ] `*Attributes` model is instantiated with all required fields (those without `Optional`)
- [ ] All mandatory `str` fields are non-empty — use `or ""` / `or "Unknown"` as fallbacks
- [ ] Free-text fields (summary, title, message, description) pass through `_truncate()`
- [ ] `event_time` is a timezone-aware `datetime` in UTC:
  `datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)` or `datetime.now(timezone.utc)`
- [ ] All relationship types used are in `SUPPORTED_RELATIONSHIP_TYPES`
- [ ] `direction=None` for symmetric relationships; `direction="OUT"` only when required
- [ ] Function is wrapped in `try/except` with `logger.warning` and `return None`

---

## Phase 6 — Publisher Wiring

Create the `publish_signals()` async function that orchestrates all builders.

```python
async def publish_signals(
    publisher: RabbitMQPublisher,
    ...,
) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for entity_data in await fetch_<entities>():
        signal = build_<entity>_signal(entity_data)
        if signal is None:
            continue                         # builder logged the error; skip
        publisher.publish(signal)
        counts[signal.entity_type] = counts.get(signal.entity_type, 0) + 1

    return counts
```

- [ ] `None` returns from builders are skipped without crashing the publish loop
- [ ] Publishes via `RabbitMQPublisher` from `common.messaging.rabbitmq`
- [ ] Logs signal count per entity type at the end
- [ ] Returns `Dict[str, int]` of `entity_type → count`

---

## Phase 7 — Sync Cursor (Incremental Sync)

The sync cursor persists the last successful sync timestamp to avoid redundant API calls.

```python
from connectors.producers.sync_cursor import get_sync_cursor, set_sync_cursor

# At startup
cursor = await get_sync_cursor(source=_SOURCE, resource_id=<jira_base_url_or_repo>)
last_synced_at = cursor.last_synced_at if cursor else None

# Pass to fetch functions
entities = await fetch_<entities>(since=last_synced_at)

# On success only
await set_sync_cursor(source=_SOURCE, resource_id=<id>, last_synced_at=datetime.now(timezone.utc))
```

- [ ] `get_sync_cursor()` called at startup; `last_synced_at=None` triggers a full sync
- [ ] `last_synced_at` passed to fetch functions to request only new/updated records
- [ ] `set_sync_cursor()` called only on success — failure leaves the cursor unchanged for retry
- [ ] `resource_id` uniquely identifies the source instance (e.g. the Jira base URL, repo full name)

---

## Phase 8 — Entry Point

```python
async def main() -> None:
    # Load config from environment
    # Open connections (DB, RabbitMQ)
    # Run publish_signals()
    # Close connections

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] All config from environment variables — use `os.environ.get()` with sensible defaults
- [ ] Connections are closed in a `finally` block even on failure
- [ ] Startup failures are logged with `logger.error` before the process exits non-zero

---

## Phase 9 — Dockerfile

Create `Dockerfile.<source>-producer`. Copy `Dockerfile.github-producer` and adjust:

- [ ] `CMD` points to `connectors/producers/<source>_producer.py`
- [ ] `PYTHONPATH=/app/src` is set (via `ENV` or in the `CMD`)
- [ ] Base image and Python version match the other producer Dockerfiles

---

## Phase 10 — docker-compose Registration

Add to `docker-compose.yml`:

```yaml
<source>-producer:
  build:
    context: .
    dockerfile: Dockerfile.<source>-producer
  restart: "no"
  environment:
    PYTHONPATH: /app/src
    API_SERVER: http://app:8000
    RABBITMQ_URL: amqp://guest:guest@rabbitmq:5672/
    # source-specific credentials from .env
  depends_on:
    - rabbitmq
    - postgres
  env_file:
    - .env
```

- [ ] `restart: "no"` — one-shot service, run manually via `docker compose run --rm`
- [ ] `PYTHONPATH: /app/src` set in environment
- [ ] Correct `depends_on` entries (rabbitmq; postgres if sync cursor is used)
- [ ] Credentials sourced from `.env` via `env_file`

---

## Phase 11 — Tests

Create `tests/test_<source>_producer.py`. Reference: `tests/test_github_producer_phase4.py`.

Mark all test functions with `@pytest.mark.unit`.

```python
@pytest.mark.unit
def test_build_<entity>_signal_happy_path():
    signal = build_<entity>_signal(valid_data)
    assert signal is not None
    assert signal.id == "<expected_raw_id>"
    assert signal.entity_type == "<EntityType>"
    assert signal.source == "<source>"
    assert len(signal.relationships) == <expected_count>
    assert signal.relationships[0].type == "<REL_TYPE>"
    assert signal.relationships[0].target.id == "<expected_target_raw_id>"
    assert signal.relationships[0].target.entity_type == "<TargetType>"

@pytest.mark.unit
def test_build_<entity>_signal_returns_none_on_invalid_data():
    signal = build_<entity>_signal({})   # missing required fields
    assert signal is None
```

- [ ] One test per signal builder (happy path + invalid-data path)
- [ ] Assert `signal.id` is the **raw** identifier, not the WBA canonical key
- [ ] `pytest -m unit tests -q` passes with no failures

---

## Phase 12 — End-to-End Verification

- [ ] `docker compose run --rm <source>-producer` exits with code 0
- [ ] Log output shows expected signal counts per entity type
- [ ] Open Neo4j Browser and verify canonical node IDs:
  ```cypher
  MATCH (n) WHERE n.id STARTS WITH '<source>::' RETURN n.id LIMIT 20
  ```
  All IDs must be in `{source}::{EntityType}::{raw_id}` format.
- [ ] Verify no old-format IDs exist:
  ```cypher
  MATCH (n) WHERE n.id =~ '<source>_[a-z]+_.*' RETURN count(n)
  ```
  Result must be **0**.
- [ ] If `Person` entities: verify cross-source merge:
  ```cypher
  MATCH (p:Person)-[:MAPS_TO]-(i:IdentityMapping)
  WITH p, collect(i.id) AS ids WHERE size(ids) > 1
  RETURN p.id, ids LIMIT 5
  ```

---

*Last updated: 2026-05-20*

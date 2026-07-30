# Plan 010: Command-and-Control Scan Triggering via RabbitMQ

> **Executor instructions**: This plan is structured in sequential phases. Each phase
> has its own implementation checklist, automated test requirements, and manual
> verification steps. Complete phases in order — later phases depend on earlier ones.
> Mark each task `[ ]` → `[x]` as you complete them. Update the status table at the
> top when wrapping up each phase.

> **Reference documents**: During implementation, always consult the following
> documents for project conventions, patterns, and design constraints:
> - [`.github/copilot-instructions.md`](../.github/copilot-instructions.md) —
>   project-wide rules (imports, code style, testing, architecture patterns)
> - [`docs/design/`](../docs/design/) — all design documents in this folder,
>   including the high-level design, design system, frontend design spec,
>   activity signal spec, producer/consumer development guides, RabbitMQ
>   topology, graph DB schema, relationship design, index strategy, and
>   GitHub API optimization notes. Refer to the relevant document(s) for
>   each phase (e.g. RabbitMQ design for Phases 1/5, producer guide for
>   Phase 4, graph DB docs for Neo4j-related checks).

---

## Status

| Phase | Title | Effort | Status |
|-------|-------|--------|--------|
| 1 | Shared library (`src/common/command_n_control/`) | M | DRAFT |
| 2 | Database model + migration | S | DRAFT |
| 3 | API endpoints (`/api/v1/commands/`) | M | DRAFT |
| 4 | Producer daemon conversion | L | DRAFT |
| 5 | RabbitMQ topology update | XS | DRAFT |
| 6 | Dash UI — Connectors detail page | M | DRAFT |
| 7 | Docker Compose + Dockerfiles | S | DRAFT |

---

## TL;DR

Convert the three one-shot producer containers (github-producer, jira-producer,
confluence-producer) into long-running daemons that listen on a
`command_n_control` topic exchange for generic commands. Add a `CommandStatus`
table in Postgres (via Alembic) and a `/api/v1/commands/` REST API on the app
to send commands and query status. The Dash Connectors detail page gets a "Run
Scan" button and a "Recent Scans" section. Producers update status via HTTP
callbacks to the app's API.

> **Note — Consumer unaffected**: The existing signal consumer
> (`src/connectors/consumers/`) listens on the `activity_signals` exchange and is
> completely unaffected by the new `command_n_control` exchange. No changes are
> needed in the consumer or Neo4j sync layer.

---

## Decisions Log (from design interview)

| # | Question | Decision |
|---|----------|----------|
| 1 | Producer lifecycle | Long-running daemons |
| 2 | Exchange name | `command_n_control` (generic command bus) |
| 3 | Routing key pattern | `command_n_control.<container_name>` — `container_name` is the *who*; `command_type` is the *what* in message body |
| 4 | Wildcard broadcast | Per-producer queue + routing key, app publishes separate message per target for `target: "*"` |
| 5 | Command schema | Loose JSON `parameters`, `command_id` as UUID correlation key, no `reply_to` queue |
| 6 | Status tracking | Postgres `command_status` table via SQLAlchemy (app reads) / HTTP PATCH (producers write) |
| 7 | Status lifecycle | `pending → accepted → queued → running → completed / failed` |
| 8 | "scan already running" | Accept + ack message → set status to `failed` with reason `"scan already in progress"` |
| 9 | Shared library location | `src/common/command_n_control/` |
| 10 | Config reload | Load once at daemon startup (config refresh deferred) |
| 11 | Status DB access from producers | HTTP PATCH to `/api/v1/commands/{id}/status` |
| 12 | Producer `main.py` rename | Existing `main.py` → `scan.py`, new `main.py` is daemon entry point |
| 13 | Container identity | `CONTAINER_NAME` env var, default = docker compose service name |
| 14 | Connector→producer mapping | `producer_container` field in `CONNECTOR_REGISTRY` |
| 15 | UI placement | "Run Scan" button + "Recent Scans" section on connector detail page |
| 16 | Graceful shutdown | SIGTERM → cancel scan task → mark status as `failed: "container shutting down"` |

---

## Phase 1: Shared Library (`src/common/command_n_control/`)

### What

Create the shared command-n-control package under `src/common/`. This is the
core abstraction used by both the app (to publish commands) and producers (to
listen for commands). It has no dependency on `src/app/` or `src/connectors/`.

### Files to create

#### `src/common/command_n_control/__init__.py`
```python
"""Generic RabbitMQ-based command-and-control bus.

Exchange topology (declared by ``src/app/scripts/init_rabbitmq.py``):

  exchange: command_n_control (topic, durable)
  dlx:      command_n_control_dlx  (direct, durable)
  dlq:      command_n_control_dlq  (durable classic queue bound to DLX)
  queues:   cnc.<container_name> — one per producer/daemon

Routing key convention:
  command_n_control.<container_name>
  e.g.  command_n_control.github-producer

Message format (CommandEnvelope):
  {
    "command_id": "uuid4",
    "command_type": "scan",
    "target": "github-producer",
    "parameters": {...},
    "issued_at": "2026-07-29T12:00:00Z"
  }
"""
```

#### `src/common/command_n_control/models.py`
- Pydantic model: `CommandEnvelope`
  - `command_id: UUID`
  - `command_type: str` — e.g. `"scan"`
  - `target: str` — container name e.g. `"github-producer"`, or `"*"`
  - `parameters: dict[str, Any] | None = None` — flexible per-command options
  - `issued_at: datetime` — UTC timestamp from the issuer
- Pydantic model: `CommandStatusUpdate`
  - `status: Literal["accepted", "queued", "running", "completed", "failed"]`
  - `error_message: str | None = None`
  - `started_at: datetime | None = None`
  - `completed_at: datetime | None = None`
  - `result_summary: dict | None = None` — e.g. `{"signals_published": 42}`

#### `src/common/command_n_control/publisher.py`
- Class: `CommandPublisher`
- Async context manager (`__aenter__` / `__aexit__`) — same pattern as `RabbitMQPublisher`
- **Relationship to `RabbitMQPublisher`**: This is a separate class (not a subclass or
  wrapper) because it uses a different exchange (`command_n_control` vs `activity_signals`)
  and a different routing key convention (`command_n_control.<target>` vs `<source>.<entity_type>`).
  However, the connection/channel management code is identical — consider extracting
  a shared base or simply duplicating the pattern (preferred for clarity, given the
  small amount of code involved).
- `async publish(command: CommandEnvelope)` — serializes to JSON, publishes to
  `command_n_control` exchange with routing key `command_n_control.<target>`
- If `target == "*"`, publishes one message per known routing key (list passed
  at construction or stored as class constant)
- Auto-reconnect via `_ensure_channel()` (same pattern as existing publisher)
- **Dependency**: `aio_pika` (already in all containers)

#### `src/common/command_n_control/listener.py`
- Class: `CommandListener`
- Constructor: `(rabbitmq_url: str, container_name: str)`
- `async listen()` — async generator yielding `(CommandEnvelope, AbstractIncomingMessage)`
  - Connects, declares queue `cnc.<container_name>` with binding
    `command_n_control.<container_name>`
  - Sets QoS prefetch=1
  - Invalid JSON / schema failures → nack with `requeue=False` → DLQ
- `async declare_topology(channel)` — static helper to declare exchange,
  DLX, DLQ, and the listening queue. Can also be called by `init_rabbitmq.py`
  for pre-declaration.
- Uses `passive=False` (creates queue if not exists) so producers can start
  even before `init_rabbitmq.py` runs

### Tests to write (unit, `@pytest.mark.unit`)

| Test | What it verifies |
|---|---|
| `test_command_envelope_serialization` | Round-trip: dict → model → json → model |
| `test_command_envelope_missing_fields` | Validation error on missing `command_id`, `command_type` |
| `test_command_status_update_model` | All status values accepted, unknown status rejected |
| `test_command_status_update_optional_fields` | `None` fields omitted from serialization |
| `test_publisher_publish_with_target` | Routing key = `command_n_control.github-producer` when target is set |
| `test_publisher_publish_wildcard` | Target `"*"` publishes to all known routing keys |
| `test_listener_declares_queue` | Queue name = `cnc.<container_name>`, binding = `command_n_control.<container_name>` |
| `test_listener_parse_valid_message` | Valid JSON yields `(CommandEnvelope, message)` |
| `test_listener_parse_invalid_message_nacks` | Invalid JSON nacks with `requeue=False` |

### Manual verification

1. Open a Python shell in the app container or locally:
   ```python
   from common.command_n_control.models import CommandEnvelope
   from common.command_n_control.publisher import CommandPublisher
   import asyncio, uuid
   async def test():
       async with CommandPublisher("amqp://guest:guest@localhost:5672/") as pub:
           env = CommandEnvelope(
               command_id=uuid.uuid4(),
               command_type="scan",
               target="test-container",
               parameters={"force_full": True},
               issued_at=datetime.now(timezone.utc),
           )
           await pub.publish(env)
   asyncio.run(test())
   ```
2. Verify the message appears in RabbitMQ management UI (`http://localhost:15672`)
   on the `command_n_control` exchange.
3. Verify the DLX/DLQ are visible in the management UI.

### Phase 1 progress

- [ ] `src/common/command_n_control/__init__.py` created
- [ ] `src/common/command_n_control/models.py` created
- [ ] `src/common/command_n_control/publisher.py` created
- [ ] `src/common/command_n_control/listener.py` created
- [ ] Unit tests written and passing: `pytest -m unit tests/ -q -k "command_n_control or command_envelope"`
- [ ] Manual verification: publish a command, verify in RabbitMQ UI
- [ ] `pylint src/common/command_n_control/` — no errors
- [ ] `mypy src/common/command_n_control/` — no errors

---

## Phase 2: Database Model + Migration

### What

Add the `command_status` table to Postgres via a new SQLAlchemy model and an
Alembic auto-generated migration.

### Files to create

#### `src/app/db/models/command_status.py`
```python
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Text, JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CommandStatus(Base):
    """Tracks the lifecycle of every command sent via the command_n_control exchange.

    Written by the app's API layer (``/api/v1/commands/``) when a command is
    created.  Updated by producer daemons via HTTP PATCH
    ``/api/v1/commands/{command_id}/status``.

    Status lifecycle::

        pending → accepted → queued → running → completed
                                               → failed
    """

    __tablename__ = "command_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    command_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, unique=True, nullable=False, index=True
    )
    command_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target: Mapped[str] = mapped_column(String(100), nullable=False)
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
```

### Files to modify

- `src/app/db/models/__init__.py` — add `from .command_status import CommandStatus`

### Migration

```bash
cd src/app && alembic revision --autogenerate -m "add command_status table"
cd src/app && alembic upgrade head
```

### Tests to write (unit, `@pytest.mark.unit`)

| Test | What it verifies |
|---|---|
| `test_command_status_model_create` | SQLAlchemy model can be instantiated with required fields |
| `test_command_status_default_status` | Default status is `"pending"` |
| `test_command_status_unique_command_id` | Duplicate `command_id` raises integrity error |
| `test_command_status_timestamps` | `created_at` is set, `started_at`/`completed_at` start as `None` |
| `test_command_status_status_values` | Model allows all valid status strings |
| `test_command_status_relationship` | Verify no broken relationships or FK constraints |

### Manual verification

1. Run migration: `cd src/app && alembic upgrade head`
2. Connect to Postgres and verify table:
   ```sql
   \d command_status
   SELECT * FROM command_status;
   ```
3. Verify the unique constraint on `command_id`:
   ```sql
   INSERT INTO command_status (command_id, command_type, target, created_at, status)
   VALUES ('00000000-0000-0000-0000-000000000001', 'scan', 'test', NOW(), 'pending');
   -- Second insert with same command_id should fail
   INSERT INTO command_status (command_id, command_type, target, created_at, status)
   VALUES ('00000000-0000-0000-0000-000000000001', 'scan', 'test', NOW(), 'pending');
   ```

### Phase 2 progress

- [ ] `src/app/db/models/command_status.py` created
- [ ] `src/app/db/models/__init__.py` updated
- [ ] Alembic migration generated
- [ ] Migration applied: `alembic upgrade head`
- [ ] Unit tests written and passing
- [ ] Manual verification: table exists, constraints work
- [ ] `pylint src/app/db/models/command_status.py` — no errors

---

## Phase 3: API Endpoints (`/api/v1/commands/`)

### What

Create the REST API for sending commands and querying command status. The app
publishes to RabbitMQ and writes to Postgres atomically. Producers call back
via PATCH to update status.

### Files to create

#### `src/app/api/commands/v1/__init__.py`
```python
"""REST API for the command-and-control system."""
```

#### `src/app/api/commands/v1/models.py`
- `CreateCommandRequest(command_type: str, target: str, parameters: dict | None = None)`
- `CommandResponse(command_id: UUID, command_type, target, status, parameters, created_at, started_at, completed_at, error_message, result_summary)`
  - Convert from `CommandStatus` ORM model
- `CommandStatusUpdateRequest(status: str, error_message: str | None = None, started_at: datetime | None = None, completed_at: datetime | None = None, result_summary: dict | None = None)`
- `CommandListResponse(commands: list[CommandResponse], total: int)`

#### `src/app/api/commands/v1/service.py`
- `async create_and_publish_command(request, db_session)`:
  1. Validate `target` — if it's not `"*"`, check it matches a known producer container
     from `CONNECTOR_REGISTRY`
  2. Insert row in `command_status` with status `"pending"` and `created_at = now()`
  3. Build `CommandEnvelope` with UUID, type, target, parameters, issued_at
  4. Publish to RabbitMQ via `CommandPublisher`
  5. On success, update status to `"accepted"`; on publish failure, set status to
     `"failed"` with `error_message="Failed to publish to RabbitMQ"` (this prevents
     a row stuck forever at `"pending"`)
  6. Return `CommandResponse`
- **Publisher lifecycle**: Each `create_and_publish_command` call creates a new
  `CommandPublisher` connection. For a low-frequency command API this is acceptable.
  If performance becomes a concern, a future optimization could use a long-lived
  publisher singleton (similar to how the app manages its DB session pool).
- `async get_command(command_id, db_session)` → `CommandResponse | None`
- `async list_commands(db_session, status=None, target=None, command_type=None, limit=20, offset=0)` → `(list[CommandResponse], total)`
- `async update_command_status(command_id, status_update, db_session)`:
  1. Find command by `command_id`
  2. Validate state transition (e.g. can't go from `completed` back to `running`)
  3. Update fields: `status`, `started_at`, `completed_at`, `error_message`, `result_summary`
  4. Return updated `CommandResponse`

#### `src/app/api/commands/v1/router.py`
```python
router = APIRouter(prefix="/commands", tags=["commands"])

@router.post("/", response_model=CommandResponse, status_code=201)
async def create_command(...)

@router.get("/", response_model=CommandListResponse)
async def list_commands(...)

@router.get("/{command_id}", response_model=CommandResponse)
async def get_command(...)

@router.patch("/{command_id}/status", response_model=CommandResponse)
async def patch_command_status(...)
```

### Files to modify

- `src/app/main.py` — register the new router:
  ```python
  from app.api.commands.v1.router import router as commands_router
  app.include_router(commands_router, prefix="/api/v1")
  ```
- `src/app/api/connectors/v1/registry.py` — add `producer_container` field to the
  three producer connectors only (non-producer connectors like `slack`, `teams`,
  `google_docs`, `sharepoint`, `email`, `atlassian_mcp`, `github_mcp` do NOT get
  this field — the Dash UI checks for its presence to decide whether to show the
  "Run Scan" button):
  ```python
  "github":     { ..., "producer_container": "github-producer" },
  "jira":       { ..., "producer_container": "jira-producer" },
  "confluence": { ..., "producer_container": "confluence-producer" },
  ```

### Tests to write

| Level | Test | What it verifies |
|---|---|---|
| Unit | `test_create_command_valid_target` | Valid target accepted, status=accepted |
| Unit | `test_create_command_invalid_target` | Unknown target returns 422 |
| Unit | `test_create_command_wildcard_target` | Target `"*"` creates command for all producers |
| Unit | `test_get_command_found` | Returns command by command_id |
| Unit | `test_get_command_not_found` | Unknown UUID returns 404 |
| Unit | `test_list_commands_filter_status` | Filters by status correctly |
| Unit | `test_list_commands_filter_target` | Filters by target correctly |
| Unit | `test_list_commands_pagination` | Respects limit/offset |
| Unit | `test_update_status_valid_transition` | `pending→accepted→queued→running→completed` validates |
| Unit | `test_update_status_invalid_transition` | `completed→running` returns 422 |
| Integration | `test_create_command_publishes_to_rabbitmq` | POST → message appears on `command_n_control` exchange |
| Integration | `test_update_command_status_persists` | PATCH → status visible in GET response |
| Integration | `test_command_lifecycle_end_to_end` | Full `pending→accepted→queued→running→completed` via API calls |

### Manual verification

1. Start the app: `uvicorn app.main:app --reload` (ensure RabbitMQ is running)
2. Send a command:
   ```bash
   curl -X POST http://localhost:8000/api/v1/commands/ \
     -H "Content-Type: application/json" \
     -d '{"command_type": "scan", "target": "github-producer"}'
   ```
   → Expect 201, response includes `command_id`, status=`accepted`
3. Verify RabbitMQ message:
   - Check `http://localhost:15672` (guest/guest) → `command_n_control` exchange
   - Message should have routing key `command_n_control.github-producer`
4. List commands:
   ```bash
   curl http://localhost:8000/api/v1/commands/
   ```
5. Update status (simulating a producer):
   ```bash
   curl -X PATCH http://localhost:8000/api/v1/commands/{command_id}/status \
     -H "Content-Type: application/json" \
     -d '{"status": "running", "started_at": "2026-07-29T12:00:00Z"}'
   ```
6. Verify status is reflected in GET response

### Phase 3 progress

- [ ] `src/app/api/commands/v1/__init__.py` created
- [ ] `src/app/api/commands/v1/models.py` created
- [ ] `src/app/api/commands/v1/service.py` created
- [ ] `src/app/api/commands/v1/router.py` created
- [ ] `src/app/main.py` — commands router registered
- [ ] `src/app/api/connectors/v1/registry.py` — `producer_container` field added
- [ ] Unit tests written and passing
- [ ] Integration tests written and passing (requires running app + RabbitMQ)
- [ ] Manual verification: POST/GET/PATCH via curl works end-to-end
- [ ] `pylint src/app/api/commands/` — no errors
- [ ] `mypy src/app/api/commands/` — no errors
- [ ] `pytest -m "integration and server" tests/ -q -k "command"` — passes
- [ ] Regression: existing tests still pass: `pytest -m unit tests/ -q`

---

## Phase 4: Producer Daemon Conversion

### What

Convert each of the three one-shot producer scripts into long-running daemons.
This is the largest phase. Each producer follows an identical structural pattern:

- `scan.py` — the extracted scan logic (one-shot runnable for debugging)
- `main.py` — the daemon entry point (command listener + scan worker)

### Step-by-step for GitHub producer

#### Step 4a: Rename `main.py` → `scan.py` + extract `run_scan()`
- `mv src/connectors/producers/github/main.py src/connectors/producers/github/scan.py`
- **Extract config loading**: In `scan.py`, extract the config-loading logic (reading
  from `CONFIGURATION_SOURCE` env var, fetching from `API_SERVER` or `FILE`) into a
  standalone async function: `async def load_config() -> dict`. This function is called
  once by the daemon's `main_async()` at startup (per design decision #10), not by
  `run_scan()`.
- **Create `run_scan()`**: Rename the existing `main_async()` to
  `async def run_scan(publisher: RabbitMQPublisher, command_envelope: CommandEnvelope, config: dict) -> dict[str, int]`:
  - `publisher` — pre-created `RabbitMQPublisher` instance (daemon opens one per scan)
  - `command_envelope` — the command that triggered the scan; `command_envelope.parameters`
    may contain overrides like `{"force_full": true}` or `{"since": "2026-01-01"}`
  - `config` — the pre-loaded configuration dict
  - Returns a result summary dict like `{"signals_published": 42}` for status tracking
- Keep `main()` as a one-shot convenience entry point for local debugging
- Remove RabbitMQ URL fetch from `run_scan()` — the publisher is passed in
- Update the module docstring to reflect it's now the scan logic module, not the entry point

#### Step 4b: Create new `main.py`
Structure:
```python
"""
GitHub Producer Daemon.

Listens on ``command_n_control`` exchange for ``scan`` commands targeted at
``github-producer``.  Runs one scan at a time; queues additional commands.

Environment variables:
    CONTAINER_NAME     (default: "github-producer")
    RABBITMQ_URL       (default: "amqp://guest:guest@localhost:5672/")
    API_SERVER         (default: "http://localhost:8000")
"""

import asyncio, os, signal, uuid
from datetime import datetime, timezone

import httpx

from common.command_n_control.models import CommandEnvelope, CommandStatusUpdate
from common.command_n_control.listener import CommandListener
from common.messaging.rabbitmq import RabbitMQPublisher
from common.logger import logger
from connectors.producers.github.scan import run_scan
# sync_cursor module used inside scan.py — no change needed


async def _update_status(command_id: uuid.UUID, update: CommandStatusUpdate) -> None:
    """PATCH a status update to the app's API."""
    api_base = os.environ.get("API_SERVER", "http://localhost:8000").rstrip("/")
    url = f"{api_base}/api/v1/commands/{command_id}/status"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.patch(url, json=update.model_dump(exclude_none=True))
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Failed to update command status: %s", exc)


async def scan_worker(queue: asyncio.Queue, shutdown_event: asyncio.Event):
    """Pull commands from the queue and execute scans."""
    while not shutdown_event.is_set():
        try:
            envelope = await asyncio.wait_for(queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue

        command_id = envelope.command_id
        logger.info("Starting scan command_id=%s", command_id)

        # Mark as running
        await _update_status(command_id, CommandStatusUpdate(
            status="running", started_at=datetime.now(timezone.utc)
        ))

        try:
            # The existing scan logic expects a RabbitMQPublisher.
            # We create one per scan (config loaded fresh at daemon start,
            # per design decision #10).
            async with RabbitMQPublisher(
                os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
            ) as publisher:
                result_summary = await run_scan(
                    publisher, envelope, config
                )  # returns dict[str, int] like {"signals_published": 42}

            logger.info("Scan completed command_id=%s", command_id)
            await _update_status(command_id, CommandStatusUpdate(
                status="completed", completed_at=datetime.now(timezone.utc),
                result_summary=result_summary,
            ))
        except asyncio.CancelledError:
            logger.warning("Scan cancelled command_id=%s — container shutting down", command_id)
            await _update_status(command_id, CommandStatusUpdate(
                status="failed", completed_at=datetime.now(timezone.utc),
                error_message="Scan cancelled: container shutting down",
            ))
            break  # Worker exits on cancellation
        except Exception as exc:
            logger.error("Scan failed command_id=%s: %s", command_id, exc, exc_info=True)
            await _update_status(command_id, CommandStatusUpdate(
                status="failed", completed_at=datetime.now(timezone.utc),
                error_message=str(exc),
            ))

    logger.info("Scan worker stopped")


async def listen_and_dispatch(queue: asyncio.Queue, shutdown_event: asyncio.Event):
    """Consume commands from RabbitMQ and push to the internal queue."""
    container_name = os.environ.get("CONTAINER_NAME", "github-producer")
    rabbitmq_url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    listener = CommandListener(rabbitmq_url, container_name)

    async for envelope, message in listener.listen():
        if shutdown_event.is_set():
            break

        logger.info("Received command command_id=%s type=%s", envelope.command_id, envelope.command_type)

        # Ack immediately
        await message.ack()

        # Check if queue is full → scan already running or queued
        if queue.full():
            logger.warning("Scan already in progress — rejecting command_id=%s", envelope.command_id)
            await _update_status(envelope.command_id, CommandStatusUpdate(
                status="failed", completed_at=datetime.now(timezone.utc),
                error_message="Scan already in progress",
            ))
            continue

        # Mark as queued and push to worker
        await _update_status(envelope.command_id, CommandStatusUpdate(
            status="queued"
        ))
        await queue.put(envelope)

    logger.info("Command listener stopped")


async def main_async():
    """Daemon entry point."""
    shutdown_event = asyncio.Event()

    # Register signal handlers
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, shutdown_event.set)
    loop.add_signal_handler(signal.SIGINT, shutdown_event.set)

    # Load config once at startup (design decision #10)
    # ... (existing config loading logic)

    command_queue: asyncio.Queue[CommandEnvelope] = asyncio.Queue(maxsize=1)

    listener_task = asyncio.create_task(listen_and_dispatch(command_queue, shutdown_event))
    worker_task = asyncio.create_task(scan_worker(command_queue, shutdown_event))

    logger.info("GitHub Producer daemon started (container=%s)", os.environ.get("CONTAINER_NAME", "github-producer"))

    await asyncio.gather(listener_task, worker_task, return_exceptions=True)
    logger.info("GitHub Producer daemon stopped")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
```

#### Step 4c: Repeat for Jira producer
Same pattern. `src/connectors/producers/jira/main.py` → `scan.py`, new `main.py`.
The `run_scan()` function wraps the existing `main_async()` logic.

#### Step 4d: Repeat for Confluence producer
Same pattern. `src/connectors/producers/confluence/main.py` → `scan.py`, new `main.py`.

### Files to create / rename

| Action | Path |
|---|---|
| RENAME | `src/connectors/producers/github/main.py` → `src/connectors/producers/github/scan.py` |
| CREATE | `src/connectors/producers/github/main.py` (daemon) |
| RENAME | `src/connectors/producers/jira/main.py` → `src/connectors/producers/jira/scan.py` |
| CREATE | `src/connectors/producers/jira/main.py` (daemon) |
| RENAME | `src/connectors/producers/confluence/main.py` → `src/connectors/producers/confluence/scan.py` |
| CREATE | `src/connectors/producers/confluence/main.py` (daemon) |

### Tests to write

| Level | Test | What it verifies |
|---|---|---|
| Unit | `test_daemon_accepts_command_when_idle` | Internal queue size increases when command received |
| Unit | `test_daemon_rejects_command_when_busy` | `queue.full()` → status update sent with `"scan already in progress"` |
| Unit | `test_daemon_graceful_shutdown` | SIGTERM → worker exits, cancelled status sent |
| Unit | `test_scan_worker_updates_status_running` | Status set to `"running"` before scan starts |
| Unit | `test_scan_worker_updates_status_completed` | Status set to `"completed"` after scan succeeds |
| Unit | `test_scan_worker_updates_status_failed_on_error` | Status set to `"failed"` with error message on exception |
| Int | `test_daemon_receives_command_via_rabbitmq` | Publish to `command_n_control.github-producer` → daemon picks it up |

### Manual verification

1. Build and start the modified producer:
   ```bash
   docker compose build github-producer
   docker compose up -d github-producer
   ```
2. Check logs: `docker compose logs github-producer`
   → Should show "GitHub Producer daemon started"
3. Send a scan command via API:
   ```bash
   curl -X POST http://localhost:8000/api/v1/commands/ \
     -H "Content-Type: application/json" \
     -d '{"command_type": "scan", "target": "github-producer"}'
   ```
4. Watch logs: `docker compose logs -f github-producer`
   → Should show "Received command" → "Starting scan" → progress messages → "Scan completed"
5. Check command status via API:
   ```bash
   curl http://localhost:8000/api/v1/commands/{command_id}
   ```
   → Expect status="completed"
6. Send another scan while the first is running (if slow enough):
   → Expect status="failed" with reason "Scan already in progress"
7. Test graceful shutdown:
   ```bash
   docker compose stop github-producer
   ```
   → Logs should show "Received SIGTERM — initiating graceful shutdown"
   → If a scan was running, its status should be "failed: container shutting down"
8. Repeat steps 1-7 for jira-producer and confluence-producer

### Phase 4 progress

**GitHub producer:**
- [ ] `src/connectors/producers/github/scan.py` created (renamed from main.py)
- [ ] `run_scan()` function extracted from `main_async()`
- [ ] `src/connectors/producers/github/main.py` — daemon entry point created
- [ ] Unit tests written and passing for github daemon
- [ ] Manual verification: daemon starts, receives commands, runs scans, handles shutdown

**Jira producer:**
- [ ] `src/connectors/producers/jira/scan.py` created
- [ ] `run_scan()` function extracted
- [ ] `src/connectors/producers/jira/main.py` — daemon entry point created
- [ ] Unit tests written and passing for jira daemon
- [ ] Manual verification: daemon starts, receives commands, runs scans

**Confluence producer:**
- [ ] `src/connectors/producers/confluence/scan.py` created
- [ ] `run_scan()` function extracted
- [ ] `src/connectors/producers/confluence/main.py` — daemon entry point created
- [ ] Unit tests written and passing for confluence daemon
- [ ] Manual verification: daemon starts, receives commands, runs scans

**All producers:**
- [ ] `httpx` added to `requirements.github-producer.txt`, `requirements.jira-producer.txt`, `requirements.confluence-producer.txt`
- [ ] Integration test: end-to-end scan via API → RabbitMQ → daemon → status update
- [ ] `pytest -m unit tests/ -q` — all existing tests still pass
- [ ] `pylint src/connectors/producers/*/main.py src/connectors/producers/*/scan.py` — no errors

---

## Phase 5: RabbitMQ Topology Update

### What

Add the `command_n_control` exchange, DLX, DLQ, and per-producer queues to the
`init_rabbitmq.py` script that runs at app container startup.

> **Topology design note**: Unlike the `activity_signals` exchange (which uses
> source-level wildcard queues like `github.#`), the `command_n_control` exchange
> uses **per-container queues with exact routing key matches**
> (`command_n_control.github-producer`, etc.). This is because each producer only
> needs to receive commands addressed specifically to it — there is no entity-type
> fan-out in the command bus.

### Files to modify

#### `src/app/scripts/init_rabbitmq.py`

Add after the existing `activity_signals` declaration block:

```python
# ---------------------------------------------------------------------------
# Command-and-control exchange (generic command bus)
# ---------------------------------------------------------------------------
CONTROL_EXCHANGE: str = "command_n_control"
CONTROL_DLX: str = "command_n_control_dlx"
CONTROL_DLQ: str = "command_n_control_dlq"

CONTROL_QUEUES: list[tuple[str, str]] = [
    ("cnc.github-producer", "command_n_control.github-producer"),
    ("cnc.jira-producer", "command_n_control.jira-producer"),
    ("cnc.confluence-producer", "command_n_control.confluence-producer"),
]

# Declare command_n_control exchange
control_exchange = await channel.declare_exchange(
    CONTROL_EXCHANGE,
    aio_pika.ExchangeType.TOPIC,
    durable=True,
)
logger.info("Exchange ready: %s (topic, durable)", CONTROL_EXCHANGE)

# Declare DLX
control_dlx = await channel.declare_exchange(
    CONTROL_DLX,
    aio_pika.ExchangeType.DIRECT,
    durable=True,
)
logger.info("Exchange ready: %s (direct, durable)", CONTROL_DLX)

# Declare DLQ bound to DLX
control_dlq = await channel.declare_queue(CONTROL_DLQ, durable=True)
await control_dlq.bind(control_dlx, routing_key=CONTROL_DLQ)
logger.info("Queue ready: %s, bound to exchange %s", CONTROL_DLQ, CONTROL_DLX)

# Declare per-producer control queues
for queue_name, routing_key in CONTROL_QUEUES:
    queue = await channel.declare_queue(
        queue_name,
        durable=True,
        arguments={
            "x-dead-letter-exchange": CONTROL_DLX,
            "x-dead-letter-routing-key": CONTROL_DLQ,
        },
    )
    await queue.bind(control_exchange, routing_key=routing_key)
    logger.info("Queue ready: %s, bound to %s with routing key %s", queue_name, CONTROL_EXCHANGE, routing_key)
```

### Tests to write

| Level | Test | What it verifies |
|---|---|---|
| Integration | `test_init_rabbitmq_declares_control_exchange` | `command_n_control` exchange exists after init |
| Integration | `test_init_rabbitmq_declares_control_queues` | All 3 `cnc.*` queues exist with correct bindings |
| Integration | `test_init_rabbitmq_declares_control_dlx` | DLX/DLQ declared correctly |
| Integration | `test_init_rabbitmq_idempotent` | Running init twice doesn't error (idempotent) |

### Manual verification

1. Run `cd /app && python app/scripts/init_rabbitmq.py`
2. Check RabbitMQ management UI (`http://localhost:15672`):
   - Exchanges tab → `command_n_control` (topic, durable)
   - Exchanges tab → `command_n_control_dlx` (direct, durable)
   - Queues tab → `command_n_control_dlq` (durable)
   - Queues tab → `cnc.github-producer`, `cnc.jira-producer`, `cnc.confluence-producer`
3. Verify bindings on the `command_n_control` exchange:
   - `cnc.github-producer` ← `command_n_control.github-producer`
   - `cnc.jira-producer` ← `command_n_control.jira-producer`
   - `cnc.confluence-producer` ← `command_n_control.confluence-producer`

### Phase 5 progress

- [ ] `src/app/scripts/init_rabbitmq.py` — control exchange topology added
- [ ] Integration tests written and passing
- [ ] Manual verification: queues/exchanges visible in RabbitMQ UI
- [ ] `docker compose restart app` — app starts without errors, topology created
- [ ] `pylint src/app/scripts/init_rabbitmq.py` — no errors

---

## Phase 6: Dash UI — Connectors Detail Page

### What

Add a "Run Scan" button and "Recent Scans" section to the connector detail page.
Only shown for connector types that have a `producer_container` in the registry.

### Files to modify

#### `src/app/dash_app/pages/connectors/layout.py`

In `get_detail_layout()`:
1. Import `CONNECTOR_REGISTRY` (already imported), `SPACING_SMALL` from `app.dash_app.styles`
2. After the "Test Connection" / "Delete Configuration" button row, conditionally
   render a "Run Scan" button (only if `registry.get(producer_container)` is set):
   ```python
   if CONNECTOR_REGISTRY.get(connector_type, {}).get("producer_container"):
       run_scan_button = dbc.Button(
           "Run Scan",
           id={"type": "connector-run-scan", "connector_type": connector_type},
           color="success",
           size="sm",
           className="me-2",
       )
   ```
3. Add a "Scan History" section below:
   ```python
   html.Div(id="connector-scans-list", style={"marginTop": SPACING_SMALL})
   ```
4. Add a polling interval that refreshes scans while scans are in progress:
   ```python
   dcc.Interval(id="connector-scans-poll", interval=5000)  # 5 seconds
   ```

#### `src/app/dash_app/pages/connectors/callbacks.py`

New callbacks (add to `callbacks.py`):

```python
from dash import callback_context, no_update, callback, Input, Output, State, MATCH
from app.dash_app.styles import SPACING_SMALL  # if needed for layout tokens

@callback(
    Output("connector-action-feedback", "children", allow_duplicate=True),
    Input({"type": "connector-run-scan", "connector_type": MATCH}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_run_scan(n_clicks):
    """Send a scan command via the API."""
    if not n_clicks:
        return no_update
    connector_type = callback_context.triggered_id["connector_type"]
    container_name = CONNECTOR_REGISTRY[connector_type]["producer_container"]
    # POST /api/v1/commands/
    # Parse response
    # Return success alert with command_id


@callback(
    Output("connector-scans-list", "children"),
    Input("connector-scans-poll", "n_intervals"),
    State("url", "pathname"),
)
def load_recent_scans(n_intervals, pathname):
    """Load recent scan commands for this connector."""
    connector_type = pathname.split("/app/connectors/")[-1]
    if not connector_type or connector_type not in CONNECTOR_REGISTRY:
        return no_update
    container_name = CONNECTOR_REGISTRY[connector_type].get("producer_container")
    if not container_name:
        return no_update
    # GET /api/v1/commands/?target={container_name}&limit=10
    # Render scan history list
    # If any scan is running/queued, keep polling


@callback(
    Output("connector-scans-poll", "disabled"),
    Input("connector-scans-list", "children"),
)
def stop_polling_if_idle(scans_list):
    """Disable polling when no scans are in progress."""
    # Check if any scan has status "running" or "queued"
    # If none, return True (stop polling)
    # If any, return False (keep polling)
```

#### New file: `src/app/dash_app/pages/connectors/components/scan_status.py`
```python
def render_scan_item(command: dict) -> html.Div:
    """Render a single command row with icon, status, duration, and summary."""
    status = command.get("status", "unknown")
    status_icons = {
        "pending": "fa-regular fa-clock",
        "accepted": "fa-regular fa-circle-check",
        "queued": "fa-regular fa-hourglass-half",
        "running": "fa-solid fa-spinner fa-spin",
        "completed": "fa-regular fa-circle-check",
        "failed": "fa-regular fa-circle-xmark",
    }
    # ... render with color-coded icon, relative timestamp, duration, result_summary
```

### Tests to write

| Level | Test | What it verifies |
|---|---|---|
| Unit | `test_scan_button_visible_for_producer_connectors` | GitHub/Jira/Confluence detail pages have "Run Scan" button |
| Unit | `test_scan_button_hidden_for_non_producer_connectors` | Slack/Teams etc. don't have the button |
| Unit | `test_run_scan_calls_api` | Button click triggers POST request to `/api/v1/commands/` |
| Unit | `test_recent_scans_section_renders` | Scan history section renders with correct items |
| Unit | `test_scan_status_icons` | Each status renders correct icon + color |
| Int | `test_run_scan_button_click_triggers_command` | Full flow: click → API → RabbitMQ → status visible in UI |

### Manual verification

1. Open `http://localhost:8000/app/connectors/`
2. Click "GitHub" card → detail page loads
3. Verify "Run Scan" button is visible (green, right-aligned with other buttons)
4. Click "Run Scan" → verify success alert appears with command_id
5. Scroll down → "Recent Scans" section shows the scan with status "accepted" or "queued"
6. Within a few seconds, status should transition to "running" → "completed"
7. Verify icons update accordingly (blue spinner → green checkmark)
8. Click "Run Scan" again while one is running → verify "failed: scan already in progress"
9. Navigate to Slack connector → verify "Run Scan" button is NOT visible
10. Test auto-poll stops after last scan completes (no more API calls)

### Phase 6 progress

- [ ] `src/app/dash_app/pages/connectors/components/scan_status.py` created
- [ ] `src/app/dash_app/pages/connectors/layout.py` — Run Scan button added
- [ ] `src/app/dash_app/pages/connectors/layout.py` — Recent Scans section added
- [ ] `src/app/dash_app/pages/connectors/layout.py` — polling interval added
- [ ] `src/app/dash_app/pages/connectors/callbacks.py` — `handle_run_scan` callback
- [ ] `src/app/dash_app/pages/connectors/callbacks.py` — `load_recent_scans` callback
- [ ] `src/app/dash_app/pages/connectors/callbacks.py` — `stop_polling_if_idle` callback
- [ ] Unit tests written and passing
- [ ] Manual verification: scan trigger + status monitoring works in browser
- [ ] `pylint src/app/dash_app/pages/connectors/` — no errors

---

## Phase 7: Docker Compose + Dockerfiles

### What

Update docker-compose.yml to make producers long-running, add `CONTAINER_NAME`
env var, and ensure the app `depends_on` includes the control topology.

### Dependency changes

Add `httpx` to all three producer requirement files (needed by the daemon for
async HTTP PATCH callbacks to the app's API):

| File | Addition |
|---|---|
| `requirements.github-producer.txt` | `httpx` |
| `requirements.jira-producer.txt` | `httpx` |
| `requirements.confluence-producer.txt` | `httpx` |

### Files to modify

#### `docker-compose.yml`

**github-producer:**
```yaml
github-producer:
  # ... existing build, container_name, env_file, volumes ...
  restart: unless-stopped  # CHANGED: was "no"
  environment:
    CONTAINER_NAME: github-producer  # NEW
    # ... existing env vars stay ...
  # CHANGED: Remove "app: condition: service_healthy" from depends_on.
  # The daemon no longer blocks on app startup — it connects to RabbitMQ
  # independently. Status PATCH callbacks will gracefully degrade (log a
  # warning) if the app is temporarily unavailable.
  depends_on:
    postgres:
      condition: service_healthy
    rabbitmq:
      condition: service_healthy
```

Same pattern for jira-producer and confluence-producer.

**app service — no changes needed** (already depends on rabbitmq and producers
are independent of app health now).

#### Dockerfile entrypoint verification

The existing `Dockerfile.github-producer`, `Dockerfile.jira-producer`, and
`Dockerfile.confluence-producer` each run `CMD ["python", "main.py"]` or similar.
After the rename (`main.py` → `scan.py`), the new `main.py` (daemon) lives at the
same path, so the Dockerfile `CMD` does **not** need to change. Verify this during
implementation by checking each Dockerfile's `CMD` instruction.

### Tests to verify

| Level | Test | What it verifies |
|---|---|---|
| Manual | `docker compose up -d` | All 3 producers start, logs show "daemon started" |
| Manual | `docker compose ps` | All 3 producers show "Up (health: starting)" or healthy |
| Manual | `docker compose logs github-producer` | Shows "GitHub Producer daemon started" |
| Manual | `docker compose logs jira-producer` | Shows "Jira Producer daemon started" |
| Manual | `docker compose logs confluence-producer` | Shows "Confluence Producer daemon started" |
| Manual | RabbitMQ UI | All 3 `cnc.*` queues have 1 consumer connected |
| Manual | `docker compose restart github-producer` | Producer restarts, reconnects to RabbitMQ |

### Phase 7 progress

- [ ] `docker-compose.yml` — github-producer `restart: unless-stopped` + `CONTAINER_NAME`
- [ ] `docker-compose.yml` — jira-producer `restart: unless-stopped` + `CONTAINER_NAME`
- [ ] `docker-compose.yml` — confluence-producer `restart: unless-stopped` + `CONTAINER_NAME`
- [ ] `docker-compose.yml` — producer `depends_on` updated (removed `app` dependency)
- [ ] Dockerfile entrypoints verified — `CMD` still points to the correct (new) `main.py`
- [ ] `httpx` added to `requirements.github-producer.txt`, `requirements.jira-producer.txt`, `requirements.confluence-producer.txt`
- [ ] Full stack up: `docker compose up -d` — all containers start successfully
- [ ] All 3 producers show "daemon started" in logs
- [ ] All 3 `cnc.*` queues show 1 consumer in RabbitMQ UI
- [ ] End-to-end verification: Run scan from UI → signal appears in Neo4j

---

## Full Integration Verification (all phases complete)

### Automated regression suite

```bash
# Unit tests
pytest -m unit tests/ -q

# Integration tests requiring running services
pytest -m "integration and server" tests/ -q

# RabbitMQ integration tests
pytest -m rabbitmq tests/ -q

# Neo4j integration tests (verify new data arrived)
pytest -m neo4j tests/ -q

# All tests
pytest tests/ -q
```

### Manual end-to-end scenario

1. `docker compose up -d` — all services start
2. Open browser → `http://localhost:8000/app/connectors/github`
3. Click "Run Scan" — watch the scan history section
4. Wait for scan to complete (status → "completed" with green icon)
5. Open Graph page → verify new Neo4j data is visible
6. Go to Jira connector → click "Run Scan" → verify it works independently
7. Trigger a second scan while one is running → verify "failed: scan already in progress"
8. `docker compose restart github-producer` while scan is running → verify "failed: container shutting down"
9. After restart, run scan again → verify it works normally
10. Check command history: `curl http://localhost:8000/api/v1/commands/` → see all commands

### Regression checks

- [ ] Existing connector API endpoints work (CRUD configs, test connection)
- [ ] Existing Dash pages work (Chat, People, Progress, Graph, Analytics, Settings)
- [ ] Signal consumer still processes signals correctly (unaffected by new exchange)
- [ ] Existing tests pass: `pytest -m unit tests/ -q`
- [ ] Type checking: `mypy src/`
- [ ] Linting: `pylint src/`
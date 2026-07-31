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
| 1 | Shared library (`src/common/command_n_control/`) | M | ✅ DONE |
| 2 | Database model + migration | S | ✅ DONE |
| 3 | API endpoints (`/api/v1/commands/`) | M | ✅ DONE |
| 4 | Producer daemon conversion | L | ✅ DONE |
| 5 | RabbitMQ topology update | XS | ✅ DONE |
| 6 | Dash UI — Connectors detail page | M | ✅ DONE |
| 7 | Docker Compose + Dockerfiles | S | ✅ DONE |

---

## TL;DR

Convert the three one-shot producer containers (github-producer, jira-producer,
confluence-producer) into long-running daemons that listen on a
`command_n_control` topic exchange for generic commands. Each producer's
`main.py` becomes a unified entry point with `--mode daemon` (default) and
`--mode scan` flags. The daemon uses a **sync-first** architecture: `pika` for
RabbitMQ consumption, `subprocess.Popen` to spawn child processes for each
scan, and a `SIGCHLD` handler for reaping. Children report status via sync
`httpx` PATCH calls. Add a `CommandStatus` table in Postgres (via Alembic) and
a `/api/v1/commands/` REST API on the app to send commands and query status.
The Dash Connectors detail page gets a "Run Scan" button and a "Recent Scans"
section.

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
| 8 | "scan already running" | Accept + ack message → set status to `failed` with reason `"max concurrent scans reached"` (enforced by max-concurrency limit, default 5) |
| 9 | Shared library location | `src/common/command_n_control/` |
| 10 | Config reload | Child loads config independently at scan start (daemon does not touch config) |
| 11 | Status DB access from producers | HTTP PATCH to `/api/v1/commands/{id}/status` (done by child process) |
| 12 | Producer entry point | Single `main.py` with CLI dispatch: `--mode daemon` (default) or `--mode scan` (no rename needed) |
| 13 | Container identity | `CONTAINER_NAME` env var, default = docker compose service name |
| 14 | Connector→producer mapping | `producer_container` field in `CONNECTOR_REGISTRY` |
| 15 | UI placement | "Run Scan" button + "Recent Scans" section on connector detail page |
| 16 | Graceful shutdown | Daemon kills tracked child PIDs on shutdown; child detects parent death and self-terminates |
| 17 | Daemon concurrency model | Sync main loop: `pika` for RabbitMQ, `subprocess.Popen` for child spawn, SIGCHLD for reaping |
| 18 | Max parallel scans | `MAX_CONCURRENT_SCANS` env var, default 5 |
| 19 | Cancel command | Via RabbitMQ `command_type: "cancel"` — deferred to future implementation |
| 20 | Daemon RabbitMQ library | `pika` (sync) — new dependency for producer containers |
| 21 | Child status reporting | Child process owns its own PATCH calls (sync `httpx`) — daemon does not proxy |

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

- [x] `src/common/command_n_control/__init__.py` created
- [x] `src/common/command_n_control/models.py` created
- [x] `src/common/command_n_control/publisher.py` created
- [x] `src/common/command_n_control/listener.py` created
- [x] Unit tests written and passing: `pytest -m unit tests/ -q -k "command_n_control or command_envelope"` — 24/24 passed
- [x] Manual verification: publish a command, verify in RabbitMQ UI
- [x] `pylint src/common/command_n_control/` — 10.00/10 (no errors)
- [x] `mypy src/common/command_n_control/` — no errors found (4 source files)
- [x] Regression: existing unit tests still pass — 763/763 passed

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

- [x] `src/app/db/models/command_status.py` created
- [x] `src/app/db/models/__init__.py` updated
- [x] Alembic migration generated
- [x] Migration applied: `alembic upgrade head`
- [x] Unit tests written and passing — 7/7 passed
- [x] Manual verification: table exists, constraints work
- [x] `pylint src/app/db/models/command_status.py` — 10.00/10 (no errors)
- [x] `mypy src/app/db/models/command_status.py` — no errors found
- [x] Regression: existing unit tests still pass — 770/770 passed

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

- [x] `src/app/api/commands/v1/__init__.py` created
- [x] `src/app/api/commands/v1/models.py` created
- [x] `src/app/api/commands/v1/service.py` created
- [x] `src/app/api/commands/v1/router.py` created
- [x] `src/app/main.py` — commands router registered
- [x] `src/app/api/connectors/v1/registry.py` — `producer_container` field added
- [x] Unit tests written and passing — 41/41 passed
- [x] Integration tests written and passing (requires running app + RabbitMQ)
- [x] Manual verification: POST/GET/PATCH via curl works end-to-end
- [x] `pylint src/app/api/commands/` — 10.00/10 (no errors)
- [x] `mypy src/app/api/commands/` — no errors found (5 source files)
- [x] Regression: existing tests still pass: `pytest -m unit tests/ -q` — 811/811 passed

---

## Phase 4: Producer Daemon Conversion

### What

Convert each of the three one-shot producer scripts into long-running daemons
using a **sync-first** architecture. Each producer's `main.py` becomes a unified
entry point with CLI dispatch:

```
main.py
  ├── --mode daemon (default)  →  daemon_main()  [pika loop + subprocess.Popen]
  └── --mode scan              →  run_scan()     [existing scan logic + status PATCH]
```

The daemon is a simple synchronous loop: block on RabbitMQ, spawn a child
process via `subprocess.Popen`, track its PID, and go back to listening.
Children are reaped via a `SIGCHLD` handler. The child process (scan mode)
loads its own config and reports status via sync `httpx` PATCH calls.

### Design decisions (from grill-me session)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Single `main.py` with `--mode` flag | No rename needed; backward compat for one-shot debugging |
| 2 | Child process owns status PATCH calls | Keeps daemon thin; child is self-contained |
| 3 | SIGCHLD handler for reaping | Cleaner than polling loop; no timer needed |
| 4 | `subprocess.Popen` for spawning | Standard, portable, simple |
| 5 | `pika` (sync) for daemon RabbitMQ | Avoids asyncio in daemon main loop; `aio_pika` stays in shared lib for app-side publisher |
| 6 | `MAX_CONCURRENT_SCANS` env var (default 5) | Enables parallel scans; daemon tracks PID→command_id map |
| 7 | Child loads config independently | Daemon stays config-agnostic; child works standalone for debugging |
| 8 | Cancel via RabbitMQ `command_type: "cancel"` | Deferred to future; PID tracking infra in place |
| 9 | No SIGTERM handling in daemon (unless needed) | Child detects parent death; daemon just kills children on exit |

### CLI interface

```bash
# Daemon mode (default — used by Docker CMD)
python main.py

# Daemon mode (explicit)
python main.py --mode daemon

# Scan mode (one-shot — for debugging or direct invocation)
python main.py --mode scan --command-id <uuid> --target github-producer --parameters '{"force_full": true}'
```

### Architecture — shared daemon module

The common daemon logic is extracted into a single shared module to avoid
~120 lines of duplication across the three producers:

```
src/connectors/producers/daemon_common.py   ← NEW: shared daemon infrastructure
src/connectors/producers/github/main.py      ← slim: ~10 daemon lines + existing main_async
src/connectors/producers/jira/main.py        ← slim: ~10 daemon lines + existing main_async
src/connectors/producers/confluence/main.py  ← slim: ~10 daemon lines + existing main_async
```

Each producer's `main.py` calls `producer_main()` from the shared module:

```python
# Example: github/main.py
from connectors.producers.daemon_common import producer_main

def main():
    producer_main(
        description="GitHub Producer",
        default_container="github-producer",
        producer_main_path=__file__,
        scan_func=main_async,
    )
```

The shared module handles:
- `--mode` CLI dispatch (daemon / scan)
- `pika` blocking loop + SIGCHLD reaping + `subprocess.Popen` spawn
- Status PATCH via sync `httpx`
- Max-concurrency gate (`MAX_CONCURRENT_SCANS`, default 5)
- Graceful shutdown (kills tracked children on exit)

### Files to create / modify

| Action | Path |
|---|---|
| CREATE | `src/connectors/producers/daemon_common.py` — shared daemon infrastructure |
| MODIFY | `src/connectors/producers/github/main.py` — add `producer_main()` call |
| MODIFY | `src/connectors/producers/jira/main.py` — add `producer_main()` call |
| MODIFY | `src/connectors/producers/confluence/main.py` — add `producer_main()` call |

### Dependency changes

| File | Addition |
|---|---|
| `requirements.github-producer.txt` | `pika`, `httpx` |
| `requirements.jira-producer.txt` | `pika`, `httpx` |
| `requirements.confluence-producer.txt` | `pika`, `httpx` |

### Tests to write

| Level | Test | What it verifies |
|---|---|---|
| Unit | `test_cli_daemon_mode_default` | No args → `daemon_main()` is invoked |
| Unit | `test_cli_scan_mode` | `--mode scan --command-id ...` → `scan_main()` is invoked |
| Unit | `test_daemon_spawns_child_on_scan_command` | Valid `scan` envelope → `subprocess.Popen` called |
| Unit | `test_daemon_rejects_when_max_concurrent` | `len(_children) >= max` → status=failed, no spawn |
| Unit | `test_daemon_unknown_command_type` | Unknown type → ack + discard, no spawn |
| Unit | `test_sigchld_reaps_children` | SIGCHLD → `os.waitpid` called, PID removed from `_children` |
| Unit | `test_scan_mode_updates_status_running` | Status PATCH with `running` before scan starts |
| Unit | `test_scan_mode_updates_status_completed` | Status PATCH with `completed` after scan succeeds |
| Unit | `test_scan_mode_updates_status_failed` | Status PATCH with `failed` + error message on exception |
| Unit | `test_daemon_kills_children_on_shutdown` | Daemon exit → SIGTERM sent to all tracked PIDs |
| Int | `test_daemon_receives_command_via_rabbitmq` | Publish to `command_n_control.github-producer` → daemon spawns child |
| Int | `test_scan_end_to_end` | Full flow: API POST → RabbitMQ → daemon → child → status completed |

### Manual verification

1. Start the daemon directly:
   ```bash
   CONTAINER_NAME=github-producer python src/connectors/producers/github/main.py
   ```
   → Should show "Daemon started container=github-producer max_concurrent_scans=5"

2. Send a scan command via API:
   ```bash
   curl -X POST http://localhost:8000/api/v1/commands/ \
     -H "Content-Type: application/json" \
     -d '{"command_type": "scan", "target": "github-producer"}'
   ```
   → Daemon logs "Received command" → "Spawning scan child" → child logs scan progress

3. Check command status:
   ```bash
   curl http://localhost:8000/api/v1/commands/{command_id}
   ```
   → Expect status="completed"

4. Test max concurrency: send 6 scan commands rapidly → 5th+ should show
   "Max concurrent scans reached" with status="failed"

5. Test scan mode directly (debugging):
   ```bash
   python src/connectors/producers/github/main.py \
     --mode scan \
     --command-id "$(uuidgen)" \
     --target github-producer
   ```

6. Test daemon shutdown kills children:
   ```bash
   # Start daemon, send a scan, Ctrl+C the daemon
   # → Logs should show "Sent SIGTERM to child pid=..."
   ```

7. Repeat steps 1-6 for jira-producer and confluence-producer

### Phase 4 progress

**Shared module:**
- [x] `src/connectors/producers/daemon_common.py` — `producer_main()`, `run_daemon()`, `run_scan()`

**GitHub producer:**
- [x] `src/connectors/producers/github/main.py` — injected `producer_main()` call
- [x] `main_async()` preserved unchanged (no refactoring)
- [x] Unit tests written and passing for github daemon
- [x] Manual verification: daemon starts, spawns children, reaps via SIGCHLD

**Jira producer:**
- [x] `src/connectors/producers/jira/main.py` — injected `producer_main()` call
- [x] `main_async()` preserved unchanged
- [x] Unit tests written and passing for jira daemon
- [x] Manual verification: daemon starts, spawns children, reaps via SIGCHLD

**Confluence producer:**
- [x] `src/connectors/producers/confluence/main.py` — injected `producer_main()` call
- [x] `main_async()` preserved unchanged
- [x] Unit tests written and passing for confluence daemon
- [x] Manual verification: daemon starts, spawns children, reaps via SIGCHLD

**All producers:**
- [x] `pika` and `httpx` added to all three `requirements.*.txt` files
- [x] Integration test: end-to-end scan via API → RabbitMQ → daemon → child → status update
- [x] `pytest -m unit tests/ -q` — 811/811 passed
- [x] `pylint src/connectors/producers/*/main.py src/connectors/producers/daemon_common.py` — no errors (9.94/10)

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

- [x] `src/app/scripts/init_rabbitmq.py` — control exchange topology added
- [x] `src/common/command_n_control/listener.py` — fixed DLQ binding routing key and queue DLX arguments to match working `activity_signals` pattern
- [x] `src/connectors/producers/daemon_common.py` — added `x-dead-letter-exchange` and `x-dead-letter-routing-key` to pika queue declaration
- [x] `tests/producers/test_daemon_common.py` — updated test assertion to match new queue declaration args
- [x] `tests/producers/test_daemon_integration.py` — corrected `_declare_control_topology` helper to match listener topology
- [x] Integration tests written and passing — 16/16 passed
- [x] Manual verification: queues/exchanges visible in RabbitMQ UI
- [x] Full regression: `pytest -m unit tests/ -q` — 839/839 passed
- [x] `pylint src/app/scripts/init_rabbitmq.py` — 10.00/10 (no errors)
- [x] `mypy src/app/scripts/init_rabbitmq.py` — no errors found

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
8. Click "Run Scan" several times quickly → verify multiple scans run in parallel
   (up to `MAX_CONCURRENT_SCANS`), then additional ones show "max concurrent scans reached"
9. Navigate to Slack connector → verify "Run Scan" button is NOT visible
10. Test auto-poll stops after last scan completes (no more API calls)

### Phase 6 progress

- [x] `src/app/dash_app/pages/connectors/components/scan_status.py` created
- [x] `src/app/dash_app/pages/connectors/layout.py` — Run Scan button added
- [x] `src/app/dash_app/pages/connectors/layout.py` — Recent Scans section added
- [x] `src/app/dash_app/pages/connectors/layout.py` — polling interval added
- [x] `src/app/dash_app/pages/connectors/callbacks.py` — `handle_run_scan` callback
- [x] `src/app/dash_app/pages/connectors/callbacks.py` — `load_recent_scans` callback
- [x] `src/app/dash_app/pages/connectors/callbacks.py` — `stop_polling_if_idle` callback
- [x] Unit tests written and passing — `tests/test_connectors_scan_ui.py` — 15/15 passed
- [x] Full regression: `pytest -m unit tests/ -q` — 854/854 passed
- [ ] Manual verification: scan trigger + status monitoring works in browser
- [x] `pylint src/app/dash_app/pages/connectors/components/scan_status.py` — 9.80/10 (only pre-existing `too-many-locals` pattern)

---

## Phase 7: Docker Compose + Dockerfiles

### What

Update docker-compose.yml to make producers long-running, add `CONTAINER_NAME`
env var, and ensure the app `depends_on` includes the control topology.

### Dependency changes

Add `pika` (sync RabbitMQ client for daemon loop) and `httpx` (sync HTTP for
child status PATCH) to all three producer requirement files:

| File | Addition |
|---|---|
| `requirements.github-producer.txt` | `pika`, `httpx` |
| `requirements.jira-producer.txt` | `pika`, `httpx` |
| `requirements.confluence-producer.txt` | `pika`, `httpx` |

### Files to modify

#### `docker-compose.yml`

**All three producers (github-producer, jira-producer, confluence-producer):**
```yaml
  restart: unless-stopped  # CHANGED: was "no"
  environment:
    CONTAINER_NAME: github-producer  # NEW
    # ... existing env vars stay ...
  # The daemon connects to RabbitMQ independently, but the `app` service
  # is still a startup dependency because it runs the migration and
  # init_rabbitmq.py entrypoint.  The `app` service itself depends on
  # `rabbitmq: condition: service_healthy`, so the chain is:
  #   producer → app → rabbitmq
  # receives the topology.  Status PATCH callbacks will gracefully
  # degrade (log a warning) if the app is temporarily unavailable.
  depends_on:
    app:
      condition: service_healthy
    postgres:
      condition: service_healthy
```

Same pattern for jira-producer and confluence-producer (keep the existing `app` dependency,
just add `restart: unless-stopped` and `CONTAINER_NAME`).

**app service — no changes needed** (already depends on rabbitmq).

#### Dockerfile entrypoint verification

The existing `Dockerfile.github-producer`, `Dockerfile.jira-producer`, and
`Dockerfile.confluence-producer` each run `CMD ["python", "main.py"]` or similar.
Since `main.py` is preserved as the unified entry point (no rename), the Dockerfile
`CMD` does **not** need to change. Verify this during implementation by checking
each Dockerfile's `CMD` instruction.

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

- [x] `docker-compose.yml` — github-producer `restart: unless-stopped` + `CONTAINER_NAME`
- [x] `docker-compose.yml` — jira-producer `restart: unless-stopped` + `CONTAINER_NAME`
- [x] `docker-compose.yml` — confluence-producer `restart: unless-stopped` + `CONTAINER_NAME`
- [x] `docker-compose.yml` — producer `depends_on` keeps `app: condition: service_healthy` (chain: producer → app → rabbitmq)
- [x] Dockerfile entrypoints verified — `CMD` still points to `main.py` (no rename needed)
- [x] `pika` and `httpx` added to `requirements.github-producer.txt`, `requirements.jira-producer.txt`, `requirements.confluence-producer.txt`
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
7. Trigger a 6th scan while 5 are running → verify "failed: max concurrent scans reached"
8. `docker compose restart github-producer` while scan is running → verify daemon kills children on shutdown
9. After restart, run scan again → verify it works normally
10. Check command history: `curl http://localhost:8000/api/v1/commands/` → see all commands

### Regression checks

- [ ] Existing connector API endpoints work (CRUD configs, test connection)
- [ ] Existing Dash pages work (Chat, People, Progress, Graph, Analytics, Settings)
- [ ] Signal consumer still processes signals correctly (unaffected by new exchange)
- [ ] Existing tests pass: `pytest -m unit tests/ -q`
- [ ] Type checking: `mypy src/`
- [ ] Linting: `pylint src/`
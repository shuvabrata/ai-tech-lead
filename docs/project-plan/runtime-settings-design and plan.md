# Runtime Application Settings Design

**Audience:** Developers implementing UI-configurable application settings.

---

## Overview

The application currently reads configuration through `src/app/settings.py`.
`Settings` is a Pydantic `BaseSettings` class that reads environment variables
and hardcoded defaults once per process. This works well for bootstrap
configuration, local CLI development, and Docker Compose startup, but it does
not support changing application behavior from the UI without restarting
containers.

This design introduces a DB-backed runtime settings layer for a curated subset
of non-secret settings that can safely change while the application is running.
Postgres remains the durable source for UI overrides, while RabbitMQ provides
live invalidation events so all running containers can refresh their local
settings snapshots.

The existing `Settings` class remains the bootstrap/default/env layer.
A new `runtime_settings` service becomes the read boundary for settings that
are configurable at runtime.

---

## Goals

- Expose selected application settings through the UI and REST API.
- Preserve local CLI and development behavior based on environment variables.
- Apply supported setting changes dynamically, without container restarts.
- Persist UI changes in Postgres.
- Keep hardcoded defaults in code.
- Keep `DATABASE_URL` out of DB because it is required to reach Postgres.
- Keep `CONNECTOR_ENCRYPTION_KEY` out of DB because it protects secrets already
  stored in Postgres.
- Propagate changes to all running container types using RabbitMQ fanout events.
- Keep the first implementation focused and avoid designing a generic secret or
  multi-tenant configuration system.

---

## Non-Goals

- Generic secret settings in `application_settings`.
- Project-scoped settings.
- Restart-required or reconnect-required settings.
- Auditing/history of every setting change.
- A global settings version counter.
- Redesigning environment variable alias behavior.
- Allowing the UI/API to create or delete setting catalog rows.

---

## Current State

`src/app/settings.py` defines process-local settings:

```python
class Settings(BaseSettings):
    DATABASE_URL: str
    NEO4J_URI: str = "bolt://localhost:7687"
    HTTP_REQUEST_TIMEOUT: int = 60
    TIMEZONE: str = "UTC"
    ...

settings = Settings()
```

Important current behavior:

- Each container reads its environment once at process startup.
- `DATABASE_URL` is used at import time by `src/app/db/session.py` to create the
  SQLAlchemy engine.
- `CONNECTOR_ENCRYPTION_KEY` is used by `src/app/common/encryption.py` to
  encrypt/decrypt connector credentials stored in Postgres.
- Some call sites read `settings.X` at request time.
- Some Dash callback modules cache settings into module constants, for example
  `TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT`; these constants will not
  respond to runtime changes.
- Producer containers are thin. They copy `src/connectors` and `src/common`,
  not `src/app`, and already fetch connector configuration through the app REST
  API.
- The application already uses RabbitMQ for activity signals and
  command-and-control, but the existing command-and-control exchange is
  target-oriented rather than fanout/broadcast-oriented.

---

## Core Decision

Introduce a runtime settings layer:

```text
settings
  Bootstrap/static/default/env configuration.
  Used for values needed before runtime settings can be loaded.

runtime_settings
  Synchronous in-memory snapshot of effective runtime-configurable settings.
  Used by app behavior that must reflect UI changes dynamically.
```

Runtime-configurable settings should be read through `runtime_settings`, not
directly from `settings`. Existing `settings.KEY` fields can remain temporarily
for backward compatibility while call sites are migrated.

---

## Source Precedence

For a setting that has a row in `application_settings`:

```text
1. DB override, when application_settings.value IS NOT NULL
2. Environment-loaded Settings value
3. Hardcoded code default
```

Resetting a setting means setting `application_settings.value = NULL`.
After reset, the effective value falls back to the environment value if present,
otherwise to the hardcoded code default.

This preserves all of the following:

- Docker and CLI users can configure values with env vars.
- UI changes persist and override env values for runtime-configurable settings.
- Code defaults remain authoritative when neither DB nor env provides a value.

---

## Configurability Boundary

A setting is runtime-configurable if and only if it has a row in
`application_settings`.

Unknown keys must be rejected by the settings API. This prevents typo-created
settings and prevents env-only settings like `DATABASE_URL` and
`CONNECTOR_ENCRYPTION_KEY` from becoming UI-configurable by accident.

Catalog rows are migration-managed. The UI/API can update or reset `value`, but
must not create or delete catalog rows.

---

## Database Schema

Add an Alembic migration that creates and seeds `application_settings`.

Suggested table:

```text
application_settings
- id integer primary key
- key varchar unique not null
- value jsonb nullable
- value_type varchar not null
- category varchar nullable
- description text nullable
- apply_mode varchar not null
- is_sensitive boolean not null default false
- created_at timestamptz not null default now()
- updated_at timestamptz not null default now()
```

Recommended constraints:

```text
value_type IN ('string', 'integer', 'boolean')
apply_mode IN ('dynamic')
```

`JSONB` is used so booleans, integers, and strings keep their native shape.
`value_type` keeps the API and UI predictable and prevents the table from
becoming an unbounded generic configuration language.

`is_sensitive` is included for future-proofing, but v1 generic runtime settings
are non-secret. The v1 API should reject writes to sensitive rows or exclude
them from the runtime snapshot.

Do not store default values in the DB. Defaults stay in code. The API can
compute and display fallback values from code/env when needed.

---

## Alembic Seeding Rules

Settings catalog rows should be inserted by Alembic DDL/DML.

Future migrations should use idempotent upserts that update metadata but
preserve user override values:

```sql
INSERT INTO application_settings (
    key,
    value_type,
    category,
    description,
    apply_mode,
    is_sensitive
)
VALUES (...)
ON CONFLICT (key) DO UPDATE SET
    value_type = EXCLUDED.value_type,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    apply_mode = EXCLUDED.apply_mode,
    is_sensitive = EXCLUDED.is_sensitive,
    updated_at = now();
```

The migration must not overwrite `value` on conflict.

Rationale:

- New releases can add settings.
- Metadata can evolve.
- User overrides survive upgrades.
- Removing configurability remains an explicit migration decision.

---

## Runtime Config Model

Create a dedicated Pydantic model for the runtime-configurable subset. This
model should live in shared code, not in `src/app`, because producers and
consumers should be able to use the same typed shape without importing app DB
code.

Suggested location:

```text
src/common/runtime_settings/
  __init__.py
  config.py      # RuntimeConfig Pydantic model
  cache.py       # sync snapshot reader and atomic replacement
  schema.py      # API/event DTOs
  events.py      # RabbitMQ fanout publisher/listener helpers
  client.py      # REST snapshot client for non-app containers
```

Example model:

```python
class RuntimeConfig(BaseModel):
    HTTP_REQUEST_TIMEOUT: int = Field(default=60, ge=1)
    NEO4J_QUERY_TIMEOUT: int = Field(default=10, ge=1)
    GRAPH_UI_MAX_NODES_TO_EXPAND: int = Field(default=20, ge=1)
    GRAPH_UI_MAX_NODE_LABEL_CHARS: int = Field(default=10, ge=4)
    CONNECTOR_SCAN_POLL_INTERVAL: int = Field(default=5000, ge=500)
    RECENT_ACTIONS_LIMIT: int = Field(default=5, ge=1, le=50)
    TIMEZONE: str = "UTC"
    UI_DATETIME_FORMAT: str = "%b %d, %Y %I:%M %p"
    UI_DATE_FORMAT: str = "%b %d, %Y"
    AUGMENTATION_HISTORY_TURNS: int = Field(default=5, ge=0)
    ES_CHAIN_MAX_RESULTS: int = Field(default=5, ge=1)
    MAX_MCP_ITERATIONS: int = Field(default=3, ge=1)
    FF_NEO4J_USE_PROVIDER_PIPELINE: bool = False
```

The exact validators should mirror the current behavior in `Settings`, plus any
existing bounds such as `RECENT_ACTIONS_LIMIT` being between 1 and 50.

Validation should be code/Pydantic-driven. DB metadata identifies what is
configurable and how to present broad types, but it should not become the
source of validation truth.

---

## Initial Runtime-Configurable Settings

Limit v1 to settings that are non-secret and safe to apply dynamically:

```text
HTTP_REQUEST_TIMEOUT
NEO4J_QUERY_TIMEOUT
GRAPH_UI_MAX_NODES_TO_EXPAND
GRAPH_UI_MAX_NODE_LABEL_CHARS
CONNECTOR_SCAN_POLL_INTERVAL
RECENT_ACTIONS_LIMIT
TIMEZONE
UI_DATETIME_FORMAT
UI_DATE_FORMAT
AUGMENTATION_HISTORY_TURNS
ES_CHAIN_MAX_RESULTS
MAX_MCP_ITERATIONS
FF_NEO4J_USE_PROVIDER_PIPELINE
```

These settings currently affect API request behavior, Dash UI behavior, graph
limits, search/chat context size, and other cheap runtime decisions.

Keep these out of v1:

```text
DATABASE_URL
CONNECTOR_ENCRYPTION_KEY
RABBITMQ_URL
NEO4J_URI
NEO4J_USERNAME
NEO4J_PASSWORD
ELASTICSEARCH_URL
ELASTIC_PASSWORD
OPENAI_API_KEY
LLM_MODEL
GITHUB_MCP_TOKEN
ATLASSIAN_MCP_TOKEN
GITHUB_MCP_SERVER_URL
ATLASSIAN_MCP_SERVER_URL
```

Some of these could become dynamic later, but they require explicit reconnect
or client lifecycle handling. V1 should only include settings that satisfy the
dynamic-without-restart requirement.

---

## App-Side Resolution

Inside the FastAPI app, build the effective runtime config from the existing
`settings` singleton plus DB overrides:

```text
base = RuntimeConfig from values already parsed by settings
overrides = non-null values from application_settings
effective = RuntimeConfig.validate(base + overrides)
```

Rationale:

- Preserves current env and `.env` behavior.
- Avoids duplicating environment parsing in the DB resolver.
- Keeps reset behavior simple: `NULL` returns to `settings`, which already
  represents env/default.
- Lets the existing `Settings` class continue to support CLI and bootstrap use.

Invalid persisted overrides should not prevent startup. If a bad DB value is
found, the resolver should log an error, ignore that override, and fall back to
env/default for that key. Write APIs should still reject invalid candidates
before commit.

---

## Runtime Settings Cache

`runtime_settings` should be a synchronous in-memory snapshot reader.

Reads:

```python
runtime_settings.get("HTTP_REQUEST_TIMEOUT")
runtime_settings.get_int("RECENT_ACTIONS_LIMIT")
runtime_settings.get_bool("FF_NEO4J_USE_PROVIDER_PIPELINE")
```

Method-style access is preferred because it makes dynamic reads visually
distinct from `settings.KEY`. Attribute-style access can be added as migration
convenience, but new code should prefer methods.

Refresh:

```text
load full effective snapshot
validate as RuntimeConfig
atomically replace current snapshot
```

The refresh operation should replace the entire snapshot, not patch individual
keys. This avoids drift after missed events and keeps bulk updates coherent.

Any code path that currently stores runtime-configurable values in module
constants must be migrated. For example:

```python
TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT
```

should become a runtime read at the point of use.

---

## Settings REST API

Suggested endpoints:

```text
GET   /api/v1/settings
PATCH /api/v1/settings
PATCH /api/v1/settings/{key}
POST  /api/v1/settings/reset
POST  /api/v1/settings/{key}/reset
GET   /api/v1/settings/runtime-snapshot
```

`GET /api/v1/settings` should return source-aware rows for the UI:

```json
{
  "key": "HTTP_REQUEST_TIMEOUT",
  "value": null,
  "effective_value": 60,
  "source": "env",
  "value_type": "integer",
  "category": "runtime",
  "description": "HTTP request timeout in seconds.",
  "apply_mode": "dynamic",
  "is_sensitive": false,
  "updated_at": "2026-08-03T00:00:00Z"
}
```

`source` should be one of:

```text
db
env
default
```

`PATCH /api/v1/settings` should support bulk updates as the primary write path:

```json
{
  "updates": {
    "TIMEZONE": "Asia/Kolkata",
    "HTTP_REQUEST_TIMEOUT": 90
  }
}
```

Bulk update flow:

```text
1. Load catalog rows for requested keys.
2. Reject unknown keys.
3. Build full candidate effective RuntimeConfig.
4. Validate candidate config through Pydantic.
5. Persist all changed values in one DB transaction.
6. Refresh the current app process runtime_settings cache.
7. Publish RabbitMQ settings.changed event.
8. Return effective values and propagation status.
```

Reset flow:

```text
set application_settings.value = NULL
```

The API should support lightweight optimistic concurrency on writes using
`updated_at` or an equivalent row revision. If a row changed since the UI loaded
it, return `409 Conflict` rather than silently overwriting another session's
change.

---

## RabbitMQ Propagation

The existing command-and-control exchange is targeted and command-status
oriented. Runtime settings propagation should be modeled separately as a
fanout invalidation event.

Add a new exchange:

```text
runtime_config_events
type: fanout
durable: true
```

Each running process that maintains a runtime settings cache declares its own
queue:

```text
queue name: runtime_config.<process_role>.<instance_id>
durable: false
exclusive: true
auto_delete: true
bound exchange: runtime_config_events
```

The exchange should be declared in `src/app/scripts/init_rabbitmq.py` and also
declared idempotently by publishers/listeners at runtime.

Event body:

```json
{
  "event_type": "settings.changed",
  "changed_keys": ["TIMEZONE", "HTTP_REQUEST_TIMEOUT"],
  "issued_at": "2026-08-03T00:00:00Z"
}
```

The event must not carry setting values. It is an invalidation signal only.
Receivers fetch the latest full snapshot from the authoritative source.

Reliability model:

```text
Postgres = durable source of truth
RabbitMQ fanout = live invalidation signal for currently running processes
startup refresh = recovery from missed events
```

If DB commit succeeds but RabbitMQ publish fails, the settings API should still
return success for the saved setting and include/report a propagation warning.
The updating app process should already refresh its local cache before
returning.

No global settings version is needed in v1. Receivers can simply refresh the
full snapshot for every event. Duplicate refreshes are acceptable because
settings changes should be rare and the snapshot is small.

---

## Process Integration

### FastAPI and Dash App

Startup:

```text
1. Load effective runtime settings from Postgres plus settings/env/default.
2. Initialize runtime_settings cache.
3. Start a background RabbitMQ fanout listener.
```

On settings update:

```text
1. Commit DB changes.
2. Refresh local runtime_settings cache synchronously.
3. Publish settings.changed event.
4. Return response.
```

The app should also listen to the fanout exchange so multiple app workers or
replicas refresh when another worker handles the update.

### Producer Daemons

Producer images currently avoid importing `src/app` and fetch connector config
through the app REST API. Runtime settings should follow the same boundary.

Producer daemon mode should wire the common runtime settings infrastructure.
However, scan/test child processes should fetch a fresh runtime snapshot at
startup rather than relying on the daemon parent's in-memory cache.

Rationale:

- The daemon spawns children using `subprocess.Popen`.
- Parent memory is not a reliable propagation mechanism for child processes.
- Fetching a snapshot at scan/test startup is cheap and deterministic.

### Signal Consumer

The long-running signal consumer should initialize a runtime settings cache and
listen for fanout invalidation events.

Changes should apply to new work, not interrupt in-flight message processing.
A message handler should capture or read a stable snapshot at the start of
processing and finish with that snapshot.

### Failure Behavior

RabbitMQ listener startup failure should be non-fatal.

If live propagation cannot start:

```text
log warning
continue with startup snapshot/env/default behavior
```

If an event is received but refresh fails:

```text
keep last known good snapshot
log warning
```

This preserves local development and avoids making runtime config propagation a
hard dependency for basic process startup.

---

## CLI and Local Development

Individual applications must continue to run from CLI using environment
variables and code defaults.

For app processes, `Settings` remains the bootstrap/env/default source.

For non-app processes, the shared runtime settings module should support:

```text
1. API snapshot fetch when API_SERVER is configured and reachable.
2. Env/default fallback when API is not available.
```

The first implementation should keep this simple. Do not duplicate the whole
app settings system in producers. The app API remains the authoritative source
for DB-backed runtime overrides.

---

## Implementation Implications

Call sites that should migrate from `settings` to `runtime_settings` include
runtime-safe settings in:

```text
src/app/ai_agent/
src/app/api/graph/
src/app/api/search/
src/app/dash_app/
src/app/common/timezone.py
```

Pay special attention to module-level constants such as:

```python
TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT
```

These must become dynamic reads at use time or module-level wrappers backed by
`runtime_settings`.

Bootstrap/static settings should continue to use `settings`, including:

```text
DATABASE_URL
CONNECTOR_ENCRYPTION_KEY
```

Infrastructure connection settings should remain out of v1 unless and until
the owning client lifecycle is explicitly designed:

```text
RABBITMQ_URL
NEO4J_URI
ELASTICSEARCH_URL
LLM provider/API credentials
```

---

## Testing Strategy

Unit tests:

- Effective precedence: DB override, env value, default.
- Reset behavior sets DB value to `NULL`.
- Unknown keys are rejected.
- Bulk update is atomic.
- Full candidate validation rejects invalid combinations or invalid values.
- Invalid persisted overrides fall back to env/default and report/log errors.
- Runtime cache reads are synchronous and return the latest snapshot after
  refresh.
- Snapshot replacement is atomic from the reader perspective.

API tests:

- `GET /api/v1/settings` returns source-aware metadata.
- `PATCH /api/v1/settings` validates, persists, refreshes local cache, and
  attempts propagation.
- Reset endpoints clear DB overrides.
- Optimistic concurrency returns `409 Conflict` for stale writes.
- Sensitive rows are not editable in v1.

RabbitMQ tests:

- Fanout exchange can be declared idempotently.
- Listener declares exclusive auto-delete queue.
- `settings.changed` event causes a full snapshot refresh.
- Duplicate events cause harmless duplicate refreshes.
- Refresh failure keeps last known good snapshot.
- Publish failure after DB commit produces a propagation warning, not a failed
  settings save.

Integration tests:

- FastAPI/Dash process observes settings changes without restart.
- Multiple app processes can refresh through fanout.
- Producer scan/test child fetches current runtime snapshot at startup.
- Signal consumer applies changed settings to subsequent message processing.

---

## Summary

The design keeps configuration responsibilities separated:

```text
Code defaults and env parsing:
  Settings / RuntimeConfig in code

Durable UI overrides:
  Postgres application_settings.value

Dynamic reads:
  runtime_settings in-memory snapshot

Live propagation:
  RabbitMQ fanout invalidation event
```

This satisfies the original requirements while keeping v1 focused. The system
can expose selected settings in the UI, persist changes, apply them without
restart, preserve CLI/env behavior, and avoid putting bootstrap credentials or
encryption keys into Postgres.

---

## Implementation Plan

### Phase 1 — DB Model + Migration  `[phase:db-model]`  ✅ DONE

**Goal:** Create the `application_settings` table and seed it with the initial
catalog of runtime-configurable settings.

**Files to create/modify:**
- `src/app/db/models/application_settings.py` — New SQLAlchemy model
- `src/app/db/models/__init__.py` — Register new model
- Alembic migration revision — DDL + seed data

**Model details:**
- Use `application_settings` as `__tablename__`.
- Mirror the schema from §Database Schema: `id`, `key` (unique, varchar),
  `value` (JSONB, nullable), `value_type` (varchar, checked), `category`
  (varchar, nullable), `description` (text, nullable), `apply_mode` (varchar,
  checked), `is_sensitive` (bool, default false), `created_at`, `updated_at`.
- Store keys as `UPPER_CASE` matching env var names.

**Seed data:** Insert a row for each of the 13 settings in *Initial
Runtime-Configurable Settings*. Use idempotent `ON CONFLICT DO UPDATE` that
preserves existing `value` (so user overrides survive future upgrades).

**Checkpoint** `[chk:db-model]`:
- ✅ `alembic upgrade head` succeeds.
- ✅ `alembic downgrade -1` rolls back cleanly.
- ✅ `SELECT * FROM application_settings` returns 13 seeded rows.
- ✅ `CommandStatus` model still works — no regressions.

**Tests:** `test_application_settings_model.py` (`@pytest.mark.unit`)  ✅ DONE

- ✅ Table has correct columns and constraints.
- ✅ `key` is unique.
- ✅ `value` can be `NULL`.
- ✅ `value_type` and `apply_mode` accept valid values and reject invalid ones.

---

### Phase 2 — Shared RuntimeConfig + Cache  `[phase:shared-config]`  ✅ DONE

**Goal:** Create the `RuntimeConfig` Pydantic model and the synchronous
in-memory cache in `src/common/runtime_settings/` so both app and non-app
processes can import it without pulling in `src.app`.

**Files to create:**
- `src/common/runtime_settings/__init__.py`
- `src/common/runtime_settings/config.py` — `RuntimeConfig(BaseModel)` with
  all 13 fields, validators, and defaults matching the current `Settings`.
- `src/common/runtime_settings/cache.py` — `RuntimeConfigCache` class:
  - `get(key)` / `get_int(key)` / `get_bool(key)` typed accessors.
  - `refresh(config: RuntimeConfig)` — atomic snapshot replacement.
  - `current() -> RuntimeConfig` — returns the current snapshot.
  - Thread-safe via `threading.Lock` or `copy-on-write` pattern.

**No external dependencies** — this module must not import from `src.app` or
require a DB connection. It is pure data + Pydantic.

**Checkpoint** `[chk:shared-config]`:
- ✅ `RuntimeConfig` validates all 13 fields correctly.
- ✅ `RuntimeConfigCache` returns defaults before any `refresh()` call.
- ✅ `refresh()` atomically replaces the snapshot.
- ✅ `get_int()` raises `TypeError` for bool fields, `get_bool()` for non-bool.
- ✅ Module can be imported from both `src.app` and `src.connectors` processes.

**Tests:** `test_runtime_config_model.py` (`@pytest.mark.unit`)  ✅ DONE

- ✅ Default values match `Settings` defaults.
- ✅ `RECENT_ACTIONS_LIMIT` rejects values < 1 and > 50.
- ✅ `NEO4J_QUERY_TIMEOUT` rejects values < 1.
- ✅ `TIMEZONE` validates via `ZoneInfo`.
- ✅ `FF_NEO4J_USE_PROVIDER_PIPELINE` accepts only `bool`.
- ✅ Cache getters work correctly.

---

### Phase 3 — REST API  `[phase:rest-api]`  ✅ DONE

**Goal:** Expose settings CRUD via REST API endpoints, backed by the DB model
and the RuntimeConfig for validation.

**Files to create:**
- `src/app/api/settings/v1/` with `__init__.py`, `router.py`, `service.py`,
  `models.py`. Follow the existing pattern from `commands/v1/`.

**Endpoints:**
- `GET  /api/v1/settings` — List all settings with source-aware metadata.
- `PATCH /api/v1/settings` — Bulk update (primary write path).
- `PATCH /api/v1/settings/{key}` — Single-key update.
- `POST /api/v1/settings/reset` — Bulk reset all overrides to `NULL`.
- `POST /api/v1/settings/{key}/reset` — Reset one key to `NULL`.
- `GET  /api/v1/settings/runtime-snapshot` — Returns the effective
  `RuntimeConfig` JSON (used by non-app processes).

**Service layer behavior:**
- Bulk update: load catalog rows, reject unknown keys, build candidate
  `RuntimeConfig`, validate through Pydantic, persist in one transaction,
  refresh local `runtime_settings` cache, publish RabbitMQ event (Phase 5
  adds the actual broker — phase 3 can no-op the publish or log it).
- Source precedence: `db` if `value IS NOT NULL`, else `env`, else `default`.
- Invalid persisted overrides: log error, fall back to env/default.
- Optimistic concurrency: include `updated_at` in write checks → `409 Conflict`.

**Router registration:** In `src/app/main.py`:
```python
from app.api.settings.v1.router import router as settings_v1_router
app.include_router(settings_v1_router, prefix="/api/v1")
```

**Checkpoint** `[chk:rest-api]`:
- ✅ `GET /api/v1/settings` returns 13 rows with correct `source` values.
- ✅ `PATCH /api/v1/settings` with valid values updates DB and returns success.
- ✅ `PATCH /api/v1/settings` with unknown key returns `422`.
- ✅ `PATCH /api/v1/settings` with out-of-range value returns `422`.
- ✅ `POST /api/v1/settings/{key}/reset` sets `value` to `NULL`.
- ✅ `GET /api/v1/settings/runtime-snapshot` returns a valid `RuntimeConfig`.
- ✅ `409 Conflict` on stale `updated_at`.

**Tests:**
- ✅ Unit: `test_settings_service.py` (`@pytest.mark.unit`) — precedence logic,
  source resolution, candidate validation, reset behavior, optimistic concurrency.
- ✅ Integration: `test_settings_api.py` (`@pytest.mark.integration`, `server`) —
  full HTTP round-trips against the running app.

---

### Phase 4 — Call Site Migration  `[phase:call-site-migration]`  ✅ DONE

**Goal:** Replace `settings` reads with `runtime_settings` reads at all call
sites for the 13 runtime-configurable settings.

**Pattern:**
Replace module-level constants:
```python
# Before
TIMEOUT_SECONDS = settings.HTTP_REQUEST_TIMEOUT

# After
from app.runtime_settings import runtime_settings

# At point of use:
timeout = runtime_settings.get_int("HTTP_REQUEST_TIMEOUT")
```

**Files to migrate** (in order of dependency):

| File | Setting(s) | Migration |
|---|---|---|
| `src/app/dash_app/pages/chat.py` | `HTTP_REQUEST_TIMEOUT` | Remove `TIMEOUT_SECONDS` constant, read at use |
| `src/app/dash_app/pages/connectors/callbacks.py` | `HTTP_REQUEST_TIMEOUT` | Same |
| `src/app/dash_app/pages/graph/callbacks/catalog.py` | `HTTP_REQUEST_TIMEOUT` | Same |
| `src/app/dash_app/pages/graph/callbacks/context_menu.py` | `HTTP_REQUEST_TIMEOUT` | Same |
| `src/app/dash_app/pages/graph/callbacks/expansion.py` | `HTTP_REQUEST_TIMEOUT` | Same |
| `src/app/dash_app/pages/graph/callbacks/query.py` | `HTTP_REQUEST_TIMEOUT` | Same |
| `src/app/dash_app/pages/search.py` | `HTTP_REQUEST_TIMEOUT` | Inline read |
| `src/app/ai_agent/chains/neo4j_chain.py` | `NEO4J_QUERY_TIMEOUT` | Inline read |
| `src/app/api/graph/v1/query.py` | `NEO4J_QUERY_TIMEOUT` | Inline read |
| `src/app/api/graph/v1/service.py` | `NEO4J_QUERY_TIMEOUT` | Inline read |
| `src/app/ai_agent/mcp_integration/tool_executor.py` | `HTTP_REQUEST_TIMEOUT` | Inline read |
| `src/app/common/timezone.py` | `TIMEZONE` | Read from `runtime_settings` |

**Create:** `src/app/runtime_settings.py` — thin module that initializes the
cache from `settings` + DB on startup, and exports a module-level
`runtime_settings` instance. This is the app-specific entry point that wires
the shared `RuntimeConfigCache` to the app's `Settings` and DB.

**Checkpoint** `[chk:call-site-migration]`:
- ✅ All module-level `TIMEOUT_SECONDS` constants removed.
- ✅ All migrated call sites use `runtime_settings.get_*()`.
- ✅ `pylint` and `mypy` pass on all modified files.
- ✅ Existing tests pass with same behavior.

**Tests:** No new tests needed — existing coverage should validate that
behavior is preserved. Run the full test suite to confirm.

✅ 995 unit tests pass, 14 integration tests pass — no regressions.

---

### Phase 5 — RabbitMQ Propagation  `[phase:rabbitmq-propagation]`  ✅ DONE

**Goal:** Add the `runtime_config_events` fanout exchange and wire listeners
so that all running processes refresh their cache when settings change.

**Files to create/modify:**

- `src/common/runtime_settings/events.py` — RabbitMQ event publisher and
  listener helpers:
  - `publish_settings_changed(changed_keys, connection)` — returns `bool`.
  - `listen_for_settings_changed(cache, connection, callback)`
  - Exchange declaration: `runtime_config_events` (fanout, durable).

- `src/app/scripts/init_rabbitmq.py` — Add `runtime_config_events` exchange
  declaration (local constant, not imported from `common`).

- `src/app/main.py` — Wire fanout listener in the `lifespan` context manager:
  - DB overrides loaded at startup.
  - RabbitMQ listener started as background task.
  - `get_rabbitmq_connection()` accessor for the settings API.
  - Listener startup failure is non-fatal (log warning, continue).

- `src/app/runtime_settings.py` — Added `load_db_overrides_from_session()`.

- `src/app/api/settings/v1/service.py` — `bulk_update()` and `update_single()`
  now call `publish_settings_changed()` after DB commit.  Returns a
  `propagation_warning` string when publish fails.

- `src/app/api/settings/v1/models.py` — Added `propagation_warning` field to
  `SettingResponse`.

**Event body:**
```json
{
  "event_type": "settings.changed",
  "changed_keys": ["TIMEZONE", "HTTP_REQUEST_TIMEOUT"],
  "issued_at": "2026-08-03T00:00:00Z"
}
```

**Receive flow:**
1. Listener receives event.
2. Calls `load_db_overrides_from_session()` which fetches the latest effective
   config from DB and refreshes the runtime settings cache.
3. If DB query fails, keeps last known good snapshot, logs warning.

**Failure behavior:**
- Listener startup failure → log warning, continue with env/default.
- Publish failure after DB commit → log warning, return `propagation_warning`,
  settings save still succeeds.
- Refresh failure → keep last good snapshot, log warning.

**Phase 3 integration:** The settings API service calls
`publish_settings_changed()` after a successful DB commit.

**Checkpoint** `[chk:rabbitmq-propagation]`:
- ✅ `init_rabbitmq.py` declares the fanout exchange.
- ✅ Listener starts and binds without errors.
- ✅ `PATCH /api/v1/settings` publishes a `settings.changed` event.
- ✅ Receiving process refreshes its cache (verified via log output).
- ✅ Duplicate events cause harmless duplicate refreshes.
- ✅ Publish failure after DB commit does not roll back the settings change.

**Tests:** `test_settings_rabbitmq.py` (`@pytest.mark.rabbitmq`)  ✅ DONE

- ✅ Exchange is declared idempotently.
- ✅ Listener queue is exclusive, auto-delete.
- ✅ Event triggers cache refresh.
- ✅ Publish failure does not abort DB commit.

---

### Phase 6 — Dash Settings UI  `[phase:dash-ui]`  ✅ DONE

**Goal:** Replace the placeholder settings page with a functional UI that lets
users view and edit runtime-configurable settings.

**Files to modify:**
- `src/app/dash_app/pages/settings.py` — Replaced placeholder with a full
  settings editor.
- `tests/test_settings_ui.py` — New integration tests for the settings UI.

**UI layout:**
- Grouped by `category` (e.g. "Network", "Graph", "UI", "Search", "Feature
  Flags").
- Each setting row shows: key name, current effective value, description, and
  source indicator (`db` / `env` / `default`).
- Editable fields: text input for strings, number input for integers, toggle
  for booleans.
- "Reset to default" button per row.
- "Save All" button for bulk update.
- Success/failure feedback using Dash `dcc.Store` + `dcc.ConfirmDialog`.

**Data flow:**
1. Page loads → `GET /api/v1/settings` → populate UI.
2. User edits → "Save All" → `PATCH /api/v1/settings` → refresh UI.
3. User clicks "Reset" → `POST /api/v1/settings/{key}/reset` → refresh UI.

**Checkpoint** `[chk:dash-ui]`:
- ✅ Settings page loads and displays all 13 settings with correct values.
- ✅ Editing a string value persists and reflects in the UI.
- ✅ Editing an integer value enforces min/max bounds.
- ✅ Toggling a boolean works.
- ✅ Reset restores env/default value.
- ✅ Source indicator (`db` / `env` / `default`) is accurate.
- ✅ Error feedback shown for invalid values.

**Tests:** `test_settings_ui.py` (`@pytest.mark.integration`, `server`)  ✅ DONE

- ✅ Dashboard renders settings correctly.
- ✅ Edit → save → verify flow.
- ✅ Invalid input shows error feedback.
- ✅ Reset restores default.

---

### Phase 7 — Non-App Process Integration  `[phase:non-app-integration]`  ✅ DONE

**Goal:** Wire the runtime settings infrastructure into producer daemons and
the signal consumer so they can read effective settings and refresh on changes.

**Files created:**
- `src/common/runtime_settings/client.py` — REST snapshot client for non-app
  processes that cannot import `src.app`:
  - `fetch_runtime_snapshot(api_base_url) -> RuntimeConfig`
  - Falls back to env/default if API is unreachable.
  - Logs a WARNING on connection or validation failure.

**Files modified:**
- `src/connectors/producers/daemon_common.py` — module-level `RuntimeConfigCache`
  (`runtime_cache`), refreshed at daemon startup and at each scan/test child
  startup so child processes get a fresh snapshot without inheriting the
  parent's cache. Additionally, a background daemon thread is started in
  `run_daemon()` that runs `listen_for_settings_changed()` from `events.py`
  in its own asyncio event loop using `aio_pika`, so the daemon refreshes its
  cache on every `settings.changed` event without needing a restart. Thread
  startup failure is non-fatal (log warning, continue with startup snapshot).
- Signal consumer (`src/connectors/consumers/main.py`) — module-level
  `RuntimeConfigCache` (`runtime_cache`), refreshed at consumer startup in
  `main()`. A background asyncio task is started via `asyncio.ensure_future`
  wrapping `listen_for_settings_changed()` to receive live invalidation events.
  Per-message stable snapshot capture via `runtime_cache.current()` in the
  `consume_queue()` message loop.
- `src/common/runtime_settings/__init__.py` — exports `fetch_runtime_snapshot`.

**Key constraint:** Scan/test child processes (spawned via `subprocess.Popen`)
must fetch a fresh snapshot at startup rather than inheriting the parent's
cache — satisfied by `run_scan()` and `run_test()` each calling
`runtime_cache.refresh(fetch_runtime_snapshot(...))` at the top of their body.

**Checkpoint** `[chk:non-app-integration]`:
- ✅ `RuntimeConfig` can be imported inside a connector process without triggering
  `src.app` imports.
- ✅ Producer daemon starts with env/default when API is unreachable.
- ✅ Signal consumer captures a stable snapshot at startup of each message.
- ✅ `fetch_runtime_snapshot()` returns a valid `RuntimeConfig` or falls back
  gracefully.
- ✅ RabbitMQ fanout listener is wired in both daemon (daemon thread) and consumer
  (async background task) for live invalidation.
- ✅ `run_scan()` and `run_test()` fetch fresh snapshots at child startup.

**Tests:** `test_settings_client.py` (`@pytest.mark.unit`)  ✅ DONE

- ✅ `fetch_runtime_snapshot()` parses API response correctly.
- ✅ Fallback to env/default on connection error, timeout, HTTP error.
- ✅ Fallback on invalid JSON or Pydantic validation errors.
- ✅ Timeout parameter is passed through to `requests.get`.
- ✅ Trailing slashes on `api_base_url` are stripped.
- ✅ `RuntimeConfig` importable from `sys.path` without `src.app`.

---

## Developer Validation Checklist

Use the following checklist to manually verify that the runtime settings system
is working correctly end-to-end.

### Prerequisites

- Backing services are running: `docker compose up -d postgres neo4j rabbitmq`
- App is running: `PYTHONPATH=src uvicorn app.main:app --reload`
- Virtual environment is activated: `source .venv/bin/activate`

### 1. Bootstrap / Env Defaults

```bash
# Verify the API returns all 13 settings with correct source/values.
curl -s http://localhost:8000/api/v1/settings/ | python -m json.tool | head -20
```

Expected:
- 13 items returned.
- Each item has `source` set to `"env"` or `"default"` (unless previously
  overridden via the API).
- `effective_value` matches the code defaults from `RuntimeConfig`.

### 2. Override a Setting via API

```bash
# Change a string setting.
curl -s -X PATCH http://localhost:8000/api/v1/settings/ \
  -H "Content-Type: application/json" \
  -d '{"updates": {"TIMEZONE": "Asia/Kolkata", "HTTP_REQUEST_TIMEOUT": 90}}'
```

Expected:
- Response includes `"updated": {"TIMEZONE": "Asia/Kolkata", ...}`.
- `propagation_warning` is `null` (or a string if RabbitMQ is unavailable).

```bash
# Verify the change is reflected.
curl -s http://localhost:8000/api/v1/settings/TIMEZONE | python -m json.tool
```

Expected: `"source": "db"`, `"effective_value": "Asia/Kolkata"`.

### 3. Verify Validation

```bash
# Unknown key → 422
curl -s -X PATCH http://localhost:8000/api/v1/settings/ \
  -H "Content-Type: application/json" \
  -d '{"updates": {"DATABASE_URL": "bad"}}'

# Out-of-range value → 422
curl -s -X PATCH http://localhost:8000/api/v1/settings/ \
  -H "Content-Type: application/json" \
  -d '{"updates": {"RECENT_ACTIONS_LIMIT": 999}}'
```

Expected: Both return a `422` status with a detail message.

### 4. Reset a Setting

```bash
curl -s -X POST http://localhost:8000/api/v1/settings/TIMEZONE/reset
curl -s http://localhost:8000/api/v1/settings/TIMEZONE | python -m json.tool
```

Expected: `"source"` is `"env"` or `"default"`, `"value"` is `null`.

### 5. Runtime Snapshot Endpoint

```bash
curl -s http://localhost:8000/api/v1/settings/runtime-snapshot | python -m json.tool
```

Expected: A flat JSON object with all 13 `RuntimeConfig` keys and their current
effective values.

### 6. Dash Settings UI

- Open `http://localhost:8000/app/settings` in a browser.
- Verify all 13 settings are displayed, grouped by category.
- Edit a string value (e.g. TIMEZONE), click "Save All Changes".
- Verify success feedback appears and the value persists after page reload.
- Toggle a boolean (e.g. FF_NEO4J_USE_PROVIDER_PIPELINE), save, verify.
- Click "Reset" on a single row, verify it returns to env/default.
- Click "Reset All to Default", verify all values reset.

### 7. Client Library (Non-App Processes)

```bash
# Test fetch_runtime_snapshot from Python directly.
cd src && python -c "
from common.runtime_settings.client import fetch_runtime_snapshot
config = fetch_runtime_snapshot('http://localhost:8000')
print('HTTP_REQUEST_TIMEOUT:', config.HTTP_REQUEST_TIMEOUT)
print('TIMEZONE:', config.TIMEZONE)
"
```

Expected: Prints the expected values.

```bash
# Test fallback when API is unreachable.
python -c "
from common.runtime_settings.client import fetch_runtime_snapshot
config = fetch_runtime_snapshot('http://localhost:9999')
print('Got defaults:', config.HTTP_REQUEST_TIMEOUT)
"
```

Expected: Logs a WARNING and prints default value (60).

### 8. Live Propagation (requires RabbitMQ)

```bash
# Start two terminals watching the app logs:
# Terminal 1: docker compose logs -f app
# Terminal 2: docker compose logs -f signal-consumer  (or run locally)

# Change a setting via the API.
curl -s -X PATCH http://localhost:8000/api/v1/settings/ \
  -H "Content-Type: application/json" \
  -d '{"updates": {"TIMEZONE": "America/New_York"}}'
```

Expected:
- Terminal 1: `Published settings.changed event: keys=['TIMEZONE']`.
- Terminal 2 (if consumer is running and has RabbitMQ listener):
  `Received settings.changed event: keys=['TIMEZONE']`.

---

## Adding a New Runtime Setting

This guide covers all layers that must be touched when adding a new
runtime-configurable setting — from the shared model to the Dash UI.

### Step 1: Add to `Settings` (env var bootstrap)

**File:** `src/app/settings.py`

Add the field to the `Settings` class with a sensible default. This ensures
Docker Compose and CLI users can still configure it via environment variables.

```python
# Example: add a search page size setting
SEARCH_PAGE_SIZE: int = 20
```

### Step 2: Add to `RuntimeConfig` (shared Pydantic model)

**File:** `src/common/runtime_settings/config.py`

Add the field with matching type, default, and validation constraints. This is
the **single source of truth** for the runtime-configurable setting list — all
other layers derive their list from here.

```python
# Under the appropriate section comment:
# ── Search ───────────────────────────────────────────────────────────
SEARCH_PAGE_SIZE: int = Field(default=20, ge=1, le=100)
```

### Step 3: Add to `application_settings` seed (Alembic migration)

**File:** `src/app/alembic/versions/..._add_application_settings_table.py`

Add a row to the `VALUES (...)` list in the seed INSERT. Use the idempotent
`ON CONFLICT` pattern so existing user overrides survive.

```sql
('SEARCH_PAGE_SIZE', 'integer', 'search',
 'Number of results per page in search views.', 'dynamic', false),
```

If the migration has already been applied in production, create a new migration
that inserts the row idempotently:

```sql
INSERT INTO application_settings (key, value_type, category, description, apply_mode, is_sensitive)
VALUES ('SEARCH_PAGE_SIZE', 'integer', 'search',
        'Number of results per page in search views.', 'dynamic', false)
ON CONFLICT (key) DO UPDATE SET
    value_type = EXCLUDED.value_type,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    apply_mode = EXCLUDED.apply_mode,
    is_sensitive = EXCLUDED.is_sensitive,
    updated_at = now();
```

### Step 4: Add to app wiring

**File:** `src/app/runtime_settings.py`

Add the mapping in `_build_initial_config()` so the app's env-variable value
is seeded into the runtime cache at startup:

```python
return RuntimeConfig(
    ...
    SEARCH_PAGE_SIZE=app_settings.SEARCH_PAGE_SIZE,
)
```

### Step 5: Add to `RuntimeSnapshotResponse`

**File:** `src/app/api/settings/v1/models.py`

Add the field so the snapshot API returns it for non-app processes:

```python
class RuntimeSnapshotResponse(BaseModel):
    ...
    SEARCH_PAGE_SIZE: int
```

### Step 6: Update DB override resolution

**File:** `src/app/api/settings/v1/service.py`

If the new setting needs special resolution logic (e.g., it depends on another
setting's value), update `_resolve_effective_config()`. For simple settings
this step is a no-op — the generic `RuntimeConfig(**overrides)` validation
handles it.

### Step 7: Add to category metadata (UI grouping)

**File:** `src/app/dash_app/pages/settings.py`

If the setting uses a new category (e.g. `"search"`), add it to
`CATEGORY_META` and `CATEGORY_ORDER`:

```python
CATEGORY_META["search"] = {"label": "Search", "icon": "fa-solid fa-search"}
CATEGORY_ORDER.insert(-1, "search")  # before feature_flags
```

If the setting belongs to an existing category (e.g. `"network"`), no change
is needed — the UI already groups by category.

### Step 8: Update tests

Update these test files to account for the new setting:

| Test file | Change |
|---|---|
| `tests/test_runtime_config_model.py` | Add default/validation tests for the new field |
| `tests/test_settings_api.py` | Bump expected count from 13 to 14; add override/reset test for new key |
| `tests/test_settings_ui.py` | Bump count assertions if any; add edit-save-verify test |

### Step 9: Migrate call sites

Find all places that currently read `settings.SEARCH_PAGE_SIZE` and convert
them to use `runtime_settings.get_int("SEARCH_PAGE_SIZE")`. If the old read
is a module-level constant, move it inline to benefit from dynamic updates.

### Summary: Touch Points Diagram

```text
                          ┌───────────────────┐
                          │  app/settings.py   │  ← Step 1: Env var bootstrap
                          └────────┬──────────┘
                                   │
                          ┌────────▼──────────┐
                          │ common/            │
                          │ runtime_settings/  │  ← Step 2: Shared model
                          │   config.py        │
                          └────────┬──────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
  ┌───────────────┐      ┌──────────────────┐    ┌───────────────────┐
  │ Alembic seed  │      │ app/              │    │ app/api/settings/ │
  │ migration     │      │ runtime_settings  │    │ v1/models.py      │
  │ (DDL row)     │      │ .py (wiring)      │    │ (snapshot model)  │
  └───────────────┘      └──────────────────┘    └───────────────────┘
  Step 3                   Step 4                   Step 5
                                                          
                                   ┌─────────────────┐
                                   │ app/dash_app/    │
                                   │ pages/settings   │
                                   │ .py (category)   │  ← Step 7 (if new cat)
                                   └─────────────────┘
```

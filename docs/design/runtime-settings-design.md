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

# Plan 016: Add remaining `.env.example` settings to runtime settings catalog

## Status

- **Priority**: P1 (settings completeness — 41 settings not yet in the catalog)
- **Effort**: L (spans 5 buckets × 9 layers + Phase 2 producer wiring)
- **Risk**: MEDIUM
- **Depends on**: Plan 010–015 (v1 runtime settings infrastructure — DONE)
- **Category**: feature / configuration management
- **Planned at**: 2026-08-09
- **Status**: READY

## Why this matters

The v1 runtime settings system (Plans 010–015) launched with 13 settings in
the `application_settings` catalog and `RuntimeConfig` model. The `.env.example`
file contains ~54 additional settings that are read by application code but
have **no** DB-backed row — they can only be changed by editing `.env` and
restarting containers.

This plan adds the remaining ~41 qualifying settings (excluding bootstrap-only
values like `DATABASE_URL`, Docker-only `POSTGRES_*`, and future InfluxDB) in
a single migration, then extends the Settings page UI, API, sensitive-value
masking, and producer wiring in phases.

## Discovery

Audited on 2026-08-09 via code search across `src/`, `docker-compose.yml`,
`.env.example`, and the existing `RuntimeConfig` / `settings.py` / `Settings`
page.

| Question | Answer |
|---|---|
| Settings in current `RuntimeConfig` (`config.py`) | 13 |
| Settings in `.env.example` not in the 13 | ~54 |
| Qualifying for catalog (excl. bootstrap/Docker/InfluxDB/test) | **41** |
| Settings that are **sensitive** (tokens, passwords) | 8 |
| Settings read via `os.getenv()` — bypassing `settings.py` entirely | ~20 |
| Settings that are completely dead (no code reads them) | 2 (`NEO4J_MODE`, `RUN_COLLAB_DB_VALIDATION`) |
| Zero-code-consumption settings kept for future-proofing | 0 (InfluxDB excluded per decision) |
| DB constraint on `apply_mode` | None → `'restart'` is allowed (free-text) |

## Design decisions

All decisions reached via the grill-me process:

1. **Sensitive settings in catalog**: Yes — `is_sensitive=true`, API masks on
   read, UI renders masked input fields for entry. (Design doc's original
   "v1 non-goal" is superseded.)
2. **apply_mode values**: Both `'dynamic'` and `'restart'` — free-text, no
   CHECK constraint.
3. **Bootstrap/topology settings in catalog**: Yes — `apply_mode: restart`.
   Changing these will require a container restart, but the UI documents that.
4. **Dead config removal**: `NEO4J_MODE` and `RUN_COLLAB_DB_VALIDATION`
   removed from `.env.example`, `docker-compose.yml`, and docs.
5. **InfluxDB**: Excluded entirely from this plan — no catalog rows, no
   RuntimeConfig fields, no code changes.
6. **`RABBITMQ_URL`**: `is_sensitive: true` — embeds credentials in the URL.
7. **Producer/connector settings (Bucket D)**: Two-phase — Phase 1 adds
   catalog rows + UI, Phase 2 wires producer containers to read from the
   app API instead of `os.getenv()`.

## Settings inventory

### Bucket A: AI / LLM → `category: ai` — 14 settings

| Key | Type | Sensitive | Mode |
|-----|------|-----------|------|
| `LLM_PROVIDER` | string | No | restart |
| `LLM_MODEL` | string | No | dynamic |
| `OPENAI_API_KEY` | string | **Yes** | restart |
| `OPENAI_API_URL` | string | No | restart |
| `CUSTOM_API_TOKEN` | string | **Yes** | restart |
| `CUSTOM_API_URL` | string | No | restart |
| `CUSTOM_LLM_MODEL` | string | No | dynamic |
| `MAX_TOKENS` | integer | No | dynamic |
| `GITHUB_MCP_ENABLED` | boolean | No | dynamic |
| `GITHUB_MCP_SERVER_URL` | string | No | restart |
| `GITHUB_MCP_TOKEN` | string | **Yes** | restart |
| `ATLASSIAN_MCP_ENABLED` | boolean | No | dynamic |
| `ATLASSIAN_MCP_SERVER_URL` | string | No | restart |
| `ATLASSIAN_MCP_TOKEN` | string | **Yes** | restart |

### Bucket B: System → `category: system` — 8 settings

| Key | Type | Sensitive | Mode |
|-----|------|-----------|------|
| `NEO4J_ENABLED` | boolean | No | restart |
| `NEO4J_URI` | string | No | restart |
| `NEO4J_USERNAME` | string | No | restart |
| `NEO4J_PASSWORD` | string | **Yes** | restart |
| `ELASTICSEARCH_ENABLED` | boolean | No | restart |
| `ELASTICSEARCH_URL` | string | No | restart |
| `ELASTIC_PASSWORD` | string | **Yes** | restart |
| `RABBITMQ_URL` | string | **Yes** | restart |

### Bucket C: Logging → `category: system` — 5 settings

| Key | Type | Sensitive | Mode |
|-----|------|-----------|------|
| `LOG_LEVEL` | string | No | restart |
| `LOG_FORMAT` | string | No | restart |
| `ENABLE_FILE_LOGGING` | boolean | No | restart |
| `LOG_DIR` | string | No | restart |
| `LOG_SIGNAL_DUMPS` | boolean | No | restart |

### Bucket D: Connectors / Producers → `category: connectors` — 14 settings

| Key | Type | Sensitive | Mode |
|-----|------|-----------|------|
| `COMMIT_DAYS_LIMIT` | integer | No | dynamic |
| `PULL_REQUEST_DAYS_LIMIT` | integer | No | dynamic |
| `IDENTITY_REFRESH_DAYS` | integer | No | dynamic |
| `MAX_TEAM_SIZE` | integer | No | dynamic |
| `JIRA_LOOKBACK_DAYS` | integer | No | dynamic |
| `JIRA_MAX_RESULTS_PER_PAGE` | integer | No | dynamic |
| `CONFLUENCE_LOOKBACK_DAYS` | integer | No | dynamic |
| `JIRA_EPIC_TEAM_FIELD` | string | No | dynamic |
| `JIRA_ISSUE_TEAM_FIELD` | string | No | dynamic |
| `JIRA_EPIC_START_DATE_FIELD` | string | No | dynamic |
| `JIRA_EPIC_DUE_DATE_FIELD` | string | No | dynamic |
| `GITHUB_TOKEN_FOR_PUBLIC_REPOS` | string | **Yes** | dynamic |
| `API_SERVER` | string | No | restart |
| `CONFIGURATION_SOURCE` | string | No | restart |

## Implementation steps

### Step 1: Add fields to `Settings` (env var bootstrap)

**File:** `src/app/settings.py`

Add every new setting to the `Settings` class. Many already exist (e.g.
`ELASTICSEARCH_ENABLED`, `NEO4J_ENABLED`, `OPENAI_API_KEY`, `LLM_MODEL`).
Add the missing ones that are currently read via `os.getenv()`:

- `MAX_TOKENS: int = 16000`
- `CUSTOM_LLM_MODEL: str = ""`
- `OPENAI_API_URL: str = "https://api.openai.com/v1/chat/completions"`
- `CUSTOM_API_URL: str = ""`
- `CUSTOM_API_TOKEN: str = ""`
- `LLM_PROVIDER: str = "openai"`
- `LOG_LEVEL: str = "INFO"` (and sibling logging vars)
- `COMMIT_DAYS_LIMIT: int = 60` (and sibling producer vars)
- All JIRA_*, CONFLUENCE_* field settings
- `API_SERVER: str = "http://app:8000/"`
- `CONFIGURATION_SOURCE: str = "SERVER"`
- `GITHUB_TOKEN_FOR_PUBLIC_REPOS: str = ""`
- `LOG_SIGNAL_DUMPS: bool = False`

Use `Field()` with validation aliases where sensible.

### Step 2: Extend `RuntimeConfig` (shared Pydantic model)

**File:** `src/common/runtime_settings/config.py`

Add all 41 settings grouped under their section comments:

```python
# ── AI / LLM ──────────────────────────────────────────────────────────
LLM_PROVIDER: str = "openai"
LLM_MODEL: str = "gpt-5"
MAX_TOKENS: int = Field(default=16000, ge=1000)
GITHUB_MCP_ENABLED: StrictBool = False
ATLASSIAN_MCP_ENABLED: StrictBool = False
# (exclude OPENAI_API_KEY etc. — secrets go in catalog but NOT in RuntimeConfig)

# ── System ────────────────────────────────────────────────────────────
NEO4J_ENABLED: StrictBool = False
# (exclude NEO4J_URI, NEO4J_USERNAME etc. — bootstrap topology)

# ── Connectors ─────────────────────────────────────────────────────────
COMMIT_DAYS_LIMIT: int = Field(default=60, ge=1)
PULL_REQUEST_DAYS_LIMIT: int = Field(default=60, ge=1)
IDENTITY_REFRESH_DAYS: int = Field(default=7, ge=0)
MAX_TEAM_SIZE: int = Field(default=100, ge=1)
JIRA_LOOKBACK_DAYS: int = Field(default=90, ge=1)
JIRA_MAX_RESULTS_PER_PAGE: int = Field(default=100, ge=1, le=500)
CONFLUENCE_LOOKBACK_DAYS: int = Field(default=60, ge=1)
JIRA_EPIC_TEAM_FIELD: str = "Team"
JIRA_ISSUE_TEAM_FIELD: str = "Team"
JIRA_EPIC_START_DATE_FIELD: str = "created"
JIRA_EPIC_DUE_DATE_FIELD: str = "duedate"
GITHUB_TOKEN_FOR_PUBLIC_REPOS: str = ""
API_SERVER: str = "http://app:8000/"
CONFIGURATION_SOURCE: str = "SERVER"

# ── Logging ───────────────────────────────────────────────────────────
LOG_LEVEL: str = "INFO"
LOG_FORMAT: str = "JSON"
ENABLE_FILE_LOGGING: StrictBool = False
LOG_DIR: str = "logs"
LOG_SIGNAL_DUMPS: StrictBool = False
```

**SECRETS**: `OPENAI_API_KEY`, `CUSTOM_API_TOKEN`, `GITHUB_MCP_TOKEN`,
`ATLASSIAN_MCP_TOKEN`, `CUSTOM_API_URL`, `OPENAI_API_URL`, `NEO4J_PASSWORD`,
`ELASTIC_PASSWORD`, `RABBITMQ_URL`, `CONNECTOR_ENCRYPTION_KEY` — these go into
the DB catalog but **NOT** into `RuntimeConfig`. They are bootstrap/secret
values that should never be served by the runtime snapshot API. The `GET
/api/v1/settings` endpoint returns their metadata but masks the `value` and
`effective_value` fields (see Step 6).

### Step 3: Add Alembic migration (seed catalog rows)

**File:** `src/app/alembic/versions/..._add_remaining_settings.py`

Create a new migration that upserts all 41 catalog rows idempotently:

```sql
INSERT INTO application_settings (key, value_type, category, description, apply_mode, is_sensitive)
VALUES
    -- AI / LLM
    ('LLM_PROVIDER', 'string', 'ai', 'LLM provider selection (openai, custom).', 'restart', false),
    ('LLM_MODEL', 'string', 'ai', 'Model name for the LLM provider.', 'dynamic', false),
    ('OPENAI_API_KEY', 'string', 'ai', 'OpenAI API key.', 'restart', true),
    ('OPENAI_API_URL', 'string', 'ai', 'OpenAI API endpoint URL.', 'restart', false),
    ('CUSTOM_API_TOKEN', 'string', 'ai', 'Custom provider API token.', 'restart', true),
    ('CUSTOM_API_URL', 'string', 'ai', 'Custom provider endpoint URL.', 'restart', false),
    ('CUSTOM_LLM_MODEL', 'string', 'ai', 'Custom provider model name.', 'dynamic', false),
    ('MAX_TOKENS', 'integer', 'ai', 'Maximum tokens before history pruning.', 'dynamic', false),
    ('GITHUB_MCP_ENABLED', 'boolean', 'ai', 'Enable GitHub MCP chain.', 'dynamic', false),
    ('GITHUB_MCP_SERVER_URL', 'string', 'ai', 'GitHub MCP server URL.', 'restart', false),
    ('GITHUB_MCP_TOKEN', 'string', 'ai', 'GitHub PAT for MCP server.', 'restart', true),
    ('ATLASSIAN_MCP_ENABLED', 'boolean', 'ai', 'Enable Atlassian MCP chain.', 'dynamic', false),
    ('ATLASSIAN_MCP_SERVER_URL', 'string', 'ai', 'Atlassian MCP server URL.', 'restart', false),
    ('ATLASSIAN_MCP_TOKEN', 'string', 'ai', 'Atlassian MCP API token.', 'restart', true),

    -- System
    ('NEO4J_ENABLED', 'boolean', 'system', 'Enable Neo4j graph database integration.', 'restart', false),
    ('NEO4J_URI', 'string', 'system', 'Neo4j Bolt URI.', 'restart', false),
    ('NEO4J_USERNAME', 'string', 'system', 'Neo4j username.', 'restart', false),
    ('NEO4J_PASSWORD', 'string', 'system', 'Neo4j password.', 'restart', true),
    ('ELASTICSEARCH_ENABLED', 'boolean', 'system', 'Enable Elasticsearch integration.', 'restart', false),
    ('ELASTICSEARCH_URL', 'string', 'system', 'Elasticsearch endpoint URL.', 'restart', false),
    ('ELASTIC_PASSWORD', 'string', 'system', 'Elasticsearch password.', 'restart', true),
    ('RABBITMQ_URL', 'string', 'system', 'RabbitMQ AMQP connection URL.', 'restart', true),

    -- Logging
    ('LOG_LEVEL', 'string', 'system', 'Logging level (DEBUG, INFO, WARNING, ERROR).', 'restart', false),
    ('LOG_FORMAT', 'string', 'system', 'Log format (JSON or TEXT).', 'restart', false),
    ('ENABLE_FILE_LOGGING', 'boolean', 'system', 'Enable persistent file logging.', 'restart', false),
    ('LOG_DIR', 'string', 'system', 'Log file directory path.', 'restart', false),
    ('LOG_SIGNAL_DUMPS', 'boolean', 'system', 'Enable signal payload dumps to disk.', 'restart', false),

    -- Connectors
    ('COMMIT_DAYS_LIMIT', 'integer', 'connectors', 'Lookback days for commit sync.', 'dynamic', false),
    ('PULL_REQUEST_DAYS_LIMIT', 'integer', 'connectors', 'Lookback days for PR sync.', 'dynamic', false),
    ('IDENTITY_REFRESH_DAYS', 'integer', 'connectors', 'Days before re-scanning identity data.', 'dynamic', false),
    ('MAX_TEAM_SIZE', 'integer', 'connectors', 'Max team members before skipping.', 'dynamic', false),
    ('JIRA_LOOKBACK_DAYS', 'integer', 'connectors', 'Lookback days for Jira issue sync.', 'dynamic', false),
    ('JIRA_MAX_RESULTS_PER_PAGE', 'integer', 'connectors', 'Max results per Jira API page.', 'dynamic', false),
    ('CONFLUENCE_LOOKBACK_DAYS', 'integer', 'connectors', 'Lookback days for Confluence sync.', 'dynamic', false),
    ('JIRA_EPIC_TEAM_FIELD', 'string', 'connectors', 'Jira custom field name for epic team.', 'dynamic', false),
    ('JIRA_ISSUE_TEAM_FIELD', 'string', 'connectors', 'Jira custom field name for issue team.', 'dynamic', false),
    ('JIRA_EPIC_START_DATE_FIELD', 'string', 'connectors', 'Jira field name for epic start date.', 'dynamic', false),
    ('JIRA_EPIC_DUE_DATE_FIELD', 'string', 'connectors', 'Jira field name for epic due date.', 'dynamic', false),
    ('GITHUB_TOKEN_FOR_PUBLIC_REPOS', 'string', 'connectors', 'GitHub token for accessing public repos.', 'dynamic', true),
    ('API_SERVER', 'string', 'connectors', 'Base URL for the API server.', 'restart', false),
    ('CONFIGURATION_SOURCE', 'string', 'connectors', 'Config source (SERVER or FILE).', 'restart', false)
ON CONFLICT (key) DO UPDATE SET
    value_type = EXCLUDED.value_type,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    apply_mode = EXCLUDED.apply_mode,
    is_sensitive = EXCLUDED.is_sensitive,
    updated_at = now();
```

The `ON CONFLICT` clause must NOT overwrite `value` — existing user overrides
are preserved.

### Step 4: Wire app startup (`_build_initial_config()`)

**File:** `src/app/runtime_settings.py`

Extend `_build_initial_config()` to map every new `Settings` field to its
`RuntimeConfig` field:

```python
def _build_initial_config() -> RuntimeConfig:
    return RuntimeConfig(
        # existing 13...
        HTTP_REQUEST_TIMEOUT=app_settings.HTTP_REQUEST_TIMEOUT,
        ...
        # Bucket A
        LLM_PROVIDER=app_settings.LLM_PROVIDER,
        LLM_MODEL=app_settings.LLM_MODEL,
        MAX_TOKENS=app_settings.MAX_TOKENS,
        GITHUB_MCP_ENABLED=app_settings.GITHUB_MCP_ENABLED,
        ATLASSIAN_MCP_ENABLED=app_settings.ATLASSIAN_MCP_ENABLED,
        # Bucket B
        NEO4J_ENABLED=app_settings.NEO4J_ENABLED,
        # Bucket C
        LOG_LEVEL=app_settings.LOG_LEVEL,
        LOG_FORMAT=app_settings.LOG_FORMAT,
        ENABLE_FILE_LOGGING=app_settings.ENABLE_FILE_LOGGING,
        LOG_DIR=app_settings.LOG_DIR,
        LOG_SIGNAL_DUMPS=app_settings.LOG_SIGNAL_DUMPS,
        # Bucket D
        COMMIT_DAYS_LIMIT=app_settings.COMMIT_DAYS_LIMIT,
        PULL_REQUEST_DAYS_LIMIT=app_settings.PULL_REQUEST_DAYS_LIMIT,
        IDENTITY_REFRESH_DAYS=app_settings.IDENTITY_REFRESH_DAYS,
        MAX_TEAM_SIZE=app_settings.MAX_TEAM_SIZE,
        JIRA_LOOKBACK_DAYS=app_settings.JIRA_LOOKBACK_DAYS,
        JIRA_MAX_RESULTS_PER_PAGE=app_settings.JIRA_MAX_RESULTS_PER_PAGE,
        CONFLUENCE_LOOKBACK_DAYS=app_settings.CONFLUENCE_LOOKBACK_DAYS,
        JIRA_EPIC_TEAM_FIELD=app_settings.JIRA_EPIC_TEAM_FIELD,
        JIRA_ISSUE_TEAM_FIELD=app_settings.JIRA_ISSUE_TEAM_FIELD,
        JIRA_EPIC_START_DATE_FIELD=app_settings.JIRA_EPIC_START_DATE_FIELD,
        JIRA_EPIC_DUE_DATE_FIELD=app_settings.JIRA_EPIC_DUE_DATE_FIELD,
        GITHUB_TOKEN_FOR_PUBLIC_REPOS=app_settings.GITHUB_TOKEN_FOR_PUBLIC_REPOS,
        API_SERVER=app_settings.API_SERVER,
        CONFIGURATION_SOURCE=app_settings.CONFIGURATION_SOURCE,
    )
```

### Step 5: Extend `RuntimeSnapshotResponse`

**File:** `src/app/api/settings/v1/models.py`

Add all 41 fields to `RuntimeSnapshotResponse` matching `RuntimeConfig`.

**Important**: This model is consumed by non-app processes (producers,
consumers) via `GET /api/v1/settings/runtime-snapshot`. Adding topology
settings like `API_SERVER` here creates a circular reference concern — a
producer that fetches `API_SERVER` from the snapshot is trying to learn its
own upstream from the upstream. The producer should already know `API_SERVER`
from its env. Keep these fields but document that producers must have env
fallbacks.

### Step 6: Handle sensitive settings in API and resolution

**Files:**
- `src/app/api/settings/v1/service.py`
- `src/app/api/settings/v1/query.py`

Two sub-steps:

**6a. Skip sensitive values from runtime snapshot.** In
`_resolve_effective_config()`, skip rows where `is_sensitive=True` — these
secrets should not appear in the `RuntimeConfig` that gets served to producer
containers via the snapshot endpoint.

**6b. Mask sensitive values in GET response.** In `get_all_settings()`, when
`row.is_sensitive is True` and `effective_value` is a non-empty string,
replace `effective_value` with a partially masked version:

```python
def _mask_value(value: str) -> str:
    """Return a partially masked string for sensitive settings.

    Examples:
        "sk-abc...xyz"              →  "sk-abc…xyz"
        "ghp_abc123def456"          →  "ghp_abc…456"
        "amqp://user:pass@host:5672" →  "amqp://…@host:5672"
        "short"                     →  "****"
    """
    if len(value) <= 8:
        return "****"
    prefix_len = max(6, len(value) // 3)
    suffix_len = max(3, len(value) // 4)
    return value[:prefix_len] + "…" + value[-suffix_len:]
```

The raw `value` (DB override) and the masked `effective_value` must both be
masked in the API response. The source badge still functions normally.

### Step 7: Update Dash Settings UI for sensitive & restart settings

**File:** `src/app/dash_app/pages/settings.py`

**7a. Add new categories.** The `system` category needs a `CATEGORY_META` entry
(it already exists for `network/graph/connectors/ui/ai/feature_flags`):

```python
CATEGORY_META["system"] = {"label": "System", "icon": "fa-solid fa-server"}
CATEGORY_ORDER.insert(0, "system")  # first category
```

**7b. Render `type="password"` inputs for sensitive settings.** In
`_build_setting_row()`, when `setting["is_sensitive"]` is true, render the
input with `type="password"` instead of `type="text"`:

```python
if setting.get("is_sensitive"):
    input_component = dbc.Input(
        id=input_id,
        type="password",
        value=effective,
        style={**INPUT_STYLE, "width": "300px"},
        placeholder="(sensitive — enter to change)",
    )
```

**7c. Show `apply_mode` badge.** Add a small badge next to each setting row
indicating `dynamic` vs `restart`. For `restart` settings, also add a tooltip
or warning text: "This setting takes effect after a container restart."

**7d. Add `system` category to `CATEGORY_ORDER`**.

### Step 8: Update tests

**Files:**

| File | Change |
|---|---|
| `tests/test_settings_api.py` | Bump `test_returns_13_settings` from 13 to 54. Add tests for sensitive masking, restart apply_mode, unknown key rejection for new keys. |
| `tests/test_settings_ui_integration.py` | Bump count from 13 to 54. Verify system category renders. |
| `tests/test_settings_ui.py` | Add tests for password input rendering when `is_sensitive=true`. |
| `tests/test_settings_service.py` | Add tests for `_mask_value()`, sensitive-value exclusion from snapshot, `_resolve_source` for new types. |
| `tests/test_settings_client.py` | Update test payloads to include new fields. |
| `tests/test_runtime_config_model.py` | Add default/validation tests for every new field. |
| `tests/test_settings_rabbitmq.py` | Update expected snapshot shape. |

### Step 9: Remove dead config

**9a. `.env.example`** — Remove these lines:
```diff
- NEO4J_MODE=chain
- RUN_COLLAB_DB_VALIDATION=1
```

**9b. `docker-compose.yml`** — Remove this line from the `app` service
environment section:
```diff
- NEO4J_MODE: ${NEO4J_MODE}
```

**9c. Docs** — Remove these lines from
`docs/project-plan/completed/project-plan-analytics-configurability-collaboration-network.md`:
```diff
- - Requires `RUN_COLLAB_DB_VALIDATION=1`
- RUN_COLLAB_DB_VALIDATION=1 pytest tests/test_collaboration_query_integration.py -q -s
```

### Step 10 — Phase 2: Migrate producer/consumer call sites

This step is the second phase for Bucket D settings. It should be implemented
**after** the DB migration (Step 3) has been applied to the target environment.

**10a. Producer daemon wiring.** In `src/connectors/producers/daemon_common.py`,
replace `os.getenv("COMMIT_DAYS_LIMIT")` etc. with reads from the runtime
snapshot fetched via `fetch_runtime_snapshot(API_SERVER)`:

```python
from common.runtime_settings.client import fetch_runtime_snapshot

snapshot = fetch_runtime_snapshot(api_server)
commit_days_limit = snapshot.COMMIT_DAYS_LIMIT
```

**10b. Consumer wiring.** In `src/connectors/consumers/main.py` and
`sinks/neo4j_sink.py`, replace `os.getenv("LOG_SIGNAL_DUMPS")` etc. with the
runtime settings cache already initialized in `main()`.

**10c. GitHub/Jira/Confluence producer files.** Replace `os.getenv()` calls in:
- `src/connectors/producers/github/fetch_github.py` (`COMMIT_DAYS_LIMIT`, `PULL_REQUEST_DAYS_LIMIT`)
- `src/connectors/producers/github/process_repo_signals.py` (`IDENTITY_REFRESH_DAYS`)
- `src/connectors/producers/github/process_teams.py` (`MAX_TEAM_SIZE`)
- `src/connectors/producers/jira/main.py` (`JIRA_LOOKBACK_DAYS`, `JIRA_MAX_RESULTS_PER_PAGE`)
- `src/connectors/producers/confluence/confluence_settings.py` (`CONFLUENCE_LOOKBACK_DAYS`)
- `src/connectors/producers/jira/map_jira.py` (`JIRA_EPIC_TEAM_FIELD`, `JIRA_ISSUE_TEAM_FIELD`, `JIRA_EPIC_START_DATE_FIELD`, `JIRA_EPIC_DUE_DATE_FIELD`)

**10d. `API_SERVER` / `CONFIGURATION_SOURCE`.** These are special — the
producer uses `API_SERVER` to contact the app. A producer cannot bootstrap
its own `API_SERVER` from the app's snapshot (chicken-and-egg). These must
continue to be read from env vars, not from runtime settings. Mark them
`apply_mode: restart` and keep the env-fallback in Step 1.

## Testing

- **Unit**: `pytest -m unit tests/test_settings_api.py tests/test_settings_service.py tests/test_settings_ui.py`
- **Integration**: `pytest -m integration tests/test_settings_ui_integration.py`
- **Manual**: Load Settings page, verify system/AI/connectors tabs show new settings, verify sensitive inputs render as password type, verify restart badge appears, verify value is masked in inputs.

## Rollback

- **Migration**: `alembic downgrade -1` on the new migration. All 41 rows are
  removed from `application_settings`. Existing user override values (not
  metadata) are lost. To preserve them, take a DB snapshot before applying.
- **Code**: Revert `RuntimeConfig`, `settings.py`, `RuntimeSnapshotResponse`,
  `_build_initial_config()`, `service.py`, `settings.py` (Dash page), and
  test files.
- **Dead config reversion**: Re-add the removed lines in `.env.example`,
  `docker-compose.yml`, and docs.
- **Phase 2**: Revert producer call sites to `os.getenv()`.
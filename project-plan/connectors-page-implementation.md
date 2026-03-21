# Plan: Connectors Page — Frontend, API & DB

**Status**: Not Started  
**Created**: March 15, 2026  
**Last Updated**: March 15, 2026

## Progress Summary
- [x] **Phase 1**: Database Layer (models, migration, seed data)
- [x] **Phase 2**: Encryption Utility
- [x] **Phase 3**: API Layer (router, service, query, models)
- [ ] **Phase 4**: Frontend (Dash UI — Github and Jira completed, test connection and other connectors pending)

---

## TL;DR
Add a "Connectors" page (after Graph in the sidebar) where users can view and configure 8 external integrations (GitHub, Jira, Slack, Teams, Confluence, Google Docs, SharePoint, Email). Each connector is represented by a card with a visual status indicator. Clicking a card navigates to a dedicated sub-page (`/app/connectors/{type}`) with a config form and a live "Test Connection" button. All config is stored in PostgreSQL across 9 tables; credentials are encrypted at rest using Fernet (local key).

---

## Decisions
- **Connectors in scope**: GitHub, Jira, Slack, Microsoft Teams, Confluence, Google Docs, SharePoint, Email
- **DB schema**: 9 tables total — one `connectors` base table (with a `config` JSONB column for connector-level settings) + one `{type}_configs` child table per connector for per-item rows (repos, channels, spaces, etc.)
- **No separate per-connector config tables**: Connector-level settings live in a `config` JSONB column on the `connectors` table — no `github_config`, `jira_config`, etc. (currently unused; reserved for future settings)
- **Child tables follow `{type}_configs` naming**: `github_configs`, `jira_configs`, `slack_configs`, etc. Each stores multiple rows (one per repo/project/channel) with an `encrypted_*` column for per-item credentials
- **No PostgreSQL native Enum**: `connector_type` and `status` use `String` columns; validation enforced by Python `enum.Enum` in the application layer (avoids painful ALTER TYPE migrations when adding new connectors)
- **Static connector registry in code**: `display_name` and icon are not stored in the DB — a hardcoded `CONNECTOR_REGISTRY` dict in the service layer maps connector type slugs to display metadata
- **Credentials in API responses**: Masked — never returned in cleartext
- **Connector detail**: Dedicated sub-page at `/app/connectors/{type}` (no modal)
- **Test Connection**: Stubbed in v1 (returns simulated OK/fail), real logic in Phase 2/4
- **Card status indicator**: `not_configured` (grey) / `connected` (green) / `error` (red)
- **Out of scope**: Actual connector polling/ingestion logic; OAuth flow; multi-instance per connector type

---

## Phase 1: Database Layer

### DB Schema (9 tables total)

| Table | Purpose |
|-------|---------|
| `connectors` | One row per connector type — status, enabled, `config` JSONB, timestamps |
| `github_configs` | Per-repo rows: `url`, `encrypted_access_token`, `branch_name_patterns` (JSONB), `extraction_sources` (JSONB) |
| `jira_configs` | Per-account rows: `url`, `email`, `encrypted_api_token` |
| `slack_configs` | Per-channel rows: `channel_id`, `channel_name` |
| `teams_configs` | Per-channel rows: `channel_id`, `channel_name` |
| `confluence_configs` | Per-space rows: `space_key`, `space_name` |
| `google_docs_configs` | Per-drive rows: `drive_id`, `drive_name` |
| `sharepoint_configs` | Per-site rows: `site_url` |
| `email_configs` | Per-account rows: `smtp_host`, `smtp_port`, `imap_host`, `imap_port`, `username`, `use_tls`, `encrypted_password` |

### Example data — GitHub connector

**`connectors` table** (one row, holds connector-level JSONB config):

| id | connector_type | status | enabled | config | last_tested_at | last_test_error |
|----|---------------|--------|---------|--------|----------------|-----------------|
| 1 | `github` | `connected` | true | `null` | 2026-03-15 10:00 | null |

**`github_configs` table** (one row per watched repo):

| id | connector_id | url | encrypted_access_token | branch_name_patterns | extraction_sources | enabled |
|----|-------------|-----|------------------------|----------------------|--------------------|---------|
| 1 | 1 | `https://github.com/shuvabrata/*` | `gAAAAA...` (Fernet) | `["(?:feature\|bugfix)/([A-Z]+-\\d+)"]` | `["branch", "commit_message"]` | true |
| 2 | 1 | `https://github.com/my-org/backend` | `gAAAAB...` (Fernet) | `null` | `["branch"]` | true |

### Implementation steps

- [x] **1. Create `connectors` SQLAlchemy model** at `app/db/models/connector.py`
   - `connector_type`: `String(50)`, `unique=True`, `nullable=False` — validated by Python `enum.Enum`, not a DB Enum type
   - `status`: `String(20)`, `nullable=False`, `default="not_configured"`
   - `enabled`: `Boolean`, `default=True`
   - `config`: `JSONB` (from `sqlalchemy.dialects.postgresql`), `nullable=True` — stores connector-level settings (currently unused; reserved for future settings)
   - `last_tested_at`: `DateTime(timezone=True)`, nullable
   - `last_test_error`: `String(1023)`, nullable
   - `created_at`: `DateTime(timezone=True)`, `server_default=func.now()`
   - `updated_at`: `DateTime(timezone=True)`, `server_default=func.now()`, `onupdate=func.now()`

- [x] **2. Create 8 `{type}_configs` SQLAlchemy models** at `app/db/models/connector_configs.py`
   - All share: `id` (PK), `connector_id` (FK → connectors.id), `enabled` (Boolean, default True), `created_at`, `updated_at`
   - `github_configs`: adds `url` (String, unique per connector), `encrypted_access_token` (Text), `branch_name_patterns` (JSONB, nullable — array of regex strings), `extraction_sources` (JSONB, nullable — e.g. `["branch", "commit_message"]`)
   - `jira_configs`: adds `url` (String — Jira base URL, e.g. `https://your-company.atlassian.net`), `email` (String), `encrypted_api_token` (Text)
   - `slack_configs`: adds `channel_id` (String), `channel_name` (String)
   - `teams_configs`: adds `channel_id` (String), `channel_name` (String)
   - `confluence_configs`: adds `space_key` (String), `space_name` (String)
   - `google_docs_configs`: adds `drive_id` (String), `drive_name` (String)
   - `sharepoint_configs`: adds `site_url` (String)
   - `email_configs`: adds `smtp_host`, `smtp_port` (Int), `imap_host`, `imap_port` (Int), `username` (String), `use_tls` (Boolean), `encrypted_password` (Text)

- [x] **3. Define static connector registry in code** at `app/api/connectors/v1/registry.py`
   ```python
   CONNECTOR_REGISTRY = {
       "github":      {"display_name": "GitHub",           "icon": "fa-brands fa-github"},
       "jira":        {"display_name": "Jira",             "icon": "fa-brands fa-jira"},
       "slack":       {"display_name": "Slack",            "icon": "fa-brands fa-slack"},
       "teams":       {"display_name": "Microsoft Teams",  "icon": "fa-brands fa-microsoft"},
       "confluence":  {"display_name": "Confluence",       "icon": "fa-brands fa-confluence"},
       "google_docs": {"display_name": "Google Docs",      "icon": "fa-brands fa-google"},
       "sharepoint":  {"display_name": "SharePoint",       "icon": "fa-brands fa-microsoft"},
       "email":       {"display_name": "Email",            "icon": "fa-solid fa-envelope"},
   }
   ```

- [x] **4. Register all new models** in `app/db/models/__init__.py`

- [x] **5. Generate Alembic schema migration**: `alembic revision --autogenerate -m "add connectors schema"`
   - Produces one migration covering all 9 new tables

- [x] **6. Add Alembic data migration** (separate revision) to seed the 8 base rows in `connectors`:
   ```python
   def upgrade():
       op.execute("""
           INSERT INTO connectors (connector_type, status, enabled)
           VALUES
               ('github', 'not_configured', false),
               ('jira', 'not_configured', false),
               ...
           ON CONFLICT (connector_type) DO NOTHING
       """)
   ```
   - Apply both via `alembic upgrade head`

---

## Phase 2: Encryption Utility

- [x] **7. Create `app/common/encryption.py`**
   - Uses `cryptography.fernet.Fernet`
   - `encrypt(value: str) -> str` and `decrypt(value: str) -> str`
   - Reads key from `settings.CONNECTOR_ENCRYPTION_KEY`
   - If key is missing/invalid, raises a clear startup error

- [x] **8. Add `CONNECTOR_ENCRYPTION_KEY`** to `app/settings.py` (optional field with empty default, validated at use time) and document in `.env.example`
   - To generate a key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

---

## Phase 3: API Layer

Follows the same layered pattern as `app/api/projects/v1/` (router → service → query).

- [x] **9. Create `app/api/connectors/v1/model.py`** — Pydantic models:
   - **Request models**:
     - `ConnectorConfigUpdateRequest`: `config: Optional[dict]` — body for `PATCH /connectors/{type}` (connector-level JSONB config; `null` clears)
     - Per-connector child item request models (e.g., `GithubConfigItemRequest`, `JiraConfigItemRequest`, etc.) — one per connector type, fields mirror the Phase 1 child table columns; credential fields accepted as plaintext (encrypted in service layer)
       - `GithubConfigItemRequest`: `url: str`, `access_token: Optional[str]`, `branch_name_patterns: Optional[List[str]] = None`, `extraction_sources: Optional[List[str]] = None`
       - `JiraConfigItemRequest`: `url: str`, `email: str`, `api_token: Optional[str]`
       - `SlackConfigItemRequest`: `channel_id: str`, `channel_name: str`
       - `TeamsConfigItemRequest`: `channel_id: str`, `channel_name: str`
       - `ConfluenceConfigItemRequest`: `space_key: str`, `space_name: str`
       - `GoogleDocsConfigItemRequest`: `drive_id: str`, `drive_name: str`
       - `SharepointConfigItemRequest`: `site_url: str`
       - `EmailConfigItemRequest`: `smtp_host: str`, `smtp_port: int`, `imap_host: str`, `imap_port: int`, `username: str`, `use_tls: bool`, `password: Optional[str]`
   - **Response models**:
     - `ConnectorStatus`: `connector_type`, `display_name` (from registry), `status`, `enabled`, `config`, `last_tested_at`, `last_test_error`
     - `ConnectorListResponse`: list of `ConnectorStatus`
     - Per-connector child item response models (e.g., `GithubConfigItem`, `JiraConfigItem`, etc.) — `encrypted_*` fields masked as `"********"` in responses, omitted if empty
     - `TestConnectionResponse`: `success: bool`, `message: str`

- [x] **10. Create `app/api/connectors/v1/query.py`** — async DB query functions:
   - `get_all_connectors(db)` — returns all 8 connector rows (guaranteed to exist after seed migration)
   - `get_connector(db, connector_type)` — fetch connector row + JSONB config
   - `update_connector_config(db, connector_type, config_dict)` — update JSONB config field
   - `update_connector_status(db, connector_type, status, last_tested_at=None, error=None)` — updates `status`, `last_test_error`, and `last_tested_at` (when provided) on the connector row
   - `get_configs(db, connector_type)` — fetch rows from `{type}_configs`
   - `upsert_config_item(db, connector_type, item_id: Optional[int], data)` — create (item_id=None) or update a child config row
   - `delete_config_item(db, connector_type, item_id)` — delete a child config row

- [x] **11. Create `app/api/connectors/v1/service.py`** — business logic:
    - `list_connectors(db)` — fetches all 8 rows, merges with `CONNECTOR_REGISTRY` for display metadata
    - `get_connector(db, connector_type)` — validates `connector_type`, returns connector row with JSONB config
    - `update_connector_config(db, connector_type, config)` — validates `connector_type`, saves JSONB config (allows `null` to clear)
    - `list_config_items(db, connector_type)` — returns child rows with credentials masked
    - `save_config_item(db, connector_type, item)` — encrypts credential fields, upserts child row
    - `delete_config_item(db, connector_type, item_id)` — deletes child row
    - `test_connection(db, connector_type)` — stub: calls `update_connector_status(status="connected", last_tested_at=now(), error=None)`, returns `{success: True, message: "Connection verified (stub)"}`; on simulated failure calls `update_connector_status(status="error", last_tested_at=now(), error="...")` and returns `{success: False, message: "..."}`
    - `delete_all_configs(db, connector_type)` — deletes all child rows, resets status to `not_configured`

- [x] **12. Create `app/api/connectors/v1/router.py`** — FastAPI routes:
    - `GET  /connectors/` → list all 8 connectors with status
    - `GET  /connectors/{type}` → get connector-level config
    - `PATCH /connectors/{type}` → update JSONB config
    - `GET  /connectors/{type}/configs` → list child config items (credentials masked)
    - `POST /connectors/{type}/configs` → add a child config item
    - `PUT  /connectors/{type}/configs/{id}` → update a child config item
    - `DELETE /connectors/{type}/configs/{id}` → delete a child config item
    - `POST /connectors/{type}/test` → test connection
    - `DELETE /connectors/{type}` → delete all configs, reset to `not_configured`
    - Validate `connector_type` against `CONNECTOR_REGISTRY`; unknown types return 404

- [x] **13. Register router in `app/main.py`**:
    ```python
    from app.api.connectors.v1.router import router as connectors_router
    app.include_router(connectors_router, prefix="/api/v1")
    ```

---

## Phase 4: Frontend (Dash)

- [x] **14. Update sidebar in `app/dash_app/layout.py`**:
    - Add `NavLink("Connectors", href="/app/connectors", ...)` after Graph, before Settings
    - Update `display_page` callback to handle `/app/connectors` and `/app/connectors/*` patterns

- [x] **15. Create `app/dash_app/pages/connectors/` folder** (modular, following graph page pattern):
    - `__init__.py`
    - `layout.py` — exports `get_layout()` (listing page) and `get_detail_layout(connector_type)` (detail page)
    - `components/connector_card.py` — card factory with Font Awesome icon, connector name, color-coded status badge
    - `components/config_forms.py` — per-connector form field definitions (dict of field specs per type)
    - `callbacks.py` — Dash callbacks for the connectors pages

- [x] **16. Connectors listing page (`/app/connectors`)**:
    - Fetches `GET /api/v1/connectors/` on page load
    - Renders 8 cards in a responsive grid (`dbc.Row` + `dbc.Col`)
    - Each card: Font Awesome icon (FA Brands for GitHub/Jira/Slack/Teams/Confluence, generic icons for others), connector name, status badge
    - Click on card triggers `dcc.Location` navigation to `/app/connectors/{type}`
    - Status badge: green circle (connected), grey circle (not_configured), red circle (error)

- [x] **17. Connector detail sub-pages (`/app/connectors/{type}`)**:
    - Breadcrumb: Connectors > {Connector Name}
    - Form fields per connector type:
      - Non-credential fields: visible text inputs pre-populated from existing config
      - Credential fields: password inputs — show `"••••••••"` placeholder if already configured, empty if not
    - "Save Configuration" button — two distinct calls depending on form section:
      - Connector-level config fields → `PATCH /api/v1/connectors/{type}` (updates JSONB config)
      - Child config item fields → `POST /api/v1/connectors/{type}/configs` (add) or `PUT /api/v1/connectors/{type}/configs/{id}` (update)
    - "Test Connection" button → `POST /api/v1/connectors/{type}/test` → inline success/error feedback
    - "Delete Configuration" button → `DELETE /api/v1/connectors/{type}` → redirects back to listing
    - Follows Executive Dashboard aesthetic (match existing `settings.py` style)

- [x] **18. Wire routing in `app/dash_app/layout.py`**:
    ```python
    elif pathname and pathname.startswith("/app/connectors/"):
        connector_type = pathname.split("/app/connectors/")[-1]
        return connectors.get_detail_layout(connector_type)
    elif pathname == "/app/connectors":
        return connectors.get_layout()
    ```

---

## Affected Files Summary

| File | Change |
|------|--------|
| `app/db/models/connector.py` | New — `Connector` SQLAlchemy model (base table with JSONB config) |
| `app/db/models/connector_configs.py` | New — 8 `{type}_configs` SQLAlchemy models |
| `app/db/models/__init__.py` | Add imports for all new models |
| `app/alembic/versions/<hash>_add_connectors_schema.py` | Autogenerated schema migration (9 tables) |
| `app/alembic/versions/<hash>_seed_connectors.py` | Data migration — inserts 8 base rows into `connectors` |
| `app/common/encryption.py` | New — Fernet encrypt/decrypt utility |
| `app/settings.py` | Add `CONNECTOR_ENCRYPTION_KEY` field |
| `app/api/connectors/v1/__init__.py` | New (empty) |
| `app/api/connectors/v1/registry.py` | New — `CONNECTOR_REGISTRY` dict (display names, icons) |
| `app/api/connectors/v1/model.py` | New — Pydantic request/response models |
| `app/api/connectors/v1/query.py` | New — async DB query functions |
| `app/api/connectors/v1/service.py` | New — business logic |
| `app/api/connectors/v1/router.py` | New — FastAPI routes |
| `app/main.py` | Register connectors router |
| `app/dash_app/layout.py` | Add nav link + routing for `/app/connectors/*` |
| `app/dash_app/pages/connectors/__init__.py` | New (empty) |
| `app/dash_app/pages/connectors/layout.py` | New — listing + detail page layouts |
| `app/dash_app/pages/connectors/components/connector_card.py` | New — card component factory |
| `app/dash_app/pages/connectors/components/config_forms.py` | New — per-connector form field specs |
| `app/dash_app/pages/connectors/callbacks.py` | New — Dash callbacks |

---

## Verification Checklist

1. `alembic upgrade head` — confirm all 9 new tables created + 8 seed rows in `connectors`
2. `GET /api/v1/connectors/` — returns list of 8 connectors, all `not_configured`, with display names from registry
3. `PATCH /api/v1/connectors/github` with a JSON body that includes a `config` object — confirm `config` JSONB updated
4. `POST /api/v1/connectors/github/configs` with `{"url": "https://github.com/my-org/*", "access_token": "ghp_..."}` — verify row created in `github_configs`
5. `SELECT encrypted_access_token FROM github_configs` — confirm value is Fernet ciphertext, not plaintext
6. `GET /api/v1/connectors/github/configs` — verify `access_token` is masked as `"********"` in response
7. `POST /api/v1/connectors/github/test` — returns stub success response
8. `PUT /api/v1/connectors/github/configs/{id}` — verify update works for URL and token independently
9. `DELETE /api/v1/connectors/github/configs/{id}` — verify row removed
10. `DELETE /api/v1/connectors/github` — all `github_configs` rows deleted, status resets to `not_configured`
11. `PATCH /api/v1/connectors/github` with `{"config": null}` — clears connector-level config
12. Unknown `connector_type` (e.g., `GET /api/v1/connectors/unknown`) returns 404
13. Navigate to `/app/connectors` — all 8 cards render with grey status badges
14. Click GitHub card → navigates to `/app/connectors/github`
15. Add a repo via the form → card status badge updates; repo appears in list

## Phase 4 Progress Note

- **Phase 4 implementation is complete. UI workflows still need manual testing.**

### UI Test Checklist (Phase 4)

**Global Checks:**
- [x] 1. `/app/connectors` renders 8 cards with correct names/icons/status badges
- [x] 2. Clicking a card navigates to `/app/connectors/{type}` and breadcrumb shows correct name
- [x] 3. Connector detail page loads config + items without errors
- [x] 4. Dark theme placeholder text is readable across all forms

**Per-Connector Workflows:**

- [x] **GitHub**
  - [x] Save connector-level config
  - [x] Add new item (repo)
  - [x] Edit item (pre-populates, persists)
  - [x] Delete item (removed from list)
  - [x] Secret fields masked (access token)
  - [ ] Test Connection button shows success
  - [x] Delete Configuration clears items

- [ ] **Jira**
  - [x] Save connector-level config
  - [x] Add new item (account)
  - [x] Edit item (pre-populates, persists)
  - [x] Delete item
  - [x] Secret fields masked (API token)
  - [ ] Test Connection button shows success
  - [x] Delete Configuration clears items

- [ ] **Slack**
  - [ ] Save connector-level config
  - [ ] Add new item (channel)
  - [ ] Edit item (pre-populates, persists)
  - [ ] Delete item
  - [ ] Test Connection button shows success
  - [ ] Delete Configuration clears items

- [ ] **Microsoft Teams**
  - [ ] Save connector-level config
  - [ ] Add new item (channel)
  - [ ] Edit item (pre-populates, persists)
  - [ ] Delete item
  - [ ] Test Connection button shows success
  - [ ] Delete Configuration clears items

- [ ] **Confluence**
  - [ ] Save connector-level config
  - [ ] Add new item (space)
  - [ ] Edit item (pre-populates, persists)
  - [ ] Delete item
  - [ ] Test Connection button shows success
  - [ ] Delete Configuration clears items

- [ ] **Google Docs**
  - [ ] Save connector-level config
  - [ ] Add new item (drive)
  - [ ] Edit item (pre-populates, persists)
  - [ ] Delete item
  - [ ] Test Connection button shows success
  - [ ] Delete Configuration clears items

- [ ] **SharePoint**
  - [ ] Save connector-level config
  - [ ] Add new item (site)
  - [ ] Edit item (pre-populates, persists)
  - [ ] Delete item
  - [ ] Test Connection button shows success
  - [ ] Delete Configuration clears items

- [ ] **Email**
  - [ ] Save connector-level config
  - [ ] Add new item (account)
  - [ ] Edit item (pre-populates, persists)
  - [ ] Delete item
  - [ ] Secret fields masked (password)
  - [ ] Test Connection button shows success
  - [ ] Delete Configuration clears items

---

## Further Considerations

1. **Encryption key bootstrap**: If `CONNECTOR_ENCRYPTION_KEY` is not set and the user tries to save credentials, the app should hard-fail with a clear error and print instructions to generate a key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. **One config instance per connector type**: This plan assumes one config per type (one GitHub org, one Jira instance). If multiple instances per type are needed in future, the schema can be extended by adding a `name` discriminator column to the `connectors` table. Deferred.

3. **OAuth flow**: Connectors like GitHub, Slack, Google Docs support OAuth. This plan uses API token/key-based auth only. OAuth is deferred to a later phase.

4. **Real connection testing**: The `test_connection` stub should be replaced with actual HTTP calls to each service's health/auth endpoint in Phase 2/4 when the connector polling/ingestion logic is implemented.

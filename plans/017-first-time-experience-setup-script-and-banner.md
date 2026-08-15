# Plan 017: First-Time Experience — Setup Script + Guided Banner

## Status

- **Priority**: P1 (user experience — first impression)
- **Effort**: M (4 independent work items: Bash script, DB migration, API field, Dash banner)
- **Risk**: LOW
- **Depends on**: 016 (runtime settings catalog — DONE)
- **Category**: feature / developer experience
- **Planned at**: 2026-08-15
- **Status**: READY

## Why this matters

A new user cloning this repo today faces a `.env.example` with 30+ `FIXME`
placeholders, no guidance on which are mandatory vs. optional, and a
`docker compose up -d` that fails silently if any backing service is
misconfigured. The first-time experience is hostile.

This plan delivers a zero-friction guided setup: a single `./setup.sh` command
that produces a working `.env` and launches the app, plus a subtle in-browser
banner that nudges toward optional-but-recommended settings without blocking
anything.

## Design decisions

All decisions reached via the grill-me process on 2026-08-15:

1. **Workflow**: Full Docker Compose only. Local-dev is out of scope (the
   developer already knows how to craft a `.env` by hand).
2. **Script language**: Bash (`scripts/setup.sh`). Zero dependencies beyond
   Docker. Matches the project's existing `entrypoint.sh` pattern.
3. **Script is additive only**: Never overwrites an existing `.env`. Only
   fills `FIXME` placeholders and missing values. Safe to re-run.
4. **Mandatory settings**: Owned entirely by the script. The DB `importance`
   column has no `mandatory` tier — the script can't read the DB (runs
   pre-Docker), so a DB "mandatory" value would be dead weight.
5. **Skipped optional values**: Written as commented-out lines
   (`# OPENAI_API_KEY=FIXME`) — invisible to the app, visible as hints to
   humans reading `.env`.
6. **`GITHUB_MCP_TOKEN` is already optional**: Verified 2026-08-15 with
   `ghcr.io/github/github-mcp-server:latest` (v1.4.0) — the server starts
   and `list-scopes` exits 0 with an empty token. No `docker-compose.yml`
   change needed.
7. **Later GitHub MCP config**: Re-run `./setup.sh` and enter the token at
   the prompt. The browser cannot apply it (the MCP server is a separate
   container that reads the token at boot).
8. **DB column**: `application_settings.importance` (String, default
   `'optional'`), values `'recommended'` / `'optional'`.
9. **Recommended settings**: `OPENAI_API_KEY` and `GITHUB_MCP_TOKEN` only.
   Everything else is `optional`.
10. **Banner**: Subtle, dismissable, between `top_menu` and page content.
    Thin muted-amber strip with left border accent. Dismissal persists per
    browser session via `dcc.Store`. Flags `recommended` settings where
    `source == "default"`.
11. **Connector creds**: Deferred to the existing browser Settings/Connectors
    page. Not in the script or banner.

## Implementation

### Work Item 1: `scripts/setup.sh` (Bash)

**File**: `scripts/setup.sh` (new)

**Behavior**:

```
./setup.sh                          # Interactive wizard
```

**Interactive flow**:

1. Check prerequisites: `docker` and `docker compose` on PATH.
2. If `.env` exists, offer: `[k]eep / [r]eset`. Default: keep.
3. Copy `.env.example` → `.env` (if reset or first run).
4. Prompt for mandatory settings (each with a sensible default; press Enter to accept):
   - PostgreSQL user, password, database (defaults: `postgres`/`postgres`/`postgres`)
   - Neo4j username, password (defaults: `neo4j`/`password`)
   - RabbitMQ user, password (defaults: `guest`/`guest`)
   - `DATABASE_URL` is derived from the chosen PostgreSQL values
   - `CONNECTOR_ENCRYPTION_KEY` — auto-generated Fernet key (only when unset)
   - `ELASTIC_PASSWORD` — cleared to empty (security is disabled in compose)
5. Guided optional prompts (skippable with Enter):
   - "GitHub personal access token? (optional, for GitHub MCP) [skip]"
   - "OpenAI API key? (optional, for AI Chat) [skip]"
   - Skipped values → commented-out in `.env` (`# OPENAI_API_KEY=FIXME`)
6. Offer to start: "Run `docker compose up -d` now? [Y/n]"
7. If yes: run `docker compose up -d`, wait for healthy, print
   `http://localhost:8000/app`.

**Idempotency**: Mandatory defaults and the Fernet key are only written when
the current value is a placeholder (`FIXME`/`fixme`/empty); existing values are
never overwritten. Optional values are only set when the user enters them in
the interactive prompt; otherwise they are commented out.

**Fernet key generation**: Use `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
If Python is unavailable, print instructions and abort (the user needs Python
for the app anyway).

### Work Item 2: Alembic migration — `importance` column

**Files**:
- `src/app/db/models/application_settings.py` — add `importance` column
- `src/app/alembic/versions/<rev>_add_importance_to_application_settings.py` — new migration

**Model change** (`application_settings.py`):

```python
importance: Mapped[str] = mapped_column(
    String(20), nullable=False, default="optional"
)
```

**Migration**: Add column with `server_default='optional'`, then backfill:

```sql
UPDATE application_settings SET importance = 'recommended'
WHERE key IN ('OPENAI_API_KEY', 'GITHUB_MCP_TOKEN');
```

### Work Item 3: Settings API — expose `importance`

**Files**:
- `src/app/api/settings/v1/models.py` — add `importance` to `SettingResponse`
- `src/app/api/settings/v1/service.py` — include `importance` in query results

**Model change** (`models.py`):

```python
class SettingResponse(BaseModel):
    # ... existing fields ...
    importance: str = "optional"  # "recommended" | "optional"
```

**Service change** (`service.py`): Include `row.importance` when building
`SettingResponse` objects in `get_all_settings()`.

### Work Item 4: Dash global banner

**Files**:
- `src/app/dash_app/layout.py` — add `html.Div(id="setup-banner")` between
  `top_menu` and the `dbc.Row`, plus `dcc.Store(id="banner-dismissed")`
- `src/app/dash_app/components/setup_banner.py` — new file with banner
  component and callback
- `src/app/dash_app/assets/executive-dashboard.css` — banner styles

**Layout change** (`layout.py`):

Insert between `top_menu` and the `dbc.Row`:

```python
dcc.Store(id="banner-dismissed", data=False),
html.Div(id="setup-banner"),
```

**Banner component** (`setup_banner.py`):

- Callback triggered by `url.pathname` (fires on every page navigation).
- Fetches `GET /api/v1/settings/` from `http://localhost:8000`.
- Finds rows where `importance == "recommended"` AND `source == "default"`.
- If none, returns empty `html.Div()` (hidden).
- If any, renders a thin strip:
  - Background: `#FFF8E1` (muted amber)
  - Left border: `3px solid #FFC107`
  - Text: "⚠️ N recommended settings not configured — <list>. Configure now →"
  - "Configure now" links to `/app/settings/runtime`
  - × dismiss button on the right
  - Typography: Inter, `FONT_SIZE_XSMALL` from `styles.py`
- Dismiss sets `banner-dismissed` store to `True`; banner stays hidden for
  the session.

**CSS** (`executive-dashboard.css`):

```css
.setup-banner {
    padding: 8px 16px;
    border-left: 3px solid #FFC107;
    background: #FFF8E1;
    font-family: var(--font-sans);
    font-size: var(--font-size-xsmall);
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.setup-banner a {
    color: var(--color-navy);
    text-decoration: underline;
}
.setup-banner .dismiss-btn {
    cursor: pointer;
    opacity: 0.6;
    font-size: 1.2em;
    line-height: 1;
}
.setup-banner .dismiss-btn:hover {
    opacity: 1;
}
```

## Verification

### Script
- Run `./setup.sh` on a clean checkout (no `.env`) → `.env` created with
  prompted values (defaults accepted via Enter), Fernet key generated,
  optional values commented out.
- Run `./setup.sh` again → detects existing `.env`, offers keep/reset;
  Fernet key and existing values are **preserved** (re-offered as defaults).

### Migration
- `alembic upgrade head` succeeds.
- `SELECT key, importance FROM application_settings WHERE importance = 'recommended'`
  returns `OPENAI_API_KEY` and `GITHUB_MCP_TOKEN`.

### API
- `GET /api/v1/settings/` returns `importance` field on every setting.
- `OPENAI_API_KEY` and `GITHUB_MCP_TOKEN` show `importance: "recommended"`.

### Banner
- With no OpenAI key or GitHub token set: banner visible on every page.
- Dismiss banner → hidden for session, persists across page navigations.
- Set OpenAI key via Settings page → banner updates (fewer items or hidden).
- Refresh browser → banner reappears (session reset).

## Files changed

| File | Change |
|------|--------|
| `scripts/setup.sh` | **New** — Bash setup wizard |
| `src/app/db/models/application_settings.py` | Add `importance` column |
| `src/app/alembic/versions/<rev>_add_importance_to_application_settings.py` | **New** — migration |
| `src/app/api/settings/v1/models.py` | Add `importance` to `SettingResponse` |
| `src/app/api/settings/v1/service.py` | Include `importance` in query results |
| `src/app/dash_app/layout.py` | Add `setup-banner` div + `banner-dismissed` store |
| `src/app/dash_app/components/setup_banner.py` | **New** — banner component + callback |
| `src/app/dash_app/assets/executive-dashboard.css` | Banner styles |
| `USER_GUIDE.md` | Update first-run instructions to reference `./setup.sh` |
| `.env.example` | No change (script reads it as template) |
| `docker-compose.yml` | No change (GITHUB_MCP_TOKEN already optional) |

## Dependency notes

- Independent of all other plans. Can execute immediately.
- Work items 2, 3, 4 depend on each other (DB → API → banner), but item 1
  (script) is fully independent and can be built first.
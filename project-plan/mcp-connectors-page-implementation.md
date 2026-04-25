# Plan: MCP Connectors Page

**Status**: Execution Tracker  
**Created**: April 25, 2026  
**Last Updated**: April 25, 2026

## Status Legend

- `[NS]` Not started
- `[IP]` In progress
- `[BL]` Blocked
- `[DN]` Done

## Overall Status

- Project status: `[IP]`
- Current phase: `Phase 3 - Connectors Page Grouping, Atlassian Form, and GitHub Manual Page`
- Next gate: `Phase 3 verification`
- Stop rule: `Do not begin the next phase until the current phase verification passes and the phase status is updated in this document.`

## Progress Log

- `2026-04-25`: Initial execution tracker created for hybrid MCP connectors scope.
- `2026-04-25`: Scope locked to two MCP cards with split behavior:
  - Atlassian MCP is DB-backed
  - GitHub MCP is manual-setup guidance
- `2026-04-25`: Added explicit requirement for connector-level `include_secrets=true` retrieval for Atlassian MCP.
- `2026-04-25`: Phase 1 implementation started.
- `2026-04-25`: Added `atlassian_mcp` and `github_mcp` metadata to the connector registry, including grouping and setup-mode metadata.
- `2026-04-25`: Added Alembic migration `c4f3a8b7d912` to seed the two MCP connector rows.
- `2026-04-25`: Verified new Phase 1 files with `python -m py_compile`; database migration/application verification still pending.
- `2026-04-25`: Manual verification completed after app container restart:
  - confirmed `atlassian_mcp` and `github_mcp` rows exist in the `connectors` table
  - confirmed both new MCP cards appear in the UI
  - confirmed grouped MCP section rendering remains Phase 3 work
- `2026-04-25`: Phase 2 implementation started.
- `2026-04-25`: Added connector-level secret handling for `atlassian_mcp`:
  - masked token output by default
  - decrypted token output when `include_secrets=true`
  - token preservation when update payload leaves the secret blank
- `2026-04-25`: Updated the connector PATCH route so validation errors return `400` instead of being incorrectly mapped to `404`.
- `2026-04-25`: Added integration-test coverage for Atlassian MCP connector config masking and `include_secrets=true`.
- `2026-04-25`: Added service-level unit coverage for Atlassian MCP connector config normalization, encryption, validation, and secret preservation.
- `2026-04-25`: Added `DELETE /api/v1/connectors/{type}/config` endpoint to fully wipe connector-level config including encrypted secrets.
- `2026-04-25`: Added `test_atlassian_mcp_clear_connector_config` integration test covering clear, secret-gone confirmation, and first-save re-validation.
- `2026-04-25`: Phase 2 manual verification completed. All exit gate conditions met. Phase 2 marked done.

## Goal
Add a new `MCP Connectors` section on the Connectors page with two cards:

- `Atlassian MCP Server`
- `GitHub MCP Server`

Both cards should follow the existing click-through connector pattern.

- `Atlassian MCP Server` should use the normal DB-backed connector pattern and move its settings from `.env` into PostgreSQL.
- `GitHub MCP Server` should open a guided manual-setup page that explains how to configure the Docker-managed sidecar via env vars in `docker-compose.yml` and restart the service safely.

---

## Workspace Findings

### Current Connectors UI
- [app/dash_app/pages/connectors/layout.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/dash_app/pages/connectors/layout.py) renders a single flat grid of cards; there is no concept of grouped sections yet.
- [app/dash_app/pages/connectors/callbacks.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/dash_app/pages/connectors/callbacks.py) builds that grid directly from `CONNECTOR_REGISTRY`.
- Existing cards navigate to detail pages; they do not contain inline editable forms on the listing page.
- The detail page already supports connector-level fields (`connector.config`) and item-level fields (`/{type}/configs` rows).

### Current Connectors Data Model
- [app/db/models/connector.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/db/models/connector.py) stores one row per connector type with a `config` JSONB column.
- [app/db/models/connector_configs.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/db/models/connector_configs.py) stores per-item rows for connectors that can have multiple configured items.
- Secret encryption currently exists only for child config rows in [app/api/connectors/v1/service.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/api/connectors/v1/service.py). `connector.config` itself is not encrypted today.

### Current MCP Runtime
- [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py) still defines `GITHUB_MCP_*` and `ATLASSIAN_MCP_*` env-based settings.
- [app/ai_agent/mcp_integration/tool_executor.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp_integration/tool_executor.py) builds MCP client managers directly from `settings`, not from the connectors DB.
- [app/ai_agent/mcp_integration/client_manager.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp_integration/client_manager.py) expects:
  - Atlassian MCP runtime config: `enabled`, `server_url`, `token`
  - GitHub MCP runtime config: `enabled`, `server_url`, `token`

### Docker / Runtime Constraint
- The devcontainer compose file at [.devcontainer/docker-compose.yml](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/.devcontainer/docker-compose.yml) is only the editor/dev shell container and does not define the app runtime services.
- The real runtime dependency is in [docker-compose.yml](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/docker-compose.yml):
  - `app` gets `ATLASSIAN_MCP_*` env vars today
  - `app` also gets `GITHUB_MCP_*` env vars today
  - `github-mcp` gets `GITHUB_PERSONAL_ACCESS_TOKEN` from env
- Atlassian is cloud-hosted, so it can move to DB-backed config in the app without the GitHub sidecar-style token propagation problem.
- GitHub MCP is different because the running sidecar is still configured by Docker/env, not by connector records.

### Existing Connector Naming Collision Risk
- Existing connector types `github`, `jira`, and `confluence` already mean ingestion/data-source connectors.
- MCP server configuration should not reuse those existing connector slugs.

---

## Recommended Design

## Locked Decisions

- Add two MCP cards under a new `MCP Connectors` section
- Both cards use the existing click-through detail-page pattern
- `Atlassian MCP Server` is DB-backed and stored in PostgreSQL
- `GitHub MCP Server` is manual-setup guidance only in this phase
- GitHub MCP should not create fake DB-backed persistence while runtime still depends on Docker/env
- Atlassian MCP connector secrets should support masked default reads plus decrypted reads when `include_secrets=true`
- Do not proceed phase-to-phase without updating this tracker

### Connector Types
Add two new connector types:

- `atlassian_mcp`
- `github_mcp`

Display names:

- `Atlassian MCP Server`
- `GitHub MCP Server`

### Storage Shape
#### Atlassian MCP
Use `connectors.config` for Atlassian MCP settings, not a new child table.

Recommended stored shape:

```json
{
  "enabled": true,
  "server_url": "https://mcp.atlassian.com/v1/mcp",
  "encrypted_token": "gAAAAA..."
}
```

Returned API shape should mask the secret:

```json
{
  "enabled": true,
  "server_url": "https://mcp.atlassian.com/v1/mcp",
  "token": "********"
}
```

Why this is the best fit:

- Atlassian MCP config is singleton connector-level state, not a multi-item list
- the existing detail page already has a connector-level form section
- adding item tables would force an awkward one-row-only UX
- `connector.config` can be extended to support secret-field encryption with less schema churn

#### GitHub MCP
Do not store the GitHub MCP token in DB in this phase.

Why:

- the actual runtime still depends on env vars in [docker-compose.yml](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/docker-compose.yml)
- the `github-mcp` service itself reads `GITHUB_PERSONAL_ACCESS_TOKEN` from env
- storing GitHub credentials in DB without changing the running architecture would create split-brain configuration

Recommended behavior:

- seed a `github_mcp` connector row so the card exists
- use its detail page for manual setup guidance only
- optionally allow status/test behavior that reflects the live env-driven runtime

### UI Shape
Recommended first implementation:

- Keep the existing click-through connector flow
- Add a new grouped section on the listing page named `MCP Connectors`
- Clicking the Atlassian MCP card opens `/app/connectors/atlassian_mcp`
- Clicking the GitHub MCP card opens `/app/connectors/github_mcp`
- The Atlassian MCP detail page shows connector-level settings only
- The GitHub MCP detail page shows manual setup instructions, required env vars, Docker touchpoints, and restart guidance
- Hide the `Configured Items` section entirely for connectors that have no item fields

### Runtime Precedence
#### Atlassian MCP
Use a staged transition:

1. DB config becomes the primary source for Atlassian MCP settings used by the app
2. env remains a temporary fallback during rollout
3. env fallback is removed only after DB-backed runtime behavior is verified

#### GitHub MCP
Keep GitHub MCP manual for now:

1. Docker/env remains the source of truth
2. the connector page becomes operator guidance, not a DB-backed settings form
3. optional connectivity validation can be added without claiming DB persistence

---

## Key Risks / Open Questions

### 1. Listing Page UX
Current cards only navigate.

Confirmed direction:
- both new MCP cards should behave like the existing connectors and open detail pages

### 2. Atlassian Scope
The current Atlassian runtime only needs `enabled`, `server_url`, and `token`. No additional site URL is currently used by the codebase.

### 3. GitHub MCP Scope
GitHub MCP should be visible in the same `MCP Connectors` section, but it should not pretend to save runtime config to DB while the real runtime still depends on Docker env vars.

Recommended rule:
- GitHub MCP page is informational/manual-setup first
- do not add a fake Save flow that writes token values to Postgres unless the runtime is also changed to consume them

---

## Phase 1: Data Contract and Seeded MCP Connectors

- Phase status: `[DN]`

**Goal**: Add the Atlassian and GitHub MCP connector types to the shared connectors system without changing MCP runtime behavior yet.

### Changes
- Update [app/api/connectors/v1/registry.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/api/connectors/v1/registry.py)
  - add `atlassian_mcp`
  - add `github_mcp`
  - add metadata needed for page grouping, for example `section: "mcp"`
- Update the seed migration pattern so the `connectors` table contains base rows for both MCP connectors
  - likely a new Alembic revision rather than editing the old seed migration
- Add a small connector metadata contract for:
  - `display_name`
  - `icon`
  - `section`
  - `supports_items`
  - optionally `mode` or `setup_type` (`db_backed` vs `manual`)

### Steps
1. `[DN]` Add `atlassian_mcp` and `github_mcp` to the connector registry.
2. `[DN]` Add connector metadata for grouping and behavior (`section`, `supports_items`, optional setup mode).
3. `[DN]` Create a new Alembic revision to seed both MCP connector rows.
4. `[DN]` Confirm list-connectors responses include both new connector types.

### Notes
- No new child tables are recommended in this phase
- No runtime switch from env to DB yet

### Incremental Verification
1. Apply the migration and confirm `connectors` contains `atlassian_mcp` and `github_mcp`.
2. Call `GET /api/v1/connectors/` and confirm both connector rows are returned.
3. Confirm existing connectors still render and behave normally.

### Exit Gate
- Do not start Phase 2 until the new connector rows exist and are visible through the existing connectors API.

---

## Phase 2: Encrypted Connector-Level Atlassian Settings in the API Layer

- Phase status: `[DN]`

**Goal**: Make the connectors API able to store and return Atlassian MCP singleton config safely.

### Changes
- Extend [app/api/connectors/v1/service.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/api/connectors/v1/service.py) so connector-level config can support secret fields for specific connector types
- Add connector-config secret metadata:
  - `atlassian_mcp`: `token -> encrypted_token`
- Keep `github_mcp` out of DB-backed secret persistence in this phase
- Keep secrets encrypted at rest using the existing encryption utility
- Mask secrets in `GET /api/v1/connectors/{type}` responses, matching the current child-item secret handling pattern
- Add a connector-level `include_secrets=true` retrieval path for `atlassian_mcp`, mirroring the existing `list_config_items(..., include_secrets=True)` behavior in [app/api/connectors/v1/service.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/api/connectors/v1/service.py:156)
  - recommended shape: `GET /api/v1/connectors/atlassian_mcp?include_secrets=true`
  - default behavior stays masked
  - when `include_secrets=true`, the API returns decrypted plaintext `token`
  - include the same caveat already present in the codebase: this is a temporary convenience path and should eventually be replaced by proper permission checks rather than a raw query parameter
- Preserve the current UX behavior where leaving a masked secret field blank during edit does not wipe the stored secret
- Add validation rules:
  - `server_url` required when `enabled=true`
  - `token` required on first save when `enabled=true`
  - connector type must be `atlassian_mcp` for the new DB-backed MCP save flow

### Steps
1. `[DN]` Add connector-level secret metadata for `atlassian_mcp`.
2. `[DN]` Extend connector read logic to support masked secret output by default.
3. `[DN]` Add connector-level decrypted output when `include_secrets=true`.
4. `[DN]` Preserve existing secret values when edit submissions leave the token blank.
5. `[DN]` Add validation for enabled Atlassian MCP settings.
6. `[DN]` Add or update automated tests for masking and `include_secrets=true`.

### Files Likely Affected
- [app/api/connectors/v1/service.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/api/connectors/v1/service.py)
- [app/api/connectors/v1/model.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/api/connectors/v1/model.py)
- [app/api/connectors/v1/router.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/api/connectors/v1/router.py)
- possibly [app/api/connectors/v1/query.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/api/connectors/v1/query.py) if response shape helpers are centralized there

### Incremental Verification
1. `PATCH /api/v1/connectors/atlassian_mcp` saves `enabled`, `server_url`, and `token`.
2. `GET /api/v1/connectors/atlassian_mcp` returns masked `token`, never plaintext.
3. `GET /api/v1/connectors/atlassian_mcp?include_secrets=true` returns decrypted plaintext `token`.
4. Editing the connector without re-entering the token preserves the existing encrypted secret.
5. Existing connectors API tests still pass.

### Suggested Tests
- Extend [tests/test_connectors_api.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/tests/test_connectors_api.py) for `atlassian_mcp`
- Add assertions specifically for connector-level secret masking
- Add assertions for connector-level secret retrieval when `include_secrets=true`

### Exit Gate
- Do not start Phase 3 until the Atlassian MCP connector config can be saved, read back, and masked correctly through the API.

---

## Phase 3: Connectors Page Grouping, Atlassian Form, and GitHub Manual Page

- Phase status: `[IP]`

**Goal**: Surface both MCP connectors in the Dash UI, with DB-backed management for Atlassian and manual guidance for GitHub.

### Changes
- Update [app/dash_app/pages/connectors/callbacks.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/dash_app/pages/connectors/callbacks.py)
  - render grouped sections instead of one flat grid
  - keep existing connection cards in the current section
  - add a new `MCP Connectors` section for both MCP cards
- Update [app/dash_app/pages/connectors/layout.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/dash_app/pages/connectors/layout.py)
  - hide `Configured Items` when `supports_items=False`
  - render connector-only forms cleanly for the Atlassian MCP connector
  - render a manual setup page for the GitHub MCP connector
- Update [app/dash_app/pages/connectors/components/config_forms.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/dash_app/pages/connectors/components/config_forms.py)
  - add connector-level field specs for `atlassian_mcp`
  - recommended fields:
    - `enabled` (`checkbox`)
    - `server_url` (`text`)
    - `token` (`password`)
- Update [app/dash_app/pages/connectors/components/tooltips.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/dash_app/pages/connectors/components/tooltips.py)
  - add MCP-specific help text

### GitHub MCP Manual Page Content
- Explain that GitHub MCP is configured manually through [docker-compose.yml](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/docker-compose.yml)
- Show the relevant env vars:
  - `GITHUB_MCP_ENABLED`
  - `GITHUB_MCP_TOKEN`
  - `GITHUB_MCP_SERVER_URL`
  - `GITHUB_PERSONAL_ACCESS_TOKEN` on the `github-mcp` service
- Explain the affected services:
  - `app`
  - `github-mcp`
- Include restart/redeploy guidance after editing env vars
- Optionally include a `Test Connection` action if the current runtime is reachable
- Do not render a misleading DB-backed Save button for GitHub MCP

### Steps
1. `[NS]` Group connectors into `Connections` and `MCP Connectors` sections on the listing page.
2. `[NS]` Add an Atlassian MCP detail page with connector-level form fields only.
3. `[NS]` Add a GitHub MCP detail page with manual setup instructions.
4. `[NS]` Hide configured-items UI for both MCP connectors.
5. `[NS]` Add tooltips/help text for Atlassian MCP fields.
6. `[NS]` Decide whether GitHub MCP shows a validation/test action or instruction-only UX.

### UX Expectations
- List page shows a separate `MCP Connectors` heading and two cards
- Clicking the Atlassian card opens a DB-backed detail page
- Clicking the GitHub card opens a manual-setup detail page
- Atlassian detail page has the connector settings block and standard save/test/delete actions
- GitHub detail page has instruction content and optional validation action, but no misleading DB save flow
- No item list or add-item controls are shown for either MCP connector

### Incremental Verification
1. `/app/connectors` shows a distinct `MCP Connectors` section.
2. Both MCP cards navigate correctly.
3. Atlassian form saves persist values to Postgres and survive page reload.
4. Atlassian tokens are not echoed back in plaintext after reload.
5. GitHub page clearly shows manual configuration instructions and does not expose a broken save flow.
6. Existing connector detail pages still show their item-based forms unchanged.

### Exit Gate
- Do not start Phase 4 until the UI can fully manage Atlassian MCP settings and clearly present GitHub MCP manual setup.

---

## Phase 4: App Runtime Reads Atlassian MCP Settings from Postgres

- Phase status: `[NS]`

**Goal**: Move Atlassian MCP client configuration in the app from env-only to DB-first, while keeping GitHub MCP manual.

### Changes
- Introduce a DB-backed MCP config loader, for example a small module under `app/ai_agent/mcp_integration/` or `app/api/connectors/v1/`
- That loader should:
  - fetch the `atlassian_mcp` connector config
  - decrypt stored secrets internally
  - return the runtime shape expected by the MCP client managers
- Update [app/ai_agent/mcp_integration/tool_executor.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp_integration/tool_executor.py)
  - stop building the Atlassian manager directly from `settings` only
  - use DB-first Atlassian config
  - keep env fallback temporarily while rollout is incomplete
- Keep [app/ai_agent/mcp_integration/client_manager.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/ai_agent/mcp_integration/client_manager.py) mostly unchanged if possible; only the config source should change

### Atlassian Runtime Note
- This should be straightforward because the app itself sends the bearer token to the remote Atlassian MCP endpoint.

### GitHub Runtime Note
- GitHub MCP remains env-driven in this phase.
- The connectors page should stay explicit that GitHub runtime configuration is still managed through Docker/env, not Postgres.

### Steps
1. `[NS]` Add a DB-backed Atlassian MCP config loader.
2. `[NS]` Decrypt the stored Atlassian token at runtime only where needed.
3. `[NS]` Update Atlassian manager creation to use DB-first config.
4. `[NS]` Preserve env fallback until rollout verification passes.
5. `[NS]` Confirm GitHub MCP behavior remains unchanged and env-driven.

### Incremental Verification
1. With DB config present and env disabled, Atlassian MCP still lists tools and serves chat requests.
2. `tests/test_mcp_integration_comprehensive.py` is updated to cover DB-backed settings resolution.
3. The app behaves correctly when DB config is absent and env fallback is still enabled.
4. GitHub MCP continues to work unchanged with env-driven configuration.

### Exit Gate
- Do not start Phase 5 until Atlassian is confirmed DB-backed in runtime.

---

## Phase 5: Real Atlassian Connection Testing and GitHub Validation Guidance

- Phase status: `[NS]`

**Goal**: Replace stub-like Atlassian MCP connector behavior with real connectivity checks and add GitHub manual-page validation where useful.

### Changes
- Update `POST /api/v1/connectors/{type}/test` for `atlassian_mcp`
  - use the real MCP client managers and DB-backed config
  - return meaningful connection errors
- Decide whether `POST /api/v1/connectors/{type}/test` for `github_mcp` should:
  - remain unavailable
  - perform a lightweight reachability check against the current configured GitHub MCP endpoint
  - or check only that the app-side env configuration is present
- Decide whether to retire `ATLASSIAN_MCP_*` from [app/settings.py](/home/shuva/github/shuvabrata/work-behavior-analytics-ai/app/settings.py) or keep it as fallback/bootstrap config

### Steps
1. `[NS]` Replace stub Atlassian test behavior with a real MCP connectivity check.
2. `[NS]` Persist meaningful success/error status for Atlassian MCP tests.
3. `[NS]` Decide the final GitHub validation behavior.
4. `[NS]` Clarify whether Atlassian env fallback remains or is removed after rollout.
5. `[NS]` Update the progress log and phase statuses as implementation completes.

### Incremental Verification
1. `Test Connection` on the Atlassian MCP card performs a real connection test.
2. Chat flow still works with Atlassian MCP enabled after saving config through the UI.
3. Failure states are surfaced clearly in the UI and persisted in connector status fields.
4. GitHub MCP page either exposes a clearly defined validation action or explicitly says testing is manual.

### Exit Gate
- Phase complete only when the Atlassian MCP card supports save, reload, masked secrets, and real test behavior, and the GitHub MCP page clearly supports manual setup without misleading persistence behavior.

---

## Suggested File Impact Summary

| File | Expected Change |
|------|-----------------|
| `app/api/connectors/v1/registry.py` | Add Atlassian and GitHub MCP connector entries and grouping metadata |
| `app/api/connectors/v1/service.py` | Add encrypted connector-level secret handling for Atlassian MCP config |
| `app/api/connectors/v1/model.py` | Tighten request/response handling for Atlassian MCP connector config |
| `app/api/connectors/v1/router.py` | Reuse existing connector routes; possibly improve validation paths |
| `app/api/connectors/v1/query.py` | Minimal or no change unless helper methods are added |
| `app/dash_app/pages/connectors/layout.py` | Add grouped sections, support connectors with no item section, and render the GitHub manual page |
| `app/dash_app/pages/connectors/callbacks.py` | Render grouped listing, manage Atlassian MCP form flow, and support the GitHub manual page |
| `app/dash_app/pages/connectors/components/config_forms.py` | Add `atlassian_mcp` connector field specs |
| `app/dash_app/pages/connectors/components/tooltips.py` | Add MCP field tooltip text |
| `app/ai_agent/mcp_integration/tool_executor.py` | Switch Atlassian config resolution from env-only to DB-first |
| `app/ai_agent/mcp_integration/client_manager.py` | Possibly unchanged, or lightly adjusted for config source compatibility |
| `app/settings.py` | Keep temporary Atlassian fallback env vars until runtime migration is complete |
| `app/alembic/versions/<new_revision>.py` | Seed/add the Atlassian and GitHub MCP connector rows |
| `tests/test_connectors_api.py` | Add CRUD + masking tests for Atlassian MCP connector-level settings |
| `tests/test_mcp_integration_comprehensive.py` | Add DB-backed Atlassian MCP settings coverage |

---

## Recommended Implementation Order

1. Phase 1: seed and registry metadata
2. Phase 2: encrypted API persistence for Atlassian MCP connector-level config
3. Phase 3: Dash page grouping, Atlassian MCP form, and GitHub manual page
4. Phase 4: DB-backed Atlassian runtime resolution
5. Phase 5: real Atlassian connection testing and GitHub validation guidance

This order keeps every phase independently testable and avoids mixing UI work with unresolved runtime configuration behavior.

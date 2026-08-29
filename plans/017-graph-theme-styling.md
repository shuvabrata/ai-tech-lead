# Plan 017: User-configurable Graph Themes (override hardcoded styling)

## Status

- **Priority**: P2 (feature / customization)
- **Effort**: L (DB + API + 3 consumer pages + editor UI + live preview)
- **Risk**: MEDIUM (touches Graph, Collaboration Network, and Search rendering paths)
- **Depends on**: — (independent; no prior plan)
- **Category**: feature / graph styling
- **Planned at**: 2026-08-28
- **Status**: READY

## Why this matters

Graph node/edge styling (shape, color, size) is currently **hardcoded** in
`src/app/dash_app/styles.py` (`THEME_TOKENS`) and
`src/app/dash_app/pages/graph/styles.py` (`build_cytoscape_stylesheet()`).
Users cannot customize appearance without editing source code and restarting
the app.

This plan introduces **named "Graph Themes"** stored in Postgres. Each theme
carries per-nodeType overrides (color, border, border_width, shape, width,
height) plus edge and global styling that are merged **over** the hardcoded
base at render time. A new REST API serves CRUD + a server-merged `/effective`
endpoint, and a new "Graph Styling" settings page (replacing the existing
`coming_soon` card) lets users create/edit themes with a live single-node
preview. Graph, Collaboration Network, and Search all consume the same merged
output.

## Core principle (anti-drift)

The DB stores **deltas only**, never full palette snapshots. The hardcoded
`THEME_TOKENS` remain the single source of truth for the *base*; a theme row
contains only the properties it changes. Effective theme is always computed:

```
effective = base_tokens (code)  ⊕  overrides (DB)
```

This mirrors the existing `application_settings` pattern (`value` is a
nullable override; effective value = DB → env → code default).

## Design decisions

All decisions reached via the grill-me process:

1. **Model**: Layered override — hardcoded `THEME_TOKENS` (executive-light /
   executive-dark) is the fallback; DB themes carry partial overrides.
2. **Active selection**: Named theme documents with `is_default` scoped **per
   base mode** (a user can have a default light theme and a default dark theme).
3. **Scope**: ALL Cytoscape properties configurable; per-property hardcoded
   fallback. Propagation to Search + Collaboration Network is in scope.
4. **Override structure**: Structured per-nodeType document (semantic keys),
   stored as a single JSONB `overrides` column.
5. **Out-of-the-box**: Seed one empty immutable "Default" anchor per base mode
   PLUS one illustrative example theme per mode.
6. **Merge location**: Server-side merge in a single `/effective` endpoint
   (returns merged tokens; client assembles Cytoscape rules).
7. **Base mode source**: The app's existing `theme-store` toggle (light/dark)
   is the base mode. No separate graph mode selector.
8. **is_default enforcement**: Postgres **partial unique index**
   `ON graph_themes (base_theme) WHERE is_default`.
9. **Builtin immutability**: Builtin themes are immutable in DB; editing one
   creates a NEW row (copy-on-write via explicit `clone`).
10. **Caching**: None — `/effective` does a fresh DB query per render
    (cheap at single-user scale).
11. **Re-fetch signal**: Refresh-on-navigation only (no polling/websocket).
12. **Editor UI**: Two base-mode sections; non-collapsible grid of node-type
    cards; single-node Cytoscape live preview; explicit Save (full-document
    PATCH); "Set as default" via confirm dialog.
13. **Shapes**: Full Cytoscape shape set (not just the 16 currently in use).

## Override JSONB schema (contract)

```json
{
  "nodes": {
    "Person": {"color": "#00FF00", "border": "#008800", "border_width": 2,
               "shape": "diamond", "width": 80, "height": 60},
    "default": {"color": "#CCCCCC"}
  },
  "edges": {
    "line_color": "#999999", "width": 3,
    "arrow_shape": "triangle", "label_color": "#666666"
  },
  "global": {
    "node_label_color": "#FFFFFF",
    "selection_color": "#FFAA00",
    "edge_label_background": "#222222"
  }
}
```

- Semantic keys (`color` → Cytoscape `background-color`) translated in ONE
  layer in `common/graph_theme.py`.
- Dimensions are **plain numeric px** (no "px" suffix).
- `nodes.<Type>` keys mirror the existing `nodeType` values (`Person`,
  `Project`, `Issue`, `Epic`, `Repository`, `Branch`, `Team`,
  `IdentityMapping`, `Initiative`, `Sprint`, `Commit`, `File`, `PullRequest`,
  `Space`, `Page`, `Blogpost`) plus `default` for untyped nodes.
- Excluded from v1: `curve-style`, `arrow-scale`, `control-point-step-size`,
  fonts, layout/zoom/physics (additive later without schema rewrite).

## API surface

`graph-themes` domain under `src/app/api/graph_themes/v1/`
(router/service/query/models, mirroring `settings/v1`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/graph-themes/` | List all themes |
| POST | `/api/v1/graph-themes/` | Create a user theme |
| GET | `/api/v1/graph-themes/{id}` | Fetch one theme |
| PATCH | `/api/v1/graph-themes/{id}` | Update a user theme (builtin → 409) |
| DELETE | `/api/v1/graph-themes/{id}` | Delete a user theme (builtin → 409) |
| POST | `/api/v1/graph-themes/{id}/set-default` | Clear old + set new (txn) |
| POST | `/api/v1/graph-themes/{id}/clone` | Copy-on-write (builtin → new user row) |
| GET | `/api/v1/graph-themes/effective?base_theme=` | Merged tokens |

`/effective` returns **merged tokens** (base ⊕ overrides), not a Cytoscape
stylesheet. The client's existing `build_cytoscape_stylesheet()` turns tokens
into rules.

## DB model

`graph_themes` table:

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `name` | str | unique per `base_theme` |
| `base_theme` | str | `executive-light` \| `executive-dark` |
| `is_default` | bool | partial unique index on `(base_theme) WHERE is_default` |
| `overrides` | JSONB | structured override doc (schema above) |
| `source` | str | `builtin` \| `user` |
| `created_at` / `updated_at` | timestamptz | |

---

## Phase 1 — Shared core + DB layer

> **Exit criteria**: pure merge/translation functions unit-tested; model + migration applied; seed rows present. No behavior change yet.

- [x] **1.1** Create `src/app/common/graph_theme.py`:
  - `ALLOWED_SHAPES` (full Cytoscape set)
  - override schema types (dataclasses or TypedDicts)
  - `merge_theme_overrides(base_tokens, overrides) -> dict`
  - `overrides_to_cytoscape_rules(merged_tokens) -> list[dict]`
  - Kept **pure** — base tokens passed as arguments (never imports `dash_app`).
- [x] **1.2** Create `src/app/db/models/graph_theme.py` (`GraphTheme` model).
- [x] **1.3** Register `GraphTheme` in `src/app/db/models/__init__.py`.
- [x] **1.4** Alembic migration: create `graph_themes` + partial unique index;
  seed 2 empty "Default" anchors + 2 illustrative example themes.

### Automated tests (Phase 1)
- `pytest -m unit tests/test_graph_theme.py -q` (new file):
  - `merge_theme_overrides` — override wins over base; missing keys fall through to base; empty overrides → base unchanged.
  - `overrides_to_cytoscape_rules` — semantic key (`color`) → Cytoscape `background-color`; numeric px → `"80px"` string; `shape` passes through.
  - `ALLOWED_SHAPES` contains all 16 in-use shapes + full Cytoscape set.
- `pytest -m unit tests/test_graph_theme_validation.py -q` (new file):
  - reject invalid hex (`"red"`, `"#GGG"`), unknown shape, negative width/height.

### Manual tests (Phase 1)
- `cd src/app && alembic upgrade head` → no errors; table + index + 4 seed rows present.
- `psql` (or admin) check: `SELECT * FROM graph_themes` shows the seeded defaults.
- Confirm partial unique index rejects a second `is_default` for the same `base_theme` (manual insert attempt fails).

---

## Phase 2 — API layer

> **Exit criteria**: all 8 endpoints functional; validation enforced; builtin immutability enforced; partial index blocks duplicate default.

- [x] **2.1** Create `src/app/api/graph_themes/v1/models.py` — Pydantic
  request/response + nested `NodeOverride`/`EdgeOverride`/`GlobalOverride`
  (HexColor regex, shape `Literal` from `ALLOWED_SHAPES`, numeric `gt`/`le`).
- [x] **2.2** Create `query.py` (CRUD + `get_default_for_base_theme`).
- [x] **2.3** Create `service.py` — create/update/delete/clone/set-default
  with builtin guards and transactional default swap.
- [x] **2.4** Create `router.py` — wire endpoints; builtin PATCH/DELETE → 409;
  `/effective` calls `merge_theme_overrides`.
- [x] **2.5** Register router in `src/app/main.py`.

### Automated tests (Phase 2)
- `pytest -m unit tests/test_graph_themes_service.py -q` (new file):
  - `set_default` clears prior default and sets new (single default invariant).
  - `clone` copies `overrides` to a new `user` row; builtin `PATCH` raises 409.
  - `effective` returns base ⊕ overrides (via mocked DB rows).
- `pytest -m "integration and server" tests/test_graph_themes_api.py -q` (new file):
  - POST create → GET list → PATCH → DELETE round-trip.
  - PATCH builtin → 409; DELETE builtin → 409.
  - `set-default` twice for same base → second returns 409 (index).

### Manual tests (Phase 2)
- `PYTHONPATH=src uvicorn app.main:app --reload`; hit `/api/v1/graph-themes/` via browser/curl.
- Create a theme with a few overrides; `GET /effective?base_theme=executive-light` shows merged tokens.
- Confirm a second `set-default` in the same base mode fails with 409.

---

## Phase 3 — Wire the three consumers

> **Exit criteria**: Graph + Collab + Search all render the merged theme; consistency test updated and green.

Sub-phases are **strictly sequential**: do not start sub-phase N+1 until sub-phase N's
automated **and** manual tests pass. Each sub-phase is independently shippable and testable.

### Sub-phase 3.1 — Refactor `build_cytoscape_stylesheet()` to consume merged tokens

> **Exit criteria**: `build_cytoscape_stylesheet()` drives shape/size from merged tokens (not inline literals); no visual change with empty overrides.

- [x] Refactor `build_cytoscape_stylesheet()` in `pages/graph/styles.py` to
  consume merged tokens (drive shape/size from token output rather than
  inline literals).

**Automated tests**:
- `pytest -m unit tests/test_graph_theme.py -q` — regression on merge/rules.

**Manual tests**:
- With no overrides, navigate Graph; confirm appearance is identical to current hardcoded output.

### Sub-phase 3.2 — Graph page stylesheet callback

> **Exit criteria**: Graph page fetches `/effective` for the current `theme-store` mode.

- [x] Graph page: `update_graph_stylesheet` callback fetches `/effective` for
  the current `theme-store`.

**Automated tests**:
- `pytest -m unit tests/test_graph_theme.py -q` — regression on merge/rules.

**Manual tests**:
- Create a theme overriding `Person` fill to a distinctive color; navigate Graph; confirm the node reflects the override.

### Sub-phase 3.3 — Collab page stylesheet callback

> **Exit criteria**: Collab page renders the merged theme via a stylesheet callback (mirroring Graph); no longer uses the hardcoded `CYTOSCAPE_STYLESHEET` constant.

- [x] Collab page: add a `stylesheet` callback (mirror Graph); convert
  `stylesheet=CYTOSCAPE_STYLESHEET` in `collaboration_network/layout.py` to
  callback-driven.

**Automated tests**:
- `pytest -m unit tests/test_collab_network_controls.py -q` — Collab stylesheet callback returns merged rules.

**Manual tests**:
- Navigate Collab; confirm a `Person` **shape/size** override is reflected (color is masked by community coloring on Collab, so use shape — e.g. `diamond` — or size to verify propagation).

### Sub-phase 3.4 — Search page dynamic badge colors

> **Exit criteria**: Search page resolves `_badge_color()` dynamically from `/effective` (no import-time `TOKENS` snapshot).

- [x] Search page: fetch `/effective` into a `dcc.Store`; resolve
  `_badge_color()` dynamically (replace import-time `TOKENS` snapshot).

**Automated tests**:
- `pytest -m unit tests/test_search_node_color_consistency.py -q` — badge colors == effective node colors.

**Manual tests**:
- Navigate Search; confirm a `Person`-color override is reflected in badge colors.

### Sub-phase 3.5 — Update consistency test for dynamic resolution

> **Exit criteria**: `test_search_node_color_consistency.py` updated for dynamic resolution and green.

- [x] Update `tests/test_search_node_color_consistency.py` for the new dynamic resolution.

**Automated tests**:
- `pytest -m unit tests/test_search_node_color_consistency.py -q` — invariant still holds (badge colors == effective node colors).

**Manual tests**:
- Full smoke test: create → edit a theme; verify all three pages (Graph / Collab / Search) reflect the override.

---

## Phase 4 — Editor UI ("Graph Styling" settings page)

> **Exit criteria**: full create/edit/clone/set-default/delete flow; single-node live preview; card un-gated and route registered.

Sub-phases are **strictly sequential**: do not start sub-phase N+1 until sub-phase N's
automated **and** manual tests pass. Each sub-phase is independently shippable and testable.

### Sub-phase 4.1 — Scaffolding, route, and card un-gate

> **Exit criteria**: the Graph Styling page is reachable at `/app/settings/graph-styling` and renders an empty-but-valid shell (no editor controls yet).

- [x] Create `src/app/dash_app/pages/settings/graph_styling/` package with a
  `layout.py` exposing `get_layout()` (minimal placeholder) and a `callbacks.py`
  (registered via the package `__init__.py`).
- [x] Register the page route in `dash_app/layout.py` (`/app/settings/graph-styling`).
- [x] Un-gate the `graph-styling` card in `settings/layout.py`
  (`coming_soon=False`, add `href="/app/settings/graph-styling"`).
- [x] Add a `graph-styling` branch in `settings/callbacks.py` `handle_card_click()`.
- [x] Export `get_layout` from `settings/__init__.py` and register callbacks.

**Automated tests**:
- `pytest -m unit tests/test_graph_styling_page.py -q` (new) — layout returns a `html.Div` shell; package import registers callbacks without error.

**Manual tests**:
- Rebuild app; navigate Settings → click the "Graph Styling" card → page loads (empty shell, no errors).

### Sub-phase 4.2 — Editor layout (base-mode sections + node-type cards)

> **Exit criteria**: page renders two base-mode sections (light/dark), each with a non-collapsible grid of node-type cards (color/border/border-width/shape/width/height) plus an Edges card and a Global card.

- [ ] Build the two base-mode sections (light/dark).
- [ ] Build the node-type card grid (one card per `NODE_TYPES` entry, excluding `default`), with inputs for color/border/border-width/shape/width/height.
- [ ] Add the Edges card (line_color/width/arrow_shape/label_color).
- [ ] Add the Global card (node_label_color/selection_color/edge_label_background).

**Automated tests**:
- `pytest -m unit tests/test_graph_styling_page.py -q` — layout renders two base-mode sections + node-type cards; Edges/Global cards present.

**Manual tests**:
- Open Settings → Graph Styling; confirm both base-mode sections and all node-type/Edges/Global cards render.

### Sub-phase 4.3 — Single-node live preview

> **Exit criteria**: a single-node Cytoscape preview reflects the currently edited node's shape/color/size in real time.

- [ ] Add a single-node Cytoscape preview component driven by a `dcc.Store` working dict via `overrides_to_cytoscape_rules()`.

**Automated tests**:
- `pytest -m unit tests/test_graph_styling_page.py -q` — preview callback emits a stylesheet with the edited node's shape/color/size.

**Manual tests**:
- Edit a node type's shape/color/size; confirm the preview updates live.

### Sub-phase 4.4 — Actions (clone / set-default / save / delete)

> **Exit criteria**: full create/edit/clone/set-default/delete flow works end-to-end against the API.

- [ ] "Duplicate to edit" (builtin → clone) affordance on builtin cards.
- [ ] "Set as default" (ConfirmDialog) action.
- [ ] "Save" (full-document PATCH) action.
- [ ] "Delete" (ConfirmDialog) action; builtin delete disabled.

**Automated tests**:
- `pytest -m unit tests/test_graph_styling_page.py -q` — builtin card renders "Duplicate" affordance, not plain Edit.

**Manual tests**:
- "Duplicate to edit" a builtin → new user row appears; edit → Save → persists.
- "Set as default" on the new theme; navigate Graph; confirm it applies.
- "Delete" a user theme → confirm dialog → removed (builtin delete disabled).

### Sub-phase 4.5 — Legend glyph parity

> **Exit criteria**: every `ALLOWED_SHAPES` entry has a `get_shape_css()` mapping.

- [ ] Add missing legend glyphs to `get_shape_css()` in
  `graph/utils/ui_components.py` for the full `ALLOWED_SHAPES` set.

**Automated tests**:
- `pytest -m unit tests/test_graph_theme.py -q` — legend glyph parity: every `ALLOWED_SHAPES` entry has a `get_shape_css` mapping.

**Manual tests**:
- Open the shape dropdown in the editor; confirm every shape renders a sensible legend glyph (no broken/empty swatches).

---

## Files touched

| File | Change |
|---|---|
| `src/app/common/graph_theme.py` | **new** — shapes, merge, translation |
| `src/app/db/models/graph_theme.py` | **new** — model |
| `src/app/db/models/__init__.py` | register `GraphTheme` |
| `src/app/alembic/versions/..._add_graph_themes.py` | **new** — table + index + seed |
| `src/app/api/graph_themes/v1/*` | **new** — models/query/service/router |
| `src/app/main.py` | register router |
| `src/app/dash_app/pages/graph/styles.py` | `build_cytoscape_stylesheet` (merged tokens) |
| `src/app/dash_app/pages/graph/callbacks/display.py` | `update_graph_stylesheet` → `/effective` |
| `src/app/dash_app/pages/collaboration_network/layout.py` + callbacks | stylesheet callback |
| `src/app/dash_app/pages/search.py` | dynamic badge colors |
| `src/app/dash_app/pages/graph/utils/ui_components.py` | `get_shape_css` (add glyphs) |
| `src/app/dash_app/pages/settings/layout.py` | un-gate card |
| `src/app/dash_app/pages/settings/graph_styling/` | **new** — editor UI + callbacks |
| `tests/test_graph_theme.py`, `test_graph_theme_validation.py`, `test_graph_themes_service.py`, `test_graph_themes_api.py`, `test_graph_styling_page.py` | **new** |
| `tests/test_search_node_color_consistency.py` | update for dynamic resolution |

## Progress markers

Track completion by ticking the `- [ ]` checkboxes in each phase above.
Phases are strictly sequential: **do not start Phase N+1 until all Phase N
automated tests and manual tests pass.**

- [x] Phase 1 complete (shared core + DB)
- [x] Phase 2 complete (API)
- [x] Phase 3.1 complete (`build_cytoscape_stylesheet` consumes merged tokens)
- [x] Phase 3.2 complete (Graph page stylesheet callback)
- [x] Phase 3.3 complete (Collab page stylesheet callback)
- [x] Phase 3.4 complete (Search page dynamic badge colors)
- [x] Phase 3.5 complete (consistency test updated)
- [x] Phase 3 complete (all consumers wired)
- [x] Phase 4.1 complete (scaffolding + route + card un-gate)
- [ ] Phase 4.2 complete (editor layout — sections + cards)
- [ ] Phase 4.3 complete (single-node live preview)
- [ ] Phase 4.4 complete (actions — clone/set-default/save/delete)
- [ ] Phase 4.5 complete (legend glyph parity)
- [ ] Phase 4 complete (editor UI)
- [ ] All automated suites green (`pytest -m unit tests -q`)
- [ ] Manual smoke test full pass (create → edit → set-default → verify on all 3 pages)

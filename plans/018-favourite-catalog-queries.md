# Plan 018: Favourite Catalog Queries

## Status

- **Priority**: P2 (UX enhancement — query catalog favourites)
- **Effort**: M (DB table + API + UI across 5 phases)
- **Risk**: LOW
- **Depends on**: — (independent)
- **Category**: feature / query catalog
- **Planned at**: 2026-09-03
- **Status**: IN PROGRESS 🚧

## Why this matters

The Graph page's Query Catalog presents YAML-backed catalog queries grouped by
namespace (filesystem folders), listed alphabetically. Users frequently run the
same queries and currently have no way to surface them. This plan adds:

1. A **star icon** beside each catalog query to mark it as a favourite.
2. **Favourites-first sorting** (most recently favourited on top), then the
   remaining queries alphabetically.
3. A dynamic **"My Fav"** namespace listing all favourites, which is the
   **default** selection when the user opens the Query Catalog (only when
   favourites exist).
4. A **DB-backed metadata table** (`catalog_metadata`) to persist favourite
   state, exposed via a REST API the UI consumes.

## Discovery

Explored on 2026-09-03 across `src/app/query_catalog/`, `src/app/api/queries/`,
`src/app/dash_app/pages/graph/`, and `src/app/db/`.

| Question | Answer |
|---|---|
| Catalog loader | `src/app/query_catalog/loader.py` — `load_catalog()` sorts by `(namespace.order, name.lower())`; `CatalogQuery.id = "<namespace.directory>/<slug>"` |
| YAML-backed API | `src/app/api/queries/v1/router.py` — `GET /api/v1/queries/catalog`, `/catalog/namespaces`, `/catalog/{namespace}/{slug}`; prefix `/queries`, registered in `main.py` |
| UI layout | `layout.py` `create_catalog_tab_content()` — namespace filter `catalog-namespace-filter`, search `catalog-search-input`, list `catalog-query-list`, detail `catalog-query-detail` |
| UI stores | `create_stores()` — `query-catalog-store`, `selected-catalog-query-store`, `catalog-parameters-store` |
| UI callbacks | `callbacks/catalog.py` — `build_namespace_options()`, `filter_catalog_queries()`, `render_catalog_query_list()`, `load_query_catalog()`, `populate_namespace_filter()`, `sync_selected_catalog_query()` |
| DB pattern template | `graph_themes` — model in `db/models/graph_theme.py`, query/service/router in `api/graph_themes/v1/`, registered in `main.py`, Alembic migration, `get_async_db` dependency |
| Sentinel convention | `ALL_NAMESPACES = "__all__"` in `catalog.py` |
| Alembic model discovery | `alembic/env.py` imports `app.db.models` — new model must be added to `db/models/__init__.py` |

## Design decisions

All decisions reached via the grill-me process:

1. **Table**: `catalog_metadata` — `id` (PK int), `catalog_id` (str, unique,
   NOT NULL), `is_favourite` (bool, NOT NULL, default false), `created_at`
   (timestamptz), `updated_at` (timestamptz). No metadata JSONB, no `user_id`.
2. **Row population**: Lazy upsert on toggle (Option A). No seeding. Rows only
   for queries the user has interacted with.
3. **API surface** (under existing `/api/v1/queries` prefix):
   - `GET /catalog-metadata` (optional `?is_favourite=` filter)
   - `GET /catalog-metadata/{catalog_id}`
   - `PUT /catalog-metadata/{catalog_id}` — generic partial-patch body,
     validates `catalog_id` against the YAML catalog (404 if missing),
     idempotent upsert.
4. **Naming**: endpoint `catalog-metadata`, table `catalog_metadata`.
5. **"My Fav" namespace**: virtual namespace in the UI layer (not the YAML
   loader), sentinel `"__favourites__"`, option at the top of the dropdown.
6. **Default selection**: "My Fav" is default **only when favourites exist**;
   otherwise "All namespaces".
7. **Sorting**: favourites first (sorted by `updated_at` DESC, most recent on
   top), then non-favourites alphabetically. Applies in both "My Fav" and other
   namespaces. Sort key: `(not is_favourite, -updated_at if favourite else 0,
   name.lower())`. Applied client-side in the UI callback, not the YAML loader.
8. **Star icon**: top-right of each list item. Toggle = Option B: **no
   immediate re-sort**. Star flips in place; re-sort on next namespace
   change/reload.

---

## Phase 1 — Database layer

**Status**: ✅ COMPLETE

- [x] **1.1 Create the model** — `src/app/db/models/catalog_metadata.py`:
  `CatalogMetadata(Base)` with `__tablename__ = "catalog_metadata"`, columns
  per decision #1, `updated_at` with `onupdate=func.now()` (mirroring
  `GraphTheme`). Unique constraint on `catalog_id`.
- [x] **1.2 Register the model** — add `CatalogMetadata` to
  `src/app/db/models/__init__.py` (required for Alembic autogenerate).
- [x] **1.3 Alembic migration** —
  `src/app/alembic/versions/2026_09_03_1200-0c1d2e3f4a5b_add_catalog_metadata.py`:
  `create_table('catalog_metadata', ...)` + unique constraint on `catalog_id`.
  Follows the `graph_themes` migration as the template.
- [x] **1.4 Verify** — `alembic upgrade head` applied cleanly; `\d
  catalog_metadata` confirms the expected columns + unique constraint.

### Phase 1 — Tests (must pass before Phase 2)

**Automated:**
- `tests/test_catalog_metadata_model.py` (`@pytest.mark.unit`): 7 tests pass.
  - Model instantiates with defaults (`is_favourite=False`).
  - `catalog_id` uniqueness is enforced at the model/constraint level.
  - `updated_at` is set on create and bumps on update.

**Manual:**
- `alembic upgrade head` runs cleanly on a fresh DB. ✅
- `alembic downgrade -1` rolls back cleanly. ✅
- `\d catalog_metadata` in psql shows the expected columns + unique
  constraint. ✅

---

## Phase 2 — API layer

**Status**: ✅ COMPLETE

- [x] **2.1 Query layer** — `src/app/api/queries/v1/query.py`:
  - `list_catalog_metadata(db, is_favourite=None)` — select rows, optional
    filter.
  - `get_catalog_metadata(db, catalog_id)` — single row or None.
  - `upsert_catalog_metadata(db, catalog_id, is_favourite)` —
    `INSERT ... ON CONFLICT (catalog_id) DO UPDATE SET is_favourite=...,
    updated_at=now()`.
- [x] **2.2 Service layer** — `src/app/api/queries/v1/service.py`:
  - `list_catalog_metadata(...)`, `get_catalog_metadata(...)`,
    `set_catalog_metadata(...)`.
  - `set_catalog_metadata` validates `catalog_id` against the YAML catalog via
    `get_catalog_query()` → raise `CatalogQueryNotFoundError` (404) if missing.
- [x] **2.3 Router** — `src/app/api/queries/v1/router.py`:
  - `GET /catalog-metadata` (optional `?is_favourite=` query param) →
    `{"items": [...], "count": n}`.
  - `GET /catalog-metadata/{catalog_id}` → single row or 404.
  - `PUT /catalog-metadata/{catalog_id}` → body `{"is_favourite": bool}`
    (generic partial patch), upsert, return updated row.
  - Add Pydantic models to `model.py` (`CatalogMetadataResponse`,
    `CatalogMetadataPatch`, `CatalogMetadataListResponse`).
  - Wire `db: AsyncSession = Depends(get_async_db)`.
- [x] **2.4 Verify** — curl the three endpoints; confirm upsert idempotency and
  404 on unknown `catalog_id`.

> **Note:** `catalog_id` contains a `/` (e.g. `schema/view_all_node_types`), so
> the `{catalog_id}` path param uses the `:path` converter
> (`/catalog-metadata/{catalog_id:path}`) to capture slashes.

### Phase 2 — Tests (must pass before Phase 3)

**Automated:**
- `tests/test_catalog_metadata_api.py` (`@pytest.mark.integration` + `server`):
  8 tests pass.
  - `GET /catalog-metadata` returns empty list initially.
  - `GET /catalog-metadata?is_favourite=true` filters correctly.
  - `PUT /catalog-metadata/{id}` creates a row (200) and returns it.
  - `PUT` again with same value is idempotent (no duplicate rows).
  - `PUT` with `is_favourite=false` flips an existing row.
  - `PUT` with unknown `catalog_id` returns 404.
  - `GET /catalog-metadata/{id}` returns the row; 404 when absent.

**Manual:**
- `curl` the three endpoints against a running server. ✅
- Confirm `updated_at` changes on a second `PUT`. ✅

---

## Phase 3 — UI: favourites state & star icons

**Status**: ✅ COMPLETE

- [x] **3.1 New store** — add `catalog-metadata-store` to `create_stores()` in
  `layout.py`, holding `{catalog_id: {is_favourite, updated_at}}`.
- [x] **3.2 Load favourites** — extend `load_query_catalog()` to fetch
  `GET /catalog-metadata` alongside the catalog list, populate the store.
- [x] **3.3 Star icon in list items** — in `render_catalog_query_list()`, add a
  star button (`fas fa-star` filled / `far fa-star` outline) in the top-right
  of each `dbc.ListGroupItem`, with id
  `{"type": "catalog-favourite-toggle", "catalog_id": ...}`. Filled state
  derived from the metadata store.
- [x] **3.4 Toggle callback** — new callback on the star button:
  - Fire `PUT /catalog-metadata/{catalog_id}` with `{"is_favourite": <new>}`.
  - On success, update the metadata store (flip the star in place — no
    re-sort).

> **Notes:**
> - Dash's `html.Button` uses `aria-label` (hyphenated), not `aria_label`.
> - Star styling lives in `executive-dashboard.css`
>   (`.graph-catalog-favourite-toggle`, `.graph-catalog-list-item-title-row`).

### Phase 3 — Tests (must pass before Phase 4)

**Automated:**
- `tests/test_catalog_favourites_ui.py` (`@pytest.mark.unit`): 9 tests pass.
  - Star renders filled for a favourited query, outline for non-favourite.
  - Toggle callback fires `PUT` with the correct payload.
  - Store updates after a successful toggle (star flips in place).
  - No re-sort occurs on toggle (list order unchanged).

**Manual:**
- Open Graph → Catalog; stars render per stored favourites.
- Click a star → it flips filled/outline; list order does **not** change.
- Reload the page → star state persists (DB-backed).

---

## Phase 4 — UI: "My Fav" namespace, default selection & sorting

**Status**: ✅ COMPLETE

- [x] **4.1 Namespace option** — in `build_namespace_options()`, prepend
  `{"label": "My Fav", "value": "__favourites__"}` at the top.
- [x] **4.2 Filter logic** — in `filter_catalog_queries()`, special-case
  `"__favourites__"`: filter to queries whose `catalog_id` is in the favourites
  set.
- [x] **4.3 Default selection** — in `populate_namespace_filter()` , set
  `catalog-namespace-filter` value to `"__favourites__"` if favourites exist,
  else `"__all__"`.
- [x] **4.4 Sorting** — in `render_catalog_query_list()`, apply sort key
  `(not is_favourite, -updated_at if favourite else 0, name.lower())`.
  Favourites first (recent on top), then alphabetical.

> **Notes:**
> - New constant `FAVOURITES_NAMESPACE = "__favourites__"`.
> - `build_namespace_options` now always prepends "My Fav" at the top (existing
>   test `test_build_namespace_options_includes_all_namespaces_first` updated
>   to reflect the new order).
> - `_sort_catalog_queries` uses `_timestamp_ordinal` (parses ISO-8601 to epoch
>   seconds; missing timestamps sort as oldest).

### Phase 4 — Tests (must pass before Phase 5)

**Automated:**
- `tests/test_catalog_favourites_ui.py` (extended): 18 tests pass (Phase 3 + 4).
  - "My Fav" option present at the top of the namespace dropdown.
  - Selecting "My Fav" filters to favourited queries only.
  - Default selection is "My Fav" when favourites exist, else "All namespaces".
  - Sorting: favourites first (by `updated_at` DESC), then alphabetical.

**Manual:**
- With favourites: open Catalog → defaults to "My Fav", favourites listed
  recent-first.
- With no favourites: open Catalog → defaults to "All namespaces".
- Switch to a real namespace → favourites float to the top, then alphabetical.
- Unfavourite a query in "My Fav" → it disappears from the list.

---

## Phase 5 — Tests & polish

**Status**: ⬜ NOT STARTED

- [ ] **5.1 Backend tests** — consolidate/expand
  `tests/test_catalog_metadata_api.py` for edge cases:
  - Empty `is_favourite` filter, malformed body, concurrent upserts.
- [ ] **5.2 UI tests** — extend `tests/test_catalog_favourites_ui.py` for:
  - Empty-state messaging for "My Fav" with no favourites.
  - Keyboard accessibility of the star button.
  - No regression to deep-link selection (`?catalog=`).
- [ ] **5.3 Polish** —
  - Empty-state message for "My Fav" with no favourites.
  - Ensure star is keyboard-accessible.
  - Confirm no regression to deep-link selection.

### Phase 5 — Tests (must pass before completion)

**Automated:**
- Full backend + UI suite for favourites passes.
- Existing catalog tests (`test_catalog_*`) still pass (no regression).

**Manual:**
- End-to-end: favourite a query, reload, confirm persistence; unfavourite in
  "My Fav" and confirm removal; deep-link to a query still works.

---

## Suggested execution order & dependencies

```
Phase 1 (DB) → Phase 2 (API) → Phase 3 (UI stars) → Phase 4 (My Fav + sort) → Phase 5 (tests)
```

Phases 1–2 are prerequisites for 3–4. Phase 3 and 4 could be merged if
preferred, but splitting keeps each review focused. Each phase's tests must
pass before moving to the next.

## Progress marker

Each phase has its own **Status** line and per-task checkboxes above. This is a
roll-up summary:

- [x] **Phase 1 — Database layer** (model, registration, migration, verify)
- [x] **Phase 2 — API layer** (query, service, router, verify)
- [x] **Phase 3 — UI: favourites state & star icons**
- [x] **Phase 4 — UI: "My Fav" namespace, default selection & sorting**
- [ ] **Phase 5 — Tests & polish**
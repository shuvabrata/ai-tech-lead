# Search Capability — Project Plan

## Objective

Add full-text search capability so users can find nodes and relationships of interest across all
entity types ingested from GitHub and Jira. Neo4j is the authoritative graph store but is not
optimised for free-text attribute search. Elasticsearch provides the fast keyword search layer.

Search results serve multiple surfaces:
- Dedicated search page (browse and filter all entities)
- Global search bar in the sidebar (quick navigation to the search page)
- Graph filter panel (highlight nodes already rendered in the graph — client-side, no ES call)
- Graph-from-search (deferred — needs its own design session)

---

## 1. Data Population

### 1.1 Primary path — Consumer pipeline

The existing consumer (`src/connectors/consumers/main.py`) writes `ActivitySignal` events to
Neo4j via `neo4j_sink.py`. After a **successful** Neo4j write, it calls a new
`elasticsearch_sink.py` to index the same signal into Elasticsearch.

- ES write is **non-fatal**: on failure, log a warning with the `wba_id` and continue.
  The RabbitMQ message is still acknowledged. The reconciliation script corrects any drift.
- `elasticsearch_sink.py` lives alongside the existing sink:
  `src/connectors/consumers/sinks/elasticsearch_sink.py`
- `elasticsearch` must be added to `requirements.github-consumer.txt` and
  `requirements.jira-consumer.txt` (it is already in `requirements.app.txt`).

### 1.2 Reconciliation script — `scripts/reconcile_es.py`

A **full sync** script run on demand (rarely) to correct drift between Neo4j and Elasticsearch.

**Algorithm:**
1. For each Neo4j node label, read all nodes and their relationship targets.
2. Upsert each node as an ES document into the correct index (using `wba_id` as `_id`).
3. After upserting all Neo4j nodes, query each ES index for all document `_id`s.
4. Delete any ES document whose `_id` is not present in Neo4j (full sync — inserts, updates, and deletes).

The script derives the target index name from the `id` property on every Neo4j node, which
stores the WBA canonical key (`{source}::{entity_type}::{raw_id}`), making source and entity
type parseable without additional metadata.

### 1.3 Index bootstrap — `src/app/scripts/create_es_indexes.py`

Creates all Elasticsearch indexes with explicit field mappings and registers them under the
`wba_all` alias. Called automatically from `src/app/entrypoint.sh` on every app container
start (guarded by `ELASTICSEARCH_ENABLED=true`). Idempotent — safe to re-run on every
startup (`ignore=400` for existing indexes).

The Neo4j index creation script (`src/app/scripts/create_neo4j_indexes.py`, moved from
`scripts/create_indexes.py`) is called unconditionally in the same entrypoint, before the
Elasticsearch step.

**Design constraint:** The script must export a module-level constant:

```python
MANAGED_INDEXES: list[tuple[str, str]] = [
    ("github", "Repository"),
    ("github", "Branch"),
    # ... all (source, entity_type) pairs
]
```

This constant is the authoritative registry of all `(source, entity_type)` pairs managed by
the script. It is imported by `tests/test_es_index_coverage.py` to verify that every entity
type in `SUPPORTED_ENTITY_TYPES` (from `models.py`) is covered. **Any new entity type added
to `models.py` must also be added to `MANAGED_INDEXES` — the integration test enforces this.**

**Startup sequence in `entrypoint.sh`:**
1. Wait for PostgreSQL → run `alembic upgrade head`
2. Run `init_rabbitmq.py`
3. Run `create_neo4j_indexes.py` (always)
4. Run `create_es_indexes.py` (only if `ELASTICSEARCH_ENABLED=true`)
5. Start uvicorn

---

## 2. Index Design

### 2.1 Index naming

Pattern: **`{source}_{entity_type_lowercase}_index`**

Source and entity type are included together because the same entity type name can appear in
different sources with incompatible schemas (e.g. `File` from GitHub differs from a future
`File` from another source).

| Source | Entity Type | Index Name |
|--------|-------------|------------|
| github | Repository | `github_repository_index` |
| github | Branch | `github_branch_index` |
| github | Commit | `github_commit_index` |
| github | PullRequest | `github_pullrequest_index` |
| github | Person | `github_person_index` |
| github | Team | `github_team_index` |
| github | File | `github_file_index` |
| jira | Project | `jira_project_index` |
| jira | Issue | `jira_issue_index` |
| jira | Epic | `jira_epic_index` |
| jira | Initiative | `jira_initiative_index` |
| jira | Sprint | `jira_sprint_index` |
| jira | Person | `jira_person_index` |

Derived directly from the signal: `f"{signal.source}_{signal.entity_type.lower()}_index"` —
no hardcoded mapping table required.

### 2.2 `wba_all` alias

All indexes are registered under a single alias: **`wba_all`**.

- Unfiltered searches query `wba_all` and ES fans out to all backing indexes in parallel.
- When `entity_type` or `source` filters are present, the search service constructs the
  specific index name(s) and bypasses the alias for a tighter query.
- Adding a new entity type in the future requires only updating `create_es_indexes.py` —
  zero code changes to the search API.

### 2.3 Document shape

Each ES document is a **flat merge** of the signal envelope and its entity attributes.
Relationships are stored as a keyword array of WBA canonical keys (sufficient to resolve them,
not full-text indexed).

```json
{
  "wba_id":       "jira::Issue::PROJ-123",
  "source":       "jira",
  "entity_type":  "Issue",
  "source_config":"https://mycompany.atlassian.net",
  "event_time":   "2026-05-01T12:00:00Z",

  "key":          "PROJ-123",
  "summary":      "Fix login bug on mobile",
  "priority":     "High",
  "status":       "In Progress",
  "type":         "Bug",
  "created_at":   "2026-04-01T09:00:00Z",
  "updated_at":   "2026-05-01T12:00:00Z",
  "story_points": 3.0,
  "url":          "https://mycompany.atlassian.net/browse/PROJ-123",

  "relationship_ids": [
    "jira::Epic::EPIC-10",
    "jira::Sprint::42",
    "jira::Person::557058:abc123"
  ]
}
```

The document `_id` is the `wba_id`. Indexing the same signal twice is a natural upsert — no
duplicates, no deduplication logic required.

### 2.4 Field mappings

| Field category | Fields | Mapping |
|----------------|--------|---------|
| Free-text descriptive | `summary`, `title`, `message`, `description`, `name`, `project_name`, `full_name`, `path` | `text` (english analyser) + `.keyword` sub-field (ignore_above: 512) |
| Issue / entity keys | `key` | `text` (standard analyser — tokenises `PROJ-123` → `["proj", "123"]`, enabling prefix and number matches) + `.keyword` sub-field for exact match and sort |
| Person identifiers | `login`, `email` | `text` (standard analyser — enables partial match: `alice` matches `alice_dev`; `alice` matches local part of `alice@company.com`) + `.keyword` sub-field for exact filter |
| Identifiers | `sha`, `branch_name`, `id`, `wba_id` | `keyword` |
| Categorical | `entity_type`, `source`, `status`, `priority`, `type`, `state` | `keyword` |
| Temporal | `event_time`, `created_at`, `updated_at`, `merged_at`, `closed_at` | `date` |
| Numeric | `story_points`, `additions`, `deletions`, `commits_count`, `changed_files`, `comments` | `float` / `integer` |
| Relationship targets | `relationship_ids` | `keyword` array |

**Dual mapping rationale:** `text` enables tokenised full-text search (`"login bug"` matches
`"Fix login bug on mobile"`). The `.keyword` sub-field enables exact filter, sort, and
aggregation on the same field. Storage overhead is negligible at this scale.

**`key` field note:** Jira issue keys (`PROJ-123`) are queried frequently. The standard
analyser tokenises on the hyphen, so `PROJ`, `123`, and `PROJ-123` all match. The `.keyword`
sub-field preserves the exact value for filtering and sorting.

**`login` / `email` note:** Person partial-name search is a primary use case. `login` and
`email` use the standard analyser so `alice` matches `alice_dev` and the local part of
`alice@company.com`. The `.keyword` sub-field is retained for exact filter and deduplication.

---

## 3. Search API

### 3.1 Location

New versioned endpoint in the existing FastAPI app:

```
src/app/api/search/v1/
    __init__.py
    router.py    ← GET /api/v1/search
    service.py   ← Elasticsearch query construction
    model.py     ← Pydantic request/response models
```

Registered in `src/app/main.py` following the existing router pattern.

### 3.2 Request

```
GET /api/v1/search
```

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| `q` | string | No | Free-text query. If absent, returns all documents sorted by `event_time` desc. |
| `entity_type` | string | No | Filter to a specific entity type (e.g. `Issue`, `PullRequest`). |
| `source` | string | No | Filter to a specific source (`github`, `jira`). |
| `status` | string | No | Filter by status (categorical exact match). |
| `priority` | string | No | Filter by priority (categorical exact match). |
| `date_from` | ISO date | No | Filter `event_time` ≥ this value. |
| `date_to` | ISO date | No | Filter `event_time` ≤ this value. |
| `page` | int | No | Page number, 1-based. Default: `1`. |
| `page_size` | int | No | Results per page. Default: `20`, max: `100`. |
| `full` | bool | No | If `true`, include all stored attributes in each result. Default: `false`. |

### 3.3 Elasticsearch query strategy

- **Target index:** `wba_all` alias when no `entity_type`/`source` filters are set. When
  filters are present, derive the specific index name(s): `{source}_{entity_type_lower}_index`.
- **`q` present:** `bool` query with a `multi_match` in the `must` clause and `filter` clauses
  for any categorical/date filters.
- **`q` absent:** `match_all` with `filter` clauses and `sort` by `event_time` desc.
- **`multi_match` type:** `best_fields` — the document's strongest matching field drives the
  relevance score.

**`multi_match` field list with boost weights:**

```
full_name^5, login^4, email^4, key^4,
summary^3, title^3,
message^2, description^2, name^2, project_name^2, path^2,
entity_type^1, source^1, id^1, branch_name^1
```

Person-identity fields and `key` receive the highest boost (`^4–5`) because people-centric
search and issue key lookup (e.g. `PROJ-123`) are the two most common search patterns.
Primary content fields (`summary`, `title`) are boosted above structural identifiers.

**Highlight:** Always requested via the ES `highlight` clause. One best-matching fragment per
result, capped at 150 characters, with `<em>` tags wrapping matched terms.

### 3.4 Response schema

**Default (`full=false`):**

```json
{
  "total": 47,
  "page": 1,
  "page_size": 20,
  "results": [
    {
      "wba_id":     "jira::Issue::PROJ-123",
      "score":      1.84,
      "url":        "https://mycompany.atlassian.net/browse/PROJ-123",
      "event_time": "2026-05-01T12:00:00Z",
      "highlight":  "Fix <em>login</em> <em>bug</em> on mobile Safari"
    }
  ]
}
```

**Full (`?full=true`):** Each result additionally includes an `attributes` object containing
all stored document fields exactly as indexed — no transformation layer, no custom mapping.

```json
{
  "wba_id":     "jira::Issue::PROJ-123",
  "score":      1.84,
  "url":        "https://mycompany.atlassian.net/browse/PROJ-123",
  "event_time": "2026-05-01T12:00:00Z",
  "highlight":  "Fix <em>login</em> <em>bug</em> on mobile Safari",
  "attributes": {
    "key": "PROJ-123",
    "summary": "Fix login bug on mobile",
    "priority": "High",
    "status": "In Progress",
    ...
  }
}
```

> **Important:** The `attributes` object in a `?full=true` response is the **flat ES document**
> as stored in Elasticsearch (see section 2.3). It is **not** the original `ActivitySignal`
> JSON format and must never be treated as one. Specifically:
>
> - The nested `attributes` sub-object from `ActivitySignal` is flattened — all attribute
>   fields appear at the top level of the stored document.
> - `relationships` are stored as a flat `relationship_ids` keyword array (WBA canonical keys
>   only), not as the original `Relationship` objects with `type`, `direction`, and `target`.
> - `entity_type` is present as a top-level field; it does not appear inside `attributes`.
> - Fields excluded by the `ActivitySignal` Pydantic model (e.g. internal discriminator fields)
>   may be absent.
>
> No consumer of the search API should attempt to reconstruct an `ActivitySignal` from a search
> result. **The original `ActivitySignal` shape is only guaranteed at the point of production
> (the RabbitMQ message emitted by the producer). Neither the Neo4j sink nor the Elasticsearch
> sink preserves the original signal envelope structure — both transform the signal into their
> own storage representation during ingestion.**

---

## 4. Configuration

The following env vars are already defined in `.env.example`. Wire them into
`src/app/settings.py` following the existing pydantic-settings pattern:

| Variable | Default | Description |
|----------|---------|-------------|
| `ELASTICSEARCH_ENABLED` | `false` | Feature flag. Sink and search API are no-ops when `false`. |
| `ELASTICSEARCH_URL` | `http://localhost:9200` | ES HTTP endpoint. |
| `ELASTIC_PASSWORD` | — | ES password (only needed if xpack security is enabled). |

The consumer reads these via `os.environ` directly (consistent with how it reads
`NEO4J_URI`, `RABBITMQ_URL`, etc.).

---

## 5. UI Surfaces

### 5.1 Dedicated search page — `src/app/dash_app/pages/search.py`

- **Layout:** Search bar at top, optional filter dropdowns (`entity_type`, `source`, `status`,
  `priority`, date range pickers), paginated results list below.
- **Result card:** Shows `wba_id`, `entity_type` badge, `source` badge, `url` link,
  `event_time`, and `highlight` snippet. `?full=true` toggle to expand all attributes.
- **Submit-on-Enter** (search-as-you-type deferred to a future enhancement).
- Registered as a page route in `src/app/dash_app/layout.py`.

### 5.2 Global search bar — top navbar in `src/app/dash_app/layout.py`

- Single text input in the top navbar, always visible regardless of which page is active.
- On Enter, navigates to the search page with `?q=<value>` pre-filled in the URL.
- No filter controls — just the search box.

### 5.3 Graph filter panel — client-side node highlight

- Search input in the existing graph filter panel.
- Filters/highlights nodes **already rendered** in the current graph — no ES call.
- Implementation: client-side string match against the rendered node label data.

### 5.4 Graph-from-search

Each search result card includes a **"View in Graph"** button.
Clicking it navigates to `/app/graph?node_id=<wba_id>`. The graph page detects the
`node_id` URL parameter on load and auto-executes a node-expansion query to fetch
the target node and its immediate neighbours, rendering them into the Cytoscape canvas.

The `wba_id` maps directly to the Neo4j node `id` property (same canonical key), so
no extra lookup is needed.

### 5.5 AI Agent search chain

A new `elasticsearch_chain.py` augmentation chain enriches AI chat responses with
entity context from Elasticsearch. When the user asks about a person, ticket, or
repository, the chain queries ES for matching documents and injects the top results
as structured context into the LLM prompt, alongside the existing Neo4j and MCP chains.

Feature flag: `ELASTICSEARCH_ENABLED` (reuses the existing setting).

---

## 6. Implementation Checklist

### Phase A — Infrastructure & indexing pipeline ✅ Complete (2026-05-21)

- [x] Add `elasticsearch` to `requirements.github-consumer.txt` and `requirements.jira-consumer.txt`
- [x] Wire `ELASTICSEARCH_ENABLED`, `ELASTICSEARCH_URL`, `ELASTIC_PASSWORD` into `src/app/settings.py`
- [x] Create `src/app/scripts/create_es_indexes.py` — define mappings for all 13 indexes, register `wba_all` alias; **must export `MANAGED_INDEXES: list[tuple[str, str]]`** (imported by the coverage test); apply standard analyser to `key`, `login`, `email`
- [x] ⁠~~`scripts/create_neo4j_indexes.py`~~ already done — moved from `scripts/create_indexes.py` and wired into `entrypoint.sh`
- [x] Create `src/connectors/consumers/sinks/elasticsearch_sink.py` — builds a flat document by merging signal envelope fields (`wba_id`, `source`, `entity_type`, `source_config`, `event_time`) with all attribute fields at the top level; stores `relationship_ids` as a WBA canonical key array; uses `wba_id` as the ES `_id`; upserts via `client.index()`
- [x] Update `src/connectors/consumers/main.py` — call ES sink after successful Neo4j write; log-and-continue on failure
- [x] Create `scripts/reconcile_es.py` — full sync: upsert all Neo4j nodes, delete stale ES documents (workspace root — dev tool, not in Docker image)

**Post-implementation fixes discovered during Phase A validation:**

- **Cross-provider Person dedup bug fixed** (`elasticsearch_sink.py`, `neo4j_sink.py`, `main.py`): When a Jira Person signal is deduplicated into an existing GitHub Person node by the identity resolver, the ES sink was creating a stale document under the non-existent `jira::Person::xxx` wba_id. Fixed by having `upsert_signal` return the canonical wba_id actually stored in Neo4j, and routing the ES sink through `index_signal_with_canonical_id()` which uses a partial `update` on the canonical document instead of a full `index` on the wrong id.
- **Parity test hardened** (`tests/test_es_neo4j_parity.py`): The parity test now unconditionally excludes stub nodes (`size(keys(n)) > 1`) from the Neo4j count for all entity types. Stub nodes (only `id` property) are relationship-target placeholders created by the sync module; no `ActivitySignal` is published for them so they are never indexed in ES. Confirmed stub-forming types: `jira/Issue` and `jira/Person`. Validated with a full fresh scan — **all 13 entity type parity checks pass**.

### Phase B — Search API ✅ Complete (2026-05-21)

- [x] Create `src/app/api/search/v1/__init__.py`
- [x] Create `src/app/api/search/v1/model.py` — `SearchRequest` (q, entity_type, source, status, priority, date_from, date_to, page, page_size, full), `SearchResult` (wba_id, score, url, event_time, highlight; optional attributes dict when full=true), `SearchResponse` (total, page, page_size, results)
- [x] Create `src/app/api/search/v1/service.py` — ES query builder: uses `wba_all` alias by default; derives `{source}_{entity_type_lower}_index` when filters present; `multi_match` with boost weights when `q` present; `match_all` + `event_time` desc sort when `q` absent; highlight clause (150 chars, `<em>` tags); page/offset pagination; returns raw `_source` for `full=true` without transformation
- [x] Create `src/app/api/search/v1/router.py` — `GET /api/v1/search`
- [x] Register router in `src/app/main.py`

**Post-implementation fixes discovered during Phase B validation:**

- **ES `max_result_window` guard added** (`service.py`): Requesting a page whose offset would exceed ES's default `max_result_window` of 10 000 raised `BadRequestError`. Fixed by capping `from_offset` at `min(offset, 10000)` and catching `BadRequestError` as a fallback, returning an empty result set gracefully instead of a 500.
- **`test_search_api.py` completed early** (Phase D item): 17 integration tests covering response shape, highlight, `full=true` flat attributes, Person partial login/email match, Jira key prefix/number/full-key lookup, entity_type and source filters, status filter, sort order, and pagination. Tests seed ES directly via `elasticsearch_sink.index_signal()` with controlled `wba_id` prefixes (`wbatst::`) and clean up in fixture teardown — no RabbitMQ, Neo4j, or real-data assertions.

### Phase C — UI

Phase C is broken into four sub-phases aligned with the four user-facing workflows.
C1 is the largest and is itself broken into four sequential steps (C1a–C1d). C2, C3,
and C4 are independently deliverable once C1 is live.

**Status (2026-05-22):** C1 ✅ C2 ✅ C3 ✅ C4 ⏸ blocked

#### C1 — Standalone search page with Graph-from-Search

The primary search surface. Full-featured with advanced filter options. Each result
card includes a **"View in Graph"** button that navigates to the graph page with
the node and its immediate neighbours pre-loaded.

**C1a — Route, nav link, and static layout** ✅ Complete (2026-05-22)

- [x] Create `src/app/dash_app/pages/search.py` with `get_layout()` returning:
  - Search bar (`dbc.Input`, id=`search-q-input`, placeholder "Search entities…") with
    submit button (id=`search-submit-btn`); Enter handled via `n_submit`
  - Collapsible advanced filters row: `entity_type` dropdown, `source` dropdown,
    `status` text input, `priority` text input, `date_from` / `date_to` date pickers
  - Results count label (`html.Div`, id=`search-results-count`)
  - Results area (`html.Div`, id=`search-results-container`)
  - Pagination row: Prev / page-indicator / Next (`html.Div`, id=`search-pagination-row`)
  - Hidden stores: `search-current-page` (int, default 1),
    `search-last-query-params` (dict)
  - `dcc.Location` id=`search-url` for reading `?q=` on page load
  - Design: Executive Dashboard tokens from `styles.py`; no ad-hoc inline values
- [x] Add `/app/search` branch to `display_page` routing callback in `layout.py`
- [x] Add "Search" `NavLink` to the sidebar (`fas fa-search` icon,
  `executive-nav-link` pattern)

**C1b — Search execution and result cards** ✅ Complete (2026-05-22)

- [x] Add callback `[Input("search-submit-btn", "n_clicks"), Input("search-q-input", "n_submit")]`
  → builds query params from filter controls → calls `GET /api/v1/search` (sync `httpx`
  inside the Dash callback) → renders result cards; updates `search-last-query-params`;
  resets `search-current-page` to 1; updates results count
- [x] Result card: `entity_type` badge (colour-coded by source), `source` badge,
  `wba_id` monospace, `url` hyperlink, `event_time` (formatted via `UI_DATETIME_FORMAT`),
  `highlight` snippet (`dangerously_allow_html=True` for `<em>` rendering),
  **"View in Graph" button** linking to `/app/graph?node_id=<wba_id>`
- [x] Inline alert when ES is disabled or request fails

**C1c — Pagination** ✅ Complete (2026-05-22)

- [x] Callback on Prev/Next clicks → reads `search-last-query-params` +
  `search-current-page` → calls API with updated `page` → re-renders results;
  disables Prev on page 1, disables Next when `page * page_size >= total`

**C1d — Graph-from-Search: graph page URL parameter handler** ✅ Complete (2026-05-22)

> **Note — supported URL parameters to implement:**
> The graph page currently supports `?catalog=<id>` and `?view=<graph|tabular>` (deep-linking
> to catalog queries). C1d must add two new parameters handled in the same `navigation.py`
> callback:
> - `?node_id=<wba_id>` — expand a specific node and load its immediate neighbours (primary use case from Search results)
> - `?cypher=<encoded_cypher>` — pre-fill the query console with a URL-encoded Cypher string and optionally auto-execute it

- [x] Add `dcc.Location` id=`graph-url` to the graph page layout (if not already present; the global `url` component already carries `pathname` but a page-scoped location is needed for `search` params)
- [x] Add callback in `src/app/dash_app/pages/graph/callbacks/navigation.py`:
  `Input("url", "search")` → parse `?node_id=<wba_id>` → auto-execute a
  node-expansion API call (`GET /api/v1/graph/expand`) for the target node →
  load the node + its immediate neighbours into the Cytoscape canvas;
  no-op when `node_id` param is absent
- [x] Same callback also handles `?cypher=<encoded>`: URL-decode the value, pre-fill
  `graph-query-input`, and auto-execute the query (same path as clicking Run); no-op
  when `cypher` param is absent
- [x] Follow the existing `parse_catalog_deep_link()` pattern in `catalog.py` — add a
  `parse_node_deep_link(search)` helper that returns `(node_id, cypher)`
- [x] The `wba_id` maps directly to the Neo4j node `id` property — no extra lookup needed

#### C2 — Global search bar in top navbar ✅ Complete (2026-05-22)

Always-visible quick search. No advanced filters — just the query box.

- [x] Add `dbc.Input` (id=`global-search-input`, size=`sm`, placeholder "Quick search…")
  to the top navbar row in `layout.py`, between the toggle button and the right-side
  controls
- [x] Add callback on `n_submit` → navigates to `/app/search?q=<value>` via
  `dcc.Location` and clears the input
- [x] Add callback in `search.py` on `Input("search-url", "search")` → parses `?q=`
  parameter → pre-fills `search-q-input` and auto-fires the search

**Post-implementation additions:**
- Input cleared after navigation; sun/moon icon toggle replaces text theme selector;
  `test_layout_callback_registration.py` (6 tests) guards Output declarations on key
  layout callbacks

#### C3 — Graph node spotlight search ✅ Complete (2026-05-22)

> **Design revised from original spec.** Original plan called for a client-side label
> match in the filter panel with no API call. After a design session, the approach was
> changed: ES-backed spotlight using the same search engine as C1/C2, placed in the
> graph controls bar (not the filter panel), matching via `wba_id` on both sides (renamed from the former `businessId`).

- [x] Add `dbc.Input` (id=`graph-spotlight-input`, placeholder "Search nodes…") to the
  graph controls bar in `layout.py`; inline count label (`graph-spotlight-count`);
  `dcc.Store(id="spotlight-debounced-store", storage_type="memory")`
- [x] Create `src/app/dash_app/pages/graph/callbacks/spotlight.py`:
  clientside Promise debounce (400 ms, min 3 chars) → `spotlight-debounced-store`;
  server callback calls `search_service.search()` directly (no HTTP) → applies
  `spotlight-match` / `spotlight-dim` classes; count label shows `"N of M nodes match"`
- [x] Add spotlight Cytoscape stylesheet rules to `styles.py` (amber border `#F59E0B`,
  opacity transitions, highest specificity after community-colour rules)

#### C4 — AI Agent Elasticsearch chain ⏸ Pending (blocked)

> **Status:** Blocked on chat completion / streaming pipeline issues. Will resume once
> the underlying chat stream is stable.

Integrates ES search into the AI chat augmentation pipeline so the agent can ground
its answers with real entity data from Elasticsearch.

- [ ] Create `src/app/ai_agent/chains/elasticsearch_chain.py`:
  - Async generator following the existing chain contract
  - Passes the user message directly as `q` to `GET /api/v1/search` with `full=true`,
    capped at a small result set (configurable via `ELASTICSEARCH_SEARCH_CHAIN_MAX_RESULTS`)
  - Yields `{"source": "elasticsearch", "context": "<formatted entity summary>"}` envelope
  - Returns immediately (empty envelope) when `ELASTICSEARCH_ENABLED=false`
- [ ] Register in `chains.py` `augment_message_stream()` guarded by
  `settings.ELASTICSEARCH_ENABLED`, alongside the existing Neo4j and MCP chains
- [ ] Add `ELASTICSEARCH_SEARCH_CHAIN_MAX_RESULTS: int = 5` to `settings.py`

### Phase D — Tests

- [x] `tests/test_elasticsearch_sink.py` (unit) — mock ES client; verify: flat document shape (no nested sub-objects), all envelope fields present at top level, `relationship_ids` is a list of WBA key strings, `_id` equals `wba_id`, exception propagation from `index_signal()` (non-fatal wrapping is at consumer level in `main.py`)
- [x] `tests/test_create_es_indexes.py` (unit) — assert mapping structure: dual-mapping on free-text fields, standard analyser on `key`/`login`/`email`, correct types for categorical/temporal/numeric fields, `MANAGED_INDEXES` covers all `SUPPORTED_ENTITY_TYPES`
- [x] `tests/test_es_index_coverage.py` (unit + integration/elasticsearch) — **regression guard**: schema coverage check (unit, no live ES) asserts every `SUPPORTED_ENTITY_TYPES` entry appears in `MANAGED_INDEXES`; index existence check (integration/elasticsearch) connects to live ES and asserts each `{source}_{entity_type_lower}_index` exists; `wba_all` alias coverage also verified

  **How it works:**
  - `create_es_indexes.py` must export a `MANAGED_INDEXES: list[tuple[str, str]]` constant — the authoritative list of `(source, entity_type)` pairs managed by the script.
  - The test asserts that every type in `SUPPORTED_ENTITY_TYPES` appears in at least one entry in `MANAGED_INDEXES` (schema coverage check — no live ES needed for this assertion).
  - The test also connects to live ES and asserts each `{source}_{entity_type_lower}_index` actually exists (index existence check).
  - Run with: `pytest -m "integration and elasticsearch" tests/test_es_index_coverage.py`

- [x] `tests/test_search_api.py` (integration, server, elasticsearch) — completed early during Phase B; see Phase B notes above.

---

## 7. Out of Scope

- Search-as-you-type / autocomplete (future enhancement)
- Graph-from-search is **now in scope** — see Phase C1d
- Delete reconciliation triggered automatically on signal deletion
- Multi-tenancy / access control (single-user local deployment)

---

## 8. Non-Negotiable Constraints

- **`wba_id` = Neo4j node id.** Every search result must include `wba_id`. This value is identical to the `id` property stored on every Neo4j node (`{source}::{entity_type}::{raw_id}`). The search API and UI must never omit it — it is the join key between ES results and the graph.
- **ES stays in sync with Neo4j.** The consumer pipeline and reconciliation script together guarantee this. ES is a derived read model; Neo4j is the authoritative store.
- **Original `ActivitySignal` shape is not preserved.** Neither ES nor Neo4j reconstructs the original signal envelope. Do not design any feature that assumes the original format is recoverable from either store.
- **Partial person name matching is required.** `login` and `email` use the standard analyser (dual-mapped). A user typing a partial name or email fragment must get relevant Person results.

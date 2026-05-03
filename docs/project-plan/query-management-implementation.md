# Query Catalog Integration - Implementation Plan

**Status**: Implementation In Progress (Phases 1-3 Complete)  
**Created**: March 2, 2026  
**Last Updated**: May 3, 2026  
**Related**: Graph Visualization, Query Catalog, Future Query History and Favorites

## Overview

Build a query catalog experience for the Graph page using the YAML files in `queries_catalog/` as the source of truth for shipped queries. The catalog already contains curated Cypher queries grouped by namespace, with both tabular and graph variants. The application should expose those queries through an API and present them in the Dash UI as a browsable, searchable workbench.

This replaces the earlier database-first example-query plan. PostgreSQL should not be used for shipped catalog queries. Database-backed storage can be introduced later for user-owned data such as query history, favorites, custom saved queries, and catalog usage metrics.

### Key Features

- **YAML Source of Truth**: Curated catalog queries live in `queries_catalog/` and are versioned with the repository.
- **Namespace Organization**: Query groups come from `queries_catalog/catalog.yaml`.
- **Graph and Table Variants**: Each catalog entry can expose `queries.graph` and `queries.tabular`.
- **Parameter Support**: Parameterized queries, such as person-to-person queries, render inputs in the UI and execute with Neo4j parameters.
- **Catalog API**: FastAPI endpoints serve normalized catalog metadata for browsing and selection.
- **Unified Execution API**: Raw console queries and catalog-selected queries execute through one consistent Graph API contract.
- **Graph Page Integration**: The Graph page becomes a query workbench with catalog browsing plus the existing Cypher console.
- **Future Personalization**: Query history, favorites, and custom saved queries can use PostgreSQL later without duplicating the shipped catalog.

### Design Principles

- **Catalog-first**: Shipped examples are files, not database rows.
- **No Duplication**: Do not seed catalog YAML into PostgreSQL.
- **Stable IDs**: Query IDs are derived from namespace directory and filename, such as `github/top_contributors`.
- **Safe Execution**: Catalog queries are still validated as read-only before execution.
- **Parameter Safety**: Use Neo4j parameters, not string interpolation.
- **Single Execution Path**: The UI should have one request and response shape for running queries, regardless of whether the query came from the console or the catalog.
- **Clear Ownership**: YAML catalog owns shipped queries; database owns user-generated state later.

---

## Current Catalog Shape

### Master Catalog

File: `queries_catalog/catalog.yaml`

```yaml
namespaces:
- name: Schema
  directory: schema
- name: Cross-Domain
  directory: cross_domain
- name: GitHub
  directory: github
- name: Jira
  directory: jira
- name: People & Identity
  directory: people_and_identity
- name: Person-to-Person
  directory: person_to_person
```

### Query Entry

Example: `queries_catalog/github/top_contributors.yaml`

```yaml
name: Top Contributors
description: Top 10 contributors by commit count.
queries:
  tabular: |-
    MATCH (p:Person)-[:AUTHORED_BY]-(c:Commit)
    RETURN p.name as name, p.title as title, count(c) as commits
    ORDER BY commits DESC
    LIMIT 10
  graph: |-
    MATCH p1=(p:Person)-[:AUTHORED_BY]-(c:Commit)
    RETURN p1
    LIMIT 100
tags:
- test
- table
- graph
```

Parameterized entries may include:

```yaml
parameters:
- name: person1_id
  env_var: PERSON1_ID
  required: true
- name: person2_id
  env_var: PERSON2_ID
  required: true
```

---

## Target Architecture

### Source of Truth

| Data Type | Source |
| --- | --- |
| Shipped catalog queries | YAML files in `queries_catalog/` |
| Namespace ordering and labels | `queries_catalog/catalog.yaml` |
| Query history | PostgreSQL, future phase |
| Favorites | PostgreSQL, future phase |
| User-created custom queries | PostgreSQL, future phase |
| Catalog usage metrics | PostgreSQL or analytics store, future phase |

### Normalized Catalog Model

The backend should normalize YAML into a stable shape:

```json
{
  "id": "github/top_contributors",
  "name": "Top Contributors",
  "description": "Top 10 contributors by commit count.",
  "namespace": {
    "name": "GitHub",
    "directory": "github"
  },
  "queries": {
    "tabular": "...",
    "graph": "..."
  },
  "available_views": ["tabular", "graph"],
  "parameters": [],
  "tags": ["test", "table", "graph"],
  "source_path": "queries_catalog/github/top_contributors.yaml"
}
```

### API Endpoints

**Base Path**: `/api/v1/queries`

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/catalog` | List normalized catalog entries |
| GET | `/catalog/{namespace}/{slug}` | Get one catalog entry |
| GET | `/catalog/namespaces` | Optional endpoint for namespace metadata |

Catalog endpoints are for metadata and selection only. Query execution should use the unified Graph execution endpoint.

**Base Path**: `/api/v1/graph`

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/execute` | Execute either a raw query or a catalog query using one request contract |

Raw execution request:

```json
{
  "source": "raw",
  "query": "MATCH (n) RETURN n LIMIT 10",
  "view": "auto",
  "parameters": {}
}
```

Catalog execution request:

```json
{
  "source": "catalog",
  "catalog_id": "person_to_person/direct_code_reviews",
  "view": "graph",
  "parameters": {
    "person1_id": "person-1",
    "person2_id": "person-2"
  }
}
```

Execution response should reuse the existing Graph API response model:

```json
{
  "nodes": [],
  "relationships": [],
  "rawResults": [],
  "isGraph": true,
  "resultCount": 0
}
```

---

## Phase 1: Catalog Loader and Validation

**Status**: Complete

### Objectives

- Load the YAML catalog from disk.
- Normalize all query entries.
- Validate required fields and query variants.
- Provide a small service API for other backend modules.

### Tasks

- [x] **1.1 Create Catalog Module**
  - Suggested file: `src/app/query_catalog/__init__.py`
  - Suggested file: `src/app/query_catalog/loader.py`
  - Suggested file: `src/app/query_catalog/model.py`
  - Keep filesystem access isolated in this module.

- [x] **1.2 Define Pydantic Models**
  - Suggested models:
    - `CatalogNamespace`
    - `CatalogParameter`
    - `CatalogQuery`
    - `CatalogQueryListResponse`
  - Validate:
    - `name` is present.
    - `description` is present.
    - At least one of `queries.graph` or `queries.tabular` exists.
    - Parameters have `name` and `required`.
    - Query IDs are stable and path-safe.

- [x] **1.3 Implement Loader**
  - Read `queries_catalog/catalog.yaml`.
  - Iterate namespaces in declared order.
  - Load `*.yaml` files from each namespace directory.
  - Generate IDs as `{directory}/{filename_without_ext}`.
  - Attach namespace metadata to each query.
  - Sort by namespace order, then query name.

- [x] **1.4 Validate Cypher Variants**
  - Reuse existing graph query read-only validation from `src/app/api/graph/v1/query.py`.
  - Validate both `graph` and `tabular` variants.
  - Fail fast at startup or return clear loader errors in tests.

- [x] **1.5 Tests**
  - Suggested file: `tests/test_query_catalog_loader.py`
  - Cover:
    - Master catalog loads.
    - All query IDs are unique.
    - Every query has at least one view.
    - Existing parameterized queries are detected.
    - Invalid YAML shape produces useful errors.

### Notes

Avoid caching too early unless file loading becomes expensive. A simple in-process cache is acceptable later, but tests should be able to reload from a temporary catalog path.

---

## Phase 2: Catalog API

**Status**: Complete

### Objectives

- Expose catalog metadata to the Dash frontend.
- Support graph/table variants and parameters.

### Tasks

- [x] **2.1 Create API Package**
  - Suggested files:
    - `src/app/api/queries/v1/model.py`
    - `src/app/api/queries/v1/service.py`
    - `src/app/api/queries/v1/router.py`
  - Follow the existing API package style used by `src/app/api/projects/v1/` and `src/app/api/graph/v1/`.

- [x] **2.2 Add List Endpoint**
  - `GET /api/v1/queries/catalog`
  - Optional query params:
    - `namespace`
    - `tag`
    - `q` for search
    - `view=graph|tabular`
  - Return metadata and query text only if needed by the UI. If exposing Cypher is acceptable for the console, include it; otherwise provide detail endpoint for full text.

- [x] **2.3 Add Detail Endpoint**
  - `GET /api/v1/queries/catalog/{namespace}/{slug}`
  - Return complete catalog entry with both query variants.
  - Support slash-containing IDs carefully. Options:
    - Use a path parameter like `/catalog/{namespace}/{slug}`.
    - Or encode IDs in URLs.
  - Preferred route shape:
    - `GET /api/v1/queries/catalog/{namespace}/{slug}`

- [x] **2.4 Include Router**
  - Register the queries router in `src/app/main.py` or the existing API router assembly location.

- [x] **2.5 Tests**
  - Suggested file: `tests/test_query_catalog_api.py`
  - Cover:
    - List endpoint.
    - Namespace filtering.
    - Search.
    - Detail lookup.
    - Missing query returns 404.

---

## Phase 3: Unified Graph Execution API

**Status**: Complete

### Objectives

- Replace raw-query-only execution with one request contract.
- Support both user-authored Cypher and catalog-selected queries.
- Preserve the existing `GraphResponse` response shape.
- Execute catalog queries with Neo4j parameters, not string substitution.

### Request Contract

Endpoint:

```text
POST /api/v1/graph/execute
```

Model:

```python
class GraphExecuteRequest(BaseModel):
    source: Literal["raw", "catalog"] = "raw"
    query: str | None = None
    catalog_id: str | None = None
    view: Literal["auto", "graph", "tabular"] = "auto"
    parameters: dict[str, Any] = {}
```

Validation rules:

- `source="raw"` requires `query`.
- `source="raw"` should default to `view="auto"`.
- `source="catalog"` requires `catalog_id`.
- `source="catalog"` requires `view="graph"` or `view="tabular"` unless the catalog entry declares a `default_view`.
- `source="catalog"` must validate that the requested view exists in the YAML entry.
- `source="catalog"` must validate that all required parameters are present.
- `source="catalog"` should reject unknown parameters unless the catalog entry explicitly allows them.
- All resolved Cypher is validated as read-only before execution.

### Tasks

- [x] **3.1 Replace Graph Query Request Model**
  - File: `src/app/api/graph/v1/model.py`
  - Replace or supersede `CypherQueryRequest` with `GraphExecuteRequest`.
  - Keep `GraphResponse` as the shared response model.

- [x] **3.2 Add Unified Execute Endpoint**
  - File: `src/app/api/graph/v1/router.py`
  - Add `POST /api/v1/graph/execute`.
  - No backward compatibility is required for the old `/api/v1/graph/query` endpoint.

- [x] **3.3 Add Query Resolution Service**
  - File: `src/app/api/graph/v1/service.py`
  - Flow:
    - Resolve executable Cypher from raw query or catalog reference.
    - Resolve catalog view to `queries.graph` or `queries.tabular`.
    - Validate parameters.
    - Validate read-only Cypher.
    - Execute and format result.

- [x] **3.4 Add Parameterized Execution**
  - Current lower-level Neo4j execution already supports `parameters`.
  - Extend the graph service path so formatted execution accepts `query + parameters`.
  - Do not duplicate graph/tabular response formatting.

- [x] **3.5 Tests**
  - Suggested file: `tests/test_graph_execute_api.py`
  - Cover:
    - Raw query execution request validation.
    - Catalog query resolution.
    - Missing catalog query returns 404.
    - Missing required parameter returns 400.
    - Unknown catalog parameter returns 400.
    - Invalid view returns 400.
    - Write query validation still blocks raw and catalog queries.

---

## Phase 4: Graph Page Catalog Workbench

**Status**: In Progress

### Objectives

- Present catalog queries directly inside the Graph page.
- Let users browse, search, choose Graph/Table view, enter parameters, and run.
- Keep the existing Cypher console available for inspection and manual edits.

### Current Graph Page Files

- Layout: `src/app/dash_app/pages/graph/layout.py`
- Query execution callback: `src/app/dash_app/pages/graph/callbacks/query.py`
- Analytics mode callbacks: `src/app/dash_app/pages/graph/callbacks/analytics_mode.py`
- Collaboration mode callbacks: `src/app/dash_app/pages/graph/callbacks/collaboration.py`

### UI Direction

Use a catalog workbench rather than a long accordion:

- Namespace tabs or dropdown.
- Search input.
- Query list grouped by namespace.
- Query detail area with description and tags.
- Graph/Table segmented control.
- Parameter form for required parameters.
- Buttons:
  - `Run`
  - `Load into Console`
  - Future: `Save Favorite`

The existing query console should remain the lower-level editor. Selecting a catalog query can populate the console. Running from either the catalog workbench or the console should call the same unified Graph execution endpoint.

### Tasks

- [x] **4.1 Add Layout Components**
  - Update `src/app/dash_app/pages/graph/layout.py`.
  - Add a new function such as `create_catalog_section()`.
  - Place catalog controls above the Query Console or as a left-side workbench panel.
  - Add stores:
    - `dcc.Store(id="query-catalog-store")`
    - `dcc.Store(id="selected-catalog-query-store")`
    - `dcc.Store(id="catalog-parameters-store")`

- [x] **4.2 Create Catalog Callbacks**
  - Suggested file: `src/app/dash_app/pages/graph/callbacks/catalog.py`
  - Responsibilities:
    - Fetch catalog from API on Graph page load.
    - Filter by namespace/search/view.
    - Render query list.
    - Render selected query detail.
    - Render parameter inputs.
    - Populate console with selected query variant.

- [x] **4.3 Unified Execution Callback**
  - Add a callback for the catalog `Run` button.
  - Update the existing console execute callback to call `POST /api/v1/graph/execute`.
  - Console execution sends `source="raw"` with `query`.
  - Catalog execution sends `source="catalog"` with `catalog_id`, `view`, and `parameters`.
  - Extract common response-to-UI rendering from `execute_query()` so both triggers render results through the same code path.

- [ ] **4.4 Remove Legacy Graph Query Endpoint**
  - Delete old `/api/v1/graph/query` route after the Dash Graph page has migrated to `/api/v1/graph/execute`.
  - Remove `CypherQueryRequest` if no remaining code or tests use it.
  - Update or delete tests that target `/api/v1/graph/query`.
  - Verify console and catalog execution both use the unified endpoint.

- [x] **4.5 Graph/Table Toggle**
  - Use `dbc.RadioItems` or a segmented control with values:
    - `graph`
    - `tabular`
  - Disable unavailable views if a query only has one variant.
  - Default to `graph` when available, otherwise `tabular`.

- [x] **4.6 Parameter Inputs**
  - Generate inputs from query metadata.
  - Required parameters block execution until filled.
  - Use parameter names as labels initially.
  - Later enhancement: add parameter type, label, placeholder, and helper text to the YAML schema.

- [x] **4.7 Deep Links**
  - Support URLs like:
    - `/app/graph?catalog=github/top_contributors&view=graph`
    - `/app/graph?catalog=person_to_person/direct_code_reviews&view=tabular`
  - Initial behavior can select and populate the query.
  - Later behavior can auto-run when all required parameters are present.

- [ ] **4.8 Tests and Verification**
  - Unit test pure helper functions where possible.
  - Manually verify:
    - Catalog loads.
    - Search filters entries.
    - Namespace selection works.
    - Graph variant renders Cytoscape.
    - Tabular variant renders table.
    - Parameterized query shows inputs and validates required values.

---

## Phase 5: Catalog Metadata Improvements

### Objectives

Improve the YAML schema to make the UI more useful without hardcoding behavior.

### Optional YAML Additions

```yaml
name: Direct Code Reviews
description: Find all PRs created by one and reviewed by the other.
summary: Code review collaboration between two people.
default_view: graph
parameters:
- name: person1_id
  label: First person
  type: person_id
  required: true
  placeholder: Select a person
- name: person2_id
  label: Second person
  type: person_id
  required: true
  placeholder: Select a person
queries:
  tabular: |-
    ...
  graph: |-
    ...
tags:
- code-review
- person-to-person
```

Useful additions:

- `default_view`
- Parameter `type`
- Parameter `label`
- Parameter `placeholder`
- Parameter `description`
- `recommended_layout`
- `result_limit`
- `owner`
- `status`: active, draft, deprecated

---

## Security Considerations

- Validate all catalog Cypher as read-only.
- Execute with Neo4j parameters.
- Do not perform string interpolation for parameter values.
- Validate parameter names against the catalog entry before execution.
- Keep write operations blocked for raw console queries.
- Avoid exposing filesystem paths in public API responses unless useful for internal debugging.
- Future user-generated fields such as titles and descriptions should be sanitized for UI rendering.

---

## Testing Strategy

### Unit Tests

- Catalog YAML loader.
- Stable ID generation.
- Catalog schema validation.
- Parameter requirement validation.
- Search/filter helper functions.

### API Tests

- Catalog list/detail endpoints.
- Execute endpoint request validation.
- Invalid namespace/slug handling.
- Missing parameter handling.
- Read-only validation failures.

### Frontend Verification

- Catalog section renders on Graph page.
- Namespace and search controls work.
- Query selection updates detail panel.
- Graph/Table toggle updates selected variant.
- `Load into Console` populates `graph-query-input`.
- Catalog `Run` renders graph and table responses correctly.

---

## Success Metrics

- All YAML catalog entries are discoverable in the Graph page.
- Users can run a catalog query in fewer than three interactions.
- Graph and tabular variants both work from the catalog UI.
- Parameterized person-to-person queries can be executed without editing Cypher.

---

## Dependencies

### New

- None expected if PyYAML is already available in the project. If not, add it explicitly.

### Existing

- `fastapi`
- `pydantic`
- `dash`
- `dash_bootstrap_components`
- Existing Graph API execution and formatting utilities
- Existing YAML query catalog

---

## References

- Master catalog: `queries_catalog/catalog.yaml`
- Query files: `queries_catalog/*/*.yaml`
- Graph page layout: `src/app/dash_app/pages/graph/layout.py`
- Graph query callback: `src/app/dash_app/pages/graph/callbacks/query.py`
- Graph API: `src/app/api/graph/v1/`
- Existing API style: `src/app/api/projects/v1/`

---

## Changelog

- **2026-03-02**: Initial database-first query management plan created.
- **2026-05-03**: Reworked plan to use YAML query catalog as source of truth and reserve PostgreSQL for future history, favorites, and user-owned queries.
- **2026-05-03**: Completed Phase 1 catalog loader and Phase 2 catalog metadata API.
- **2026-05-03**: Completed Phase 3 unified graph execution API with catalog query resolution and parameter validation.

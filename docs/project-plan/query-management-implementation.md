# Query Catalog Integration - Implementation Plan

**Status**: Planning Phase  
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
- **Catalog API**: FastAPI endpoints serve normalized catalog metadata and execute catalog queries.
- **Graph Page Integration**: The Graph page becomes a query workbench with catalog browsing plus the existing Cypher console.
- **Future Personalization**: Query history, favorites, and custom saved queries can use PostgreSQL later without duplicating the shipped catalog.

### Design Principles

- **Catalog-first**: Shipped examples are files, not database rows.
- **No Duplication**: Do not seed catalog YAML into PostgreSQL.
- **Stable IDs**: Query IDs are derived from namespace directory and filename, such as `github/top_contributors`.
- **Safe Execution**: Catalog queries are still validated as read-only before execution.
- **Parameter Safety**: Use Neo4j parameters, not string interpolation.
- **Incremental UI**: Reuse the existing Graph page executor and rendering behavior where possible.
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
| GET | `/catalog/{catalog_id}` | Get one catalog entry |
| POST | `/catalog/{catalog_id}/execute` | Execute graph or tabular variant with parameters |
| GET | `/catalog/namespaces` | Optional endpoint for namespace metadata |

Execution request:

```json
{
  "view": "graph",
  "parameters": {
    "person1_id": "person-1",
    "person2_id": "person-2"
  }
}
```

Execution response should reuse the existing Graph API response model where possible:

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

### Objectives

- Load the YAML catalog from disk.
- Normalize all query entries.
- Validate required fields and query variants.
- Provide a small service API for other backend modules.

### Tasks

- [ ] **1.1 Create Catalog Module**
  - Suggested file: `src/app/queries_catalog/__init__.py`
  - Suggested file: `src/app/queries_catalog/loader.py`
  - Suggested file: `src/app/queries_catalog/model.py`
  - Keep filesystem access isolated in this module.

- [ ] **1.2 Define Pydantic Models**
  - Suggested models:
    - `CatalogNamespace`
    - `CatalogParameter`
    - `CatalogQuery`
    - `CatalogQueryListResponse`
    - `CatalogExecuteRequest`
  - Validate:
    - `name` is present.
    - `description` is present.
    - At least one of `queries.graph` or `queries.tabular` exists.
    - Parameters have `name` and `required`.
    - Query IDs are stable and path-safe.

- [ ] **1.3 Implement Loader**
  - Read `queries_catalog/catalog.yaml`.
  - Iterate namespaces in declared order.
  - Load `*.yaml` files from each namespace directory.
  - Generate IDs as `{directory}/{filename_without_ext}`.
  - Attach namespace metadata to each query.
  - Sort by namespace order, then query name.

- [ ] **1.4 Validate Cypher Variants**
  - Reuse existing graph query read-only validation from `src/app/api/graph/v1/query.py`.
  - Validate both `graph` and `tabular` variants.
  - Fail fast at startup or return clear loader errors in tests.

- [ ] **1.5 Tests**
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

### Objectives

- Expose catalog metadata to the Dash frontend.
- Execute catalog queries safely through a backend endpoint.
- Support graph/table variants and parameters.

### Tasks

- [ ] **2.1 Create API Package**
  - Suggested files:
    - `src/app/api/queries/v1/model.py`
    - `src/app/api/queries/v1/service.py`
    - `src/app/api/queries/v1/router.py`
  - Follow the existing API package style used by `src/app/api/projects/v1/` and `src/app/api/graph/v1/`.

- [ ] **2.2 Add List Endpoint**
  - `GET /api/v1/queries/catalog`
  - Optional query params:
    - `namespace`
    - `tag`
    - `q` for search
    - `view=graph|tabular`
  - Return metadata and query text only if needed by the UI. If exposing Cypher is acceptable for the console, include it; otherwise provide detail endpoint for full text.

- [ ] **2.3 Add Detail Endpoint**
  - `GET /api/v1/queries/catalog/{catalog_id}`
  - Return complete catalog entry with both query variants.
  - Support slash-containing IDs carefully. Options:
    - Use a path parameter like `/catalog/{namespace}/{slug}`.
    - Or encode IDs in URLs.
  - Preferred route shape:
    - `GET /api/v1/queries/catalog/{namespace}/{slug}`
    - `POST /api/v1/queries/catalog/{namespace}/{slug}/execute`

- [ ] **2.4 Add Execute Endpoint**
  - Validate requested view exists.
  - Validate required parameters are present.
  - Execute using Neo4j parameters, not string substitution.
  - Reuse graph formatting from `src/app/api/graph/v1/service.py`.

- [ ] **2.5 Extend Existing Graph Execution Internals**
  - Current public Graph API request only accepts `query`.
  - Lower-level Neo4j execution already supports `parameters`.
  - Add a service path that can execute `query + parameters` and format the result without duplicating graph transformation logic.

- [ ] **2.6 Include Router**
  - Register the queries router in `src/app/main.py` or the existing API router assembly location.

- [ ] **2.7 Tests**
  - Suggested file: `tests/test_query_catalog_api.py`
  - Cover:
    - List endpoint.
    - Namespace filtering.
    - Search.
    - Detail lookup.
    - Missing query returns 404.
    - Missing required parameter returns 400.
    - Invalid view returns 400.

---

## Phase 3: Graph Page Catalog Workbench

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

The existing query console should remain the lower-level editor. Selecting a catalog query can populate the console. Running from the catalog can execute directly through the catalog API.

### Tasks

- [ ] **3.1 Add Layout Components**
  - Update `src/app/dash_app/pages/graph/layout.py`.
  - Add a new function such as `create_catalog_section()`.
  - Place catalog controls above the Query Console or as a left-side workbench panel.
  - Add stores:
    - `dcc.Store(id="query-catalog-store")`
    - `dcc.Store(id="selected-catalog-query-store")`
    - `dcc.Store(id="catalog-parameters-store")`

- [ ] **3.2 Create Catalog Callbacks**
  - Suggested file: `src/app/dash_app/pages/graph/callbacks/catalog.py`
  - Responsibilities:
    - Fetch catalog from API on Graph page load.
    - Filter by namespace/search/view.
    - Render query list.
    - Render selected query detail.
    - Render parameter inputs.
    - Populate console with selected query variant.

- [ ] **3.3 Direct Catalog Execution**
  - Add a callback for the catalog `Run` button.
  - Call `POST /api/v1/queries/catalog/{namespace}/{slug}/execute`.
  - Reuse the same result rendering utilities already used by `callbacks/query.py`.
  - Consider extracting common response-to-UI code from `execute_query()` to avoid duplication.

- [ ] **3.4 Graph/Table Toggle**
  - Use `dbc.RadioItems` or a segmented control with values:
    - `graph`
    - `tabular`
  - Disable unavailable views if a query only has one variant.
  - Default to `graph` when available, otherwise `tabular`.

- [ ] **3.5 Parameter Inputs**
  - Generate inputs from query metadata.
  - Required parameters block execution until filled.
  - Use parameter names as labels initially.
  - Later enhancement: add parameter type, label, placeholder, and helper text to the YAML schema.

- [ ] **3.6 Deep Links**
  - Support URLs like:
    - `/app/graph?catalog=github/top_contributors&view=graph`
    - `/app/graph?catalog=person_to_person/direct_code_reviews&view=tabular`
  - Initial behavior can select and populate the query.
  - Later behavior can auto-run when all required parameters are present.

- [ ] **3.7 Tests and Verification**
  - Unit test pure helper functions where possible.
  - Manually verify:
    - Catalog loads.
    - Search filters entries.
    - Namespace selection works.
    - Graph variant renders Cytoscape.
    - Tabular variant renders table.
    - Parameterized query shows inputs and validates required values.

---

## Phase 4: Query History and Favorites

### Objectives

- Add user-owned query state without duplicating the shipped catalog.
- Store executed raw Cypher and selected catalog references.

### Database Scope

Use PostgreSQL only for user state:

```sql
CREATE TABLE saved_queries (
    id SERIAL PRIMARY KEY,
    query_type VARCHAR(20) NOT NULL, -- history, favorite, custom
    title VARCHAR(200),
    description TEXT,
    cypher_query TEXT,
    catalog_id VARCHAR(200),
    catalog_view VARCHAR(20),
    parameters JSONB,
    tags VARCHAR(100)[],
    metadata JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    execution_count INTEGER DEFAULT 0,
    last_executed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

Rules:

- `history` can store either `cypher_query` or `catalog_id + catalog_view + parameters`.
- `favorite` can reference a catalog query without copying its Cypher.
- `custom` stores user-authored Cypher.
- Catalog entries remain in YAML.

### Future API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/history` | List recent query history |
| POST | `/history` | Save executed query |
| DELETE | `/history/{id}` | Remove history entry |
| GET | `/favorites` | List favorite queries |
| POST | `/favorites` | Create favorite |
| PATCH | `/favorites/{id}` | Update favorite metadata |
| DELETE | `/favorites/{id}` | Remove favorite |

### Notes

Favorites should store catalog references when possible. This lets a favorite benefit from future YAML query fixes without stale duplicated Cypher.

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
- No shipped catalog query is duplicated into PostgreSQL.

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

# Phase 2: Filtering & Search

[← Back to Overview](README.md) | [Next: Phase 3 →](phase-3-path-exploration.md)

---

## Phase Overview

**Goal**: Find and focus on relevant subgraphs  
**Timeline**: 2-3 weeks  
**Priority**: High (P1)  
**Status**: Planned ⏳ (Filtering plan updated)

**Scope Note**: This document now makes a concrete implementation decision for the **filtering** part of Phase 2.  
**Search strategy is intentionally left as-is for now** and will be revisited later.

---

## Progress So Far

### Completed in the first local-only filtering slice

- ✅ Clarified the current filter panel as a **loaded-graph refinement** tool
- ✅ Added a local filter mode label (`Refining loaded graph`)
- ✅ Added live before/after counts for visible vs loaded nodes/edges
- ✅ Added active filter chips for current local filter state
- ✅ Hid weight-based controls when the current graph has no weighted edges
- ✅ Added a small explanatory note when weight-based controls are unavailable
- ✅ Updated local filtering logic so unweighted graphs ignore stale weight / top-N selections
- ✅ Added focused regression tests for the local filtering behavior

### What is still intentionally not implemented yet

- ⏳ Hide-vs-dim rendering mode
- ⏳ Property-based local filtering UI
- ⏳ Backend filter registry
- ⏳ Metadata/introspection endpoint
- ⏳ `/api/v1/graph/filter`
- ⏳ Server-side property/date filtering
- ⏳ Automatic size-threshold fallback

### Why this order

- The first slice reduced current UX ambiguity without changing architecture
- It gives a stable local-filtering baseline for manual testing
- It keeps the next iteration focused on **rendering behavior** (`Hide` vs `Dim`) before introducing backend complexity

---

## Pre-Phase Decision Review

**Status**: 1 question answered ✅, 1 question pending ❓

### ✅ **Q9. Filter Execution Model**
- **Status**: ANSWERED ✅
- **Phase**: 2.1 (Node Filtering)
- **Decision**: **(c) Hybrid**
- **Decision Summary**:
  - Use **client-side filtering** for fast refinement of the **already-loaded graph** in the browser
  - Use **server-side filtering** when the user wants to filter the **database-backed graph**, when filters depend on indexed properties/date ranges, or when the loaded graph is too large for smooth browser interaction
  - Keep the graph page usable for the current Cypher-console workflow while adding a backend path for scalable filtering

#### Findings Behind This Decision

- **Current frontend architecture already favors local refinement**
  - The graph page stores a local unfiltered baseline (`unfiltered-elements-store`)
  - Existing graph filters already derive the rendered graph from that local baseline
  - The graph query console currently encourages users to load manageable subgraphs rather than the whole database

- **Current backend architecture does not yet have a dedicated filter/search API**
  - Today the graph flow is centered around:
    - `POST /api/v1/graph/query`
    - node expansion
    - collaboration graph loading
  - That means a fully server-side filtering system would be a meaningful architectural addition, not a minor extension

- **Observed Neo4j graph size is too large for browser-only filtering at full scale**
  - Raw graph observed at approximately:
    - **52,984 nodes**
    - **390,107 relationships**
  - Dominant labels:
    - `File` ~27,923
    - `Commit` ~11,951
    - `Branch` ~6,982
    - `PullRequest` ~3,214
    - `Person` ~1,441
  - Dominant relationship types:
    - `MODIFIES` ~153,492
    - `MODIFIED_BY` ~153,492
    - then much smaller review, PR, and issue relationships
  - Degree distribution is skewed:
    - `p50` degree ~5
    - `p90` degree ~22
    - `p99` degree ~130
    - max observed degree ~**14,105**

- **The raw graph is property-rich and index-rich, which makes server-side filtering valuable**
  - Neo4j already has many useful `RANGE` indexes for common fields such as:
    - `Person.name`, `Person.email`, `Person.role`, `Person.title`
    - `File.path`, `File.extension`, `File.language`
    - `PullRequest.state`, `PullRequest.created_at`, `PullRequest.merged_at`
    - `Issue.status`, `Issue.type`, `Issue.created_at`
    - `Branch.name`, `Branch.is_default`, `Branch.is_protected`
  - This strongly supports a server-side path for property/date filtering

- **The raw graph does not have a universal edge-weight concept**
  - The generic raw graph relationships do **not** have a shared `weight` property
  - That means the current weight slider / top-N relationship controls are not universally meaningful for arbitrary graph-query results

- **The collaboration graph is a special weighted case**
  - The collaboration graph is derived, weighted, and much more suitable for density filtering
  - Observed collaboration graph size:
    - about **1,050 people**
    - about **22,418 weighted collaboration edges**
  - Observed estimated Cytoscape payload sizes:
    - top-N off: about **4.33 MB**
    - top-5 per node: about **0.96 MB**
    - top-10 per node: about **1.34 MB**
    - top-20 per node: about **1.90 MB**
  - This is a strong signal that collaboration density controls should remain a first-class server-backed filtering path

#### Why Not Pure Client-Side?

- Can only filter what is already loaded into the browser
- Does not solve full-graph discovery
- Breaks down on large or hub-heavy graph results
- Cannot cleanly support scalable property/date filtering against the source graph

#### Why Not Pure Server-Side?

- Adds latency for simple interactive toggles
- Fights the current local-baseline graph page design
- Would make small graph refinement feel heavier than necessary
- Requires a larger upfront API/query-builder investment

#### Practical Conclusion

- **Client-side only** is too limited for this data size and graph variety
- **Server-side only** is too heavy for the current interaction model
- **Hybrid** best matches:
  - the existing app architecture
  - the observed Neo4j data
  - the weighted collaboration graph use case

#### Execution Rule of Thumb

- If the user is refining the **currently loaded graph**, prefer **client-side**
- If the user is narrowing the **database result set**, applying property/date filters, or working with an oversized graph, prefer **server-side**

### ❓ **Q10. Search Match Highlighting Strategy**
- **Status**: UNANSWERED ❓
- **Phase**: 2.2 (Graph Search)
- **Review Trigger**: Before starting Phase 2.2.2
- **Options**:
  - (a) Highlight nodes in-place - Change node color/border in existing graph
  - (b) Isolate matches - Hide non-matching nodes, show only results
  - (c) Both - Toggle between highlight and isolate modes
- **Impact**:
  - User experience when exploring search results
  - UI complexity for showing/hiding nodes
  - Performance for large result sets
- **Action Required**: Decide before implementing Phase 2.2.2 (Search Results Display)

---

## 2.1 Node Filtering

**Objective**: Filter visible nodes by type, property, or criteria

### Implementation Direction

Implement filtering in **two layers**:

1. **Local Graph Filters (client-side)**
   - Operate on the currently loaded `unfiltered-elements-store`
   - Fast, interactive, no network round-trip
   - Best for graph refinement after a query, expansion, or collaboration graph load

2. **Database Filters (server-side)**
   - Operate by applying filters in Neo4j before the graph payload is returned
   - Best for property/date filtering, larger result sets, and intentional narrowing of the source graph
   - Required for scalable filtering beyond the current viewport/subgraph

### Recommended Execution Rules

- **Always client-side**
  - node type toggles
  - relationship type toggles
  - hide vs dim mode
  - active filter chips/counts
  - lightweight filtering of a small already-loaded graph

- **Prefer server-side**
  - property-based filtering on the source graph
  - date/time range filtering
  - high-cardinality text filtering
  - filtering that should apply to the full database-backed result rather than the visible subset
  - collaboration graph density reduction before large Cytoscape payloads are shipped

- **Fallback to or recommend server-side when**
  - loaded graph exceeds roughly **2,000-5,000 elements**
  - estimated payload exceeds roughly **1-2 MB**
  - local graph interaction becomes noticeably sluggish
  - the user explicitly chooses **Apply to Database**

### Property Exposure Policy

- **All discovered properties are not automatically first-class filters**
- The filtering system should distinguish between:
  - **Discoverable properties**
    - properties seen in the currently loaded graph or returned by metadata introspection
    - useful for display, inspection, and limited local filtering on small graphs
  - **Supported server-filterable properties**
    - a curated backend-owned subset that is validated, typed, and safe to translate into database filters
    - generally backed by known semantics and preferably by indexes

- **Phase 2 rule**
  - all discovered properties may be surfaced for inspection
  - only **whitelisted / registry-backed properties** are server-filterable
  - the supported subset expands intentionally as new node types and indexes are introduced

### UX Model

- The filter panel should distinguish between:
  - **Refine Loaded Graph**
  - **Apply to Database**
- Avoid silent execution-mode switching when possible
- If automatic fallback happens, show a small banner or status message explaining why
- Search UI remains out of scope for this filtering update

### Backend Tasks

- [ ] **2.1.1 Filter Models and Contracts**
  - Add explicit request/response models for server-side filtering
  - Introduce:
    - `POST /api/v1/graph/filter`
  - Initial request shape:
    ```json
    {
      "baseQuery": "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 500",
      "mode": "database",
      "nodeTypeFilters": ["Person", "PullRequest"],
      "relationshipTypeFilters": ["REVIEWED_BY", "AUTHORED_BY"],
      "nodePropertyFilters": [
        {"label": "Person", "property": "name", "operator": "CONTAINS", "value": "john"},
        {"label": "Issue", "property": "status", "operator": "IN", "value": ["In Progress", "To Do"]}
      ],
      "relationshipPropertyFilters": [
        {"type": "REVIEWED_BY", "property": "state", "operator": "=", "value": "APPROVED"}
      ],
      "dateRangeFilters": [
        {"scope": "node", "label": "PullRequest", "property": "created_at", "from": "2025-01-01", "to": "2025-03-31"}
      ],
      "resultOptions": {
        "limitNodes": 1000,
        "limitRelationships": 5000,
        "includeImplicitRelationships": true
      }
    }
    ```
  - Response:
    - `GraphResponse`
    - plus optional metadata for applied filters, truncation, and execution mode

- [ ] **2.1.1a Filter Property Registry**
  - Introduce a backend-owned filter registry defining which properties are officially filterable
  - Recommended location:
    - `app/api/graph/v1/filter_registry.py`
  - Registry responsibilities:
    - define supported node labels and relationship types
    - define supported properties for each label/type
    - define property type information:
      - string
      - number
      - boolean
      - date/datetime
      - enum/list-like
    - define allowed operators per property
    - define whether the property is:
      - local-filterable
      - server-filterable
      - indexed / preferred
    - define optional UI hints:
      - widget type
      - display label
      - suggested sort order
      - enum options when known
  - Example shape:
    ```python
    FILTER_REGISTRY = {
        "nodes": {
            "Person": {
                "name": {"type": "string", "operators": ["=", "CONTAINS", "STARTS WITH"], "server": True, "indexed": True},
                "email": {"type": "string", "operators": ["=", "CONTAINS"], "server": True, "indexed": True},
                "role": {"type": "string", "operators": ["=", "IN"], "server": True, "indexed": True},
                "is_manager": {"type": "boolean", "operators": ["="], "server": False, "local": True}
            },
            "File": {
                "path": {"type": "string", "operators": ["=", "CONTAINS", "STARTS WITH"], "server": True, "indexed": True},
                "extension": {"type": "string", "operators": ["=", "IN"], "server": True, "indexed": True},
                "language": {"type": "string", "operators": ["=", "IN"], "server": True, "indexed": True},
                "is_test": {"type": "boolean", "operators": ["="], "server": True, "indexed": True}
            }
        },
        "relationships": {
            "REVIEWED_BY": {
                "state": {"type": "string", "operators": ["="], "server": True}
            }
        }
    }
    ```
  - This registry becomes the source of truth for **server-side filterability**

- [ ] **2.1.2 Filter Query Builder**
  - Build server-side filter translation from validated filter specs to Cypher fragments
  - Support:
    - node label/type filters
    - relationship type filters
    - property predicates
    - date range predicates
  - Preserve read-only guarantees
  - Avoid raw user Cypher injection
  - Treat `baseQuery` as the graph-producing source query, then apply validated filters to the resulting graph scope
  - Only generate server-side predicates for properties defined in the filter registry

- [ ] **2.1.3 Graph Metadata / Introspection Endpoint**
  - Add endpoint for filter UI metadata, for example:
    - available node labels in current graph
    - relationship types in current graph
    - property keys by label/type
    - primitive type hints when inferable
  - Purpose:
    - avoid guessing filter forms in the frontend
    - support richer filter UIs for both loaded-graph and database modes
  - Metadata response should merge two sources:
    - **live discovery** from the current graph / database sample
    - **registry metadata** for officially supported server-side filters
  - This lets the UI distinguish:
    - “property exists”
    - “property is supported for server filtering”

- [ ] **2.1.4 Collaboration Density Filtering**
  - Keep collaboration-specific density controls as a first-class server-side filtering path
  - Extend the collaboration endpoint and/or pipeline to support:
    - `top_n_edges_per_node`
    - optional minimum weight threshold
    - optional layer include/exclude toggles
  - Long-term improvement:
    - push more pair pruning earlier in the pipeline so we do not always ship/process the full weighted pair set before reduction

- [ ] **2.1.5 Result Metadata**
  - Include metadata on whether results were:
    - client-refined locally
    - filtered server-side
    - truncated due to safety limits
  - Include counts such as:
    - nodes before/after
    - relationships before/after
    - execution time
    - any threshold-triggered fallback reason

### Frontend Tasks

- [ ] **2.1.6 Filter Panel UI**
  - Component: Collapsible panel on right side
  - Keep current sections and extend them:
    - **Node Type Filter**: Multi-select checkboxes for labels
    - **Property Filters**: Dynamic form based on node properties
    - **Relationship Filter**: Show/hide relationship types
    - **Advanced**: Cypher WHERE clause input
  - Add execution-mode grouping:
    - **Refine Loaded Graph**
    - **Apply to Database**
  - Add status text showing current mode and whether fallback occurred

- [ ] **2.1.7 Property-Based Filtering**
  - Auto-detect properties from loaded nodes and/or metadata endpoint
  - Operators:
    - `=`, `!=`, `>`, `<`, `>=`, `<=`, `CONTAINS`, `STARTS WITH`, `IN`
  - Property types:
    - String, Number, Boolean, Date, List
  - Add date range picker for temporal properties
  - Add multi-select for categorical properties
  - Prefer server-side execution for:
    - date ranges
    - high-cardinality text fields
    - indexed properties when filtering the full graph
  - Keep simple local property filtering only for small loaded graphs
  - UI should clearly mark whether a property is:
    - available only for local filtering
    - fully supported for database filtering
  - Avoid exposing “Apply to Database” for properties not present in the backend registry

- [ ] **2.1.8 Visual Filter Feedback**
  - Dim filtered-out nodes (opacity: 0.3)
  - Option: Hide vs. dim
  - Filter count badge: `Showing 45/200 nodes`
  - Active filters tag list (removable chips)
  - Show whether counts are:
    - local graph counts
    - database result counts
  - Show warning/banner when graph is too large for smooth local filtering

- [ ] **2.1.9 Saved Filters**
  - Save filter presets with names
  - Quick apply from dropdown
  - Share filter URLs
  - Presets should store execution hints:
    - local-only safe preset
    - database-backed preset
  - Share URLs should include enough state to recreate server-side filters deterministically

### Concrete Rollout Plan

- [ ] **2.1.A Phase 1 - Stabilize and clarify existing local filtering**
- [x] **2.1.A Phase 1 - Stabilize and clarify existing local filtering**
  - Keep current node type / relationship type / weight / top-N controls
  - Make the current panel explicitly a **loaded-graph refinement** tool
  - Add hide-vs-dim behavior
  - Add active-filter chips and before/after counts
  - Add safeguards so weight-based controls are only shown when the current graph actually has weighted edges
  - Rationale:
    - current raw graph results generally do not carry a `weight` property
    - collaboration graphs do
  - **Implemented so far**:
    - explicit loaded-graph refinement label
    - active-filter chips
    - before/after counts
    - weighted-edge gating for weight controls
    - unweighted-graph guard for stale weight / top-N selections
  - **Remaining within this phase**:
    - add `Hide` vs `Dim` display mode

- [ ] **2.1.B Phase 2 - Add server-side filter API for database-backed filtering**
  - Introduce `/api/v1/graph/filter`
  - Add validated filter models
  - Add backend filter registry as the initial source of truth for server-filterable fields
  - Support node/relationship type filters and a minimal property/date filter subset first
  - Start with indexed/high-value fields:
    - `Person.name`, `Person.email`, `Person.role`, `Person.title`
    - `File.path`, `File.extension`, `File.language`, `File.is_test`
    - `PullRequest.state`, `PullRequest.created_at`, `PullRequest.merged_at`
    - `Issue.status`, `Issue.type`, `Issue.created_at`
    - `Branch.name`, `Branch.is_default`, `Branch.is_protected`

- [ ] **2.1.C Phase 3 - Add execution thresholds and automatic fallback**
  - Introduce heuristics for switching/recommending database mode when:
    - graph element count is too high
    - payload estimate is too large
    - local interaction latency becomes poor
  - Suggested starting thresholds:
    - soft warning at about **2,000 elements**
    - recommend database filtering at about **5,000 elements**
    - recommend server-side/density reduction at about **1-2 MB** estimated payload
  - Record threshold hits in logs for tuning

- [ ] **2.1.D Phase 4 - Collaboration-specific optimization**
  - Move collaboration density controls into a more explicit server-backed filter workflow
  - Preserve existing `top_n_edges_per_node`
  - Add optional minimum weight threshold and layer toggles
  - Evaluate pruning earlier in Cypher or earlier in the analytics pipeline to avoid always processing the largest pair set

- [ ] **2.1.E Phase 5 - Presets and URL state**
  - Save and share hybrid filter states
  - Persist whether a preset is intended for local refinement or database-backed filtering

### Risks and Mitigations

- **Risk: confusing dual-mode UX**
  - Mitigation:
    - explicitly label local vs database actions
    - show current execution mode
    - show fallback banner when mode changes automatically

- **Risk: trying to support arbitrary Cypher + arbitrary server-side filtering too early**
  - Mitigation:
    - start with validated filter models and a bounded property whitelist
    - keep advanced raw Cypher filtering as a later phase

- **Risk: future node types appear in the graph but have no useful filters**
  - Mitigation:
    - allow discovery of new labels/properties automatically
    - add server-side support by extending the backend filter registry
    - make registry updates part of onboarding new graph entities

- **Risk: weight-based controls appear broken on generic graph queries**
  - Mitigation:
    - hide or disable weight-specific controls unless the current graph contains weighted edges
    - keep collaboration density controls as a separate, well-labeled weighted-graph use case

- **Risk: backend complexity grows quickly**
  - Mitigation:
    - stage rollout
    - prioritize indexed properties and common labels first
    - instrument execution time and payload size from day one

---

## 2.2 Graph Search

**Objective**: Find nodes by property or pattern

### Tasks
- [ ] **2.2.1 Full-Text Search**
  - Backend: Leverage Neo4j full-text indexes
  - Endpoint: `POST /api/v1/graph/search`
  - Request: `{"query": "John Doe", "labels": ["Person"], "properties": ["name", "email"]}`
  - Response: Matching nodes + their immediate neighbors

- [ ] **2.2.2 Search UI**
  - Component: Search bar at top of graph view
  - Features:
    - Auto-complete from loaded nodes
    - Search as you type (debounced)
    - Filter by node type
    - Regex support toggle
  - Results: Highlight matching nodes, zoom to fit

- [ ] **2.2.3 Advanced Search (Cypher Patterns)**
  - Pattern builder UI: Drag nodes/edges to construct patterns
  - Example: "Find Persons who work on Projects in London"
  - Preview: Show pattern as visual graph template
  - Execute: Run pattern match, visualize results

- [ ] **2.2.4 Search History**
  - Store recent searches (last 20)
  - Quick re-run from dropdown

---

## 2.3 Relationship Filtering

**Objective**: Show/hide relationships by type or property

### Tasks
- [ ] **2.3.1 Relationship Type Toggle**
  - UI: Checkbox list of all relationship types in graph
  - Action: Show/hide edges of selected types
  - Batch toggle: "Show All" / "Hide All"
  - Default execution mode:
    - client-side for loaded graphs
    - server-side only when the user is filtering the source graph or the graph exceeds size thresholds

- [ ] **2.3.2 Relationship Property Filter**
  - Similar to node property filters
  - Example: Show only relationships where `since > 2020`
  - Prefer server-side execution because relationship properties in the raw graph are sparse and type-specific
  - Start with bounded, known fields instead of generic arbitrary property filtering

- [ ] **2.3.3 Relationship Density Control**
  - Slider: Show top-N relationships (by weight, count, etc.)
  - Use case: Reduce visual clutter in dense graphs
  - Split this feature into two variants:
    - **Local density refinement** for already-loaded weighted graphs
    - **Server-backed density reduction** for collaboration graphs and oversized graph results
  - Do not assume generic graph relationships carry a `weight` property

---

## Related Changelog Entries

_No changelog entries yet for Phase 2._

---

[← Back to Overview](README.md) | [Next: Phase 3 →](phase-3-path-exploration.md)

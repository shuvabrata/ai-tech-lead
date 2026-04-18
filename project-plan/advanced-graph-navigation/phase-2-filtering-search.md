# Phase 2: Filtering & Search

[← Back to Overview](README.md) | [Next: Phase 3 →](phase-3-path-exploration.md)

---

## Phase Overview

**Goal**: Find and focus on relevant subgraphs  
**Timeline**: 2-3 weeks  
**Priority**: High (P1)  
**Status**: In Progress 🔄 (2.1.A complete, 2.1.B mostly complete, 2.1.C UX layer complete — database execution pending)

**Scope Note**: This document now makes a concrete implementation decision for the **filtering** part of Phase 2.  
**Search strategy is intentionally left as-is for now** and will be revisited later.

---

## Progress So Far

### Completed in the first local-only filtering slice

- ✅ Clarified the current filter panel as a **loaded-graph refinement** tool
- ✅ Added a local filter mode label (`Refining loaded graph`)
- ✅ Added live before/after counts for visible vs loaded nodes/edges
- ✅ Added active filter chips for current local filter state
- ✅ Added **Hide vs Dim** display behavior for filtered-out elements *(with known hover interaction issue in Dim mode)*
- ✅ Hid weight-based controls when the current graph has no weighted edges
- ✅ Added a small explanatory note when weight-based controls are unavailable
- ✅ Updated local filtering logic so unweighted graphs ignore stale weight / top-N selections
- ✅ Added focused regression tests for the local filtering behavior

### What is still intentionally not implemented yet

- ⏳ Property-based local filtering UI
- ⏳ Full filter query-builder translation into Cypher
- ⏳ Advanced server-side property/date filtering coverage
- ⏳ Automatic size-threshold fallback

### Why this order

- The first slice reduced current UX ambiguity without changing architecture
- It gives a stable local-filtering baseline for manual testing
- It keeps the next iteration focused on **property filtering and backend scaffolding** after completing `Hide` vs `Dim`

### Hide vs Dim Slice (Implemented)

#### Exact coding checklist completed

- ✅ Added a local-only display mode control to the filter panel
- ✅ Refactored filter logic so one shared helper computes the logical visible subset
- ✅ Kept `Hide` mode returning only visible elements
- ✅ Added `Dim` mode returning all loaded elements while tagging non-visible ones with a dimming class
- ✅ Preserved existing Cytoscape classes when dimming, including collaboration graph classes
- ✅ Made dimming work for edges with and without explicit edge ids
- ✅ Kept summary counts based on the logical visible subset, not the rendered element count
- ✅ Added stylesheet rules for dimmed nodes/edges
- ✅ Added focused tests for:
  - `Hide` mode
  - `Dim` mode
  - unweighted graph behavior
  - logical counts in `Dim` mode
  - edge dimming when edge ids are absent

#### Code areas updated

- `app/dash_app/layout.py` (added `Hide | Dim` display-mode control)
- `app/dash_app/pages/graph/filtering.py` (shared logical visibility helper + `Dim` rendering behavior)
- `app/dash_app/styles.py` (dimming stylesheet rules)
- `tests/test_graph_filtering_callbacks.py` (focused filtering behavior tests)

#### Verification status

- Command run:
  - `PYTHONPATH=. pytest tests/test_graph_filtering_callbacks.py tests/test_graph_callbacks_regression.py`
- Result:
  - ✅ `6 passed`

#### Manual test checklist

- [x] Load a normal graph query and switch between `Hide` and `Dim`
- [x] Apply node/relationship filters and confirm:
  - `Hide` removes non-matches
  - `Dim` keeps non-matches faintly visible
- [x] Load collaboration mode and confirm:
  - community colors still show
  - dimming layers on top without breaking styling
- [x] Toggle filters while in `Dim` mode and confirm summary counts still reflect visible matches, not total rendered elements
- [x] Use `Clear All` and confirm graph returns to unfiltered state while selected display mode remains unchanged

#### Known Issues

**Issue: Dim mode + edge hover interaction conflict**
- **Description**: When hovering over edges in `Dim` mode, if the connected nodes are dimmed (filtered), the hover highlighting interacts poorly with the filter dimming. Attempting to preserve the dimmed class during hover causes unexpected visual behavior.
- **Root Cause**: The clientside edge hover callback and the filter dimming CSS class are not properly separated. The hover interaction applies/removes classes globally without distinguishing between filter-applied dimming and interaction-state highlighting.
- **Workaround**: Use `Hide` mode instead of `Dim` to avoid the interaction, or avoid hovering over edges connected to dimmed nodes.
- **Future Fix Strategy**: Requires refactoring the hover highlighting to use a separate state mechanism (e.g., CSS pseudo-classes, data attributes, or a distinct interaction class) that doesn't conflict with the filter dimming class.
- **Priority**: Nice-to-have; current core filtering functionality works correctly in both `Hide` and `Dim` modes when not interacting via hover.

#### Next recommended slice

- `Option A`: local property filtering UI
- `Option B`: collaboration density reduction and weighted-edge pruning before render

### 2.1.B Backend Filtering Experiment (Rolled Back)

This slice was implemented experimentally and then removed after validation showed it did not improve the actual user experience. The main bottleneck remained Cytoscape rendering of large payloads, so the active plan no longer includes backend filtering.

#### Outcome

- Code and tests for backend filtering have been removed from the active codebase
- The graph page now uses local-only filtering on the loaded graph
- Future performance work should focus on reducing graph payload size before rendering, especially for collaboration graphs

#### Code areas updated

- Backend filter-specific files and tests were removed during rollback

#### Verification status

- Verified by focused graph callback, query regression, router, and service tests after rollback

#### Status

- Archived. Do not extend this path further.

### 2.1.3 Graph Metadata / Introspection Endpoint (Removed)

The temporary metadata endpoint created to support backend filtering was also removed as part of the rollback.

#### Outcome

- Filter metadata responsibilities are no longer part of the active graph API surface
- Any future schema/introspection work should be scoped to local UI affordances or search, not backend filter execution


---

## Pre-Phase Decision Review

**Status**: 1 question answered ✅, 1 question pending ❓

### ✅ **Q9. Filter Execution Model**
- **Status**: ANSWERED ✅
- **Phase**: 2.1 (Node Filtering)
- **Decision**: **(a) Local-only**
- **Decision Summary**:
  - Use **client-side filtering** for refinement of the **already-loaded graph** in the browser
  - Keep graph filtering scoped to visible data and avoid extra backend filter APIs
  - Focus performance work on loading smaller graphs and pruning collaboration payloads before Cytoscape render

#### Findings Behind This Decision

- **Current frontend architecture already favors local refinement**
  - The graph page stores a local unfiltered baseline (`unfiltered-elements-store`)
  - Existing graph filters already derive the rendered graph from that local baseline
  - The graph query console currently encourages users to load manageable subgraphs rather than the whole database

- **Current graph architecture already centers on loaded-graph interaction**
  - Today the graph flow is centered around:
    - `POST /api/v1/graph/query`
    - node expansion
    - collaboration graph loading
  - This fits local refinement naturally and avoids maintaining a second filter execution path

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

- **Large-graph pain comes primarily from render density, not just query size**
  - Manual validation showed that returning a server-filtered graph still felt slow when Cytoscape had to render a large edge set
  - That makes density reduction and query scoping more valuable than maintaining a separate backend filter API

- **The raw graph does not have a universal edge-weight concept**
  - The generic raw graph relationships do **not** have a shared `weight` property
  - That means the current weight slider / top-N relationship controls are not universally meaningful for arbitrary graph-query results

- **The collaboration graph is the special weighted case**
  - The collaboration graph is derived, weighted, and still the strongest place to invest in density filtering
  - Observed collaboration graph size:
    - about **1,050 people**
    - about **22,418 weighted collaboration edges**
  - Observed estimated Cytoscape payload sizes:
    - top-N off: about **4.33 MB**
    - top-5 per node: about **0.96 MB**
    - top-10 per node: about **1.34 MB**
    - top-20 per node: about **1.90 MB**
  - This is a strong signal that collaboration density controls should prune payloads before render, not that the generic graph page needs a separate backend filter API

#### Why Local-Only Fits Better

- Matches the existing loaded-graph baseline design
- Keeps interaction fast and predictable once a graph is loaded
- Avoids a second API/model/query-builder surface that did not pay for its complexity
- Keeps future optimization effort focused on graph loading strategy and collaboration pruning

#### Practical Conclusion

- Use local filtering for the current graph page
- Load narrower graphs when working with raw Neo4j data
- Optimize collaboration payload size before render for the weighted graph use case

#### Execution Rule of Thumb

- If the user is refining the **currently loaded graph**, use **local filtering**
- If the graph is too large, reduce it at query/load time rather than trying to introduce a separate backend filter workflow

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

Implement filtering in **one layer**:

1. **Local Graph Filters (client-side)**
  - Operate on the currently loaded `unfiltered-elements-store`
  - Fast, interactive, no network round-trip
  - Best for graph refinement after a query, expansion, or collaboration graph load

### Recommended Execution Rules

- **Always client-side**
  - node type toggles
  - relationship type toggles
  - hide vs dim mode
  - active filter chips/counts
  - lightweight filtering of a small already-loaded graph

- **When local filtering is not enough**
  - narrow the source Cypher query before loading
  - rely on node expansion instead of loading larger subgraphs up front
  - reduce collaboration density before render with top-N, thresholds, or layer-specific pruning

### Property Exposure Policy

- **All discovered properties are not automatically first-class filters**
- The filtering system should distinguish between:
  - properties that are practical for local UI controls on the loaded graph
  - properties that are better handled by writing a narrower source query before loading results

- **Phase 2 rule**
  - all discovered properties may be surfaced for inspection
  - local controls should stay bounded and purposeful
  - if a property needs heavy-duty filtering semantics, revisit it as part of query authoring or search, not a generic backend filter system

### UX Model

- The filter panel should explicitly present itself as **Refine Loaded Graph**
- Avoid dual-mode behavior or execution-mode switching
- Show a warning/banner when the loaded graph is too large for smooth local interaction
- Search UI remains out of scope for this filtering update

### Backend Tasks

- [ ] **2.1.1 Local Property Filter UX Review**
  - Decide which loaded-graph properties deserve first-class local controls
  - Keep the control set intentionally small and understandable

- [ ] **2.1.2 Query Narrowing Guidance**
  - Improve the graph page guidance for writing narrower Cypher before load
  - Prefer better query templates, examples, and expansion workflows over generic backend filter execution
  - Build server-side filter translation from validated filter specs to Cypher fragments
  - Support:
    - node label/type filters
    - relationship type filters
    - property predicates
- [ ] **2.1.3 Graph Property Discovery for Local UX**
  - Improve local filter affordances using the properties already present in the loaded graph
  - Surface only the information needed to build useful local controls
  - Avoid introducing a dedicated metadata endpoint unless a future search feature actually requires it

- [ ] **2.1.4 Collaboration Density Filtering**
  - Keep collaboration-specific density controls as a first-class optimization path
  - Extend the collaboration endpoint and/or pipeline to support:
    - `top_n_edges_per_node`
    - optional minimum weight threshold
    - optional layer include/exclude toggles
  - Long-term improvement:
    - push more pair pruning earlier in the pipeline so we do not always ship/process the full weighted pair set before reduction

- [ ] **2.1.5 Result Metadata**
  - Include metadata on whether results were:
    - client-refined locally
    - truncated due to safety limits
  - Include counts such as:
    - nodes before/after
    - relationships before/after
    - execution time
    - any threshold-triggered warning reason

### Frontend Tasks

- [ ] **2.1.6 Filter Panel UI**
  - Component: Collapsible panel on right side
  - Keep current sections and extend them:
    - **Node Type Filter**: Multi-select checkboxes for labels
    - **Property Filters**: Dynamic form based on node properties
    - **Relationship Filter**: Show/hide relationship types
  - Add status text showing loaded-graph size and local refinement scope

- [ ] **2.1.7 Property-Based Filtering**
  - Auto-detect properties from loaded nodes
  - Operators:
    - `=`, `!=`, `>`, `<`, `>=`, `<=`, `CONTAINS`, `STARTS WITH`, `IN`
  - Property types:
    - String, Number, Boolean, Date, List
  - Add date range picker for temporal properties
  - Add multi-select for categorical properties
  - Keep property filtering bounded to practical loaded-graph cases
  - For larger source-graph narrowing, rely on the initial Cypher query instead of a separate filter execution mode

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
    - `Hide` vs `Dim` display mode
    - active-filter chips
    - before/after counts
    - weighted-edge gating for weight controls
    - unweighted-graph guard for stale weight / top-N selections

- [x] **2.1.B Phase 2 - Simplify to local-only filtering**
  - Remove the experimental alternate filtering path
  - Remove no-longer-used models, service code, registry, and tests
  - Keep graph filtering local-only

- [ ] **2.1.C Phase 3 - Add execution thresholds and automatic fallback**
  - Keep heuristics only as local warning banners when:
    - graph element count is too high
    - local interaction latency becomes poor
  - Suggested starting thresholds:
    - soft warning at about **2,000 elements**
    - high warning at about **5,000 elements**
  - Record threshold hits in logs for tuning if needed
  - **Current state**:
    - ✅ local-only threshold warning banner remains available for large loaded graphs
    - ✅ no auto-switch or dual-mode controls remain in the graph UI

#### 2.1.C Current Progress

- [x] Remove the alternate filtering callback path
- [x] Remove auto-switch / restore-original filter UI controls
- [x] Remove extra fallback-only stores from graph layout/query/collaboration callback contracts
- [x] Simplify threshold feedback to local-only warning banners
- [x] Realign local filtering callback tests and query callback regression tests
- [x] Remove unused API/model/service/query-builder code tied to the alternate path
- [x] Rewrite remaining Phase 2 plan sections around a local-only strategy

#### 2.1.C Progress Update

- ✅ Large-graph threshold feedback remains as local-only UI guidance
- ✅ Dual-mode UI and auto-switching have been removed
- ✅ Query and collaboration callbacks are back to a single working baseline contract
- ✅ Removed API, model, service, and dedicated test code for the discarded alternate path
- ⚠️ Observed in manual validation: reducing query work alone does not solve lag when Cytoscape still renders very large edge sets
- ➡️ Practical next target moved to `2.1.D`: collaboration-specific payload reduction before render (top-N/weight/layer pruning)

#### 2.1.C Known Limitation

- The remaining large-graph banner is informational only; it does not trigger any alternate execution mode.

- [ ] **2.1.D Phase 4 - Collaboration-specific optimization**
  - Keep collaboration density controls focused on payload reduction before render
  - Preserve existing `top_n_edges_per_node`
  - Add optional minimum weight threshold and layer toggles
  - Evaluate pruning earlier in Cypher or earlier in the analytics pipeline to avoid always processing the largest pair set

- [ ] **2.1.E Phase 5 - Presets and URL state**
  - Save and share local filter states
  - Persist only the state needed to recreate the loaded-graph refinement view

### Risks and Mitigations

- **Risk: local filtering applied to a graph that is already too large**
  - Mitigation:
    - explicitly label the panel as loaded-graph refinement
    - show warning banners for large loaded graphs
    - encourage narrower queries and expansion-driven exploration

- **Risk: trying to turn the filter panel into a generic query builder**
  - Mitigation:
    - keep local controls bounded and purposeful
    - use the Cypher console for advanced source-graph narrowing

- **Risk: future node types appear in the graph but have no useful filters**
  - Mitigation:
    - allow discovery of new labels/properties automatically
    - add or adjust local controls only when they materially improve the UX

- **Risk: weight-based controls appear broken on generic graph queries**
  - Mitigation:
    - hide or disable weight-specific controls unless the current graph contains weighted edges
    - keep collaboration density controls as a separate, well-labeled weighted-graph use case

- **Risk: collaboration graphs still ship too much data**
  - Mitigation:
    - prioritize pruning earlier in the collaboration pipeline
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

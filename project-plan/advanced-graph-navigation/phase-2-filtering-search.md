# Phase 2: Filtering & Search

[← Back to Overview](README.md) | [Next: Phase 3 →](phase-3-path-exploration.md)

---

## Phase Overview

**Goal**: Find and focus on relevant subgraphs  
**Timeline**: 2-3 weeks  
**Priority**: High (P1)  
**Status**: In Progress 🔄 (2.1.A complete, 2.1.B complete, 2.1.C complete)

**Scope Note**: This document now makes a concrete implementation decision for the **filtering** part of Phase 2.  
**Search strategy is intentionally left as-is for now** and will be revisited later.

---

## Progress So Far

### Completed

- ✅ Clarified the current filter panel as a **loaded-graph refinement** tool
- ✅ Added a local filter mode label (`Refining loaded graph`)
- ✅ Added live before/after counts for visible vs loaded nodes/edges
- ✅ Added active filter chips for current local filter state
- ✅ Added **Hide vs Dim** display behavior for filtered-out elements *(with known hover interaction issue in Dim mode)*
- ✅ Hid weight-based controls when the current graph has no weighted edges
- ✅ Added a small explanatory note when weight-based controls are unavailable
- ✅ Updated local filtering logic so unweighted graphs ignore stale weight / top-N selections
- ✅ Added focused regression tests for the local filtering behavior

### Next Up

- ⏳ Property-based local filtering UI
- ⏳ Query narrowing guidance in graph UX

### Current Recommendation

- `Option A`: local property filtering UI
- `Option B`: collaboration density reduction and weighted-edge pruning before render


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
  - reduce collaboration density before render with top-N, minimum-weight controls, or layer-specific pruning

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
- Search UI remains out of scope for this filtering update

### Implementation Tasks

- [ ] **2.1.1 Local Property Filter UX Review**
  - Decide which loaded-graph properties deserve first-class local controls
  - Keep the control set intentionally small and understandable

- [ ] **2.1.2 Query Narrowing Guidance**
  - Improve the graph page guidance for writing narrower Cypher before load
  - Prefer better query templates, examples, and expansion workflows over generic backend filter execution
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
    - optional performance notes

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
  - Show local graph counts clearly

- [ ] **2.1.9 Saved Filters**
  - Save filter presets with names
  - Quick apply from dropdown
  - Share filter URLs
  - Presets should store local refinement state only
  - Share URLs should include enough state to recreate local filter selections

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

- [x] **2.1.C Phase 3 - Remove threshold-based suggestions from filter UX**
  - Remove threshold-warning suggestion UI from local filtering panel
  - Keep filter UX focused on deterministic controls (type/relationship/weight/top-N/hide-dim)
  - **Current state**:
    - ✅ no threshold-based suggestions remain in the graph UI
    - ✅ no auto-switch or dual-mode controls remain in the graph UI

#### 2.1.C Current Progress

- [x] Remove the alternate filtering callback path
- [x] Remove auto-switch / restore-original filter UI controls
- [x] Remove extra fallback-only stores from graph layout/query/collaboration callback contracts
- [x] Remove threshold feedback from local filter panel callbacks/layout/tests
- [x] Realign local filtering callback tests and query callback regression tests
- [x] Remove unused API/model/service/query-builder code tied to the alternate path
- [x] Rewrite remaining Phase 2 plan sections around a local-only strategy

#### 2.1.C Progress Update

- ✅ Threshold-based suggestions have been removed from the filter panel
- ✅ Dual-mode UI and auto-switching have been removed
- ✅ Query and collaboration callbacks are back to a single working baseline contract
- ✅ Removed API, model, service, and dedicated test code for the discarded alternate path
- ⚠️ Observed in manual validation: reducing query work alone does not solve lag when Cytoscape still renders very large edge sets
- ➡️ Practical next target moved to `2.1.D`: collaboration-specific payload reduction before render (top-N/weight/layer pruning)

#### 2.1.C Known Limitation

- No automatic suggestion layer is present for large loaded graphs; users must narrow queries manually when performance degrades.

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
    - prioritize top-N / minimum-weight / layer-level reductions before render
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
  - Default execution mode: client-side for loaded graphs

- [ ] **2.3.2 Relationship Property Filter**
  - Similar to node property filters
  - Example: Show only relationships where `since > 2020`
  - Start with bounded, known fields instead of generic arbitrary property filtering

- [ ] **2.3.3 Relationship Density Control**
  - Slider: Show top-N relationships (by weight, count, etc.)
  - Use case: Reduce visual clutter in dense graphs
  - Prioritize local density refinement for already-loaded weighted graphs
  - For collaboration graphs, reduce density in the collaboration pipeline before render
  - Do not assume generic graph relationships carry a `weight` property

---

## Related Changelog Entries

_No changelog entries yet for Phase 2._

---

## Archived Appendix: Rollback History (Condensed)

- An experimental backend filtering path was implemented and then removed.
- Removed surfaces included:
  - `/api/v1/graph/filter`
  - `/api/v1/graph/filter/metadata`
  - backend filter request/response models and query-builder logic
  - backend filter registry and dedicated filter tests
  - dual-mode/auto-switch UI controls and related fallback stores
- Current architecture is local-only filtering on loaded graph data.
- Historical rationale: the primary UX bottleneck remained Cytoscape render density, so effort shifted to query narrowing and collaboration payload reduction before render.

---

[← Back to Overview](README.md) | [Next: Phase 3 →](phase-3-path-exploration.md)

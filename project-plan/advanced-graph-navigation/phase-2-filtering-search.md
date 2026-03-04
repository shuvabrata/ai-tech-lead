# Phase 2: Filtering & Search

[← Back to Overview](README.md) | [Next: Phase 3 →](phase-3-path-exploration.md)

---

## Phase Overview

**Goal**: Find and focus on relevant subgraphs  
**Timeline**: 2-3 weeks  
**Priority**: High (P1)  
**Status**: Planned ⏳ (Not Started)

**⚠️ PRE-PHASE REVIEW REQUIRED**: Review and answer **Q9** (Filter Execution Model) before starting Phase 2

---

## Pre-Phase Decision Review

**Status**: 0 questions answered ✅, 2 questions pending ❓

### ❓ **Q9. Filter Execution Model**
- **Status**: UNANSWERED ❓
- **Phase**: 2.1 (Node Filtering)
- **Review Trigger**: Before starting Phase 2.1.1
- **Options**: 
  - (a) Client-side filtering - Filter already-loaded graph data in browser
  - (b) Server-side filtering - Send filter criteria to backend, run filtered query
  - (c) Hybrid - Start client-side, offload to server when dataset grows
- **Impact**: 
  - Performance implications for large graphs
  - Backend complexity vs frontend complexity
  - Affects API design (filter endpoint vs no filter endpoint)
- **Action Required**: Decide before implementing Phase 2.1.1

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

### Backend Tasks
- [ ] **2.1.1 Filter Endpoint** ❓ **DEPENDS ON: Q9**
  - **⚠️ DECISION REQUIRED**: Choose filter execution model (client-side vs server-side)
  - Endpoint: `POST /api/v1/graph/filter`
  - Request:
    ```json
    {
      "baseQuery": "MATCH (n) RETURN n LIMIT 100",
      "nodeFilters": [
        {"label": "Person", "property": "age", "operator": ">", "value": 30}
      ],
      "relationshipFilters": [...]
    }
    ```
  - Response: Filtered `GraphResponse`
  - **Review Question Q9 in Decision Log before implementation**

### Frontend Tasks
- [ ] **2.1.2 Filter Panel UI**
  - Component: Collapsible panel on right side (below details panel)
  - Sections:
    - **Node Type Filter**: Multi-select checkboxes for labels
    - **Property Filters**: Dynamic form based on node properties
    - **Relationship Filter**: Show/hide relationship types
    - **Advanced**: Cypher WHERE clause input

- [ ] **2.1.3 Property-Based Filtering**
  - Auto-detect properties from loaded nodes
  - Operators: `=`, `!=`, `>`, `<`, `>=`, `<=`, `CONTAINS`, `STARTS WITH`, `IN`
  - Property types: String, Number, Boolean, Date, List
  - Date range picker for temporal properties
  - Multi-select for categorical properties

- [ ] **2.1.4 Visual Filter Feedback**
  - Dim filtered-out nodes (opacity: 0.3)
  - Option: Hide vs. dim
  - Filter count badge: "Showing 45/200 nodes"
  - Active filters tag list (removable chips)

- [ ] **2.1.5 Saved Filters**
  - Save filter presets with names
  - Quick apply from dropdown
  - Share filter URLs

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

- [ ] **2.3.2 Relationship Property Filter**
  - Similar to node property filters
  - Example: Show only relationships where `since > 2020`

- [ ] **2.3.3 Relationship Density Control**
  - Slider: Show top-N relationships (by weight, count, etc.)
  - Use case: Reduce visual clutter in dense graphs

---

## Related Changelog Entries

_No changelog entries yet for Phase 2._

---

[← Back to Overview](README.md) | [Next: Phase 3 →](phase-3-path-exploration.md)

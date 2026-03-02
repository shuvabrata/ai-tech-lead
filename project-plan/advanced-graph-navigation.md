# Advanced Graph Navigation & Exploration Implementation Plan

**Status**: Planning Phase 🔄  
**Created**: March 2, 2026  
**Last Updated**: March 2, 2026  
**Parent Document**: `graph-visualization-implementation.md`  
**Related Phases**: Phase 6 (Graph Visualization UI) - Advanced Features

## Executive Summary

This plan extends the basic graph visualization (completed in Phase 1-5 of `graph-visualization-implementation.md`) with advanced navigation, exploration, and investigative capabilities inspired by Neo4j Browser and Neo4j Bloom. The goal is to transform the static graph viewer into a powerful investigative tool for exploring large, complex graphs.

### Current Limitations
1. ❌ **No node expansion** - Cannot double-click nodes to load connected neighbors
2. ⚠️ **Limited relationship visibility** - Relationships shown but may need styling improvements
3. ❌ **No filtering** - Cannot filter nodes/edges by type, property, or pattern
4. ❌ **No search** - Cannot search for specific nodes or patterns
5. ❌ **No path exploration** - Cannot find paths between nodes
6. ❌ **No context actions** - Right-click context menus missing
7. ❌ **Static view** - Cannot hide/show/group nodes dynamically
8. ❌ **No history** - Cannot navigate back through exploration steps
9. ❌ **Limited scalability** - Performance degrades with >500 nodes
10. ❌ **No export** - Cannot save or share graph views

### Success Criteria
- ✅ Load 10,000+ nodes without performance degradation
- ✅ Expand/collapse nodes with <200ms response time
- ✅ Filter nodes by multiple criteria simultaneously
- ✅ Find shortest paths between any two nodes
- ✅ Navigate complex graphs with breadcrumb history
- ✅ Export views as images or shareable URLs
- ✅ Support collaborative graph exploration

---

## Decision Log

**Last Updated**: March 2, 2026  
**Status**: Partial answers received, unanswered questions to be resolved before each phase implementation

### ✅ Answered Questions

**Q1. Edge Rendering Issue**
- **Status**: RESOLVED ✅
- **Decision**: Was an implementation error, now fixed
- **Impact**: Basic relationship visibility confirmed working
- **Phase**: Prerequisite

**Q2. Node Expansion Interaction Pattern**
- **Status**: DECIDED ✅
- **Decision**: **Option b** - Single-click expansion with confirmation dialog ("Expand this node?")
- **Rationale**: Better UX than double-click (especially on mobile/touchpads), confirmation prevents accidental expansions
- **Impact**: Phase 1.1.3 implementation
- **Phase**: 1.1

**Q3. Expansion Results Pagination**
- **Status**: DECIDED ✅
- **Decision**: **Option a** - Show first 50 + "Load More" button
- **Rationale**: Safer, better UX, prevents performance issues
- **Impact**: Phase 1.1.1 backend endpoint should return pagination metadata
- **Phase**: 1.1

**Q4. Expansion Direction Default**
- **Status**: DECIDED ✅
- **Decision**: **Option a** - "Both" (incoming + outgoing)
- **Rationale**: Shows full picture, more comprehensive exploration (accept potential clutter)
- **Impact**: Phase 1.1.1 default direction parameter, Phase 1.1 UI controls
- **Phase**: 1.1

**Q5. Expansion Auto-Collapse Behavior**
- **Status**: DECIDED ✅ (with addition)
- **Decision**: **Option a** - Keep all previous expansions (graph grows indefinitely)
- **Additional Requirement**: Add manual option for removing nodes from the plot
- **Rationale**: User wants flexibility to grow graph AND manually prune as needed
- **Impact**: Phase 1.1, requires new "Remove Node" functionality (context menu or button)
- **Phase**: 1.1, 1.3

**Q7. Breadcrumb Position**
- **Status**: DECIDED ✅
- **Decision**: **Option a** - Above graph (near layout controls)
- **Rationale**: Keeps navigation controls together, doesn't compete with bottom performance metrics
- **Impact**: Phase 1.4.2 UI layout
- **Phase**: 1.4

### ❓ Unanswered Questions (Review Before Implementation)

**IMPORTANT**: Each question below MUST be answered before starting its associated phase.

**Q6. Context Menu Implementation Approach**
- **Status**: UNANSWERED ❓
- **Phase**: 1.3 (Context Menu)
- **Review Trigger**: Before starting Phase 1.3.4
- **Options**: (a) dash-extensions library, (b) dcc.ContextMenu component, (c) Custom React component
- **Impact**: Development complexity, library dependencies

**Q8. History Persistence Strategy**
- **Status**: UNANSWERED ❓
- **Phase**: 1.4 (Breadcrumb Navigation & History)
- **Review Trigger**: Before starting Phase 1.4.4
- **Options**: (a) Browser localStorage, (b) No persistence (session-only), (c) Server-side storage
- **Impact**: Phase 1.4.4 implementation, user experience across sessions

**Q9. Filter Execution Model**
- **Status**: UNANSWERED ❓
- **Phase**: 2.1 (Node Filtering)
- **Review Trigger**: Before starting Phase 2
- **Options**: (a) Client-side filtering (hide/show existing nodes), (b) Server-side re-query, (c) Hybrid
- **Impact**: Phase 2.1 architecture, performance characteristics

**Q10. Search Implementation**
- **Status**: UNANSWERED ❓
- **Phase**: 2.2 (Graph Search)
- **Review Trigger**: Before starting Phase 2.2
- **Options**: Search strategy (full-text, property-based, pattern-based)
- **Impact**: Phase 2.2 backend endpoint

**Q11-Q14. Path Finding Features**
- **Status**: UNANSWERED ❓
- **Phase**: 3 (Path & Pattern Exploration)
- **Review Trigger**: Before starting Phase 3
- **Questions**: Path algorithms, visualization style, multiple paths handling, max path length
- **Impact**: Phase 3 entire implementation

**Q15-Q18. Performance & Scalability**
- **Status**: UNANSWERED ❓
- **Phase**: 4 (Performance & Scalability)
- **Review Trigger**: Before starting Phase 4
- **Questions**: LOD implementation, sampling strategy, clustering algorithm, progressive loading
- **Impact**: Phase 4 technical approach

**Q19-Q21. Export & Collaboration**
- **Status**: UNANSWERED ❓
- **Phase**: 5 (Export & Collaboration)
- **Review Trigger**: Before starting Phase 5
- **Questions**: Export formats, shareable URL scope, collaboration features priority
- **Impact**: Phase 5 feature scope

**Q22-Q24. Analytics Priority**
- **Status**: UNANSWERED ❓
- **Phase**: 6 (Advanced Analytics)
- **Review Trigger**: Before starting Phase 6
- **Questions**: Centrality metrics priority, pattern detection approach, time-based analysis
- **Impact**: Phase 6 feature prioritization

### 🔄 Pre-Implementation Review Protocol

Before starting implementation of each phase:
1. **Review unanswered questions** for that phase (marked with ❓)
2. **Get user decisions** on all relevant questions
3. **Update this Decision Log** with answers
4. **Adjust phase plan** based on decisions
5. **Proceed with implementation** only after all blocking questions resolved

---

## Research Summary: Neo4j Ecosystem Features

### Neo4j Browser Capabilities
1. **Query-driven exploration** - Write Cypher, visualize results
2. **Tabular + graph views** - Switch between table and graph
3. **Node expansion** - Click to expand connected nodes
4. **Relationship inspection** - Click edges to see properties
5. **Export results** - CSV, JSON, PNG exports
6. **Result pagination** - Handle large result sets
7. **Query history** - Rerun previous queries
8. **Favorites** - Save commonly used queries

### Neo4j Bloom Capabilities (Business User Tool)
1. **Natural language search** - "Find John's colleagues"
2. **Perspectives** - Predefined graph views for business users
3. **Visual query builder** - Drag-and-drop query construction
4. **Pattern matching** - Find similar subgraphs
5. **Shortest path** - Automatic path finding
6. **Node grouping** - Collapse nodes by type/property
7. **Rule-based styling** - Conditional node/edge styling
8. **Time-based filtering** - Temporal graph exploration
9. **Collaboration** - Share views with team
10. **Deep linking** - Shareable URLs to specific views

### Industry Best Practices (Gephi, Graphistry, yFiles)
1. **Hierarchical clustering** - Automatic node grouping
2. **Force-directed layouts** - Physics-based positioning
3. **Heatmaps** - Visualize node importance
4. **Subgraph extraction** - Create focused views
5. **Animation** - Transitions between states
6. **Minimap** - Overview of entire graph
7. **Brushing & linking** - Select in one view, highlight in another
8. **GPU acceleration** - Render massive graphs (100k+ nodes)

---

## Phase 1: Core Navigation & Expansion

**Goal**: Enable basic graph drilling and exploration
**Timeline**: 2-3 weeks  
**Priority**: Critical (P0)

### 1.1 Node Expansion (Double-Click to Expand)

**Objective**: Load and display connected nodes on demand

**Backend Tasks**:
- [ ] **1.1.1 Create Expansion Endpoint**
  - File: `app/api/graph/v1/router.py`
  - New endpoint: `POST /api/v1/graph/expand`
  - Request model: `NodeExpansionRequest(node_id: str, direction: str, relationship_types: Optional[List[str]], limit: int)`
  - Direction: `"incoming"`, `"outgoing"`, `"both"`
  - Returns: `GraphResponse` with new nodes/relationships
  - Query example: 
    ```cypher
    MATCH (n)-[r]->(m) WHERE elementId(n) = $nodeId
    RETURN n, r, m LIMIT $limit
    ```
  - Deduplication: Exclude already-loaded nodes

- [ ] **1.1.2 Expansion Service Layer**
  - File: `app/api/graph/v1/service.py`
  - Function: `expand_node(node_id, direction, rel_types, limit) -> GraphResponse`
  - Track expansion state (which nodes are expanded)
  - Handle circular references
  - Limit expansion depth (max 3 levels by default)

**Frontend Tasks**:
- [ ] **1.1.3 Single-Click Event Handler with Confirmation** ✅ **DECISION: Q2**
  - File: `app/dash_app/pages/graph.py`
  - Callback: Listen to `tapNode` (Cytoscape single-click event)
  - Show confirmation dialog: "Expand this node?" with Expand/Cancel buttons
  - Dialog includes options:
    - Direction: Both/Incoming/Outgoing (default: Both per Q4)
    - Limit: 50 nodes (default per Q3)
  - Show loading indicator on expanding node after confirmation
  - Debounce: Prevent multiple rapid clicks (300ms)

- [ ] **1.1.4 Visual Expansion Feedback**
  - Add "expanding..." spinner on node during load
  - Animate new nodes appearing (fade-in effect)
  - Highlight newly added nodes with temporary border
  - Update node style to show "expanded" state (e.g., darker border)

- [ ] **1.1.5 Expansion State Management** ✅ **DECISION: Q5**
  - Store: `dcc.Store(id="expanded-nodes")` - Track which nodes are expanded
  - Store: `dcc.Store(id="removed-nodes")` - Track manually removed nodes
  - Feature: **Manual Node Removal** (per Q5 requirement)
    - Button on node or context menu: "Remove from view"
    - Removed nodes stored in state (can be restored)
    - "Show All Hidden Nodes" button to restore removed nodes
  - Button: "Collapse" to remove expanded children (optional, as graph grows indefinitely per Q5)
  - Indicator: Show expansion count badge on nodes (e.g., "+23")

**UI/UX**:
- Visual indicator on nodes showing they can be expanded (+ icon overlay)
- Confirmation dialog on click (per Q2): "Expand this node?"
  - Direction selector: Both (default per Q4) / Incoming / Outgoing
  - Limit info: "Will show first 50 neighbors" (per Q3)
  - "Load More" button if >50 connections (per Q3)
- Expansion direction controls accessible from dialog and settings

**Performance**:
- Limit to 50 nodes per expansion (configurable)
- Debounce rapid clicks (300ms)
- Virtualization for >1000 total nodes

---

### 1.2 Enhanced Relationship Visibility

**Objective**: Ensure relationships are clearly visible and interactive

**Tasks**:
- [ ] **1.2.1 Verify Relationship Rendering**
  - Debug: Check if current implementation renders edges correctly
  - Test: Create queries with various relationship types
  - Fix: Any edge rendering bugs

- [ ] **1.2.2 Relationship Styling Improvements**
  - Edge thickness based on property (e.g., weight, count)
  - Curved edges for multiple relationships between same nodes
  - Edge labels always visible (not just on hover)
  - Arrow size proportional to edge thickness
  - Dashed lines for specific relationship types (e.g., virtual, inferred)

- [ ] **1.2.3 Relationship Interaction**
  - Click relationship → show in details panel
  - Hover → highlight connected nodes
  - Right-click → context menu (coming in Phase 2)

- [ ] **1.2.4 Relationship Filtering UI**
  - Checkbox list: Show/hide relationship types
  - Slider: Filter by relationship count
  - Toggle: Show all relationships vs. sample

---

### 1.3 Context Menu (Right-Click Actions)

**Objective**: Provide quick actions on nodes and edges

**Tasks**:
- [ ] **1.3.1 Node Context Menu**
  - Actions:
    - **Expand** (if not expanded)
    - **Collapse** (if expanded)
    - **Hide** (remove from view)
    - **Find Paths To...** (prompt for target node)
    - **Show Only Neighbors** (hide everything else)
    - **Copy Node ID**
    - **Copy Properties as JSON**
    - **Open in Neo4j URL** (deep link to Neo4j Browser)

- [ ] **1.3.2 Edge Context Menu**
  - Actions:
    - **Hide Relationship**
    - **Show Only This Type**
    - **Remove Edge** (from view, not database)
    - **Copy Relationship Details**

- [ ] **1.3.3 Canvas Context Menu**
  - Actions:
    - **Reset View**
    - **Fit to Screen**
    - **Export as PNG**
    - **Clear All Filters**
    - **Show All Hidden Nodes**

- [ ] **1.3.4 Implementation** ❓ **UNANSWERED: Q6**
  - **⚠️ DECISION REQUIRED**: Choose implementation approach before starting Phase 1.3
  - Option a: Use `dash-extensions` for custom context menus
  - Option b: Implement with `dcc.ContextMenu` component
  - Option c: Custom React component
  - Styling: Match application theme
  - **Review Question Q6 in Decision Log before implementation**

---

### 1.4 Breadcrumb Navigation & History

**Objective**: Track exploration steps and navigate back

**Tasks**:
- [ ] **1.4.1 History State Management**
  - Store: `dcc.Store(id="graph-history")` - Array of graph states
  - Each state:
    ```python
    {
      "timestamp": "2026-03-02T10:30:00Z",
      "query": "MATCH (n:Project) RETURN n LIMIT 10",
      "nodes": [...],  # Node IDs
      "relationships": [...],  # Relationship IDs
      "layout": "cose",
      "zoom": 1.0,
      "pan": {"x": 0, "y": 0},
      "filters": {...}
    }
    ```
  - Max history: 50 states (configurable)

- [ ] **1.4.2 Breadcrumb UI** ✅ **DECISION: Q7**
  - Component: Horizontal breadcrumb trail **above graph (near layout controls)** per Q7
  - Format: `Query 1 > Expanded Node A > Filtered by Person > Current`
  - Actions: Click any breadcrumb to restore that state
  - Style: Compact, scrollable for long histories
  - Positioning: Integrated with existing layout controls row

- [ ] **1.4.3 Navigation Buttons**
  - Back button (⬅️): Restore previous state
  - Forward button (➡️): Restore next state (if went back)
  - Keyboard shortcuts: `Ctrl+Z` (back), `Ctrl+Shift+Z` (forward)

- [ ] **1.4.4 State Persistence** ❓ **UNANSWERED: Q8**
  - **⚠️ DECISION REQUIRED**: Choose persistence strategy before starting Phase 1.4.4
  - Option a: Save history to browser localStorage
  - Option b: No persistence (session-only)
  - Option c: Server-side storage
  - Features (if persistence enabled):
    - Restore history on page reload
    - Clear history button
  - **Review Question Q8 in Decision Log before implementation**

---

## Phase 2: Filtering & Search

**Goal**: Find and focus on relevant subgraphs  
**Timeline**: 2-3 weeks  
**Priority**: High (P1)

**⚠️ PRE-PHASE REVIEW REQUIRED**: Review and answer **Q9** (Filter Execution Model) before starting Phase 2

### 2.1 Node Filtering

**Objective**: Filter visible nodes by type, property, or criteria

**Backend Tasks**:
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

**Frontend Tasks**:
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

### 2.2 Graph Search

**Objective**: Find nodes by property or pattern

**Tasks**:
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

### 2.3 Relationship Filtering

**Objective**: Show/hide relationships by type or property

**Tasks**:
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

## Phase 3: Path Exploration & Pattern Detection

**Goal**: Discover connections and patterns  
**Timeline**: 3-4 weeks  
**Priority**: High (P1)

**⚠️ PRE-PHASE REVIEW REQUIRED**: Review and answer **Q11-Q14** (Path Finding Features) before starting Phase 3

### 3.1 Path Finding

**Objective**: Find paths between two nodes

**Backend Tasks**:
- [ ] **3.1.1 Shortest Path Endpoint**
  - Endpoint: `POST /api/v1/graph/path/shortest`
  - Request: `{"startNodeId": "...", "endNodeId": "...", "maxDepth": 5, "relationshipTypes": [...]}`
  - Algorithm: Dijkstra's or A* for weighted graphs
  - Response: List of paths (nodes + relationships)

- [ ] **3.1.2 All Paths Endpoint**
  - Endpoint: `POST /api/v1/graph/path/all`
  - Request: Same as shortest, plus `limit` (max paths to return)
  - Algorithm: BFS with depth limit

- [ ] **3.1.3 Path Algorithms**
  - Weighted shortest path (by relationship property)
  - K-shortest paths (find top-K paths)
  - Dijkstra, A*, Yen's algorithm

**Frontend Tasks**:
- [ ] **3.1.4 Path Finder UI**
  - Mode: "Path Finding Mode" toggle
  - Instructions: "Click two nodes to find paths"
  - Source/target selection: Click nodes or search
  - Options:
    - Max path length (depth)
    - Relationship types to traverse
    - Algorithm selection
    - Max paths to return

- [ ] **3.1.5 Path Visualization**
  - Highlight path nodes/edges with distinct color (e.g., gold)
  - Animate path traversal (node-by-node)
  - Multiple paths: Different colors or toggle between them
  - Path info panel: Show path length, cost, sequence

- [ ] **3.1.6 Path Actions**
  - Export path as list
  - Save path for later
  - Compare multiple paths side-by-side

---

### 3.2 Pattern Detection

**Objective**: Find recurring subgraph patterns

**Backend Tasks**:
- [ ] **3.2.1 Pattern Matching Endpoint**
  - Endpoint: `POST /api/v1/graph/pattern/match`
  - Request: Pattern as Cypher MATCH clause or visual template
  - Example: "Find all triangles: (a)-[:KNOWS]->(b)-[:KNOWS]->(c)-[:KNOWS]->(a)"
  - Response: All matching subgraphs

- [ ] **3.2.2 Motif Detection**
  - Common patterns: Triangles, stars, chains, cliques
  - Algorithms: Subgraph isomorphism
  - Performance: Limit to subgraphs of size ≤10 nodes

**Frontend Tasks**:
- [ ] **3.2.3 Pattern Template Library**
  - Predefined templates: Triangles, diamonds, hierarchies
  - Visual previews
  - One-click apply

- [ ] **3.2.4 Visual Pattern Builder**
  - Drag-and-drop to create custom patterns
  - Node/edge wildcards (match any type)
  - Property constraints

- [ ] **3.2.5 Pattern Results**
  - List all matches
  - Highlight matches in graph
  - Navigate between matches (next/prev buttons)

---

### 3.3 Neighborhood Exploration

**Objective**: Explore node neighborhoods at various depths

**Tasks**:
- [ ] **3.3.1 Ego Network**
  - Select node → show N-hop neighborhood
  - Depth slider (1-5 hops)
  - Center on selected node

- [ ] **3.3.2 Common Neighbors**
  - Select 2+ nodes → show shared neighbors
  - Use case: Find common connections

- [ ] **3.3.3 Network Intersection**
  - Select multiple nodes → show subgraph connecting them
  - Steiner tree problem (minimum connecting subgraph)

---

## Phase 4: Performance & Scalability

**Goal**: Handle large graphs efficiently  
**Timeline**: 3-4 weeks  
**Priority**: Medium (P2)

**⚠️ PRE-PHASE REVIEW REQUIRED**: Review and answer **Q15-Q18** (Performance & Scalability) before starting Phase 4

### 4.1 Progressive Loading

**Objective**: Load graph incrementally

**Tasks**:
- [ ] **4.1.1 Pagination for Large Results**
  - Backend: Return results in batches (page_size, page_number)
  - Frontend: "Load More" button or infinite scroll
  - Example: Load 100 nodes initially, fetch next 100 on demand

- [ ] **4.1.2 Level-of-Detail (LOD) Rendering**
  - Show simplified nodes when zoomed out (smaller circles, no labels)
  - Show full details when zoomed in
  - Threshold: Zoom level < 0.5 = simplified

- [ ] **4.1.3 Viewport Culling**
  - Only render nodes in visible viewport
  - Cytoscape extension or custom implementation
  - Performance gain for >5000 nodes

---

### 4.2 Graph Clustering & Aggregation

**Objective**: Group nodes to reduce visual clutter

**Tasks**:
- [ ] **4.2.1 Community Detection (Backend)**
  - Algorithms: Louvain, Label Propagation, Connected Components
  - Endpoint: `POST /api/v1/graph/cluster`
  - Response: Node-to-cluster assignments

- [ ] **4.2.2 Cluster Visualization**
  - Replace cluster nodes with "super-node"
  - Super-node size = cluster member count
  - Double-click super-node to expand cluster

- [ ] **4.2.3 Hierarchical Grouping**
  - Group by property (e.g., all Person nodes → "People" group)
  - Collapsible groups
  - Group styling (backgrounds, borders)

---

### 4.3 Caching & Optimization

**Objective**: Speed up repeated queries

**Tasks**:
- [ ] **4.3.1 Backend Query Caching**
  - Cache expansion queries (5-minute TTL)
  - Cache path finding results
  - Use Redis or in-memory LRU cache

- [ ] **4.3.2 Frontend State Caching**
  - Cache node positions (layout preservation)
  - Cache expanded node states
  - Persist in localStorage

- [ ] **4.3.3 Lazy Rendering**
  - Only render visible elements
  - Virtual scrolling for large lists
  - Debounced layout recalculation

---

### 4.4 Graph Sampling

**Objective**: Show representative subset of large graphs

**Tasks**:
- [ ] **4.4.1 Sampling Strategies**
  - Random sampling: Select N random nodes + their relationships
  - Degree-based: Sample high-degree nodes (hubs)
  - PageRank-based: Sample important nodes
  - Stratified: Sample proportionally from each node type

- [ ] **4.4.2 Sampling UI**
  - Warning: "Graph too large (10,000 nodes). Showing sample of 500."
  - Sampling method selector
  - "Load Full Graph" option (with confirmation)

---

## Phase 5: Collaboration & Export

**Goal**: Share and export graph views  
**Timeline**: 2 weeks  
**Priority**: Medium (P2)

**⚠️ PRE-PHASE REVIEW REQUIRED**: Review and answer **Q19-Q21** (Export & Collaboration) before starting Phase 5

### 5.1 Export Capabilities

**Tasks**:
- [ ] **5.1.1 Image Export**
  - Format: PNG, SVG
  - Options: Include/exclude labels, customize resolution
  - Implementation: `cytoscape.js` export plugin

- [ ] **5.1.2 Data Export**
  - Formats: JSON, CSV (nodes/edges as tables), GraphML, GEXF
  - Include filters and current view state
  - Export subgraphs (visible nodes only)

- [ ] **5.1.3 Cypher Export**
  - Generate Cypher query that recreates current view
  - Copy to clipboard or download `.cypher` file

---

### 5.2 Shareable Views

**Tasks**:
- [ ] **5.2.1 View State Serialization**
  - Encode entire view state in URL parameters or short hash
  - State includes: query, filters, layout, zoom/pan, expanded nodes

- [ ] **5.2.2 Shareable Links**
  - "Share" button → generate URL
  - Open shared URL → restore exact view
  - Optional: Password protection for sensitive graphs

- [ ] **5.2.3 Saved Views (Bookmarks)**
  - Save named views to database
  - Personal vs. shared views
  - Tag/categorize views

---

### 5.3 Annotations & Comments

**Tasks**:
- [ ] **5.3.1 Node Annotations**
  - Add text notes to nodes
  - Pin notes to graph (visible to all viewers)
  - Edit/delete annotations

- [ ] **5.3.2 Annotation UI**
  - Right-click → "Add Note"
  - Note editor: Markdown support
  - Notes panel: List all annotations

---

## Phase 6: Analytics & Insights

**Goal**: Discover graph metrics and insights  
**Timeline**: 3-4 weeks  
**Priority**: Low (P3)

**⚠️ PRE-PHASE REVIEW REQUIRED**: Review and answer **Q22-Q24** (Analytics Priority) before starting Phase 6

### 6.1 Graph Metrics

**Backend Tasks**:
- [ ] **6.1.1 Node Centrality Metrics**
  - Degree centrality
  - Betweenness centrality
  - Closeness centrality
  - PageRank
  - Endpoint: `POST /api/v1/graph/metrics/centrality`

- [ ] **6.1.2 Graph Statistics**
  - Node count by type
  - Relationship count by type
  - Average degree
  - Connected components
  - Diameter, radius
  - Clustering coefficient

**Frontend Tasks**:
- [ ] **6.1.3 Metrics Panel**
  - Show graph statistics
  - Visualize metrics as bar charts, histograms
  - Color-code nodes by centrality (heatmap)

---

### 6.2 Temporal Analysis

**Tasks**:
- [ ] **6.2.1 Time Slider**
  - Filter graph by time range (if nodes/edges have timestamps)
  - Animate graph evolution over time
  - Playback controls: Play, pause, speed

- [ ] **6.2.2 Temporal Patterns**
  - Detect trending patterns
  - Show growth/decay of node types over time

---

### 6.3 Anomaly Detection

**Tasks**:
- [ ] **6.3.1 Outlier Detection**
  - Highlight nodes with unusual properties (e.g., very high degree)
  - Detect disconnected components
  - Flag suspicious patterns (fraud detection use case)

---

## Technical Architecture

### Backend Components

```
app/api/graph/v1/
├── router.py              # Existing + new endpoints
├── service.py             # Existing + expansion/filter/path logic
├── query.py               # Existing + new query builders
├── model.py               # Existing + new request/response models
└── algorithms/            # NEW: Graph algorithms
    ├── paths.py           # Shortest path, all paths, Dijkstra
    ├── clustering.py      # Community detection, grouping
    ├── centrality.py      # PageRank, betweenness, degree
    └── patterns.py        # Motif detection, subgraph matching
```

### Frontend Components

```
app/dash_app/pages/graph.py
├── get_layout()                    # Existing
├── neo4j_to_cytoscape()           # Existing
├── execute_query()                # Existing callback
└── NEW Components:
    ├── expansion_controls.py       # Expand/collapse UI
    ├── filter_panel.py             # Filter controls
    ├── search_bar.py               # Search UI
    ├── path_finder.py              # Path finding mode
    ├── context_menu.py             # Right-click menus
    ├── history_breadcrumb.py       # Navigation history
    └── metrics_panel.py            # Analytics display
```

### Data Stores

```python
dcc.Store(id="graph-state", data={
    "nodes": [...],              # Currently loaded nodes
    "edges": [...],              # Currently loaded edges
    "expandedNodes": [],         # Node IDs that have been expanded
    "hiddenNodes": [],           # Node IDs hidden by user
    "filters": {...},            # Active filters
    "history": [...],            # Navigation history
    "layout": "cose",            # Current layout
    "zoom": 1.0,                 # Current zoom level
    "selection": [],             # Selected node/edge IDs
    "pathMode": false,           # Path finding mode active
    "pathSource": null,          # Source node for path finding
    "annotations": {...}         # User annotations
})
```

---

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Node expansion latency | <200ms | API response time |
| Render 1000 nodes | <1s | Time to first paint |
| Render 10,000 nodes (sampled) | <2s | With progressive loading |
| Filter application | <100ms | Client-side update |
| Path finding (depth 5) | <500ms | API response |
| Layout recalculation | <300ms | For <500 nodes |
| Search results | <200ms | Including backend |
| Export PNG (1000 nodes) | <3s | Generation time |

---

## Testing Strategy

### Unit Tests
- Path finding algorithms (correctness, edge cases)
- Filter logic (combinations, empty results)
- Clustering algorithms
- Serialization/deserialization of view state

### Integration Tests
- Expansion workflow (backend → frontend)
- Filter + search combination
- Path finding end-to-end
- Export formats (validate output)

### Performance Tests
- Load testing with 10k, 50k, 100k node graphs
- Memory profiling (detect leaks)
- Rendering benchmarks (FPS under various loads)

### User Acceptance Tests
- Task-based scenarios:
  - "Find all paths between Person A and Company B"
  - "Filter projects started in 2024 with >10 team members"
  - "Identify the most central person in the network"
  - "Export subgraph of London-based teams"

---

## Rollout Plan

### Phase 1-2 (Weeks 1-6): Foundation
- Core expansion, filtering, search
- Impact: Users can drill down and focus on relevant subgraphs

### Phase 3 (Weeks 7-10): Advanced Exploration
- Path finding, pattern detection
- Impact: Discovery of hidden connections

### Phase 4 (Weeks 11-14): Scale
- Performance optimization, clustering
- Impact: Handle enterprise-scale graphs (10k+ nodes)

### Phase 5 (Weeks 15-16): Collaboration
- Export, sharing, annotations
- Impact: Team collaboration on graph analysis

### Phase 6 (Weeks 17-20): Analytics (Optional)
- Metrics, temporal analysis, anomalies
- Impact: Data-driven insights and reporting

---

## Success Metrics

### Quantitative
- **Query count**: 50% reduction in manual queries (via expansion)
- **Time to insight**: 70% faster problem investigation
- **User engagement**: 3x increase in graph tab usage
- **Performance**: 90th percentile latency <500ms

### Qualitative
- User feedback: "This is as good as Neo4j Browser"
- Use cases enabled: Fraud detection, root cause analysis, dependency mapping
- Adoption: 80% of tech leads use graph exploration weekly

---

## Dependencies

### New Python Packages
```python
# requirements.txt additions
dash-extensions>=0.1.0    # Context menus, advanced callbacks
networkx>=3.0             # Graph algorithms (paths, clustering)
python-louvain>=0.16      # Community detection
scikit-learn>=1.3         # Clustering algorithms
```

### Neo4j Requirements
- Neo4j 5.0+ (for modern Cypher features)
- APOC plugin (for advanced path algorithms)
- Graph Data Science library (optional, for centrality metrics)

### Browser Requirements
- Modern browser with Canvas/WebGL support
- 4GB+ RAM for large graphs (10k+ nodes)

---

## Risk Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Performance degradation with large graphs | High | High | Implement sampling, progressive loading, LOD rendering |
| Complex UI overwhelming users | Medium | Medium | Progressive disclosure, tooltips, onboarding wizard |
| Neo4j connection timeouts | High | Medium | Query timeouts, retry logic, clear error messages |
| Browser memory limits | High | Medium | Viewport culling, node limit warnings, cleanup on unmount |
| Feature creep | Medium | High | Strict phase adherence, MVP mindset per phase |

---

## Open Questions

1. **Authentication**: Do we need user-level permissions for graph exploration?
   - **Decision**: Out of scope (addressed in parent roadmap)

2. **Real-time updates**: Should graph auto-refresh when data changes?
   - **Decision**: Phase 7 (future), for now provide manual refresh button

3. **Multi-graph support**: Can users switch between multiple Neo4j databases?
   - **Decision**: Single database for MVP, multi-db in Phase 7

4. **Mobile support**: Should graph work on tablets/phones?
   - **Decision**: Desktop-first, responsive layout for tablets (Phase 5+)

5. **AI-assisted exploration**: Should we add AI-powered query suggestions?
   - **Decision**: Phase 8 (leverages existing AI agent, see main roadmap Phase 4)

---

## References

- [Neo4j Browser Documentation](https://neo4j.com/docs/browser-manual/current/)
- [Neo4j Bloom User Guide](https://neo4j.com/docs/bloom-user-guide/current/)
- [Cytoscape.js Documentation](https://js.cytoscape.org/)
- [Dash Cytoscape Examples](https://dash.plotly.com/cytoscape/reference)
- [Graph Visualization Best Practices (Gephi)](https://gephi.org/users/)
- [Interactive Graph Exploration (Graphistry)](https://www.graphistry.com/blog)
- [Network Analysis Tutorial (NetworkX)](https://networkx.org/documentation/stable/tutorial.html)

---

## Changelog

- **2026-03-02**: Initial plan created based on Neo4j Browser/Bloom research
- **2026-03-02**: Added 6 phases covering navigation, filtering, paths, performance, collaboration, analytics
- **2026-03-02**: Defined success criteria, performance targets, and rollout plan
- **2026-03-02**: Added Decision Log section with answered questions (Q1-Q5, Q7) and unanswered questions (Q6, Q8-Q24)
- **2026-03-02**: Updated Phase 1 tasks to reflect decisions:
  - Single-click expansion with confirmation dialog (Q2)
  - Paginated results: 50 + Load More (Q3)
  - Default direction: Both (Q4)
  - Manual node removal feature (Q5)
  - Breadcrumbs above graph (Q7)
- **2026-03-02**: Added pre-phase review warnings for all phases to ensure unanswered questions resolved before implementation

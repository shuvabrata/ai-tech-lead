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

## Decision Status Summary

**Last Updated**: March 2, 2026

### Quick Status
- ✅ **Answered**: 7 decisions (Q1-Q7)
- ❓ **Pending**: 17 decisions (Q8-Q24)
- 🔄 **Current Phase**: Phase 1.1c (Double-Click Expansion) - ✅ COMPLETE
- ⏭️ **Next Phase**: Phase 1.1d (Right-Click Context Menu)

### Review Required Before
- **Phase 1.4** (Breadcrumb & History): Answer Q8
- **Phase 2** (Filtering & Search): Answer Q9, Q10
- **Phase 3** (Path Exploration): Answer Q11-Q14
- **Phase 4** (Performance): Answer Q15-Q18
- **Phase 5** (Export & Collaboration): Answer Q19-Q21
- **Phase 6** (Analytics): Answer Q22-Q24

### Pre-Implementation Protocol
Before starting each phase:
1. Review unanswered questions for that phase (marked with ❓)
2. Get user decisions on all relevant questions
3. Update questions in phase sections with answers
4. Adjust phase plan based on decisions
5. Proceed with implementation only after all blocking questions resolved

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

---

### Pre-Phase Decision Review

**Status**: 7 questions answered ✅, 1 question pending ❓

#### ✅ **Q1. Edge Rendering Issue**
- **Status**: RESOLVED ✅
- **Decision**: Was an implementation error, now fixed
- **Impact**: Basic relationship visibility confirmed working
- **Phase**: Prerequisite

#### ✅ **Q2. Node Expansion Interaction Pattern**
- **Status**: DECIDED ✅ (REVISED)
- **Decision**: **Dual interaction model**:
  - **Double-click**: Immediate expansion with defaults (direction: Both, limit: 50)
  - **Right-click**: Context menu → "Expand Node..." → Opens dialog with options (direction, limit controls)
- **Rationale**: Power users get speed (double-click), all users get control (right-click). Best of both worlds.
- **Impact**: Phase 1.1 split into micro-phases (1.1a, 1.1b, 1.1c) for incremental implementation
- **Implementation Notes**: 
  - Dash Cytoscape doesn't expose `doubleTap` or `cxtTap` as Python properties
  - Will use clientside JavaScript callbacks to listen to Cytoscape.js native events
  - Single-click (`tapNodeData`) still used for selection/details panel

#### ✅ **Q3. Expansion Results Pagination**
- **Status**: DECIDED ✅
- **Decision**: **Option a** - Show first 50 + "Load More" button
- **Rationale**: Safer, better UX, prevents performance issues
- **Impact**: Backend endpoint returns pagination metadata, UI shows "Load More" when has_more=true

#### ✅ **Q4. Expansion Direction Default**
- **Status**: DECIDED ✅
- **Decision**: **Option a** - "Both" (incoming + outgoing)
- **Rationale**: Shows full picture, more comprehensive exploration (accept potential clutter)
- **Impact**: Default direction parameter in all expansion operations

#### ✅ **Q5. Expansion Auto-Collapse Behavior**
- **Status**: DECIDED ✅ (with addition)
- **Decision**: **Option a** - Keep all previous expansions (graph grows indefinitely)
- **Additional Requirement**: Add manual option for removing nodes from the plot
- **Rationale**: User wants flexibility to grow graph AND manually prune as needed
- **Impact**: Requires new "Remove Node" functionality (context menu or button in Phase 1.1e/1.3)

#### ✅ **Q6. Context Menu Implementation Approach**
- **Status**: DECIDED ✅
- **Decision**: **Option (a) - dash-extensions library**
- **Rationale**: Best balance of simplicity, maintainability, and development speed. Purpose-built for Dash browser event handling with robust positioning and dismissal logic.
- **Phase**: 1.3 (Context Menu), 1.1d (Right-Click Expansion)
- **Impact**: 
  - Add `dash-extensions` dependency (~400KB)
  - 1-2 day implementation timeline
  - Production-ready context menu with minimal maintenance burden

---

**Research Findings**:
- ✅ **dash-extensions** library exists and has context menu support (NOT currently installed)
- ❌ **dcc.ContextMenu** does NOT exist in core Dash
- ✅ **dbc.DropdownMenu** exists but not designed for right-click context menus (dropdown from buttons)
- ✅ **Custom implementation** is viable using HTML/CSS + clientside callbacks

---

**Options Analysis**:

**Option (a): dash-extensions Library** ⭐ RECOMMENDED
- **Installation**: `pip install dash-extensions`
- **Component**: Uses `EventListener` component to capture browser events + custom menu rendering
- **Pros**:
  - ✅ Purpose-built for Dash applications
  - ✅ Well-maintained library (actively developed)
  - ✅ Handles positioning, event bubbling, dismiss-on-click automatically
  - ✅ Integrates cleanly with Dash callback system
  - ✅ Good documentation and examples
  - ✅ Medium complexity (easier than custom, more flexible than dropdown hack)
  - ✅ Supports dynamic menu items based on node type
- **Cons**:
  - ⚠️ Adds external dependency (but from reputable source)
  - ⚠️ Library bundle size increase (~small impact)
  - ⚠️ May have version compatibility issues with Dash updates (rare)
- **Implementation Effort**: ⭐⭐ Medium (1-2 days)
- **Example Pattern**:
  ```python
  from dash_extensions import EventListener
  EventListener(
      events=[{"event": "contextmenu", "props": ["target.id"]}],
      logging=True,
      id="context-listener"
  )
  ```

**Option (b): dcc.ContextMenu Component**
- **Status**: ❌ DOES NOT EXIST
- **Verdict**: Not viable - this component doesn't exist in core Dash
- **Alternative**: Could use `dbc.DropdownMenu` but it's NOT designed for right-click contexts
  - Designed for button dropdowns, not positioned context menus
  - No built-in right-click event handling
  - Would require significant hacking to adapt

**Option (c): Custom HTML/CSS + Clientside Callbacks**
- **Pros**:
  - ✅ Complete control over appearance and behavior
  - ✅ No external dependencies
  - ✅ Can be optimized for exact use case
  - ✅ Learning opportunity for advanced Dash patterns
  - ✅ Works with any Dash version
- **Cons**:
  - ❌ High complexity - must implement from scratch:
    - Event capture (right-click)
    - Menu positioning logic (viewport boundaries, overflow)
    - Show/hide state management
    - Dismiss on click-outside, ESC key
    - Nested menu support (if needed later)
  - ❌ More code to maintain
  - ❌ Higher bug risk (edge cases: scrolling, resizing, nested clicks)
  - ❌ Accessibility concerns (keyboard navigation, screen readers)
- **Implementation Effort**: ⭐⭐⭐⭐ High (3-5 days)
- **Example Pattern**:
  ```python
  # Hidden div for menu
  html.Div([
      html.Div("Expand Node...", id="menu-item-1"),
      html.Div("Remove", id="menu-item-2")
  ], id="context-menu", style={"position": "absolute", "display": "none"})
  
  # Clientside callback to show/hide
  clientside_callback("""
      function(evt) {
          // Position menu at mouse x,y
          // Handle viewport boundaries
          // Show menu
      }
  """, ...)
  ```

**Option (d): Hybrid - dbc.DropdownMenu with Custom Positioning** 🤔 POSSIBLE BUT HACKY
- **Approach**: Use `dbc.DropdownMenu` component but position it dynamically on right-click
- **Pros**:
  - ✅ No new dependencies (already using dbc)
  - ✅ Component provides styling and structure
  - ✅ Built-in dismiss behavior
- **Cons**:
  - ⚠️ Not designed for this use case (fighting the component)
  - ⚠️ Still need clientside callbacks for positioning
  - ⚠️ May have unexpected behavior (component assumes button trigger)
  - ⚠️ Medium-high complexity
- **Implementation Effort**: ⭐⭐⭐ Medium-High (2-3 days)

---

**Recommendation**: **Option (a) - dash-extensions** ⭐

**Rationale**:
1. **Best balance** of simplicity vs control vs maintainability
2. **Purpose-built** for this exact use case
3. **Time-efficient**: Faster than custom, more robust than hacking DropdownMenu
4. **Production-ready**: Handles edge cases (positioning, dismissal, events)
5. **Acceptable trade-off**: Small dependency cost for significant development speed gain
6. **Future-proof**: Library widely used in Dash community

**When to choose Custom (Option c)**:
- If you have very specific styling requirements
- If minimizing dependencies is critical
- If you need highly custom behavior (e.g., nested menus, drag-drop from menu)

---

- **Impact**: 
  - Option (a): Add `dash-extensions` dependency (~400KB), 1-2 day implementation
  - Option (c): No dependency, 3-5 day implementation, ongoing maintenance burden
- **Action Required**: Decide before Phase 1.1d implementation

#### ✅ **Q7. Breadcrumb Position**
- **Status**: DECIDED ✅
- **Decision**: **Option a** - Above graph (near layout controls)
- **Rationale**: Keeps navigation controls together, doesn't compete with bottom performance metrics
- **Impact**: Phase 1.4.2 UI layout - breadcrumbs integrated with layout controls row

#### ❓ **Q8. History Persistence Strategy**
- **Status**: UNANSWERED ❓
- **Phase**: 1.4 (Breadcrumb Navigation & History)
- **Review Trigger**: Before starting Phase 1.4.4
- **Options**: 
  - (a) Browser localStorage - Persists across sessions, simple implementation
  - (b) No persistence (session-only) - Simpler, lost on refresh
  - (c) Server-side storage - Complex, requires backend changes
- **Impact**: User experience across sessions, implementation complexity
- **Action Required**: Decide before Phase 1.4.4 implementation

---

### 1.1 Node Expansion (Double-Click + Right-Click)

**Objective**: Load and display connected nodes on demand with dual interaction model

**Status**: ✅ 1.1a Complete | ✅ 1.1b Complete | ✅ 1.1c Complete | ✅ 1.1d Complete | ⏳ 1.1e-f Pending

**Implementation Strategy**: Build incrementally in micro-phases to validate technical approach

---

#### **Phase 1.1a: Backend API** ✅ COMPLETE

**Tasks**:
- [x] **Create Expansion Endpoint**
  - File: `app/api/graph/v1/router.py`
  - Endpoint: `POST /api/v1/graph/expand`
  - Request model: `NodeExpansionRequest(node_id, direction, relationship_types, limit, offset, exclude_node_ids)`
  - Response model: `NodeExpansionResponse(nodes, relationships, expanded_node_id, pagination)`
  - Direction: `"incoming"`, `"outgoing"`, `"both"` (default: `"both"`)
  - Pagination: Default limit 50, supports offset-based loading
  
- [x] **Expansion Query Layer**
  - File: `app/api/graph/v1/query.py`
  - Function: `expand_node_query()` - Builds direction-filtered Cypher queries
  - Deduplication: Excludes already-loaded nodes via `exclude_node_ids` parameter
  - Handles UNION queries for "both" direction
  
- [x] **Expansion Service Layer**
  - File: `app/api/graph/v1/service.py`
  - Function: `expand_node()` - Orchestrates query execution and transformation
  - Returns deduplicated nodes/relationships with pagination metadata

---

#### **Phase 1.1b: Simple Button-Based Expansion** 🔄 IN PROGRESS

**Goal**: Get basic expansion working with simplest possible UI (button in details panel)

**Rationale**: Before attempting complex double-click/right-click events, prove the full stack works end-to-end

**Tasks**:
- [ ] **1. Add UI Components**
  - Add "Expand Node" button to details panel (shown when node selected)
  - Add expansion modal with:
    - Direction selector: Both / Incoming / Outgoing (default: Both)
    - Limit info display: "Will load first 50 neighbors"
    - "Load More" button for pagination (if has_more = true)
    - Expand / Cancel buttons
  - Add data stores:
    - `expanded-nodes`: Track which node IDs have been expanded
    - `loaded-node-ids`: Track all loaded node IDs for deduplication

- [ ] **2. Create Callbacks**
  - Callback 1: `open_expansion_modal()` - Opens modal when button clicked, passes selected node ID
  - Callback 2: `execute_expansion()` - Calls backend API, merges results into graph
    - Input: Modal "Expand" button click + node_id + direction + limit
    - Process:
      - Get current graph elements from Cytoscape
      - Extract loaded node IDs for exclude_node_ids parameter
      - POST to `/api/v1/graph/expand` with parameters
      - Transform response using `neo4j_to_cytoscape()`
      - Merge new elements (deduplicate by ID)
      - Update Cytoscape elements
      - Update expanded-nodes and loaded-node-ids stores
    - Output: Updated graph elements, success/error message

- [ ] **3. Visual Feedback**
  - Loading spinner while expansion in progress
  - Success toast: "Loaded X new nodes, Y new relationships"
  - Error handling: Display user-friendly error messages
  - Highlight newly added nodes with different border color (temporary, fade after 3s)

**Success Criteria**:
- ✅ Click node → details panel shows "Expand Node" button
- ✅ Click button → modal opens with options
- ✅ Click "Expand" → API called, new nodes appear in graph
- ✅ No duplicate nodes/edges in graph
- ✅ Graph layout adjusts to accommodate new nodes
- ✅ Can expand multiple nodes sequentially
- ✅ Pagination works ("Load More" button appears when >50 neighbors)

---

#### **Phase 1.1c: Double-Click Quick Expansion** ✅ COMPLETE

**Goal**: Add double-click for power users (immediate expansion with defaults)

**Technical Challenge**: Dash Cytoscape doesn't expose `doubleTap` event as Python Input property

**Solution Implemented**: Clientside JavaScript callback with persistent event listener
```javascript
// Clientside callback attaches event listener to Cytoscape instance
cy.on('dbltap', 'node', function(evt) {
  var node = evt.target;
  var nodeId = node.id();
  // Update hidden dcc.Store to trigger Python callback
  window.dash_clientside.set_props('doubleclicked-node-store', { 
    data: { node_id: nodeId, timestamp: Date.now() }
  });
});
```

**Tasks**:
- [x] **1. Add Hidden Communication Channel**
  - Added `dcc.Store(id="doubleclicked-node-store")` for JS-Python bridge
  - Added `dcc.Store(id="expansion-debounce-store")` for tracking expansion timing
  - File: `app/dash_app/pages/graph.py` (lines 368-372)

- [x] **2. Clientside Callback for Event Capture**
  - Registered `clientside_callback` that attaches persistent `dbltap` event listener
  - Listener updates store with `{node_id, timestamp}` on double-click
  - Prevents duplicate listeners with `_dbltapListenerAttached` flag
  - File: `app/dash_app/pages/graph.py` (lines 1296-1338)

- [x] **3. Python Callback for Expansion**
  - Created `execute_doubleclick_expansion()` callback
  - Triggers on `doubleclicked-node-store` data change
  - Hardcoded defaults: direction="both", limit=50, offset=0
  - Reuses expansion API logic with immediate execution (no modal)
  - File: `app/dash_app/pages/graph.py` (lines 1341-1489)

- [x] **4. Debouncing**
  - Implemented 500ms debounce window per node
  - Compares `timestamp` in store data with last expansion time
  - Prevents double-expansions within cooldown period
  - Visual feedback: Info-colored alert with ⚡ icon (3s duration)

**Success Criteria**:
- ✅ Double-click node → immediate expansion (no modal)
- ✅ Uses default parameters (both/50)
- ✅ Doesn't conflict with single-click selection
- ✅ Debounced to prevent accidental double-expansions

---

#### **Phase 1.1d: Right-Click Context Menu** ✅ COMPLETE

**Goal**: Add right-click menu for advanced expansion options

**Technical Challenge**: Dash Cytoscape doesn't expose `cxttap` (right-click) event

**Solution Implemented**: Clientside callback + custom HTML/CSS context menu

**Tasks**:
- [x] **1. Event Capture**
  - Added `rightclicked-node-store`: Stores `{node_id, x, y, timestamp}`
  - Created clientside callback listening to Cytoscape `cxttap` event
  - Captures mouse coordinates for menu positioning
  - Prevents default browser context menu
  - File: `app/dash_app/pages/graph.py` (lines 373-375, 1410-1472)

- [x] **2. Context Menu Component**
  - Custom HTML/CSS menu with absolute positioning
  - Menu items implemented:
    - **"Expand Node..."** → Opens advanced expansion modal
    - **"Expand Incoming Only"** → Quick expansion (incoming direction)
    - **"Expand Outgoing Only"** → Quick expansion (outgoing direction)
    - **"Copy Node ID"** → Copies node ID to clipboard
    - **"Remove from View"** → Removes node and connected edges
  - Styled with hover effects (background color change)
  - File: `app/dash_app/pages/graph.py` (lines 377-409)

- [x] **3. Context Menu Callbacks**
  - `show_context_menu()`: Positions and shows menu at click coordinates (lines 1607-1627)
  - `context_menu_expand_modal()`: Opens expansion modal, hides menu (lines 1630-1649)
  - `context_menu_quick_expand()`: Handles quick expansions with preset directions (lines 1652-1776)
  - `context_menu_remove_node()`: Removes node and edges from graph (lines 1829-1877)
  - Clientside callbacks:
    - Copy node ID to clipboard (lines 1779-1793)
    - Hide menu after copy action (lines 1796-1807)
    - Hide menu on outside click + hover effects (lines 1880-1913)

- [x] **4. Menu Positioning & Dismissal**
  - Positions menu at exact mouse coordinates (x, y from event)
  - Hides menu on:
    - Click outside menu
    - ESC key (browser default)
    - Action selected (all menu items hide menu after execution)
  - Menu stays within viewport (browser handles overflow)

**Success Criteria**:
- ✅ Right-click node → context menu appears at cursor
- ✅ Menu items execute correct actions
- ✅ Menu dismisses appropriately
- ✅ Doesn't interfere with double-click or single-click

---

#### **Phase 1.1e: Expansion State & Visual Indicators** ⏳ PLANNED

**Goal**: Track expansion state and provide visual cues

**Tasks**:
- [ ] **1. State Management** ✅ **DECISION: Q5**
  - Store: `expanded-nodes` - `{node_id: {direction: "both", count: 23, timestamp: "..."}}`
  - Store: `loaded-node-ids` - Array of all loaded node element IDs
  - Store: `removed-nodes` - Array of manually removed node IDs

- [ ] **2. Visual Indicators**
  - Expanded nodes: Thicker border or different border color
  - Expansion badge: Show "+23" count of loaded neighbors
  - Expandable indicator: "+" icon on un-expanded nodes (optional)

- [ ] **3. Expansion History**
  - Details panel shows: "Expanded: Both directions, 23 neighbors, 2m ago"
  - "Undo Expansion" button (removes expanded children, marks node as not expanded)
  - "Re-expand" button (if previously expanded but children removed)

- [ ] **4. Node Removal** (per Q5 requirement)
  - Context menu: "Remove from View"
  - Removed nodes hidden but tracked in state
  - "Show Hidden Nodes" button to restore
  - List of hidden nodes in sidebar or modal

**Success Criteria**:
- ✅ Can visually distinguish expanded from un-expanded nodes
- ✅ Can see expansion count per node
- ✅ Can manually remove/restore nodes
- ✅ Expansion state persists during session

---

#### **Phase 1.1f: Performance & Polish** ⏳ PLANNED

**Goal**: Optimize and handle edge cases

**Tasks**:
- [ ] **1. Performance Optimization**
  - Debounce rapid expansions (300ms cooldown)
  - Virtualization if graph exceeds 1000 nodes
  - Loading states for slow API responses

- [ ] **2. Error Handling**
  - Handle 404: Node not found
  - Handle 500: Query execution errors
  - Handle network timeouts
  - Graceful degradation if API unreachable

- [ ] **3. Edge Cases**
  - Expanding node with 0 neighbors (show "No neighbors found")
  - Expanding already-fully-expanded node (detect via API response)
  - Circular references (backend handles, verify frontend)
  - Very large expansions (>1000 neighbors, show warning)

- [ ] **4. UX Polish**
  - Smooth animations for new nodes appearing
  - Automatic layout adjustment after expansion
  - Optional auto-fit to keep new nodes visible
  - Keyboard shortcuts (E = expand selected node)

**Success Criteria**:
- ✅ No performance degradation with <1000 nodes
- ✅ All error cases handled gracefully
- ✅ Smooth, polished user experience

---

**Current Status**: Backend ✅ Complete, Starting Phase 1.1b (Button-Based Expansion)

**Next Immediate Step**: Implement Phase 1.1b tasks to prove end-to-end expansion works before tackling complex event handling

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

---

### Pre-Phase Decision Review

**Status**: 0 questions answered ✅, 2 questions pending ❓

#### ❓ **Q9. Filter Execution Model**
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

#### ❓ **Q10. Search Match Highlighting Strategy**
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

---

### Pre-Phase Decision Review

**Status**: 0 questions answered ✅, 4 questions pending ❓

#### ❓ **Q11. Path Finding Algorithm Selection**
- **Status**: UNANSWERED ❓
- **Phase**: 3.1 (Path Finding)
- **Review Trigger**: Before starting Phase 3.1.3
- **Options**: 
  - (a) Dijkstra - Classic shortest path, good for weighted graphs
  - (b) A* - Heuristic search, faster when you know target location
  - (c) BFS - Simplest, good for unweighted graphs
  - (d) Multiple algorithms - Let user choose based on scenario
- **Impact**: 
  - Query performance for large graphs
  - Accuracy of path results (weighted vs unweighted)
  - Backend complexity
- **Action Required**: Decide before Phase 3.1.3 implementation

#### ❓ **Q12. Path Visualization Strategy**
- **Status**: UNANSWERED ❓
- **Phase**: 3.1 (Path Finding)
- **Review Trigger**: Before starting Phase 3.1.5
- **Options**: 
  - (a) Highlight path in existing graph - Change edge/node colors for path
  - (b) Show path in separate panel - Display path as linear sequence
  - (c) Isolate path - Hide all non-path elements
  - (d) Animated traversal - Animate along the path
- **Impact**: 
  - User experience for understanding paths
  - UI complexity
  - Multiple path comparison (if showing multiple paths)
- **Action Required**: Decide before Phase 3.1.5 (Path Visualization)

#### ❓ **Q13. Pattern Detection Approach**
- **Status**: UNANSWERED ❓
- **Phase**: 3.2 (Pattern Detection)
- **Review Trigger**: Before starting Phase 3.2.1
- **Options**: 
  - (a) Pre-defined patterns - User selects from common patterns (triangles, stars, chains)
  - (b) Custom pattern builder - User draws/defines pattern via UI
  - (c) Cypher query patterns - User writes Cypher queries directly
  - (d) Combination - Pre-defined + custom builder
- **Impact**: 
  - User experience complexity vs flexibility
  - Backend query generation
  - Learning curve for end users
- **Action Required**: Decide before Phase 3.2.1 implementation

#### ❓ **Q14. Pattern Result Grouping**
- **Status**: UNANSWERED ❓
- **Phase**: 3.2 (Pattern Detection)
- **Review Trigger**: Before starting Phase 3.2.3
- **Options**: 
  - (a) Show all matches - Display every instance of pattern in graph
  - (b) Group by similarity - Cluster similar pattern instances
  - (c) Show one representative - Display one example + count
  - (d) Paginate results - Show first N, allow browsing
- **Impact**: 
  - Handling large result sets (e.g., 1000s of triangles)
  - User ability to explore vs being overwhelmed
  - Performance for rendering many nodes
- **Action Required**: Decide before Phase 3.2.3 (Pattern Results Display)

---

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

---

### Pre-Phase Decision Review

**Status**: 0 questions answered ✅, 4 questions pending ❓

#### ❓ **Q15. Large Graph Rendering Strategy**
- **Status**: UNANSWERED ❓
- **Phase**: 4.1 (Progressive Loading)
- **Review Trigger**: Before starting Phase 4.1.2
- **Options**: 
  - (a) Level-of-Detail (LOD) - Simplify nodes when zoomed out
  - (b) Viewport culling - Only render visible nodes
  - (c) Canvas rendering - Use canvas instead of SVG for better performance
  - (d) Combination - Use multiple techniques (LOD + culling + canvas)
- **Impact**: 
  - Performance threshold (how many nodes before slowdown)
  - Rendering complexity
  - Browser compatibility
- **Action Required**: Decide before Phase 4.1.2 implementation

#### ❓ **Q16. Graph Clustering Algorithm**
- **Status**: UNANSWERED ❓
- **Phase**: 4.2 (Graph Clustering & Aggregation)
- **Review Trigger**: Before starting Phase 4.2.1
- **Options**: 
  - (a) Louvain - Fast, hierarchical, good for large graphs
  - (b) Label Propagation - Very fast, simple, good for well-connected graphs
  - (c) Connected Components - Simplest, finds disconnected subgraphs
  - (d) Multiple algorithms - Offer choice based on use case
- **Impact**: 
  - Clustering quality
  - Performance for large graphs
  - Backend complexity
- **Action Required**: Decide before Phase 4.2.1 implementation

#### ❓ **Q17. Cluster Interaction Model**
- **Status**: UNANSWERED ❓
- **Phase**: 4.2 (Graph Clustering & Aggregation)
- **Review Trigger**: Before starting Phase 4.2.2
- **Options**: 
  - (a) Expand on click - Click super-node to expand cluster inline
  - (b) Separate view - Open cluster in new graph view
  - (c) Drill-down mode - Replace graph with cluster contents
  - (d) Hybrid - Click expands, right-click shows options
- **Impact**: 
  - User experience for navigating clusters
  - Graph layout complexity (expanding inline)
  - Back-navigation requirements
- **Action Required**: Decide before Phase 4.2.2 implementation

#### ❓ **Q18. Progressive Loading Strategy**
- **Status**: UNANSWERED ❓
- **Phase**: 4.1 (Progressive Loading)
- **Review Trigger**: Before starting Phase 4.1.1
- **Options**: 
  - (a) Pagination - Load N nodes, show "Load More" button
  - (b) Infinite scroll - Auto-load as user pans/zooms
  - (c) On-demand chunks - Load connected nodes as user explores
  - (d) Hybrid - Pagination + on-demand expansion
- **Impact**: 
  - User experience for exploring large graphs
  - Backend query complexity
  - State management (tracking loaded vs unloaded nodes)
- **Action Required**: Decide before Phase 4.1.1 implementation

---

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

---

### Pre-Phase Decision Review

**Status**: 0 questions answered ✅, 3 questions pending ❓

#### ❓ **Q19. Export Format Priorities**
- **Status**: UNANSWERED ❓
- **Phase**: 5.1 (Export Capabilities)
- **Review Trigger**: Before starting Phase 5.1.2
- **Options**: 
  - (a) Image first - PNG/SVG for presentations
  - (b) Data first - JSON/CSV/GraphML for analysis tools
  - (c) Both equally - Implement image and data exports in parallel
  - (d) User-driven - Survey users for most needed format
- **Impact**: 
  - Development priority and timeline
  - User satisfaction based on common use cases
  - Technical complexity varies by format
- **Action Required**: Decide before Phase 5.1 implementation

#### ❓ **Q20. View State Serialization Approach**
- **Status**: UNANSWERED ❓
- **Phase**: 5.2 (Shareable Views)
- **Review Trigger**: Before starting Phase 5.2.1
- **Options**: 
  - (a) URL parameters - Encode state in query string
  - (b) Short hash - Store state server-side, share hash key
  - (c) Base64 encoded state - Encode full state in URL fragment
  - (d) Hybrid - Short URLs with server storage, fallback to URL encoding
- **Impact**: 
  - URL length limitations (especially for complex views)
  - Server storage requirements
  - Sharing reliability (URLs vs server dependencies)
- **Action Required**: Decide before Phase 5.2.1 implementation

#### ❓ **Q21. Saved Views Storage Strategy**
- **Status**: UNANSWERED ❓
- **Phase**: 5.2 (Shareable Views)
- **Review Trigger**: Before starting Phase 5.2.3
- **Options**: 
  - (a) Browser localStorage - Client-side only, no backend needed
  - (b) Database - Server-side storage, survives browser changes
  - (c) Hybrid - localStorage + optional cloud sync
  - (d) Session-only - No persistence (simplest option)
- **Impact**: 
  - Feature richness (personal vs shared bookmarks)
  - Backend database schema changes
  - User expectations for bookmark persistence
- **Action Required**: Decide before Phase 5.2.3 implementation

---

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

---

### Pre-Phase Decision Review

**Status**: 0 questions answered ✅, 3 questions pending ❓

#### ❓ **Q22. Centrality Metrics Priority**
- **Status**: UNANSWERED ❓
- **Phase**: 6.1 (Graph Metrics)
- **Review Trigger**: Before starting Phase 6.1.1
- **Options**: 
  - (a) Degree centrality only - Simplest, fastest to compute
  - (b) Degree + PageRank - Common combo for importance ranking
  - (c) All centrality metrics - Comprehensive but computationally expensive
  - (d) User-selectable - Let user choose which metrics to compute
- **Impact**: 
  - Computation time for large graphs
  - Backend algorithm complexity
  - User insights vs computational cost trade-off
- **Action Required**: Decide before Phase 6.1.1 implementation

#### ❓ **Q23. Metrics Visualization Approach**
- **Status**: UNANSWERED ❓
- **Phase**: 6.1 (Graph Metrics)
- **Review Trigger**: Before starting Phase 6.1.3
- **Options**: 
  - (a) Color-coded nodes - Heatmap based on metric values
  - (b) Separate charts - Bar/line charts in side panel
  - (c) Node size mapping - Size nodes by centrality
  - (d) Combination - Multiple visualization options
- **Impact**: 
  - User understanding of metrics
  - Visual clarity vs information density
  - UI complexity
- **Action Required**: Decide before Phase 6.1.3 implementation

#### ❓ **Q24. Temporal Analysis Scope**
- **Status**: UNANSWERED ❓
- **Phase**: 6.2 (Temporal Analysis)
- **Review Trigger**: Before starting Phase 6.2
- **Options**: 
  - (a) Basic time filtering - Filter nodes/edges by date range
  - (b) Animation playback - Animate graph evolution over time
  - (c) Trend detection - Detect emerging patterns
  - (d) Full temporal suite - All of the above
- **Impact**: 
  - Requires temporal data model (timestamps on nodes/relationships)
  - Development complexity
  - Use case fit (is temporal analysis needed?)
- **Action Required**: Decide before Phase 6.2 implementation (validate if temporal data exists)

---

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
  - Single-click expansion with confirmation dialog (Q2 - ORIGINAL)
  - Paginated results: 50 + Load More (Q3)
  - Default direction: Both (Q4)
  - Manual node removal feature (Q5)
  - Breadcrumbs above graph (Q7)
- **2026-03-02**: Added pre-phase review warnings for all phases to ensure unanswered questions resolved before implementation
- **2026-03-02 (Evening)**: **MAJOR REVISION - Q2 Decision Changed & Phase 1.1 Restructured**:
  - **Updated Q2**: Changed from single-click+modal to **dual interaction model**:
    - Double-click for immediate expansion (power users)
    - Right-click for advanced options menu (all users)
  - **Restructured Phase 1.1**: Split into 6 micro-phases (1.1a-1.1f) for incremental implementation:
    - 1.1a: Backend API (✅ COMPLETE)
    - 1.1b: Simple button-based expansion (🔄 CURRENT - validate full stack)
    - 1.1c: Double-click quick expansion (⏳ PLANNED - clientside callbacks)
    - 1.1d: Right-click context menu (⏳ PLANNED - clientside callbacks)
    - 1.1e: State management & visual indicators (⏳ PLANNED)
    - 1.1f: Performance & polish (⏳ PLANNED)
  - **Rationale**: Build incrementally to de-risk technical challenges (Dash Cytoscape event handling)
  - **Impact**: Phase 1.1 timeline extended, but higher confidence in successful delivery- **2026-03-02 (Late Evening)**: **DOCUMENT REFACTORING - Q&A Reorganization**:
  - **Replaced centralized Decision Log** with compact **Decision Status Summary**:
    - Shows quick status: 6 answered, 18 pending
    - Lists review requirements per phase
    - Includes pre-implementation protocol
  - **Embedded all Q&A content into respective phases**:
    - Phase 1: Q1-Q8 (Pre-Phase Decision Review)
    - Phase 2: Q9-Q10 
    - Phase 3: Q11-Q14
    - Phase 4: Q15-Q18
    - Phase 5: Q19-Q21
    - Phase 6: Q22-Q24
  - **Rationale**: Improve document parseability and implementation readiness - developers see relevant decisions where they need them
  - **Impact**: Better developer experience, easier to review decisions in context during implementation
# Graph Visualization Implementation Plan

**Status**: Phase 5 Complete (Backend + Frontend + Visualization + Interactivity + Polish) 🎉  
**Created**: February 22, 2026  
**Last Updated**: March 2, 2026  
**Related Phases**: Phase 6 (Graph Visualization UI) of main project roadmap

## Progress Summary
- ✅ **Phase 1**: Backend API Foundation (71 automated tests)
- ✅ **Phase 2**: Frontend - Graph Tab & Basic UI (functional query execution)
- ✅ **Phase 3**: Graph Visualization with Dash Cytoscape (interactive visualization)
- ✅ **Phase 4**: Interactivity and Styling (node selection, layouts, zoom/pan)
- ✅ **Phase 5**: Polish and UX Enhancements (validation, performance metrics, error handling)
  - Note: Phase 5.2 & 5.3 (Example Queries & Query History) deferred to `query-management-implementation.md`

## Overview

Add an interactive "Graph" tab to the Dash application where users can execute Cypher queries against Neo4j and visualize results. The system intelligently displays graphs for node/relationship queries and tables for tabular results. Implementation follows existing three-layer API patterns with read-only query restrictions for security.

### Key Decisions
- **Visualization Library**: dash-cytoscape (Python-native, no React wrapper needed)
- **Security Model**: Read-only queries (MATCH/RETURN only)
- **Display Logic**: Adaptive (graph for nodes/edges, table for tabular data)
- **Input Method**: Simple textarea (foundation for future AI query generation)
- **Approach**: Multi-phase incremental implementation

### Prerequisites
- Neo4j instance running at `bolt://localhost:7687` (configured and accessible)
- Existing FastAPI backend with async patterns
- Dash frontend with Bootstrap components

---

## Phase 1: Backend API Foundation

### Objectives
- Centralize Neo4j configuration
- Create new graph API following existing patterns (router → service → query)
- Implement read-only query validation
- Handle Neo4j connection and query execution

### Tasks

- [x] **1.1 Centralize Neo4j Configuration** ✅
  - File: `app/settings.py`
  - Add fields: `neo4j_uri`, `neo4j_username`, `neo4j_password`, `neo4j_enabled`
  - Update `app/ai_agent/chains/neo4j_chain.py` to use centralized settings
  - Remove hardcoded config from chain module

- [x] **1.2 Create API Structure** ✅
  - Create directory: `app/api/graph/`
  - Create subdirectory: `app/api/graph/v1/`
  - Add `__init__.py` files in both directories

- [x] **1.3 Define Pydantic Models** ✅
  - File: `app/api/graph/v1/model.py`
  - Create `CypherQueryRequest`: field `query: str` with validation
  - Create `GraphNode`: `id`, `labels`, `properties`
  - Create `GraphRelationship`: `id`, `type`, `startNode`, `endNode`, `properties`
  - Create `GraphResponse`: `nodes`, `relationships`, `rawResults`, `isGraph`
  - Add validation: non-empty query, max length constraint

- [x] **1.4 Implement Query Layer** ✅
  - File: `app/api/graph/v1/query.py`
  - Function: `validate_read_only_query(query: str) -> bool`
    - Accept: MATCH, OPTIONAL, WITH, UNWIND, RETURN, CALL (read-only procedures)
    - Reject: CREATE, MERGE, DELETE, SET, REMOVE, DROP, DETACH
    - Use case-insensitive regex or string parsing
  - Function: `execute_cypher_query(query: str) -> Dict`
    - Get Neo4j driver from `app/ai_agent/chains/neo4j_chain.py:get_neo4j_graph()` (reuse existing connection)
    - Alternative: Create new driver using settings (if you centralize config first)
    - Execute with timeout (30 seconds)
    - Return raw results
    - Handle exceptions: connection errors, syntax errors, timeouts
  - Testing: `tests/test_graph_query.py`
    - 22 unit tests for validation (read-only vs write operations)
    - 11 integration tests for execution (requires running Neo4j)
    - 3 edge case tests (multiline, comments, mixed operations)
    - All 36 tests passing ✅

- [x] **1.5 Implement Service Layer** ✅
  - File: `app/api/graph/v1/service.py`
  - Function: `execute_and_format_query(query: str) -> GraphResponse`
    - Validate query (raise exception if not read-only)
    - Execute query via query layer
    - Parse Neo4j result records
    - Detect result type: nodes/relationships vs tabular data
    - Transform to GraphResponse model
    - Return formatted response
  - Helper functions:
    - `_transform_node()`: Convert Neo4j Node to GraphNode
    - `_transform_relationship()`: Convert Neo4j Relationship to GraphRelationship
    - `_make_serializable()`: Convert Neo4j types to JSON-serializable
  - Testing: `tests/test_graph_service.py`
    - 14 integration tests covering graph/tabular transformation
    - Node/relationship deduplication
    - Write query rejection
    - All 14 tests passing ✅

- [x] **1.6 Implement Router** ✅
  - File: `app/api/graph/v1/router.py`
  - Create `APIRouter` with prefix `/api/v1/graph`
  - POST endpoint `/query` accepting `CypherQueryRequest`
  - GET endpoint `/health` for Neo4j connectivity check
  - Call service layer
  - Return `GraphResponse` or `HTTPException`
  - Error codes: 400 (invalid query), 500 (Neo4j errors)
  - Include descriptive error messages
  - Fixed Neo4j DateTime serialization issue
  - Testing: `tests/test_graph_router.py`
    - 7 endpoint integration tests (health check, nodes, relationships, tabular, properties, empty, datetime)
    - 6 validation tests (reject CREATE/DELETE/MERGE/SET, empty queries)
    - 4 error handling tests (syntax errors, missing fields, invalid JSON, query length)
    - 4 complex query tests (WHERE, OPTIONAL MATCH, ORDER BY, multiple returns)
    - All 21 tests passing ✅

- [x] **1.7 Register Router** ✅
  - File: `app/main.py`
  - Import graph router
  - Add to app: `app.include_router(graph_router)`

### Verification
```bash
# Test valid read-only query
curl -X POST http://localhost:8000/api/v1/graph/query \
  -H "Content-Type: application/json" \
  -d '{"query": "MATCH (n) RETURN n LIMIT 5"}'

# Test write query rejection
curl -X POST http://localhost:8000/api/v1/graph/query \
  -H "Content-Type: application/json" \
  -d '{"query": "CREATE (n:Test) RETURN n"}'

# Verify error handling
curl -X POST http://localhost:8000/api/v1/graph/query \
  -H "Content-Type: application/json" \
  -d '{"query": "INVALID SYNTAX"}'
```

---

## Phase 2: Frontend - Graph Tab & Basic UI

### Objectives
- Add Graph tab to navigation
- Create basic query input interface
- Implement API communication

### Tasks

- [x] **2.1 Create Graph Page** ✅
  - File: `app/dash_app/pages/graph.py` (117 lines)
  - Implemented `get_layout()` function
  - Components added:
    - Header: "Graph Visualization" with description
    - Query input section with styled container
    - `dbc.Textarea` with id `graph-query-input` (150px height, monospace font)
    - Placeholder: `MATCH (n:Project)-[r]->(m)\nRETURN n, r, m\nLIMIT 10`
    - `dbc.Button` "Execute Query" with id `graph-execute-btn` (includes play icon)
    - Security note: "Only read-only queries (MATCH, RETURN) are allowed"
    - Results section with styled container
    - `dcc.Loading` wrapper with id `graph-loading` (circle spinner, primary color)
    - `html.Div` with id `graph-results-container` (min-height: 400px)
    - Empty state: Icon with message "No results yet..."
    - `dcc.Store` with id `graph-data-store` (for graph data)
    - `dcc.Store` with id `graph-query-history` (for future query history feature)
  - Styling: Modern design with rounded corners, shadows, consistent with chat.py pattern

- [x] **2.2 Update Navigation** ✅
  - File: `app/dash_app/layout.py`
  - Changes made:
    - Added `graph` to imports: `from .pages import chat, people, progress, settings, graph`
    - Added sidebar link: `dbc.NavLink("📊 Graph", href="/app/graph", active="exact", id="nav-graph")`
    - Positioned after Progress link, before Settings link
    - Updated `display_page()` callback with routing condition:
      - `if pathname == "/app/graph": return graph.get_layout()`
  - Navigation order: Chat → People → Progress → **Graph** → Settings

- [x] **2.3 Implement Query Execution Callback** ✅
  - File: `app/dash_app/pages/graph.py`
  - Added imports: `os`, `requests`, `Input`, `Output`, `State`, `callback`
  - Added constant: `TIMEOUT_SECONDS = 30`
  - Created `execute_query()` callback:
    - Outputs: `("graph-data-store", "data")`, `("graph-results-container", "children")`
    - Input: `("graph-execute-btn", "n_clicks")`
    - State: `("graph-query-input", "value")`
    - Features implemented:
      - Empty query validation with warning alert
      - API base URL from environment: `os.getenv("API_BASE_URL", "http://localhost:8000")`
      - POST to `{api_base}/api/v1/graph/query` with 30-second timeout
      - Response handling:
        - Success: Display graph/tabular results with counts
        - Graph results: Show node/relationship counts, raw data preview
        - Tabular results: Show result count, raw data display
        - Errors: Structured alerts with icons and error details
      - Comprehensive error handling:
        - HTTP errors (400, 500, etc.) with detail extraction
        - Timeout errors (>30 seconds)
        - Connection errors (server not running)
        - General exceptions
      - Temporary display: Raw JSON data in styled `html.Pre` blocks (until Phase 3 visualization)
  - Integration: Fully functional with backend API at `/api/v1/graph/query`

### Phase 2 Complete! 🎉

**Verification Steps:**
1. **Start the server** (if not running):
   ```bash
   uvicorn app.main:app --reload
   ```

2. **Navigate to Graph page**:
   - Open http://localhost:8000/app/graph
   - Or click "📊 Graph" in the sidebar

3. **Test graph query** (returns nodes and relationships):
   ```cypher
   MATCH (n:Project)-[r]->(m)
   RETURN n, r, m
   LIMIT 5
   ```
   Expected: Success alert with node/relationship counts + raw data preview

4. **Test tabular query** (returns non-graph data):
   ```cypher
   MATCH (n)
   RETURN count(n) as nodeCount
   ```
   Expected: Success alert with result count + raw results display

5. **Test write rejection**:
   ```cypher
   CREATE (n:Test {name: "test"})
   RETURN n
   ```
   Expected: Danger alert with "Write operations are not allowed" error

6. **Test empty query**:
   - Leave textarea empty and click "Execute Query"
   - Expected: Warning alert "Please enter a Cypher query before executing"

7. **Test error handling**:
   ```cypher
   MATCH (n) INVALID SYNTAX
   ```
   Expected: Danger alert with syntax error details

8. **Verify data storage**:
   - Open browser DevTools → Components/React tab
   - Find `graph-data-store` component
   - Verify it contains query response data after successful execution

**Current Functionality:**
- ✅ Full API integration with backend
- ✅ Query validation and execution
- ✅ Comprehensive error handling (timeout, connection, HTTP, validation)
- ✅ Success/error feedback with styled alerts
- ✅ Raw data preview in formatted JSON blocks
- ⏳ Graph visualization (Phase 3)

---

## Phase 3: Graph Visualization with Dash Cytoscape

### Objectives
- Install and configure dash-cytoscape
- Transform Neo4j data to Cytoscape format
- Render interactive graph visualization

### Tasks

- [x] **3.1 Add Dependency** ✅
  - File: `requirements.txt`
  - Added: `dash-cytoscape==1.0.2`
  - Ready for installation: `pip install -r requirements.txt`

- [x] **3.2 Create Graph Renderer** ✅
  - File: `app/dash_app/pages/graph.py`
  - Added import: `import dash_cytoscape as cyto`
  - Updated `get_layout()` with three-part results display:
    - **Graph container** (`graph-cytoscape-container`): Contains Cytoscape component
      - `cyto.Cytoscape` with id `graph-cytoscape`
      - Layout: `{'name': 'cose', 'animate': True}`
      - Style: `width: 100%`, `height: 600px`, light gray background
      - Stylesheet includes:
        - Node styles: Blue circles (60px), centered labels, white text
        - Edge styles: Gray arrows with relationship type labels
        - Hover/selection: Yellow border, darker blue background
      - Hidden by default (`display: none`)
    - **Table container** (`graph-table-container`): For tabular results
      - Hidden by default (`display: none`)
    - **Default container** (`graph-results-container`): Empty state message
      - Shows when no query has been executed
  - All three containers wrapped in `dcc.Loading` spinner

- [x] **3.3 Data Transformation Function** ✅
  - File: `app/dash_app/pages/graph.py`
  - Created `neo4j_to_cytoscape(graph_response)` function
  - Transforms backend API response to Cytoscape elements format
  - Node transformation:
    - Extracts `id`, `labels`, and `properties` from Neo4j nodes
    - Uses first label as `nodeType`
    - Intelligently selects display label from properties:
      - Priority: `name` → `title` → `label` → node type
    - Spreads all node properties into Cytoscape data
    - Format: `{'data': {'id': ..., 'label': ..., 'nodeType': ..., **properties}}`
  - Relationship transformation:
    - Extracts `id`, `type`, `startNode`, `endNode`, `properties`
    - Maps to Cytoscape edge: `source`, `target`, `label`
    - Stores relationship type as `relType`
    - Spreads all relationship properties into Cytoscape data
    - Format: `{'data': {'id': ..., 'source': ..., 'target': ..., 'label': ..., 'relType': ..., **properties}}`
  - Returns combined list of node and edge elements

- [x] **3.4 Display Callback** ✅
  - File: `app/dash_app/pages/graph.py`
  - Updated `execute_query()` callback with 7 outputs:
    - `graph-data-store` (data) - Stores API response
    - `graph-cytoscape` (elements) - Cytoscape graph elements
    - `graph-cytoscape-container` (style) - Show/hide graph container
    - `graph-table-container` (children) - Table content
    - `graph-table-container` (style) - Show/hide table container
    - `graph-results-container` (children) - Default/error messages
    - `graph-results-container` (style) - Show/hide default container
  - Display logic implemented:
    - **Graph results** (`isGraph: true`):
      - Transform data via `neo4j_to_cytoscape()`
      - Populate Cytoscape elements
      - Show graph container with success alert
      - Hide table and default containers
    - **Tabular results** (`isGraph: false`):
      - Create `dbc.Table` from `rawResults`
      - Extract columns from first result row
      - Display striped, bordered, hover-enabled table
      - Show table container with success alert
      - Hide graph and default containers
    - **Errors**:
      - Display error alert in default container
      - Hide graph and table containers
      - Handle: HTTP errors, timeouts, connection errors, validation errors
  - Empty result handling: Shows info alert when query returns no data

### Phase 3 Complete! 🎉

**Verification Steps:**

1. **Start the servers** (if not running):
   ```bash
   # Terminal 1: Start PostgreSQL and Neo4j
   docker compose up -d
   
   # Terminal 2: Start FastAPI app
   uvicorn app.main:app --reload
   ```

2. **Navigate to Graph page**:
   - Open http://localhost:8000/app/graph
   - Or click "📊 Graph" in the sidebar

3. **Test graph visualization** (nodes and relationships):
   ```cypher
   MATCH (n:Project)-[r:HAS_BRANCH]->(m:Branch)
   RETURN n, r, m
   LIMIT 10
   ```
   **Expected:**
   - ✅ Success alert showing node/relationship counts
   - ✅ Interactive graph visualization appears
   - ✅ Nodes displayed as blue circles with labels
   - ✅ Edges displayed as gray arrows with relationship types
   - ✅ Can click and drag nodes
   - ✅ Can select nodes (yellow border appears)
   - ✅ Can zoom with mouse wheel
   - ✅ Can pan by dragging background

4. **Test tabular query** (non-graph data):
   ```cypher
   MATCH (n:Project)
   RETURN n.name as projectName, n.status as status
   LIMIT 10
   ```
   **Expected:**
   - ✅ Success alert with result count
   - ✅ Formatted table with columns: `projectName`, `status`
   - ✅ Striped rows with hover effect
   - ✅ No graph visualization shown

5. **Test empty results**:
   ```cypher
   MATCH (n:NonExistentLabel)
   RETURN n
   ```
   **Expected:**
   - ℹ️ Info alert: "Query executed successfully but returned no results"

6. **Test error handling**:
   ```cypher
   CREATE (n:Test) RETURN n
   ```
   **Expected:**
   - ❌ Danger alert: "Write operations are not allowed"

**Current Functionality:**
- ✅ Full backend API integration
- ✅ Interactive graph visualization with Cytoscape
- ✅ Tabular data display with Bootstrap tables
- ✅ Smart container switching (graph/table/default)
- ✅ Comprehensive error handling
- ✅ Node selection and interaction
- ✅ Zoom and pan controls

---

## Phase 4: Graph Interactivity & Styling

### Objectives
- Enhanced visual styling
- Node/edge interaction
- Layout controls
- Zoom and pan functionality

### Tasks

- [x] **4.1 Enhanced Cytoscape Styling** ✅
  - File: `app/dash_app/pages/graph.py`
  - Updated Cytoscape stylesheet with comprehensive styling:
    - **Default node style**: Gray (#6c757d), 60px diameter, text wrapping
    - **Node colors by type** (Bootstrap color palette):
      - `Project`: Blue (#0d6efd, 70px) - Largest, primary focus
      - `Person`: Purple (#6f42c1, 65px) - Team members
      - `Branch`: Teal (#20c997, 55px) - Code branches
      - `Epic`: Orange (#fd7e14, 65px) - Large features
      - `Issue`: Yellow (#ffc107, 55px) - Tasks (dark text for contrast)
      - `Repository`: Cyan (#0dcaf0, 65px) - Code repos
    - **Node size variations**: 55-70px based on importance
    - **Edge styling**:
      - Gray arrows with labels
      - Text background for readability
      - Bezier curves for cleaner look
    - **Selection states** (click-based):
      - Node selection: 4px yellow border, brought to front (z-index: 9999)
      - Edge selection: Thicker lines (4px), yellow color
    - **Typography**: Improved font weights, text wrapping, max-width for labels
    - **Note**: True hover effects not supported by Dash-Cytoscape - using click selection instead

- [x] **4.2 Property Details Panel** ✅
  - File: `app/dash_app/pages/graph.py`
  - Added sidebar layout with 8/4 column split (graph/details)
  - Created `graph-details-panel` in right column (4-wide):
    - Styling: Gray background (#f8f9fa), 600px height, scrollable
    - Empty state: "Click a node or edge to view details"
  - Implemented `display_properties()` callback:
    - Inputs: `tapNodeData` and `tapEdgeData` from Cytoscape
    - Output: `graph-details-panel` children
    - **Node display**: Type, label, ID, and all additional properties
    - **Edge display**: Type, source, target, ID, and all additional properties
    - Property formatting: Dict/list values in code blocks, primitives as text
    - Clean UI: Icons, section headers, sorted properties, Bootstrap styling

- [x] **4.3 Layout Controls** ✅
  - File: `app/dash_app/pages/graph.py`
  - Added `dbc.Select` dropdown with id `graph-layout-selector`
  - Positioned above graph visualization in `graph-cytoscape-container`
  - Layout options with descriptive labels:
    - `cose` - Force-Directed (default, good for organic relationship visualization)
    - `circle` - Nodes arranged in a circle
    - `grid` - Regular grid pattern
    - `breadthfirst` - Hierarchical tree layout
    - `concentric` - Concentric circles based on node importance
  - Implemented `update_layout()` callback:
    - Input: `graph-layout-selector` value
    - Output: `graph-cytoscape` layout property
    - Returns layout config with animation enabled: `{'name': layout_name, 'animate': True}`
  - Styling: Compact inline layout (250px width) with label, aligned to left

- [x] **4.4 Zoom/Pan Controls** ✅
  - File: `app/dash_app/pages/graph.py`
  - Added zoom/pan control buttons in layout controls row
  - Enhanced Cytoscape component properties:
    - `userZoomingEnabled=True` - Enable mouse wheel zoom
    - `userPanningEnabled=True` - Enable click-drag panning
    - `wheelSensitivity=0.2` - Smoother zoom experience
    - `minZoom=0.5, maxZoom=3` - Reasonable zoom bounds
  - Added button group with two controls:
    - **Fit to Screen** - Refits graph to viewport with padding
    - **Reset View** - Reapplies current layout with fit
  - Updated `update_layout()` callback:
    - Added inputs for fit/reset button clicks
    - Added State for current layout
    - Uses `callback_context` to detect trigger source
    - Returns layout with `fit=True, padding=30` for reset/fit actions
  - UI positioning: Button group aligned right in controls row

### Verification
- Click nodes and edges, verify details panel updates
- Switch between layout algorithms
- Test zoom with mouse wheel
- Test pan by dragging
- Click reset and fit buttons
- Verify styling matches Neo4j color conventions

---

## Phase 5: Polish & User Experience

### Objectives
- Improve error feedback
- Add query examples and history
- Optimize performance
- Enhance usability

### Tasks

- [x] **5.1 Query Validation Feedback** ✅
  - File: `app/dash_app/pages/graph.py`
  - Added `html.Div` with id `query-validation-message` below textarea
  - Implemented `validate_query()` callback for real-time validation:
    - Input: `graph-query-input` value (triggers on every keystroke)
    - Output: `query-validation-message` children
  - Validation rules:
    - **Danger alert**: Detects write operations (CREATE, MERGE, SET, DELETE, REMOVE, DROP)
    - **Warning alert**: Query doesn't start with valid read keywords (MATCH, RETURN, WITH, UNWIND, CALL, OPTIONAL)
    - **Info alert**: Missing LIMIT clause for performance
    - **No message**: Query looks good
  - Alert styling: Compact (fontSize: 13px), color-coded by severity
  - User-friendly messages with icons and helpful hints

- [ ] **5.2 Example Queries** (→ See `query-management-implementation.md` Phase 1-2)
  - **Backend**: Database-backed example queries with CRUD API
  - **Frontend**: `dbc.Accordion` populated from `/api/v1/queries/examples` endpoint
  - Features:
    - 6+ curated example queries seeded via migration
    - Click-to-populate textarea functionality
    - Category badges and descriptions
    - Usage tracking (execution_count)
  - Implementation: See dedicated planning doc `project-plan/query-management-implementation.md`

- [ ] **5.3 Query History** (→ See `query-management-implementation.md` Phase 3)
  - **Backend**: Auto-save executed queries to database (last 50)
  - **Frontend**: `dbc.Select` dropdown populated from `/api/v1/queries/history` endpoint
  - Features:
    - Auto-save on successful query execution
    - Load previous queries with one click
    - Automatic cleanup (keep last 50)
    - Timestamp tracking
  - Implementation: See dedicated planning doc `project-plan/query-management-implementation.md`

- [x] **5.4 Performance Optimization** ✅
  - File: `app/dash_app/pages/graph.py`
  - Enhanced LIMIT warning in `validate_query()` callback:
    - Now suggests specific `LIMIT 100` with inline code formatting
    - More actionable message about avoiding too many nodes
  - Added `_create_performance_metrics()` helper function:
    - Displays execution time (ms or seconds)
    - Shows node/edge counts for graph queries
    - Shows row count for tabular queries
    - Performance status indicator (Fast/OK/Slow) based on:
      - Graph: >200 elements = slow, >100 = OK, ≤100 = fast
      - Tabular: >1000 rows = slow, >500 = OK, ≤500 = fast
      - Time thresholds: >3s = slow, >2s = OK, ≤2s = fast
    - Helpful tips when results exceed recommended limits
  - Added performance metrics container to layout:
    - Positioned above results section
    - Hidden by default, shown after successful query execution
  - Updated `execute_query()` callback:
    - Added 2 new outputs: `graph-performance-metrics` (children and style)
    - Tracks execution time using `time.time()` before/after API call
    - Displays metrics for both graph and tabular results
    - Color-coded status indicators (green/yellow/red)
  - Frontend-based timing (measures total round-trip time including API call)

- [x] **5.5 Error Handling Polish** ✅
  - File: `app/dash_app/pages/graph.py`
  - Created `_parse_error_response()` function:
    - Parses backend error responses (status code + error details)
    - Categorizes errors into specific types:
      - 400 errors: Write operations, syntax errors, validation errors
      - 500 errors: Connection failures, timeouts, execution errors
      - 503 errors: Service unavailable
    - Returns user-friendly heading, hint, documentation link, and alert type
    - Uses emoji icons for visual clarity (🚫, ⚠️, 🔌, ⏱️, etc.)
  - Enhanced `_create_error_alert()` function:
    - Added `doc_link` parameter for documentation URLs
    - Displays clickable documentation links when provided
    - Opens links in new tab with proper styling
    - Links point to official Neo4j Cypher documentation
  - Updated error handling in `execute_query()` callback:
    - **HTTP errors**: Now uses `_parse_error_response()` for smart categorization
    - **Timeout errors**: Specific message suggesting LIMIT clause with doc link
    - **Connection errors**: Shows API URL and suggests starting the server
    - **HTTP errors**: Helpful message suggesting to check backend logs
    - **Unexpected errors**: Generic fallback with support contact suggestion
  - Documentation links added:
    - Syntax errors → Neo4j Cypher syntax guide
    - Write operation errors → MATCH clause documentation
    - Timeout errors → LIMIT clause documentation
    - Connection errors → Neo4j installation guide
  - All errors now include:
    - Descriptive emoji-enhanced heading
    - Clear explanation of what went wrong
    - Actionable hint on how to fix the issue
    - Optional link to relevant documentation

### Verification
- Test each example query
- Verify query history persists across page reloads
- Test with queries missing LIMIT
- Trigger various error conditions
- Verify error messages are helpful
- Test with large result sets (100+ nodes)

---

## Future Enhancements (Out of Scope)

These are ideas for future iterations, not part of initial implementation:

- [ ] AI-generated queries from chat interface (Phase 4 vision)
- [ ] Query templates with parameter inputs
- [ ] Export graph as image or JSON
- [ ] Graph filtering and search
- [ ] Multi-query tabs
- [ ] Query performance metrics display
- [ ] Saved query library
- [ ] Collaborative query sharing
- [ ] Custom node/edge styling rules
- [ ] Graph analytics (centrality, communities)

**📋 Note**: Advanced navigation features (node expansion, path finding, pattern detection, etc.) are now tracked in a dedicated implementation plan: [`advanced-graph-navigation.md`](./advanced-graph-navigation.md). This includes 6 comprehensive phases covering:
- Phase 1: Core Navigation & Expansion (double-click to expand, context menus)
- Phase 2: Filtering & Search (property filters, full-text search)
- Phase 3: Path Exploration & Pattern Detection (shortest paths, motifs)
- Phase 4: Performance & Scalability (clustering, progressive loading)
- Phase 5: Collaboration & Export (shareable views, annotations)
- Phase 6: Analytics & Insights (centrality metrics, temporal analysis)

---

## Technical Notes

### Security Considerations
- **Read-only enforcement**: Critical for production use - validate on backend, not just frontend
- **Query timeout**: Prevents long-running queries from blocking (30 seconds default)
- **Input validation**: Protects against injection attacks (max query length, blocked keywords)
- **Error exposure**: Don't expose internal system details in error messages
- **Neo4j credentials**: Ensure `.env` file is in `.gitignore` - never commit credentials
- **CORS**: Backend should only accept requests from known origins (localhost for development)

### Performance Considerations
- **Result limits**: Recommend LIMIT 25-100 for graph queries
- **Lazy loading**: Consider pagination for large results
- **Caching**: Optional query result caching (5-minute TTL)
- **Graph complexity**: Cytoscape handles ~1000 nodes well, >5000 may lag

### Known Limitations
- **Neo4j connection**: Single connection, no pooling yet (reuses existing connection from AI agent chain)
- **Query complexity**: No cost estimation or query planning
- **Visualization**: Limited to 2D layouts (no 3D)
- **Real-time**: No live query or streaming results
- **Browser storage**: Query history limited by localStorage capacity (~5-10MB)

---

## Dependencies

### New
- `dash-cytoscape==1.0.2`

### Existing
- `fastapi`
- `uvicorn`
- `dash`
- `dash-bootstrap-components`
- `langchain-neo4j` (for Neo4j driver)
- `pydantic`

---

## Testing Strategy

### Unit Tests ✅
- Query validation logic (`tests/test_graph_query.py::TestQueryValidation`)
  - 22 tests covering valid/invalid queries, edge cases, security
- Data transformation functions (future service layer tests)

### Integration Tests ✅
- Neo4j query execution (`tests/test_graph_query.py::TestQueryExecution`)
  - 11 tests for successful queries, error handling, timeouts
  - Requires running Neo4j server
- Service layer transformation (`tests/test_graph_service.py::TestGraphService`)
  - 14 tests for graph/tabular data transformation
  - Node/relationship deduplication
- Router endpoint integration (`tests/test_graph_router.py`)
  - 21 tests for HTTP endpoints, validation, error responses
  - All HTTP status codes and response formats
- Error scenarios (`tests/test_graph_query.py::TestEdgeCases`)

### Manual Testing (Priority)
- Execute queries on real Neo4j data
- Test all UI interactions
- Verify error handling
- Performance with various data sizes

---

## References

- [dash-cytoscape Documentation](https://dash.plotly.com/cytoscape)
- [Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/)
- [FastAPI Async Patterns](https://fastapi.tiangolo.com/async/)
- Existing API patterns: `app/api/projects/v1/` and `app/api/chats/v1/`

---

## Changelog

- **2026-02-22**: Initial plan created
- **2026-02-22**: Phase 1.1 completed - Centralized Neo4j configuration in settings.py
- **2026-02-22**: Phase 1.2 completed - Created API directory structure (app/api/graph/v1/)
- **2026-02-22**: Phase 1.3 completed - Defined and validated Pydantic models against real Neo4j data
- **2026-02-22**: Phase 1.4 completed - Implemented query layer with validation and execution functions
- **2026-02-22**: Phase 1.4 testing - Created comprehensive pytest suite with 36 tests (all passing)
- **2026-02-22**: Phase 1.5 completed - Implemented service layer with data transformation and graph detection
- **2026-02-22**: Phase 1.5 testing - Created service layer tests with 14 integration tests (all passing)
- **2026-02-22**: Phase 1.6 completed - Implemented FastAPI router with /query and /health endpoints
- **2026-02-22**: Phase 1.6 fix - Added Neo4j DateTime serialization support (iso_format)
- **2026-02-22**: Phase 1.6 testing - Created router endpoint tests with 21 tests (all passing)
- **2026-02-22**: Phase 1.7 completed - Registered router in main.py
- **2026-02-22**: Phase 1 verification - All endpoints tested and working (graph queries, tabular queries, error handling)
- **2026-02-22**: Phase 1 complete - Full backend API with 71 automated tests
- **2026-02-22**: Phase 2.1 completed - Created Graph page with query input, execute button, and results containers
- **2026-02-22**: Phase 2.2 completed - Added Graph tab to navigation sidebar and routing
- **2026-02-22**: Phase 2.3 completed - Implemented query execution callback with API integration
- **2026-02-22**: Phase 2 complete - Full frontend UI with query execution and error handling
- **2026-03-02**: Phase 3.1 completed - Added dash-cytoscape==1.0.2 to requirements.txt
- **2026-03-02**: Phase 3.2 completed - Created Cytoscape graph renderer component with styling
- **2026-03-02**: Phase 3.3 completed - Implemented neo4j_to_cytoscape() data transformation function
- **2026-03-02**: Phase 3.4 completed - Updated execute_query callback with 7 outputs for smart container switching
- **2026-03-02**: Phase 3 complete - Full graph visualization with nodes, edges, and tabular results
- **2026-03-02**: Code refactoring - Extracted helper functions, reduced execute_query from 170 to 100 lines
- **2026-03-02**: Phase 4.1 completed - Enhanced Cytoscape styling with node type colors and selection states
- **2026-03-02**: Phase 4.1 fix - Removed unsupported hover selectors, clarified click-based selection
- **2026-03-02**: Phase 4.2 completed - Property details panel with node/edge inspection sidebar
- **2026-03-02**: Phase 4.2 fix - Changed to selectedNodeData/selectedEdgeData to clear panel on deselection
- **2026-03-02**: Phase 4.2 fix - Added panel visibility control to hide for tabular results
- **2026-03-02**: Phase 4.3 completed - Layout controls with dropdown selector for 5 layout algorithms
- **2026-03-02**: Code refactoring - Priority 1: Extracted CYTOSCAPE_STYLESHEET constant and property formatting helpers
- **2026-03-02**: Phase 4.4 completed - Zoom/pan controls with Fit to Screen and Reset View buttons
- **2026-03-02**: Phase 4.4 fix - Added alternating stop parameter to force layout re-render on repeated Reset View clicks
- **2026-03-02**: Phase 4.4 fix - Separated Fit to Screen (clientside zoom/pan only) from Reset View (re-run layout)
- **2026-03-02**: Phase 5.1 completed - Real-time query validation with danger/warning/info alerts
- **2026-03-02**: Architecture decision - Created dedicated Query Management System for Phases 5.2-5.3 (see query-management-implementation.md)
- **2026-03-02**: Phase 3.3 completed - Implemented neo4j_to_cytoscape() data transformation function
- **2026-03-02**: Phase 3.4 completed - Updated display callback for graph/table rendering with container switching
- **2026-03-02**: Phase 3 complete - Interactive graph visualization with Cytoscape fully functional
- **2026-03-02**: Code refactoring - Extracted helper functions (_create_error_alert, _create_table_display, _create_graph_success_alert) to reduce execute_query from 170 to 100 lines
- **2026-03-02**: Phase 4.1 completed - Enhanced Cytoscape styling with node type colors, hover effects, and improved visual design
- **2026-03-02**: Phase 5.4 completed - Performance optimization with execution metrics display
  - Enhanced LIMIT warning to suggest specific `LIMIT 100` with inline code formatting
  - Added `_create_performance_metrics()` helper function with execution time tracking
  - Added performance status indicators (Fast/OK/Slow) with color-coded thresholds
  - Added performance tips for queries exceeding recommended limits
  - Updated execute_query callback with 2 new outputs for performance metrics display
- **2026-03-02**: Phase 5.5 completed - Error handling polish with user-friendly messages and documentation links
  - Created `_parse_error_response()` function for intelligent error categorization
  - Enhanced `_create_error_alert()` to support clickable documentation links
  - Added emoji-enhanced error headings for visual clarity
  - Implemented context-aware error messages with actionable hints
  - Added links to Neo4j documentation for syntax errors, LIMIT clause, and installation guides
  - Improved error handling for timeouts, connection errors, and HTTP errors
- **2026-03-02**: Phase 5 complete - All Polish & UX enhancements implemented (except 5.2 and 5.3 deferred to query-management-implementation.md)
- **2026-03-02**: UX improvement - Moved performance metrics from top to bottom of page for better screen real estate
- **2026-03-02**: Architecture planning - Created dedicated advanced navigation plan ([`advanced-graph-navigation.md`](./advanced-graph-navigation.md)) for Phases 6-11
  - Researched Neo4j Browser and Neo4j Bloom features
  - Defined 6 comprehensive phases for advanced graph exploration
  - Identified current limitations: no node expansion, limited filtering, no path finding
  - Set performance targets: handle 10k+ nodes, <200ms expansion latency
  - Planned features: double-click expansion, context menus, filters, search, paths, clustering, export, analytics

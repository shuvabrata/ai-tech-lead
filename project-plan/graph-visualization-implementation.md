# Graph Visualization Implementation Plan

**Status**: Not Started  
**Created**: February 22, 2026  
**Related Phases**: Phase 6 (Graph Visualization UI) of main project roadmap

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

- [ ] **1.6 Implement Router**
  - File: `app/api/graph/v1/router.py`
  - Create `APIRouter` with prefix `/api/v1/graph`
  - POST endpoint `/query` accepting `CypherQueryRequest`
  - Call service layer
  - Return `GraphResponse` or `HTTPException`
  - Error codes: 400 (invalid query), 500 (Neo4j errors)
  - Include descriptive error messages

- [ ] **1.7 Register Router**
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

- [ ] **2.1 Create Graph Page**
  - File: `app/dash_app/pages/graph.py`
  - Create `get_layout()` function
  - Add header: "Graph Visualization"
  - Add `dbc.Textarea` with id `graph-query-input`:
    - rows=10
    - placeholder with example: `MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 25`
  - Add `dbc.Button` "Execute Query" with id `graph-execute-btn`
  - Add `dcc.Loading` wrapper with id `graph-loading`
  - Add `html.Div` with id `graph-results-container`
    - Initial empty state: "Enter a Cypher query above and click Execute to visualize results"
  - Add `dcc.Store` with id `graph-data-store`

- [ ] **2.2 Update Navigation**
  - File: `app/dash_app/pages/__init__.py`
    - Add import: `from . import graph` (if using explicit imports)
  - File: `app/dash_app/layout.py`
  - Import graph page: `from .pages import graph`
  - Add sidebar link: `dbc.NavLink("📊 Graph", href="/app/graph", active="exact", id="nav-graph")`
  - Insert after Progress link
  - Update `display_page()` callback:
    - Add condition: `if pathname == "/app/graph": return graph.get_layout()`

- [ ] **2.3 Implement Query Execution Callback**
  - File: `app/dash_app/pages/graph.py`
  - Add imports: `requests`, `dash.callback`, `Input`, `Output`, `State`, `os`
  - Create callback:
    - Output: `("graph-data-store", "data")`
    - Input: `("graph-execute-btn", "n_clicks")`
    - State: `("graph-query-input", "value")`
  - Validate textarea not empty
  - Get API base URL: `os.getenv('API_BASE_URL', 'http://localhost:8000')` (follow chat.py pattern)
  - POST to `{api_base}/api/v1/graph/query`
  - Timeout: 30 seconds
  - Return success data or error dict

### Verification
- Navigate to http://localhost:8000/app/graph
- Verify tab appears in sidebar
- Enter query: `MATCH (n) RETURN n LIMIT 5`
- Click "Execute Query"
- Check browser console for API response
- Verify data stored in dcc.Store

---

## Phase 3: Graph Visualization with Dash Cytoscape

### Objectives
- Install and configure dash-cytoscape
- Transform Neo4j data to Cytoscape format
- Render interactive graph visualization

### Tasks

- [ ] **3.1 Add Dependency**
  - File: `requirements.txt`
  - Add: `dash-cytoscape>=0.3.0`
  - Run: `pip install dash-cytoscape`

- [ ] **3.2 Create Graph Renderer**
  - File: `app/dash_app/pages/graph.py`
  - Import: `import dash_cytoscape as cyto`
  - Update `get_layout()`:
    - Replace `graph-results-container` with dual display:
      - `cyto.Cytoscape` with id `graph-cytoscape`
      - `html.Div` with id `graph-table-container`
    - Cytoscape config:
      - layout: `{'name': 'cose'}`
      - style: `{'width': '100%', 'height': '600px'}`
      - stylesheet: Basic node/edge styling

- [ ] **3.3 Data Transformation Function**
  - File: `app/dash_app/pages/graph.py`
  - Function: `neo4j_to_cytoscape(graph_response: Dict) -> List[Dict]`
  - Transform nodes:
    ```python
    {'data': {'id': node['id'], 'label': node['labels'][0], **node['properties']}}
    ```
  - Transform relationships:
    ```python
    {'data': {'source': rel['startNode'], 'target': rel['endNode'], 'label': rel['type']}}
    ```
  - Return elements list

- [ ] **3.4 Display Callback**
  - File: `app/dash_app/pages/graph.py`
  - Create callback:
    - Outputs: `("graph-cytoscape", "elements")`, `("graph-table-container", "children")`
    - Input: `("graph-data-store", "data")`
  - Logic:
    - If `data['isGraph']`: render graph, hide table
    - If not: hide graph, render `dbc.Table` from `rawResults`
    - Handle errors with `dbc.Alert`

### Verification
- Execute node query: `MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 10`
- Verify graph renders with nodes and edges
- Execute tabular query: `MATCH (n) RETURN n.name as name, n.status as status LIMIT 10`
- Verify table displays
- Test with empty results

---

## Phase 4: Graph Interactivity & Styling

### Objectives
- Enhanced visual styling
- Node/edge interaction
- Layout controls
- Zoom and pan functionality

### Tasks

- [ ] **4.1 Enhanced Cytoscape Styling**
  - File: `app/dash_app/pages/graph.py`
  - Update stylesheet in Cytoscape component:
    - Node colors by label (Person, Project, Issue, Repository, etc.)
    - Node labels showing `name` or `title` property
    - Edge arrows and type labels
    - Hover effects (opacity, border)
    - Selected state highlighting

- [ ] **4.2 Property Details Panel**
  - File: `app/dash_app/pages/graph.py`
  - Add `html.Div` with id `graph-details-panel` (sidebar or modal)
  - Create callback:
    - Output: `("graph-details-panel", "children")`
    - Input: `("graph-cytoscape", "tapNodeData")` or `("graph-cytoscape", "tapEdgeData")`
  - Display properties as formatted JSON or `dbc.Table`

- [ ] **4.3 Layout Controls**
  - File: `app/dash_app/pages/graph.py`
  - Add `dbc.RadioItems` or `dbc.Select` with id `graph-layout-selector`
  - Options: cose, circle, grid, breadthfirst, concentric
  - Create callback:
    - Output: `("graph-cytoscape", "layout")`
    - Input: `("graph-layout-selector", "value")`

- [ ] **4.4 Zoom/Pan Controls**
  - File: `app/dash_app/pages/graph.py`
  - Enable in Cytoscape: `userZoomingEnabled=True`, `userPanningEnabled=True`
  - Add buttons:
    - "Reset View" - triggers stylesheet update to reset
    - "Fit to Screen" - uses Cytoscape fit method
  - Add callback for button actions

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

- [ ] **5.1 Query Validation Feedback**
  - File: `app/dash_app/pages/graph.py`
  - Add `html.Div` with id `query-validation-message` below textarea
  - Create callback for real-time validation (on input change)
  - Show `dbc.Alert` with severity level (warning, danger)
  - Example messages:
    - "Query must start with MATCH or RETURN"
    - "Write operations (CREATE, DELETE) are not allowed"

- [ ] **5.2 Example Queries**
  - File: `app/dash_app/pages/graph.py`
  - Add `dbc.Accordion` with example queries:
    - "Show all people and their projects"
    - "Find project dependencies"
    - "Show recent issues"
    - "Find shortest path between nodes"
  - Each example has click/copy button
  - Callback to populate textarea on click

- [ ] **5.3 Query History**
  - File: `app/dash_app/pages/graph.py`
  - Add `dcc.Store` with id `query-history-store`, `storage_type='local'`
  - Add `dbc.Select` showing last 10 queries
  - Save on successful execution
  - Callback to reload previous query

- [ ] **5.4 Performance Optimization**
  - Add result count indicator in UI
  - Add warning for queries without LIMIT clause
  - Suggest max LIMIT of 100 for graph queries
  - Optional: Backend caching for repeated queries

- [ ] **5.5 Error Handling Polish**
  - User-friendly error messages:
    - Connection errors: "Unable to connect to Neo4j. Please check configuration."
    - Syntax errors: Show Neo4j error with helpful hint
    - Timeout: "Query took too long. Try adding LIMIT clause."
  - Add link to Neo4j Cypher documentation
  - Color-coded error types

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
- `dash-cytoscape>=0.3.0`

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
- Full API endpoint flow (pending Phase 1.6)
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

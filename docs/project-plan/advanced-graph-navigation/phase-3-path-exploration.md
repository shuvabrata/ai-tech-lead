# Phase 3: Path Exploration & Pattern Detection

[← Back to Overview](README.md) | [Previous: Phase 2 ←](phase-2-filtering-search.md) | [Next: Phase 4 →](phase-4-performance.md)

---

## Phase Overview

**Goal**: Discover connections and patterns  
**Timeline**: 3-4 weeks  
**Priority**: High (P1)  
**Status**: Planned ⏳ (Not Started)

**⚠️ PRE-PHASE REVIEW REQUIRED**: Review and answer **Q11-Q14** (Path Finding Features) before starting Phase 3

---

## Pre-Phase Decision Review

**Status**: 0 questions answered ✅, 4 questions pending ❓

### ❓ **Q11. Path Finding Algorithm Selection**
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

### ❓ **Q12. Path Visualization Strategy**
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

### ❓ **Q13. Pattern Detection Approach**
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

### ❓ **Q14. Pattern Result Grouping**
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

## 3.1 Path Finding

**Objective**: Find paths between two nodes

### Backend Tasks
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

### Frontend Tasks
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

## 3.2 Pattern Detection

**Objective**: Find recurring subgraph patterns

### Backend Tasks
- [ ] **3.2.1 Pattern Matching Endpoint**
  - Endpoint: `POST /api/v1/graph/pattern/match`
  - Request: Pattern as Cypher MATCH clause or visual template
  - Example: "Find all triangles: (a)-[:KNOWS]->(b)-[:KNOWS]->(c)-[:KNOWS]->(a)"
  - Response: All matching subgraphs

- [ ] **3.2.2 Motif Detection**
  - Common patterns: Triangles, stars, chains, cliques
  - Algorithms: Subgraph isomorphism
  - Performance: Limit to subgraphs of size ≤10 nodes

### Frontend Tasks
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

## 3.3 Neighborhood Exploration

**Objective**: Explore node neighborhoods at various depths

### Tasks
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

## Related Changelog Entries

_No changelog entries yet for Phase 3._

---

[← Back to Overview](README.md) | [Previous: Phase 2 ←](phase-2-filtering-search.md) | [Next: Phase 4 →](phase-4-performance.md)

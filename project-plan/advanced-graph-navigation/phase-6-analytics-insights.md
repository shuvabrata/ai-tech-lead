# Phase 6: Analytics & Insights

[← Back to Overview](README.md) | [Previous: Phase 5 ←](phase-5-collaboration-export.md)

---

## Phase Overview

**Goal**: Discover graph metrics and insights  
**Timeline**: 3-4 weeks  
**Priority**: Low (P3)  
**Status**: Planned ⏳ (Not Started)

**⚠️ PRE-PHASE REVIEW REQUIRED**: Review and answer **Q22-Q24** (Analytics Priority) before starting Phase 6

---

## Pre-Phase Decision Review

**Status**: 0 questions answered ✅, 3 questions pending ❓

### ❓ **Q22. Centrality Metrics Priority**
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

### ❓ **Q23. Metrics Visualization Approach**
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

### ❓ **Q24. Temporal Analysis Scope**
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

## 6.1 Graph Metrics

### Backend Tasks
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

### Frontend Tasks
- [ ] **6.1.3 Metrics Panel**
  - Show graph statistics
  - Visualize metrics as bar charts, histograms
  - Color-code nodes by centrality (heatmap)

---

## 6.2 Temporal Analysis

### Tasks
- [ ] **6.2.1 Time Slider**
  - Filter graph by time range (if nodes/edges have timestamps)
  - Animate graph evolution over time
  - Playback controls: Play, pause, speed

- [ ] **6.2.2 Temporal Patterns**
  - Detect trending patterns
  - Show growth/decay of node types over time

---

## 6.3 Anomaly Detection

### Tasks
- [ ] **6.3.1 Outlier Detection**
  - Highlight nodes with unusual properties (e.g., very high degree)
  - Detect disconnected components
  - Flag suspicious patterns (fraud detection use case)

---

## Related Changelog Entries

_No changelog entries yet for Phase 6._

---

[← Back to Overview](README.md) | [Previous: Phase 5 ←](phase-5-collaboration-export.md)

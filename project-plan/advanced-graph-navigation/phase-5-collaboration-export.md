# Phase 5: Collaboration & Export

[← Back to Overview](README.md) | [Previous: Phase 4 ←](phase-4-performance.md) | [Next: Phase 6 →](phase-6-analytics-insights.md)

---

## Phase Overview

**Goal**: Share and export graph views  
**Timeline**: 2 weeks  
**Priority**: Medium (P2)  
**Status**: Planned ⏳ (Not Started)

**⚠️ PRE-PHASE REVIEW REQUIRED**: Review and answer **Q19-Q21** (Export & Collaboration) before starting Phase 5

---

## Pre-Phase Decision Review

**Status**: 0 questions answered ✅, 3 questions pending ❓

### ❓ **Q19. Export Format Priorities**
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

### ❓ **Q20. View State Serialization Approach**
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

### ❓ **Q21. Saved Views Storage Strategy**
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

## 5.1 Export Capabilities

### Tasks
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

## 5.2 Shareable Views

### Tasks
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

## 5.3 Annotations & Comments

### Tasks
- [ ] **5.3.1 Node Annotations**
  - Add text notes to nodes
  - Pin notes to graph (visible to all viewers)
  - Edit/delete annotations

- [ ] **5.3.2 Annotation UI**
  - Right-click → "Add Note"
  - Note editor: Markdown support
  - Notes panel: List all annotations

---

## Related Changelog Entries

_No changelog entries yet for Phase 5._

---

[← Back to Overview](README.md) | [Previous: Phase 4 ←](phase-4-performance.md) | [Next: Phase 6 →](phase-6-analytics-insights.md)

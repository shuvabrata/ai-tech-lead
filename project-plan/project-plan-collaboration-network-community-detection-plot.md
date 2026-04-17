# Project Plan: Collaboration Network & Community Detection Plot

## Overview
This document outlines the strategy for building an interactive **Collaboration Network** combined with **Community Detection** on top of our Neo4j Enterprise Graph. 

Instead of relying on the official org chart (`REPORTS_TO` / `MANAGES`), this visualization will analyze the *actual* interactions in the graph (e.g., who reviews whose code, who works on the same Jira issues) to discover the organic, de-facto teams in the organization.

---

## ⏸️ Current Status & Next Steps (Paused Here)

### What's Complete
*   **Step 1 ✅** — 6-scenario Cypher query (`app/analytics/collaboration/queries/collaboration_score.cypher`) extracts collaboration scores for all person-pairs active in the last 90 days. Handles Neo4j 5.x `elementId` syntax and bot-filtering. `test_runner.py` validates the query against live Neo4j.
*   **Step 2 ✅** — Full backend pipeline is working and tested against live data (428 people, 1254 pairs, 10 communities, modularity ≈ 0.587):
    *   `app/analytics/collaboration/algorithm.py` — builds NetworkX graph, runs Louvain, assigns `community_id` and `hub_score`, returns Cytoscape element dicts.
    *   Collaboration layout positions are now generated server-side per community (deterministic preset coordinates with separated community centroids).
    *   Community centroid spacing is configurable (`community_gap_x`, `community_gap_y`) instead of hard-coded.
    *   `app/analytics/collaboration/config.py` includes and validates community gap defaults/ranges, and exposes them in config summary.
    *   `app/analytics/collaboration/tune.py` — CLI tool for weight tuning (see *Tuning* section below).
    *   `app/api/graph/v1/router.py` — `GET /api/v1/graph/collaboration-network` endpoint.
    *   `app/api/graph/v1/service.py` — `get_collaboration_network()` service function now passes configured community gaps into Cytoscape element generation.
    *   `app/api/graph/v1/model.py` — `CollaborationNetworkResponse` Pydantic model with `elements`, `num_people`, `num_pairs`, `num_communities`, `modularity`.
    *   `networkx` and `python-louvain` added to `requirements.txt`.
*   **Step 3 ✅** — Dash UI is wired and functional:
  *   `app/dash_app/pages/graph/callbacks/collaboration.py` — `load_collaboration_network` callback fires when the graph page is opened in collaboration analytics mode (canonical route: `?mode=collaboration_network`), fetches the API, and populates the Cytoscape graph with community-coloured elements. Uses `prevent_initial_call='initial_duplicate'` to fire correctly on both page load and navigation.
    *   Collaboration mode now explicitly uses Cytoscape `preset` layout (from server-provided positions).
    *   Non-collaboration graph mode restores selector-driven generic layout behavior (no change to generic plotting).
    *   Callback parses `community_gap_x` / `community_gap_y` from query params and forwards them into config.
    *   `app/dash_app/pages/graph/callbacks/__init__.py` — callback registered.
    *   `app/dash_app/pages/graph/styles.py` — 20 `.community-N` CSS rules in `CYTOSCAPE_STYLESHEET` for Louvain community colouring (increased from 10; colours ordered for maximum contrast at low community counts).
    *   `app/dash_app/pages/graph/layout.py` — `collaboration-banner` div added at top of page (hidden in normal mode, shows network stats in collaboration mode).
  *   `app/dash_app/layout.py` + `app/dash_app/pages/analytics.py` — pre-built graph analytics are launched from a single Analytics gallery page rather than separate sidebar links.
    *   The graph loads, renders, and community colours are visible.
    *   Analytics options now include configurable `Community Gap X` and `Community Gap Y` controls.
    *   A helper tip was added to guide practical gap ranges for dense networks.
*   **Step 4 ✅** — Scalable Analytics navigation foundation is implemented:
    *   `app/analytics/registry.py` defines the analytics registry (single source of truth for graph analytics metadata and route key).
    *   `app/dash_app/pages/analytics.py` provides the Analytics gallery page with launch cards.
    *   `app/dash_app/layout.py` now exposes a single **Analytics** sidebar link and routes `/app/analytics` to the gallery page.
    *   Analytics cards navigate to the generic graph page using query-string routing (`/app/graph?mode=<analytic-key>`).
    *   `app/dash_app/pages/graph/callbacks/analytics_mode.py` hides the Cypher query panel whenever graph analytics mode is active.
    *   Collaboration loader supports the canonical mode key (`collaboration_network`) and legacy compatibility (`collaboration`).
*   **Bug fix ✅** — `num_communities` and modularity returned by the API were inaccurate when Louvain detected more than 10 communities, because community IDs were clamped before analytics. Fix: `detect_communities()` now returns raw Louvain IDs; clamping to `[0, MAX_COMMUNITY_STYLES - 1]` for the CSS class name happens only inside `to_cytoscape_elements()`. `MAX_COMMUNITY_STYLES` raised to 20.
*   **Variable node size ✅** — `hub_score` is now mapped to Cytoscape node size via a pre-compute pipeline:
    *   `app/common/node_size.py` — new shared module (`BASE_NODE_SIZES` dict + `apply_node_size()`) placed in `app/common/` to avoid a circular import between the analytics and Dash layers.
    *   `algorithm.py` — log-normalizes hub scores to a `_node_size` multiplier in `[0.25, 2.0]` (using `log(score + 1)` to compress outliers), then calls `apply_node_size()` to write `_render_size_px` onto each node element.
    *   `styles.py` — added `node[_render_size_px]` Cytoscape selector that sets `width`/`height` from the pre-computed pixel value; added `edge.collaboration-edge` selector to suppress directional arrows (collaboration scores are symmetric).
    *   `data_transform.py` — calls `apply_node_size()` in `neo4j_to_cytoscape()` so the mechanism is also available for the generic graph (no-op when `_node_size` is absent).

### Known Issues (To Address in Next Session)
1. **Intra-community density still possible** — Inter-community overlap is now controllable via configurable gaps, but very dense communities can still look busy internally. Keep tuning `top_n_edges_per_node` and optionally node radius/ring spacing for large clusters.
2. **Person node shape** — `octagon` is the current shape. `ellipse` or `round-rectangle` would be more readable at high node density.
3. **Analytics onboarding workflow** — Document and standardize the plug-in checklist for adding a new graph analytic (registry entry, loader callback, service/query implementation, tests).

### Next Step (Start Here)
Finalize readability improvements inside dense communities (top-N defaults and optional ring-spacing tuning). In parallel, finalize a short onboarding checklist for adding new analytics via the registry pattern.

### Tuning the Weights (CLI Tool)
Before wiring up the UI, use the CLI tool to validate that the weights produce meaningful community structure:

```bash
# From project root with venv active
python -m app.analytics.collaboration.tune

# With full community member lists
python -m app.analytics.collaboration.tune --verbose
```

The report prints:
1. **Graph Statistics** — node/edge counts, density, and hairball warning if density > 0.4
2. **Community Detection** — number of communities and modularity score (>0.3 = meaningful)
3. **Community Size Distribution** — bar chart of sizes, singleton warning
4. **Top Hubs** — top 15 people by weighted degree (the "glue people")

Tune the `Weight` multipliers in `queries/collaboration_score.cypher` until modularity is >0.3 and community count is between 2 and 20.

---

## Spec
The o/p of the command,
```
CALL db.schema.visualization()
```
is

```
╒══════════════════════════════════════════════════════════════════════╤══════════════════════════════════════════════════════════════════════╕
│nodes                                                                 │relationships                                                         │
╞══════════════════════════════════════════════════════════════════════╪══════════════════════════════════════════════════════════════════════╡
│[(:IdentityMapping {name: "IdentityMapping",indexes: [],constraints: [│[[:MODIFIED_BY {name: "MODIFIED_BY"}], [:MEMBER_OF {name: "MEMBER_OF"}│
│"Constraint( id=10, name='identity_id', type='UNIQUENESS', schema=(:Id│], [:INCLUDED_IN {name: "INCLUDED_IN"}], [:IN_SPRINT {name: "IN_SPRINT│
│entityMapping {id}), ownedIndex=9 )"]}), (:Issue {name: "Issue",indexe│"}], [:FROM {name: "FROM"}], [:MANAGED_BY {name: "MANAGED_BY"}], [:CON│
│s: [],constraints: ["Constraint( id=18, name='issue_id', type='UNIQUEN│TAINS {name: "CONTAINS"}], [:CONTAINS {name: "CONTAINS"}], [:CONTAINS │
│ESS', schema=(:Issue {id}), ownedIndex=17 )"]}), (:Epic {name: "Epic",│{name: "CONTAINS"}], [:CONTAINS {name: "CONTAINS"}], [:CONTAINS {name:│
│indexes: [],constraints: ["Constraint( id=16, name='epic_id', type='UN│ "CONTAINS"}], [:CONTAINS {name: "CONTAINS"}], [:CONTAINS {name: "CONT│
│IQUENESS', schema=(:Epic {id}), ownedIndex=15 )"]}), (:PullRequest {na│AINS"}], [:CONTAINS {name: "CONTAINS"}], [:CONTAINS {name: "CONTAINS"}│
│me: "PullRequest",indexes: [],constraints: ["Constraint( id=32, name='│], [:CONTAINS {name: "CONTAINS"}], [:CONTAINS {name: "CONTAINS"}], [:C│
│pull_request_id', type='UNIQUENESS', schema=(:PullRequest {id}), owned│ONTAINS {name: "CONTAINS"}], [:CONTAINS {name: "CONTAINS"}], [:CONTAIN│
│Index=31 )"]}), (:Initiative {name: "Initiative",indexes: [],constrain│S {name: "CONTAINS"}], [:CONTAINS {name: "CONTAINS"}], [:CONTAINS {nam│
│ts: ["Constraint( id=14, name='initiative_id', type='UNIQUENESS', sche│e: "CONTAINS"}], [:CONTAINS {name: "CONTAINS"}], [:CONTAINS {name: "CO│
│ma=(:Initiative {id}), ownedIndex=13 )"]}), (:Project {name: "Project"│NTAINS"}], [:CONTAINS {name: "CONTAINS"}], [:CONTAINS {name: "CONTAINS│
│,indexes: [],constraints: ["Constraint( id=12, name='project_id', type│"}], [:BLOCKED_BY {name: "BLOCKED_BY"}], [:INCLUDES {name: "INCLUDES"}│
│='UNIQUENESS', schema=(:Project {id}), ownedIndex=11 )"]}), (:Reposito│], [:REPORTS_TO {name: "REPORTS_TO"}], [:MERGED_BY {name: "MERGED_BY"}│
│ry {name: "Repository",indexes: [],constraints: ["Constraint( id=22, n│], [:RELATES_TO {name: "RELATES_TO"}], [:CREATED {name: "CREATED"}], [│
│ame='repository_id', type='UNIQUENESS', schema=(:Repository {id}), own│:DEPENDENCY_OF {name: "DEPENDENCY_OF"}], [:MAPS_TO {name: "MAPS_TO"}],│
│edIndex=21 )"]}), (:Commit {name: "Commit",indexes: [],constraints: ["│ [:MANAGES {name: "MANAGES"}], [:MANAGES {name: "MANAGES"}], [:CREATED│
│Constraint( id=28, name='commit_sha', type='UNIQUENESS', schema=(:Comm│_BY {name: "CREATED_BY"}], [:REVIEWED {name: "REVIEWED"}], [:REVIEW_RE│
│it {sha}), ownedIndex=27 )", "Constraint( id=26, name='commit_id', typ│QUESTED_BY {name: "REVIEW_REQUESTED_BY"}], [:TARGETED_BY {name: "TARGE│
│e='UNIQUENESS', schema=(:Commit {id}), ownedIndex=25 )"]}), (:Bug {nam│TED_BY"}], [:REQUESTED_REVIEWER {name: "REQUESTED_REVIEWER"}], [:DEPEN│
│e: "Bug",indexes: [],constraints: []}), (:Branch {name: "Branch",index│DS_ON {name: "DEPENDS_ON"}], [:ASSIGNED_TO {name: "ASSIGNED_TO"}], [:A│
│es: [],constraints: ["Constraint( id=24, name='branch_id', type='UNIQU│SSIGNED_TO {name: "ASSIGNED_TO"}], [:ASSIGNED_TO {name: "ASSIGNED_TO"}│
│ENESS', schema=(:Branch {id}), ownedIndex=23 )"]}), (:Team {name: "Tea│], [:PART_OF {name: "PART_OF"}], [:PART_OF {name: "PART_OF"}], [:PART_│
│m",indexes: [],constraints: ["Constraint( id=8, name='team_id', type='│OF {name: "PART_OF"}], [:PART_OF {name: "PART_OF"}], [:PART_OF {name: │
│UNIQUENESS', schema=(:Team {id}), ownedIndex=7 )"]}), (:Sprint {name: │"PART_OF"}], [:PART_OF {name: "PART_OF"}], [:PART_OF {name: "PART_OF"}│
│"Sprint",indexes: [],constraints: ["Constraint( id=20, name='sprint_id│], [:PART_OF {name: "PART_OF"}], [:PART_OF {name: "PART_OF"}], [:PART_│
│', type='UNIQUENESS', schema=(:Sprint {id}), ownedIndex=19 )"]}), (:Pe│OF {name: "PART_OF"}], [:PART_OF {name: "PART_OF"}], [:PART_OF {name: │
│rson {name: "Person",indexes: [],constraints: ["Constraint( id=4, name│"PART_OF"}], [:PART_OF {name: "PART_OF"}], [:PART_OF {name: "PART_OF"}│
│='person_id', type='UNIQUENESS', schema=(:Person {id}), ownedIndex=3 )│], [:PART_OF {name: "PART_OF"}], [:PART_OF {name: "PART_OF"}], [:REPOR│
│", "Constraint( id=6, name='person_email', type='UNIQUENESS', schema=(│TED_BY {name: "REPORTED_BY"}], [:REPORTED_BY {name: "REPORTED_BY"}], [│
│:Person {email}), ownedIndex=5 )"]}), (:File {name: "File",indexes: []│:MODIFIES {name: "MODIFIES"}], [:COLLABORATOR {name: "COLLABORATOR"}],│
│,constraints: ["Constraint( id=30, name='file_id', type='UNIQUENESS', │ [:COLLABORATOR {name: "COLLABORATOR"}], [:AUTHORED_BY {name: "AUTHORE│
│schema=(:File {id}), ownedIndex=29 )"]}), (:Story {name: "Story",index│D_BY"}], [:REFERENCED_BY {name: "REFERENCED_BY"}], [:REVIEWED_BY {name│
│es: [],constraints: []})]                                             │: "REVIEWED_BY"}], [:BRANCH_OF {name: "BRANCH_OF"}], [:BLOCKS {name: "│
│                                                                      │BLOCKS"}], [:TARGETS {name: "TARGETS"}], [:TEAM {name: "TEAM"}], [:MER│
│                                                                      │GED {name: "MERGED"}], [:REFERENCES {name: "REFERENCES"}]]            │
└──────────────────────────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────┘
```


## Step 1: Define "Working Closely" (Data Extraction)
First, we project a new, implicit relationship between `Person` nodes. We calculate a "Collaboration Score" based on how often two people intersect across Jira and GitHub.

### Cypher Query: Collaboration Score
This query independently finds recent pairs (last 90 days) from Jira interactions and GitHub interactions, then sums their weighted scores together:

```cypher
CALL () {
  // 1. Find Reporter-Assignee loops on Jira Issues (Weight: 2)
  MATCH (reporter:Person)-[:REPORTED_BY]-(work:Issue)-[:ASSIGNED_TO]-(assignee:Person)
  WHERE elementId(reporter) <> elementId(assignee) AND work.created_at >= datetime() - duration('P90D')
  WITH 
    CASE WHEN elementId(reporter) < elementId(assignee) THEN reporter ELSE assignee END AS p1,
    CASE WHEN elementId(reporter) < elementId(assignee) THEN assignee ELSE reporter END AS p2,
    work
  RETURN p1, p2, count(work) * 2 AS sub_score
  
  UNION ALL
  
  // 2. Find GitHub PR Reviews (Weight: 3)
  MATCH (reviewer:Person)<-[:REVIEWED_BY|REQUESTED_REVIEWER]-(pr:PullRequest)-[:CREATED_BY]->(author:Person)
  WHERE elementId(reviewer) <> elementId(author) AND pr.created_at >= datetime() - duration('P90D')
  WITH 
    CASE WHEN elementId(reviewer) < elementId(author) THEN reviewer ELSE author END AS p1,
    CASE WHEN elementId(reviewer) < elementId(author) THEN author ELSE reviewer END AS p2,
    pr
  RETURN p1, p2, count(pr) * 3 AS sub_score

  UNION ALL
  
  // 3. Find Shared Commits on same File (Weight: 5)
  MATCH (dev1:Person)<-[:AUTHORED_BY]-(c1:Commit)-[:MODIFIES]->(f:File)<-[:MODIFIES]-(c2:Commit)-[:AUTHORED_BY]->(dev2:Person)
  WHERE elementId(dev1) <> elementId(dev2) AND c1.created_at >= datetime() - duration('P90D') AND c2.created_at >= datetime() - duration('P90D')
    AND NOT f.name ENDS WITH '.json' AND NOT f.name ENDS WITH '.md' AND NOT f.name ENDS WITH '.lock'
  WITH CASE WHEN elementId(dev1) < elementId(dev2) THEN dev1 ELSE dev2 END AS p1,
       CASE WHEN elementId(dev1) < elementId(dev2) THEN dev2 ELSE dev1 END AS p2, f
  RETURN p1, p2, count(DISTINCT f) * 5 AS sub_score

  UNION ALL

  // 4. Find Sprint Co-workers (Weight: 2)
  // Captures pairs assigned to different issues within the exact same Sprint
  MATCH (dev1:Person)-[:ASSIGNED_TO]-(i1:Issue)-[:IN_SPRINT]->(s:Sprint)<-[:IN_SPRINT]-(i2:Issue)-[:ASSIGNED_TO]-(dev2:Person)
  WHERE elementId(dev1) < elementId(dev2) AND i1.created_at >= datetime() - duration('P90D') AND i2.created_at >= datetime() - duration('P90D')
  WITH dev1 AS p1, dev2 AS p2, s
  RETURN p1, p2, count(DISTINCT s) * 2 AS sub_score

  UNION ALL

  // 5. Find Explicit Review Requests (Bonus Weight: 2)
  // Gives extra points on top of general PR interactions when a review is actively requested
  MATCH (reviewer:Person)<-[:REQUESTED_REVIEWER]-(pr:PullRequest)-[:CREATED_BY]->(author:Person)
  WHERE elementId(reviewer) <> elementId(author) AND pr.created_at >= datetime() - duration('P90D')
  WITH CASE WHEN elementId(reviewer) < elementId(author) THEN reviewer ELSE author END AS p1,
       CASE WHEN elementId(reviewer) < elementId(author) THEN author ELSE reviewer END AS p2, pr
  RETURN p1, p2, count(pr) * 2 AS sub_score

  UNION ALL

  // 6. Find Epic Overlap (Weight: 1)
  // Weak but aggregate signal for people working under the same large initiative
  MATCH (dev1:Person)-[:ASSIGNED_TO]-(i1:Issue)-[:PART_OF]-(e:Epic)-[:PART_OF]-(i2:Issue)-[:ASSIGNED_TO]-(dev2:Person)
  WHERE elementId(dev1) < elementId(dev2) AND i1.created_at >= datetime() - duration('P90D') AND i2.created_at >= datetime() - duration('P90D')
  WITH dev1 AS p1, dev2 AS p2, e
  RETURN p1, p2, count(DISTINCT e) * 1 AS sub_score
}
// Sum the scores from all independent systems
WITH p1, p2, sum(sub_score) AS total_collaboration_score
WHERE total_collaboration_score > 0 
  AND NOT p1.name ENDS WITH '[bot]' 
  AND NOT p2.name ENDS WITH '[bot]'
RETURN p1.name AS person1, p2.name AS person2, total_collaboration_score
ORDER BY total_collaboration_score DESC
```
*(Note: Multipliers—like `* 3` for PR reviews—are applied because reviewing code is often a stronger indicator of close collaboration than simply being on the same Jira ticket. These weights can be tuned.)*

### Extensibility: Adding More Scenarios
This query architecture (`CALL { ... UNION ALL ... }`) is highly extensible. Because each collaboration scenario is isolated in its own block, you can easily add new signals without breaking existing logic or dealing with complex `OPTIONAL MATCH` chains.

To add a new scenario, add a new `UNION ALL` block following this 3-rule contract:
1. **Find the pair:** Match the two `Person` nodes interacting.
2. **Standardize order:** Use the `CASE WHEN id(a) < id(b)` trick so the final summation groups `[Alice, Bob]` and `[Bob, Alice]` together.
3. **Return sub_score:** Output `p1, p2, <calculated_weight> AS sub_score`.

---

## Step 2: Grouping into Teams (Community Detection)
Once we have the connections and their weights, we need an algorithm to group highly connected people together. 

**Implementation Options:**
1. **Outside the Database (Python/NetworkX) - *SELECTED***: Export the results of the Cypher query to the FastAPI service layer and use `NetworkX` and `python-louvain` to detect communities. This aligns perfectly with Phase 4 of our *Advanced Graph Navigation* roadmap and avoids adding a dependency on the Neo4j GDS enterprise plugin.
2. **Inside the Database (Neo4j GDS):** Running the Louvain Modularity algorithm directly via the Neo4j GDS plugin. Kept as a fallback if the graph scales beyond what NetworkX can process in memory.

---

## Step 3: Visualization Integration (Dash Cytoscape)
To ensure seamless integration with the existing Work Behavior Analytics AI platform, this feature will be built natively into the **Dash Cytoscape** environment (specifically aligning with the `app/dash_app/pages/graph` architecture).

**Why Dash Cytoscape?**
*   **Reusability:** Leverages our existing layout controls, zoom/pan functions, and the `CYTOSCAPE_STYLESHEET` defined in `styles.py`.
*   **Interactivity:** Allows users to double-click central hubs to expand them, or right-click organic team nodes to trigger the existing Context Menu.
*   **Architecture Alignment:** Keeps the entire stack in Python (FastAPI backend + Dash frontend) without needing external BI tools or raw HTML generation.

---

## Step 4: Visual Encodings (Making it Meaningful)
A generic network graph can easily become a visual "hairball." To make this chart highly insightful for leadership, we apply the following visual rules:

1. **Color (The "Groups"):** Color nodes based on their mathematically detected community. Implemented in Cytoscape via dynamic `classes` (e.g., `community-0`, `community-1`) mapped to distinct colors in the stylesheet.
   * *Insight:* Compare this to the official org chart. You might find a frontend and backend developer officially on different teams, but the algorithm colors them the same because they constantly collaborate.
2. **Node Size (The "Hubs"):** Proportional to `hub_score`, which is each person's **weighted degree** — the sum of all their collaboration scores across every edge they hold. Computed in `algorithm.py` as `dict(g.degree(weight="weight"))`. A person who reviews a lot of code, co-edits many files, and shares many sprints will have a large `hub_score` because each of those interactions adds weight to their edges. `hub_score` is log-normalized to a `_node_size` multiplier in `[0.25, 2.0]`, which is multiplied by the nodeType's base pixel size and written as `_render_size_px`; the Cytoscape stylesheet applies it via `node[_render_size_px]`.
   * *Insight:* Large nodes highlight the "Glue People" or "Knowledge Hubs." If such a person leaves the company, that structural team might fracture because they were the connective tissue bridging multiple sub-groups.
   * *Also drives layout:* Within each community cluster, nodes are sorted descending by `hub_score` before positions are assigned. The highest-scoring person is placed at the community centroid; others radiate outward in concentric rings.
3. **Edge Thickness (The "Bonds"):** Mapped to the `collaboration_score`. Implemented via Cytoscape `mapData(weight, min, max, minWidth, maxWidth)`.
   * *Insight:* Thick lines show strong pairings (e.g., pairs that always review each other's code). 
4. **Tooltips (The "Details"):** Contextual stats on hover.
   * Leverages the existing Details Panel (`app/dash_app/pages/graph/callbacks/display.py`) when a node or edge is clicked to show the Real Team Name, top repos, and PR counts.

---

## Appendix: Python + Dash Cytoscape Implementation Pattern
A conceptual implementation integrating NetworkX community detection with our Dash Cytoscape data transformation pipeline (`app/api/graph/v1/service.py`).

```python
import networkx as nx
import community.community_louvain as community_louvain # pip install python-louvain

def process_collaboration_network(records):
    """
    Processes Cypher query results into Cytoscape-compatible elements,
    injecting Louvain community IDs and hub scores.
    """
    # 1. Build the NetworkX Graph
    G = nx.Graph()
    for record in records:
        G.add_edge(record['person1'], record['person2'], weight=record['collaboration_score'])

    # 2. Detect Communities (find the organic teams)
    partition = community_louvain.best_partition(G, weight='weight')
    
    # Calculate degree for node sizing (hub score)
    degrees = dict(G.degree(weight='weight'))

    # 3. Transform to Cytoscape Elements
    elements = []
    for node in G.nodes():
        elements.append({
            'data': {
                'id': node,
                'label': node,
                'nodeType': 'Person',
                'community': partition[node],  # Passed to cytoscape style
                'hub_score': degrees[node]     # Passed to cytoscape size mapping
            },
            'classes': f'community-{partition[node]}' # Allows CSS-like color assignment
        })
        
    for source, target, data in G.edges(data=True):
        elements.append({
            'data': {
                'source': source,
                'target': target,
                'weight': data['weight']       # Passed to cytoscape width mapping
            }
        })
        
    return elements
```
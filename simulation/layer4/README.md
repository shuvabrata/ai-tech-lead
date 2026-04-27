# Layer 4: Jira Stories, Bugs & Tasks

This layer creates granular work items (stories, bugs, tasks) and sprints for tracking work execution.

## Overview

**Nodes Created:**
- 80 Issue nodes (60 Stories, 15 Bugs, 5 Tasks)
- 4 Sprint nodes (2-week sprints covering last 2 months)

**Relationships Created:**
- `PART_OF`: Issue → Epic (80 relationships)
- `ASSIGNED_TO`: Issue ↔ Person (undirected, 80 relationships)
- `REPORTED_BY`: Issue ↔ Person (undirected, 80 relationships)
- `IN_SPRINT`: Issue → Sprint (80 relationships)
- `BLOCKS`: Issue → Issue (dependencies)
- `DEPENDS_ON`: Issue → Issue (inverse of BLOCKS)
- `RELATES_TO`: Bug ↔ Story (undirected, 5 bugs linked to stories)

## Work Item Distribution

### By Type
- **Stories**: 60 distributed across 12 epics (4-8 per epic)
- **Bugs**: 15 total
  - 5 linked to stories (found during testing)
  - 10 standalone production bugs
- **Tasks**: 5 technical tasks (spikes, refactoring, documentation)

### By Status
- Done: ~40%
- In Progress: ~25%
- To Do: ~20%
- In Review: ~10%
- Blocked: ~5%

### By Priority
- Critical: ~10%
- High: ~30%
- Medium: ~45%
- Low: ~15%

## Sprints

| Sprint | Dates | Goal | Status |
|--------|-------|------|--------|
| Sprint 1 | Dec 9-20, 2025 | Platform infrastructure foundations | Completed |
| Sprint 2 | Dec 23 - Jan 3, 2026 | Customer portal authentication | Completed |
| Sprint 3 | Jan 6-17, 2026 | Data pipeline streaming components | Completed |
| Sprint 4 | Jan 20-31, 2026 | UI components and API integration | Active |

## Usage

### Prerequisites

**Layers 1-3 must be loaded first!** This layer references Person, Epic, and Team nodes.

### Step 1: Generate the Data

```bash
cd simulation/layer4
python generate_data.py
```

This creates `simulation/data/layer4_stories_bugs.json` with Issue and Sprint nodes.

### Step 2: Load into Neo4j (Incremental)

```bash
cd simulation/layer4
python load_to_neo4j.py
```

**Note:** This is an **incremental load** - it does NOT clear existing data.

### Step 3: Validate

The loader automatically runs validation queries. You can also explore in Neo4j Browser:

```cypher
// Sprint burndown data
MATCH (s:Sprint)<-[:IN_SPRINT]-(i:Issue)
RETURN s.name, 
       sum(i.story_points) as total_points,
       sum(CASE WHEN i.status = 'Done' THEN i.story_points ELSE 0 END) as completed_points,
       count(i) as issue_count
ORDER BY s.name

// Find blocked work
MATCH (blocked:Issue {status: 'Blocked'})-[:DEPENDS_ON]->(blocker:Issue)
RETURN blocked.key, blocked.summary, 
       collect(blocker.key) as blocking_issues

// Bug distribution by epic
MATCH (bug:Issue {type: 'Bug'})-[:PART_OF]->(e:Epic)
RETURN e.key, e.summary, count(bug) as bug_count
ORDER BY bug_count DESC

// Work by person
MATCH (i:Issue)-[:ASSIGNED_TO]-(p:Person)
RETURN p.name, p.title, 
       count(i) as total_issues,
       sum(i.story_points) as total_points
ORDER BY total_points DESC
LIMIT 10

// Unassigned critical issues
MATCH (i:Issue)
WHERE i.priority = 'Critical' AND NOT exists((i)-[:ASSIGNED_TO]-())
RETURN i.key, i.summary, i.status

// Bugs related to stories
MATCH (bug:Issue {type: 'Bug'})-[:RELATES_TO]-(story:Issue {type: 'Story'})
RETURN bug.key, story.key as story, bug.summary

// Dependencies and blockers
MATCH (i:Issue)-[:BLOCKS]->(blocked:Issue)
RETURN i.key, i.summary, 
       collect(blocked.key) as blocks_issues
```

## Data Structure

### Issue Node Properties
```json
{
  "id": "issue_plat_11",
  "key": "PLAT-11",
  "type": "Story",
  "summary": "Implement Kubernetes deployment component",
  "description": "Implement kubernetes deployment component as part of Migrate to Kubernetes",
  "priority": "High",
  "status": "Done",
  "story_points": 5,
  "created_at": "2025-12-15",
  "updated_at": "2025-12-15",
  "_last_synced_at": "2026-01-15T12:00:00+00:00"
}
```

### Sprint Node Properties
```json
{
  "id": "sprint_1",
  "name": "Sprint 1",
  "goal": "Platform infrastructure foundations",
  "start_date": "2025-12-09",
  "end_date": "2025-12-20",
  "status": "Completed"
}
```

## Assignment Model

**Assignees:**
- Stories: Team members from the epic's primary team
- Bugs: Engineers from relevant teams
- Tasks: Senior/Staff engineers

**Reporters:**
- Usually Product Managers or Staff engineers
- Bug reporters can be managers who discovered issues

**Sprint Assignment:**
- Done issues → Earlier sprints (Sprint 1-2)
- In Progress/In Review → Sprint 3
- To Do → Sprint 4 (current)
- Blocked → Sprint 2-3

## Realistic Patterns

- **Story Points**: Fibonacci sequence (1, 2, 3, 5, 8, 13)
- **Bug Discovery**: 5 bugs found during testing of completed stories
- **Dependencies**: Blocked issues have DEPENDS_ON relationships
- **Work Distribution**: Follows Pareto principle (80/20 rule)
- **Sprint Capacity**: Realistic point distribution across sprints

## Validation Checks

After loading, verify:

1. **Issue count**: Exactly 80 Issue nodes (60 stories + 15 bugs + 5 tasks)
2. **Sprint count**: Exactly 4 Sprint nodes
3. **All issues have epics**: Each Issue connected to an Epic via PART_OF
4. **All issues assigned**: Each Issue has ASSIGNED_TO and REPORTED_BY relationships
5. **All issues in sprints**: Each Issue has IN_SPRINT relationship
6. **Blocked issues have dependencies**: Blocked issues have DEPENDS_ON relationships
7. **Bug links**: 5 bugs have RELATES_TO relationships to stories
8. **Layers 1-3 preserved**: All previous nodes still exist

## Next Steps

Once Layer 4 is validated:

1. ✅ Work items created across all epics
2. ✅ Sprint structure established
3. ✅ Work dependencies mapped
4. ➡️ Proceed to **Layer 5: Git Repositories** to link code to work items

## Troubleshooting

**Issue**: "No Epic nodes found" or "No Person nodes found"
- Solution: Load Layers 1-3 first:
  ```bash
  cd simulation/layer1
  echo "yes" | python load_to_neo4j.py
  cd ../layer2
  python load_to_neo4j.py
  cd ../layer3
  python load_to_neo4j.py
  cd ../layer4
  python load_to_neo4j.py
  ```

**Issue**: Sprint assignment seems wrong
- Explanation: Sprint assignment based on issue status - Done issues go to early sprints, To Do to later sprints

**Issue**: Some issues have no story points
- Check: Tasks and bugs may have different point distributions than stories

## Files

- `generate_data.py` - Generates issue and sprint data
- `load_to_neo4j.py` - Incrementally loads data into Neo4j
- `README.md` - This file
- `../data/layer4_stories_bugs.json` - Generated data file

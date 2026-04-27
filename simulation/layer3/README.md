# Layer 3: Jira Epics

This layer breaks down high-level initiatives into actionable epics representing major work streams.

## Overview

**Nodes Created:**
- 12 Epic nodes distributed across 3 initiatives

**Relationships Created:**
- `PART_OF`: Epic → Initiative (12 relationships)
- `ASSIGNED_TO`: Epic ↔ Person (undirected, 12 relationships - epic owners from relevant teams)
- `TEAM`: Epic ↔ Team (undirected, 12 relationships - links epics to owning teams)

## Epics Distribution

### Platform Modernization (INIT-1) - 4 Epics
| Key | Summary | Team | Priority |
|-----|---------|------|----------|
| PLAT-1 | Migrate to Kubernetes | Platform | High |
| PLAT-2 | Implement Service Mesh | Platform | High |
| PLAT-3 | Observability Stack Upgrade | Platform | Medium |
| PLAT-4 | CI/CD Pipeline Rewrite | Platform | High |

### Customer Portal Rebuild (INIT-2) - 5 Epics
| Key | Summary | Team | Priority |
|-----|---------|------|----------|
| PORT-1 | Authentication & Authorization | API | Critical |
| PORT-2 | Dashboard UI Components | Frontend | High |
| PORT-3 | API Gateway Layer | API | High |
| PORT-4 | Mobile Responsive Design | Frontend | Medium |
| PORT-5 | Analytics Integration | Frontend | Medium |

### Data Pipeline v2 (INIT-3) - 3 Epics
| Key | Summary | Team | Priority |
|-----|---------|------|----------|
| DATA-1 | Streaming Architecture | Data | Critical |
| DATA-2 | Data Warehouse Migration | Data | High |
| DATA-3 | Real-time Analytics Engine | Data | High |

## Usage

### Prerequisites

**Layers 1 and 2 must be loaded first!** This layer references Person, Team, and Initiative nodes.

### Step 1: Generate the Data

```bash
cd simulation/layer3
python generate_data.py
```

This creates `simulation/data/layer3_epics.json` with Epic nodes and relationships.

### Step 2: Load into Neo4j (Incremental)

```bash
cd simulation/layer3
python load_to_neo4j.py
```

**Note:** This is an **incremental load** - it does NOT clear existing data. It adds to Layers 1 and 2.

### Step 3: Validate

The loader automatically runs validation queries. You can also explore in Neo4j Browser:

```cypher
// View all epics with owners and teams
MATCH (e:Epic)-[:ASSIGNED_TO]-(owner:Person)
MATCH (e)-[:TEAM]-(team:Team)
MATCH (e)-[:PART_OF]->(i:Initiative)
RETURN e.key, e.summary, 
       owner.name as owner, owner.title as owner_title,
       team.name as team,
       i.key as initiative,
       e.status, e.priority
ORDER BY i.key, e.key

// Epics by initiative
MATCH (e:Epic)-[:PART_OF]->(i:Initiative)
RETURN i.key, i.summary, collect(e.key) as epics
ORDER BY i.key

// Epic ownership distribution
MATCH (e:Epic)-[:ASSIGNED_TO]-(p:Person)
RETURN p.name, p.role, count(e) as epic_count
ORDER BY epic_count DESC

// Epics by team
MATCH (e:Epic)-[:TEAM]-(t:Team)
RETURN t.name, count(e) as epic_count, collect(e.key) as epics
ORDER BY epic_count DESC

// Epic timeline
MATCH (e:Epic)
RETURN e.key, e.summary, e.start_date, e.due_date, e.status
ORDER BY e.start_date, e.key
```

## Data Structure

### Epic Node Properties
```json
{
  "id": "epic_plat_1",
  "key": "PLAT-1",
  "summary": "Migrate to Kubernetes",
  "description": "Migrate existing services from VMs to Kubernetes clusters...",
  "priority": "High",
  "status": "In Progress",
  "start_date": "2026-01-01",
  "due_date": "2026-04-30",
  "created_at": "2025-11-15",
  "updated_at": "2025-11-15",
  "_last_synced_at": "2026-01-15T12:00:00+00:00"
}
```

## Epic Assignment Model

**Epic Owners (ASSIGNED_TO):**
- Senior/Staff Software Engineers from the epic's primary team
- Product Managers (can own epics across any team)

**Team Assignment (TEAM):**
- Each epic is assigned to exactly one primary team
- Assignment based on epic domain:
  - PLAT-* → Platform Team
  - PORT-1, PORT-3 → API Team
  - PORT-2, PORT-4, PORT-5 → Frontend Team
  - DATA-* → Data Team

**Timeline:**
- Epic dates are calculated based on parent initiative timeline
- Epics have overlapping timelines (work happens in parallel)
- Epic duration is longer than sequential slots to allow for parallelism

## Validation Checks

After loading, verify:

1. **Epic count**: Exactly 12 Epic nodes
2. **All epics have initiatives**: Each Epic connected to an Initiative via PART_OF
3. **All epics have owners**: Each Epic has an ASSIGNED_TO relationship to a Person
4. **All epics have teams**: Each Epic has a TEAM relationship to exactly one Team
5. **Distribution**: 4 epics for INIT-1, 5 for INIT-2, 3 for INIT-3
6. **Layers 1-2 preserved**: All Person, Team, Initiative, Project nodes still exist

## Next Steps

Once Layer 3 is validated:

1. ✅ Initiatives broken down into epics
2. ✅ Epic ownership and team assignments established
3. ➡️ Proceed to **Layer 4: Jira Stories & Bugs** to create granular work items

## Troubleshooting

**Issue**: "No Person nodes found" or "No Initiative nodes found"
- Solution: Load Layers 1 and 2 first:
  ```bash
  cd simulation/layer1
  echo "yes" | python load_to_neo4j.py
  cd ../layer2
  python load_to_neo4j.py
  cd ../layer3
  python load_to_neo4j.py
  ```

**Issue**: Script can't find data files
- Solution: Ensure both Layer 1 and Layer 2 data exist:
  - `simulation/data/layer1_people_teams.json`
  - `simulation/data/layer2_initiatives.json`

**Issue**: Epic owner not from correct team
- Explanation: PMs can own any epic. Senior/Staff engineers are preferred from the epic's team, but if none available, any Senior/Staff engineer may be assigned.

## Files

- `generate_data.py` - Generates epic data referencing Layers 1 and 2
- `load_to_neo4j.py` - Incrementally loads data into Neo4j
- `README.md` - This file
- `../data/layer3_epics.json` - Generated data file (created by generate_data.py)

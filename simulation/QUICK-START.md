# Quick Start Guide - Project Graph Simulation

This guide provides step-by-step instructions to set up and run the simulation from scratch.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.14 or higher
- Neo4j running (via Docker Compose)

## Initial Setup

### 1. Start Neo4j Database

```bash
# From project root
docker compose up -d
```

Verify Neo4j is running:
- Open http://localhost:7474 in your browser
- Login with username: `neo4j`, password: `password123`

### 2. Set Up Python Environment

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Loading Data Layer by Layer

### Layer 1: People & Teams (Foundation)

```bash
cd simulation/layer1
python generate_data.py
python load_to_neo4j.py
```

**What this creates:**
- 57 people (50 engineers, 5 managers, 2 PMs)
- 5 teams
- 114 identity mappings (GitHub + Jira)

### Layer 2: Jira Initiatives

```bash
cd ../layer2
python generate_data.py
python load_to_neo4j.py
```

**What this creates:**
- 1 project
- 3 high-level initiatives

### Layer 3: Jira Epics

```bash
cd ../layer3
python generate_data.py
python load_to_neo4j.py
```

**What this creates:**
- 12 epics across 3 initiatives

### Layer 4: Jira Stories & Bugs

```bash
cd ../layer4
python generate_data.py
python load_to_neo4j.py
```

**What this creates:**
- 80 issues (stories, bugs, tasks)
- 4 sprints

### Layer 5: Git Repositories

```bash
cd ../layer5
python generate_data.py
python load_to_neo4j.py
```

**What this creates:**
- 8 repositories
- Collaborator relationships (teams and people with READ/WRITE permissions)

### Layer 6: Git Branches

```bash
cd ../layer6
python generate_data.py
python load_to_neo4j.py
```

**What this creates:**
- 37 branches across 8 repositories
- 8 default branches (main)
- 29 feature branches (17 active, 12 deleted)

### Layer 7: Git Commits & Files

```bash
cd ../layer7
python generate_data.py
python load_to_neo4j.py
```

**What this creates:**
- 500 commits (default branches only)
- 286 files across repositories
- 2,488 relationships (PART_OF, AUTHORED_BY, MODIFIES, REFERENCES)
- 80% of commits reference Jira issues

### Layer 8: Pull Requests

```bash
cd ../layer8
python generate_data.py
python load_to_neo4j.py
```

**What this creates:**
- 100 pull requests (83 merged, 10 open, 7 closed)
- 1,033 relationships (INCLUDES, TARGETS, CREATED_BY, REVIEWED_BY, etc.)
- Complete review workflows with approvals and change requests

## Reload All Data from Scratch

To reload all data from scratch, use the provided script:

```bash
./reload_all_simulations.sh
```

This script will clear the database (via Layer 1) and reload all 8 layers sequentially.

## Verify Installation

### View Schema Visualization

To see the complete schema of your graph database with all node types and relationships:

```cypher
// Option 1: Visual graph structure (shows nodes and relationships)
CALL db.schema.visualization() 
or 
CALL apoc.meta.graph()

// Option 2: Detailed schema with properties
CALL db.schema.nodeTypeProperties()

// Option 3: Using APOC for comprehensive schema (if installed)
CALL apoc.meta.schema()
```

### Check Data in Neo4j Browser

Open http://localhost:7474 and try these queries:

```cypher
// Count all nodes by type
MATCH (n) RETURN labels(n)[0] as type, count(*) as count
ORDER BY count DESC

// View org structure
MATCH (p:Person)-[:MEMBER_OF]-(t:Team)
RETURN t.name, count(p) as team_size
ORDER BY team_size DESC

// View initiatives with epics
MATCH (i:Initiative)<-[:BELONGS_TO]-(e:Epic)
RETURN i.key, i.summary, count(e) as epics
ORDER BY epics DESC

// View repository ownership
MATCH (t:Team)-[c:COLLABORATOR {permission:'WRITE'}]-(r:Repository)
RETURN t.name, collect(r.name) as repos

// PR velocity by repository
MATCH (pr:PullRequest)-[:TARGETS]->(:Branch)-[:BRANCH_OF]-(r:Repository)
RETURN r.name as repo, 
       count(pr) as total_prs,
       sum(CASE WHEN pr.state = 'merged' THEN 1 ELSE 0 END) as merged
ORDER BY total_prs DESC

// End-to-end traceability: Initiative to PR
MATCH (i:Initiative)<-[:BELONGS_TO]-(e:Epic)<-[:BELONGS_TO]-(s:Story)
      <-[:BELONGS_TO]-(issue:Issue)<-[:REFERENCES]-(c:Commit)
      <-[:INCLUDES]-(pr:PullRequest)
RETURN i.key as initiative,
       e.title as epic,
       issue.key as jira_issue,
       pr.number as pr_number,
       pr.state as pr_state
LIMIT 5
```

## Common Issues

### Neo4j Connection Error

```
ModuleNotFoundError: No module named 'neo4j'
```
**Solution:** Make sure virtual environment is activated: `source .venv/bin/activate`

### Docker Not Running

```
Could not connect to bolt://localhost:7687
```
**Solution:** Start Neo4j with `docker compose up -d`

### Data Already Exists

```
Node already exists with id: person_xxx
```
**Solution:** Clear database by reloading Layer 1 (it clears all data first)

## Data Summary

After loading all 8 layers, your graph contains:

| Layer | Node Types | Count | Relationships |
|-------|-----------|-------|---------------|
| 1 | Person, Team | 62 | 114 (identities) + 50 (team membership) |
| 2 | Project, Initiative | 4 | 3 |
| 3 | Epic | 12 | 12 (initiative) + 12 (ownership) |
| 4 | Story, Bug, Issue, Sprint | 88 | 80 (epic) + 80 (sprint) + 72 (assigned) |
| 5 | Repository | 8 | 34 (collaborators) |
| 6 | Branch | 37 | 37 (branch_of) |
| 7 | Commit, File | 786 | 2,488 (PART_OF, AUTHORED_BY, MODIFIES, REFERENCES) |
| 8 | PullRequest | 100 | 1,033 (INCLUDES, TARGETS, CREATED_BY, REVIEWED_BY, etc.) |
| **Total** | **11 node types** | **~1,100 nodes** | **~3,900 relationships** |

## Next Steps

After loading all layers:

1. **Explore Documentation**
   - [graph-simulation.md](graph-simulation.md) - Complete layer design and relationships
   - Each layer's README - Specific queries and use cases
   - [design/high-level-design.md](../design/high-level-design.md) - Overall vision

2. **Run Analytics Queries**
   - Layer 7: Code hotspots, developer activity, commit patterns
   - Layer 8: PR velocity, review bottlenecks, collaboration networks
   - Cross-layer: Initiative delivery tracking, team productivity

3. **Try Sample Use Cases**
   - Track initiative progress from strategy to code
   - Identify review bottlenecks and overloaded developers
   - Analyze code ownership and repository activity
   - Measure team velocity and cycle times

## Useful Commands

```bash
# Check Neo4j logs
docker compose logs -f neo4j

# Stop Neo4j
docker compose down

# Remove all data (including volumes)
docker compose down -v

# Restart Neo4j
docker compose restart neo4j
```

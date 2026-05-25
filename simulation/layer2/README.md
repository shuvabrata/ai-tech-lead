# Layer 2: Jira Initiatives

This layer adds high-level business initiatives (Jira-like work items) that connect to people through their Jira identities.

## Files

- **`models.py`**: Convenience import from shared `../models.py`
  - `Project`, `Initiative` dataclasses
  - `merge_project()`, `merge_initiative()` - merge individual nodes
  - `get_jira_identity_id()` - helper to convert person_id to Jira identity ID
  
- **`generate_data.py`**: Simulation data generator (creates JSON file)
- **`load_to_neo4j.py`**: Incremental loader that reads JSON and loads into Neo4j

## What This Layer Creates

**Nodes:**
- 1 Project node: "Engineering 2026"
- 3 Initiative nodes representing major business objectives

**Relationships:**
- `PART_OF` ↔ `CONTAINS`: Initiative ↔ Project
- `ASSIGNED_TO` (undirected): Initiative ↔ IdentityMapping (Jira)
- `REPORTED_BY` (undirected): Initiative ↔ IdentityMapping (Jira)

## Key Design: IdentityMapping vs Person

**Important**: Initiatives link to **IdentityMapping (Jira)**, not Person directly.

```
Initiative -[:ASSIGNED_TO]- IdentityMapping(provider='Jira') -[:MAPS_TO]- Person
```

**Why?** This matches real-world Jira data where:
- Jira webhooks/APIs provide Jira account IDs
- People may have multiple Jira accounts
- Usernames can change without breaking relationships

## Data Classes

```python
@dataclass
class Project:
    id: str
    key: str
    name: str
    description: str
    start_date: str  # ISO format (YYYY-MM-DD)
    end_date: str
    status: str

@dataclass
class Initiative:
    id: str
    key: str
    summary: str
    description: str
    priority: str
    status: str
    created_at: str
    updated_at: str
    duedate: str
    _last_synced_at: str
    # Note: assignee_id and reporter_id are extracted for relationships, not stored
```

## Usage Patterns

### Pattern 1: Load Simulation Data

```python
from models import Initiative, Relationship, merge_initiative, get_jira_identity_id

with open('../data/layer2_initiatives.json') as f:
    data = json.load(f)

with driver.session() as session:
    for initiative_data in data['nodes']['initiatives']:
        # Extract relationship metadata
        assignee_person_id = initiative_data.pop('assignee_id')
        reporter_person_id = initiative_data.pop('reporter_id')
        
        initiative = Initiative(**initiative_data)
        
        # Create relationships to Jira identities
        relationships = []
        if assignee_person_id:
            jira_identity_id = get_jira_identity_id(assignee_person_id)
            relationships.append(Relationship(
                type="ASSIGNED_TO",
                from_id=initiative.id,
                to_id=jira_identity_id,
                from_type="Initiative",
                to_type="IdentityMapping"
            ))
        
        merge_initiative(session, initiative, relationships=relationships)
```

### Pattern 2: Real-time Jira Webhook

```python
@app.post("/webhooks/jira/initiative")
async def handle_jira_initiative(webhook: JiraWebhook):
    """Process Jira initiative webhook."""
    
    with driver.session() as session:
        # Look up Jira identity by Jira username
        query = """
        MATCH (i:IdentityMapping {provider: 'Jira', username: $jira_username})
        RETURN i.id as identity_id
        """
        result = session.run(query, jira_username=webhook.assignee.account_id)
        identity_id = result.single()['identity_id'] if result.peek() else None
        
        initiative = Initiative(
            id=f"initiative_{webhook.key.lower().replace('-', '_')}",
            key=webhook.key,
            summary=webhook.summary,
            ...
        )
        
        relationships = []
        if identity_id:
            relationships.append(Relationship(
                type="ASSIGNED_TO",
                from_id=initiative.id,
                to_id=identity_id,
                from_type="Initiative",
                to_type="IdentityMapping"
            ))
        
        merge_initiative(session, initiative, relationships=relationships)
```

### Pattern 3: Incremental Updates

```python
# Create initiative first
initiative = Initiative(...)
merge_initiative(session, initiative)

# Later: assign to someone
assignee_rel = Relationship(
    type="ASSIGNED_TO",
    from_id=initiative.id,
    to_id="identity_jira_person_alice",
    from_type="Initiative",
    to_type="IdentityMapping"
)
merge_relationship(session, assignee_rel)

# Even later: link to project
project_rel = Relationship(
    type="PART_OF",
    from_id=initiative.id,
    to_id="project_q1_2026",
    from_type="Initiative",
    to_type="Project"
)
merge_relationship(session, project_rel)
```

## Running the Simulation

### Prerequisites
Layer 1 must be loaded first (Person and IdentityMapping nodes must exist).

### Generate Data
```bash
cd simulation/layer2
python generate_data.py
```

### Load into Neo4j
```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=your_password

python load_to_neo4j.py
```

The loader:
1. Verifies Layer 1 data exists
2. Creates Layer 2 constraints (Project, Initiative)
3. Merges Project node
4. Merges Initiative nodes with relationships to Jira IdentityMapping
5. Creates PART_OF relationships

## Querying Examples

### Find initiatives assigned to a person

```cypher
// Through the Jira identity
MATCH (p:Person {name: 'Alice Johnson'})-[:MAPS_TO]-(jira:IdentityMapping {provider: 'Jira'})
      -[:ASSIGNED_TO]-(i:Initiative)
RETURN i.key, i.summary, i.status, i.priority
ORDER BY i.due_date
```

### All work for a person across tools

```cypher
MATCH (p:Person {name: 'Alice Johnson'})-[:MAPS_TO]-(identity:IdentityMapping)
OPTIONAL MATCH (identity)-[:ASSIGNED_TO]-(initiative:Initiative)
OPTIONAL MATCH (identity)-[:AUTHORED_BY]-(commit:Commit)
RETURN identity.provider,
       collect(DISTINCT initiative.key) as initiatives,
       count(DISTINCT commit) as commits
```

### Initiative timeline

```cypher
MATCH (i:Initiative)
RETURN i.key, i.summary, i.start_date, i.due_date, i.status
ORDER BY i.start_date
```

### Project breakdown

```cypher
MATCH (proj:Project)<-[:PART_OF]-(i:Initiative)
OPTIONAL MATCH (i)-[:ASSIGNED_TO]-(jira:IdentityMapping)-[:MAPS_TO]-(assignee:Person)
RETURN proj.name,
       collect({
         key: i.key,
         summary: i.summary,
         assignee: assignee.name,
         status: i.status
       }) as initiatives
```

## Helper Functions

### get_jira_identity_id()

Converts a `person_id` (used in simulation data) to the corresponding Jira IdentityMapping ID:

```python
from models import get_jira_identity_id

person_id = "person_john_doe"
jira_id = get_jira_identity_id(person_id)
# Returns: "identity_jira_person_john_doe"
```

This is needed because:
- Simulation JSON uses `person_id` for convenience
- But relationships must point to IdentityMapping nodes
- This function performs the ID transformation

## Architecture Notes

### Shared Models
All dataclasses and merge functions are in `../models.py` (shared across layers).

Layer 2's `models.py` simply imports and re-exports for convenience.

### MERGE vs CREATE
All operations use MERGE for idempotency:
- Safe to re-run the loader
- Updates existing nodes
- Creates missing nodes automatically

### Relationship Directionality
Directional pairs create reverse edges automatically:
- `PART_OF` creates reverse `CONTAINS`

Undirected relationships are stored once and queried without direction:
- `ASSIGNED_TO` uses `-[:ASSIGNED_TO]-`
- `REPORTED_BY` uses `-[:REPORTED_BY]-`

## Next Layer

**Layer 3**: Jira Epics (children of Initiatives)
- Epic nodes
- CHILD_OF relationships to Initiatives
- Continue building the Jira hierarchy

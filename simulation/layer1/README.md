# Layer 1: People & Teams Foundation

This layer provides the foundational data model for people, teams, and identity mappings.

## Files

- **`models.py`**: Data classes and utility functions for Neo4j operations
  - `Person`, `Team`, `IdentityMapping` dataclasses
  - `merge_person()`, `merge_team()`, `merge_identity_mapping()` - merge individual nodes
  - `merge_relationship()` - merge relationships with auto-creation of missing nodes
  - `create_constraints()` - create uniqueness constraints
  
- **`generate_data.py`**: Simulation data generator (creates JSON file)
- **`load_to_neo4j.py`**: Batch loader that reads JSON and loads into Neo4j
- **`example_usage.py`**: Examples of using the refactored utilities for real-world scenarios

## Architecture

### Data Classes

```python
@dataclass
class Person:
    id: str
    name: str
    email: str
    title: str
    role: str
    seniority: str
    hire_date: str  # ISO format
    is_manager: bool

@dataclass
class Team:
    id: str
    name: str
    target_size: int
    created_at: str  # ISO format

@dataclass
class IdentityMapping:
    id: str
    provider: str
    username: str
    email: str

@dataclass
class Relationship:
    type: str
    from_id: str
    to_id: str
    from_type: str
    to_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
```

### Utility Functions

#### Merge Individual Nodes

```python
from models import Person, merge_person

# Merge a person without relationships
person = Person(
    id="person_john_doe",
    name="John Doe",
    email="john.doe@company.com",
    title="Software Engineer",
    role="Engineer",
    seniority="Mid",
    hire_date="2024-01-15",
    is_manager=False
)

with driver.session() as session:
    merge_person(session, person)
```

#### Merge Nodes with Relationships

```python
from models import Person, Relationship, merge_person

# Merge a person with team relationship
person = Person(...)

member_rel = Relationship(
    type="MEMBER_OF",
    from_id=person.id,
    to_id="team_engineering",
    from_type="Person",
    to_type="Team"
)

with driver.session() as session:
    merge_person(session, person, relationships=[member_rel])
```

#### Add Relationships Later

```python
from models import Relationship, merge_relationship

# Create relationship between existing nodes
# If nodes don't exist, they will be auto-created
reports_rel = Relationship(
    type="REPORTS_TO",
    from_id="person_alice",
    to_id="person_bob",
    from_type="Person",
    to_type="Person"
)

with driver.session() as session:
    merge_relationship(session, reports_rel)
```

### Relationship Directionality

The utilities handle directionality automatically:

- `MEMBER_OF` (Person ↔ Team, undirected)
- `MAPS_TO` (IdentityMapping ↔ Person, undirected)
- `REPORTS_TO` → `MANAGES` (directional pair)
- `MANAGES` → `MANAGED_BY` (directional pair)

### Key Features

1. **MERGE instead of CREATE**: All operations use MERGE to handle duplicates gracefully
2. **Automatic reverse edges for directional pairs**: No need to create reverse relationships manually
3. **Auto-create missing nodes**: Relationships will create placeholder nodes if they don't exist
4. **Single-node operations**: Perfect for streaming data or API responses
5. **Flexible relationship handling**: Add relationships during node creation or separately

## Usage Patterns

### Pattern 1: Batch Processing (Simulation)

```python
# Load from JSON file (as in load_to_neo4j.py)
with open('data.json') as f:
    data = json.load(f)

with driver.session() as session:
    for person_data in data['nodes']['people']:
        person = Person(**person_data)
        merge_person(session, person)
```

### Pattern 2: Real-time API Integration

```python
# Process data as it arrives from an API
def handle_new_employee(employee_data):
    with driver.session() as session:
        person = Person(**employee_data)
        
        # Add team relationship if available
        if 'team_id' in employee_data:
            rel = Relationship(
                type="MEMBER_OF",
                from_id=person.id,
                to_id=employee_data['team_id'],
                from_type="Person",
                to_type="Team"
            )
            merge_person(session, person, relationships=[rel])
        else:
            merge_person(session, person)
```

### Pattern 3: Incremental Updates

```python
# Update person details and add relationships incrementally
with driver.session() as session:
    # Step 1: Add basic person info
    person = Person(...)
    merge_person(session, person)
    
    # Step 2: Later, add team assignment
    team_rel = Relationship(...)
    merge_relationship(session, team_rel)
    
    # Step 3: Even later, add manager relationship
    reports_rel = Relationship(...)
    merge_relationship(session, reports_rel)
```

## Running the Simulation

### Generate Data
```bash
python generate_data.py
```

This generates `../data/layer1_people_teams.json` containing all nodes and relationships.

**Note on Identity Mappings**: The generated JSON includes a `person_id` field in identity mappings to indicate which person they belong to. This field is NOT part of the `IdentityMapping` node - it's used during loading to create the `MAPS_TO` relationship. The loader extracts this field and creates the relationship automatically.

### Load into Neo4j
```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=your_password

python load_to_neo4j.py
```

The loader:
1. Creates constraints for unique IDs
2. Merges Person nodes
3. Merges Team nodes
4. Merges IdentityMapping nodes and creates MAPS_TO relationships
5. Creates remaining relationships (MEMBER_OF, REPORTS_TO, MANAGES)

### View Examples
```bash
python example_usage.py
```


This layer establishes the organizational structure that serves as the foundation for all subsequent layers.

## Overview

**Nodes Created:**
- 57 Person nodes (50 engineers, 5 managers, 2 product managers)
- 5 Team nodes
- 114 IdentityMapping nodes (GitHub and Jira for each person)

**Relationships Created:**
- `MEMBER_OF`: Person ↔ Team (undirected, 57 relationships)
- `REPORTS_TO`: Person → Person (52 relationships - engineers and PMs report to managers)
- `MANAGES`: Person → Team (5 relationships - each manager manages one team)
- `MAPS_TO`: IdentityMapping ↔ Person (undirected, 114 relationships)

## Team Structure

| Team | Size | Focus Area |
|------|------|------------|
| Platform Team | 12 | Infrastructure, DevOps, Security |
| API Team | 10 | Backend Services, Microservices |
| Frontend Team | 10 | Web UI, React, TypeScript |
| Mobile Team | 8 | iOS, Android, React Native |
| Data Team | 10 | Data Engineering, Analytics, ML |

## Engineer Distribution by Seniority

- **Junior Software Engineer**: 10 people
- **Software Engineer (Mid-level)**: 25 people
- **Senior Software Engineer**: 10 people
- **Staff Software Engineer**: 5 people
- **Engineering Managers**: 5 people
- **Product Managers**: 2 people

## Usage

### Step 1: Generate the Data

```bash
cd simulation/layer1
python generate_data.py
```

This creates `data/layer1_people_teams.json` with all the nodes and relationships.

### Step 2: Start Neo4j

Make sure your Neo4j instance is running:

```bash
docker compose up -d
```

### Step 3: Load into Neo4j

```bash
cd simulation/layer1
python load_to_neo4j.py
```

**⚠️ Warning:** This script will clear all existing data in your Neo4j database!

### Step 4: Validate

The loader automatically runs validation queries, but you can also explore in Neo4j Browser:

```cypher
// View all teams and their members
MATCH (t:Team)-[:MEMBER_OF]-(p:Person)
RETURN t.name, collect(p.name) as members

// View organizational hierarchy
MATCH (p:Person)-[:REPORTS_TO]->(m:Person)
RETURN p, m

// Find all identity mappings for a person
MATCH (p:Person {name: "Add a valid name here"})-[:MAPS_TO]-(i:IdentityMapping)
RETURN p.name, i.provider, i.username, i.email
```

## Data Quality Checks

After loading, verify:

1. **Total people count**: Should be exactly 57
2. **Team membership**: Each team should have its target size
3. **Reporting structure**: All engineers and PMs should report to someone
4. **Identity mappings**: Each person should have exactly 2 mappings (GitHub + Jira)
5. **Managers**: Each of 5 teams should have exactly 1 manager

## Generated Data Structure

### Person Node Properties
```json
{
  "id": "person_alex_smith",
  "name": "Alex Smith",
  "email": "alex.smith@company.com",
  "title": "Senior Software Engineer",
  "role": "Engineer",
  "seniority": "Senior",
  "hire_date": "2022-06-15",
  "is_manager": false
}
```

### Team Node Properties
```json
{
  "id": "team_platform_team",
  "name": "Platform Team",
  "target_size": 12,
  "created_at": "2024-01-01"
}
```

### IdentityMapping Node Properties
```json
{
  "id": "identity_github_person_alex_smith",
  "provider": "GitHub",
  "username": "alexs",
  "email": "alex.smith@company.com"
}
```

## Next Steps

Once Layer 1 is validated:

1. ✅ Organizational structure is established
2. ➡️ Proceed to **Layer 2: Jira Initiatives** to add high-level business goals
3. All future layers will reference these Person and Team nodes

## Troubleshooting

**Issue**: "Connection refused" when running loader
- Solution: Ensure Neo4j is running: `docker-compose up -d`

**Issue**: "Authentication failed"  
- Solution: Check `.env` file for correct NEO4J_USERNAME and NEO4J_PASSWORD

**Issue**: Script fails with missing module
- Solution: Install dependencies: `pip install neo4j`

**Issue**: Data already exists
- Solution: The loader will prompt to clear the database before loading

## Files

- `generate_data.py` - Generates synthetic people and team data
- `load_to_neo4j.py` - Loads data into Neo4j database
- `README.md` - This file
- `../../data/layer1_people_teams.json` - Generated data file (created by generate_data.py)

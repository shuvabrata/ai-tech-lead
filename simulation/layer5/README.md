# Layer 5: Git Repositories

This layer creates repository nodes with COLLABORATOR relationships to both teams and individuals.

## Overview

**Nodes Created:**
- 8 Repository nodes (across different teams and technology stacks)

**Relationships Created:**
- `COLLABORATOR`: Team ↔ Repository (undirected, with `permission` property: "READ" or "WRITE")
- `COLLABORATOR`: Person ↔ Repository (undirected, with `permission` property: "READ" or "WRITE")

## Repository Structure

| Repository | Language | Owning Team | Description |
|------------|----------|-------------|-------------|
| k8s-infrastructure | YAML | Platform Team | Kubernetes infrastructure configs |
| service-mesh | Go | Platform Team | Istio service mesh configuration |
| gateway | Python | API Team | API gateway with authentication |
| user-service | Python | API Team | User management microservice |
| order-service | Python | API Team | Order processing service |
| web-app | TypeScript | Frontend Team | React web application |
| ios-app | Swift | Mobile Team | iOS mobile application |
| streaming-pipeline | Python | Data Team | Kafka/Flink data pipeline |

## Permission Model

### WRITE Permission
- **Team Level**: Each repo has 1 team with WRITE access (the owning team)
- **Individual Level**: 2-3 senior/staff engineers from the owning team get individual WRITE access (maintainers)
- **Includes**: push, merge, admin access

### READ Permission
- **Team Level**: 0-2 other teams may have READ access (for cross-team dependencies)
- **Individual Level**: 3-5 people from teams with READ access get individual READ permission
- **Includes**: pull, clone, view-only access

## Usage

### Step 1: Generate the Data

```bash
cd simulation/layer5
python generate_data.py
```

This creates `../data/layer5_repositories.json` with all repositories and COLLABORATOR relationships.

### Step 2: Ensure Neo4j is Running

```bash
docker compose up -d
```

### Step 3: Load into Neo4j

```bash
cd simulation/layer5
python load_to_neo4j.py
```

**Note:** This is an incremental load. It adds to existing Layer 1-4 data.

### Step 4: Validate

The loader automatically runs validation queries. You can also explore in Neo4j Browser:

```cypher
// View all repositories with their owning teams (WRITE access)
MATCH (t:Team)-[c:COLLABORATOR {permission: 'WRITE'}]-(r:Repository)
RETURN t.name, r.name, r.language

// Find maintainers (people with WRITE access)
MATCH (p:Person)-[c:COLLABORATOR {permission: 'WRITE'}]-(r:Repository)
RETURN r.name, collect(p.name) as maintainers
ORDER BY r.name

// Cross-team collaborations (teams with READ access)
MATCH (t:Team)-[c:COLLABORATOR {permission: 'READ'}]-(r:Repository)
RETURN r.name, collect(t.name) as read_access_teams
ORDER BY r.name

// People working across multiple repos
MATCH (p:Person)-[c:COLLABORATOR]-(r:Repository)
WITH p, c.permission as perm, collect(r.name) as repos
WHERE size(repos) > 1
RETURN p.name, p.title, perm, repos, size(repos) as repo_count
ORDER BY repo_count DESC
```

## Data Quality Checks

After loading, verify:

1. **Total repository count**: Should be exactly 8
2. **WRITE access**: Each repo should have at least 1 team and 2-3 people with WRITE
3. **READ access**: Some repos should have cross-team READ access
4. **No orphans**: All repos must have at least one COLLABORATOR with WRITE permission
5. **Realistic distribution**: Senior/Staff engineers should be the primary maintainers

## Relationship Properties

### Team COLLABORATOR ↔ Repository (undirected)
```json
{
  "permission": "WRITE" | "READ",
  "granted_at": "2024-01-15"
}
```

For READ access, may also include:
```json
{
  "reason": "cross-team dependency"
}
```

### Person COLLABORATOR ↔ Repository (undirected)
```json
{
  "permission": "WRITE" | "READ",
  "granted_at": "2024-01-15"
}
```

For WRITE access (maintainers):
```json
{
  "role": "maintainer"
}
```

For READ access (occasional contributors):
```json
{
  "reason": "occasional contributor"
}
```

## Generated Data Structure

### Repository Node Properties
```json
{
  "id": "repo_k8s_infrastructure",
  "name": "k8s-infrastructure",
  "full_name": "company/k8s-infrastructure",
  "url": "https://github.com/company/k8s-infrastructure",
  "language": "YAML",
  "is_private": true,
  "description": "Kubernetes infrastructure and deployment configurations",
  "topics": ["kubernetes", "infrastructure", "devops", "k8s"],
  "created_at": "2024-01-15",
  "_last_synced_at": "2026-01-15T12:00:00+00:00"
}
```

### COLLABORATOR Relationship
```json
{
  "type": "COLLABORATOR",
  "from_id": "team_platform_team",
  "to_id": "repo_k8s_infrastructure",
  "from_type": "Team",
  "to_type": "Repository",
  "properties": {
    "permission": "WRITE",
    "granted_at": "2024-01-15"
  }
}
```

## Next Steps

With Layer 5 complete, you can now:

1. **Explore repository ownership patterns** across teams
2. **Identify cross-team dependencies** through READ access
3. **Proceed to Layer 6**: Git Branches (link branches to these repos)
4. **Continue building**: Layer 7 will link commits to repos through branches

## Key Insights from Simulated Data

After loading, you should be able to answer:
- Which teams own which repositories?
- Who are the maintainers (WRITE access) for each repo?
- Which teams need cross-team READ access?
- Which engineers contribute to multiple repositories?
- What technology stack does each team primarily use?

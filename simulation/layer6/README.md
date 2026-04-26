# Layer 6: Git Branches

This layer creates branch nodes representing Git branches in each repository.

## Overview

**Nodes Created:**
- ~40 Branch nodes (1 main branch + 3-5 feature branches per repository)

**Relationships Created:**
- `BRANCH_OF`: Branch ↔ Repository (undirected)

## Branch Types

### Default Branches
- One `main` branch per repository (8 total)
- Always protected
- Never deleted
- Most recent commits

### Feature Branches
- 3-5 per repository (~32 total)
- Naming pattern: `feature/EPIC-KEY-description` or `bugfix/EPIC-KEY-description`
- Mix of active and deleted (merged) branches
- Some stale branches (last commit > 30 days ago)

## Branch Properties

| Property | Type | Description |
|----------|------|-------------|
| id | string | Unique identifier |
| name | string | Branch name (e.g., "main", "feature/PLAT-1-k8s") |
| is_default | boolean | True for main/master branch |
| is_protected | boolean | Branch has protection rules |
| is_deleted | boolean | Branch was merged and deleted |
| last_commit_sha | string | SHA of most recent commit |
| last_commit_timestamp | datetime | When last commit was made |

**Note**: We do not track `created_at` for branches due to GitHub API limitations.
Finding the branch creation time requires iterating through all commits on the branch,
which takes minutes for long-lived branches. Use `last_commit_timestamp` instead.

## Usage

### Step 1: Generate the Data

```bash
cd simulation/layer6
python generate_data.py
```

This creates `../data/layer6_branches.json` with all branches and relationships.

### Step 2: Ensure Neo4j is Running

```bash
docker compose up -d
```

### Step 3: Load into Neo4j

```bash
cd simulation/layer6
python load_to_neo4j.py
```

**Note:** This is an incremental load. It adds to existing Layer 1-5 data.

### Step 4: Validate

The loader automatically runs validation queries. You can also explore in Neo4j Browser:

```cypher
// View all branches by repository
MATCH (b:Branch)-[:BRANCH_OF]-(r:Repository)
RETURN r.name, collect(b.name) as branches
ORDER BY r.name

// Find active feature branches
MATCH (b:Branch)-[:BRANCH_OF]-(r:Repository)
WHERE NOT b.is_default AND NOT b.is_deleted
RETURN r.name, b.name, b.last_commit_timestamp
ORDER BY b.last_commit_timestamp DESC

// Find stale branches (candidates for cleanup)
MATCH (b:Branch)
WHERE b.last_commit_timestamp < datetime() - duration({days: 30})
  AND NOT b.is_default
  AND NOT b.is_deleted
RETURN b.name, b.last_commit_timestamp,
       duration.between(b.last_commit_timestamp, datetime()).days as days_old
ORDER BY days_old DESC

// Branches linked to specific epic
MATCH (b:Branch)-[:BRANCH_OF]-(r:Repository)
WHERE b.name CONTAINS 'PLAT-1'
RETURN r.name, b.name, b.is_deleted

// Protected branches across all repos
MATCH (b:Branch)-[:BRANCH_OF]-(r:Repository)
WHERE b.is_protected
RETURN r.name, collect(b.name) as protected_branches
```

## Data Quality Checks

After loading, verify:

1. **Total branch count**: Should be ~40 branches
2. **Default branches**: Exactly 8 (one per repo)
3. **Protected branches**: All default branches should be protected
4. **Branch naming**: Feature branches follow pattern with Jira keys
5. **Deleted branches**: ~30% of feature branches should be deleted
6. **Stale branches**: Some branches should have commits > 30 days old

## Branch Naming Patterns

Feature branches follow Git Flow conventions:
- `feature/PLAT-1-implement-core-logic`
- `feature/PORT-2-add-api-endpoints`
- `bugfix/DATA-3-fix-memory-leak`

The Jira key is embedded in the branch name, allowing us to link branches to work items without explicit relationships (inferred from naming convention).

## Inferred Relationships (Layer 7)

The following will be inferred when Layer 7 (Commits) is added:
- **Branch creator**: First commit author on the branch
- **Merge relationships**: Via merge commits
- **Branch activity**: From commit timestamps
- **Contributors**: People who committed to the branch

## Next Steps

With Layer 6 complete, you can now:

1. **Identify stale branches** for cleanup
2. **Track branch naming conventions** linked to Jira
3. **Proceed to Layer 7**: Git Commits (the final layer)
4. **Analyze branching patterns** across teams and repos

## Key Insights from Simulated Data

After loading, you should be able to answer:
- How many active branches does each repository have?
- Which branches are stale and should be cleaned up?
- What percentage of branches follow the Jira naming convention?
- Which repositories have the most branch activity?
- Are all default branches properly protected?

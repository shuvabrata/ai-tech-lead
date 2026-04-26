# Neo4j Index Strategy

## Current State

The database currently has **only uniqueness constraints** which automatically create unique indexes on ID fields:
- `Person.id`, `Team.id`, `IdentityMapping.id`
- `Project.id`, `Initiative.id`, `Epic.id`, `Issue.id`, `Sprint.id`
- `Repository.id`, `Branch.id`
- `Commit.id`, `Commit.sha`, `File.id`
- `PullRequest.id`

**Problem**: These constraint-based indexes only help with ID lookups. All other property lookups (name, email, status, state, key, etc.) require full table scans, resulting in 100-1000x slower queries.

## Index Priority Strategy

The [create_indexes.py](simulation/create_indexes.py) script implements 87 indexes across 7 priority levels based on query patterns observed in the codebase.

### Priority 1: High-Impact Lookup Indexes (Critical) - 22 indexes

Properties frequently used in WHERE clauses and natural language queries:
- **Person**: name, email, role, title, seniority
- **Team**: name
- **IdentityMapping**: username, provider, email
- **Work Items**: Initiative.key, Epic.key, Issue.key
- **Git**: Repository (name, full_name, language), Branch.name, File (path, name, extension, language)
- **Pull Requests**: number, state

### Priority 2: Status and State Indexes (High) - 10 indexes

Essential for filtering queries:
- **Work Items**: Initiative.status, Epic.status, Issue (status, type), Sprint.status
- **Branch**: is_default, is_deleted, is_protected
- **File**: is_test
- **Pull Request**: mergeable_state

### Priority 3: Date/Time Indexes (Medium-High) - 17 indexes

Critical for timeline queries and trend analysis:
- **Person**: hire_date
- **Work Items**: start_date, due_date, created_at (for Initiatives, Epics, Issues, Sprints)
- **Git**: Repository.created_at, Branch.last_commit_timestamp, Commit.timestamp, File.created_at
- **Pull Request**: created_at, merged_at, updated_at, closed_at

### Priority 4: Composite Indexes (Medium) - 5 indexes

Common multi-property filter patterns:
- Person: (role, seniority)
- Issue: (type, status), (status, priority)
- Branch: (is_default, is_deleted)
- PullRequest: (state, created_at)

### Priority 5: Full-Text Search Indexes (Medium) - 5 indexes

Enable natural language search:
- Initiative, Epic, Issue: (summary, description)
- PullRequest: (title, description)
- Commit: message

### Priority 6: Range Indexes for Analytics (Low-Medium) - 11 indexes

Numeric metrics for aggregation:
- Issue: story_points
- Commit: additions, deletions, files_changed
- PullRequest: commits_count, additions, deletions, changed_files, comments, review_comments
- File: size

### Priority 7: Relationship Property Indexes (Low) - 2 indexes

Filter on relationship properties:
- COLLABORATOR.permission
- REVIEWED_BY.state

## Implementation

Run the index creation script after loading all data layers:

```bash
cd simulation
python create_indexes.py
```

The script will:
- Create all 87 indexes organized by priority
- Report progress for each index
- Handle already-existing indexes gracefully
- Provide a summary of created vs existing indexes

## Verification

Check created indexes in Neo4j:

```cypher
SHOW INDEXES;
```

Test index usage with PROFILE:

```cypher
PROFILE
MATCH (p:Person {name: "Alice Johnson"})-[:ASSIGNED_TO]-(i:Issue)
WHERE i.status = "In Progress"
RETURN i.key, i.summary;
```

The PROFILE output should show "Index Seek" operations instead of "Node By Label Scan".

## Expected Performance Improvements

| Query Type | Without Indexes | With Indexes | Improvement |
|-----------|----------------|--------------|-------------|
| Find person by name | O(n) scan | O(log n) | 100-1000x |
| Filter issues by status | O(n) scan | O(log n) | 100-1000x |
| Find PRs in date range | O(n) scan | O(log n) | 100-1000x |
| Search commit messages | Not possible | Full-text | Enables feature |
| Composite filters | O(n²) | O(log n) | 1000-10000x |

## Resource Impact

- **Disk Space**: Each index adds ~1-5% of data size
- **Total Overhead**: ~10-15% additional disk space
- **Memory**: Indexes are cached in memory for better performance
- **Write Performance**: Minimal impact (~5-10% slower writes)

## Maintenance

### Monitor Index Usage

Use Neo4j Browser or queries to monitor slow queries:

```cypher
CALL dbms.listQueries() 
YIELD queryId, query, elapsedTimeMillis
WHERE elapsedTimeMillis > 1000
RETURN queryId, query, elapsedTimeMillis
ORDER BY elapsedTimeMillis DESC;
```

### Rebuild Indexes (if needed)

Rarely required, but if data corruption occurs:

```cypher
DROP INDEX index_name;
-- Then re-run create_indexes.py
```

## Recommendation

**Start with Priority 1-3 immediately** (~47 indexes). These provide the most significant performance improvements for common queries. Add Priority 4-7 indexes as needed based on actual query patterns and performance profiling.

Total: **87 indexes** providing **100-1000x query performance** with only **10-15% disk overhead**.

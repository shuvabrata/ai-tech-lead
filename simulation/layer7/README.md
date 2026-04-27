# Layer 7: Git Commits & Files

## Overview
Layer 7 models the development activity in the system by capturing Git commits and the files they modify. This layer connects developers (from Layer 1) to their code contributions, links commits to Jira issues (from Layer 4), and tracks which files are changed across the codebase.

## Scope
- **Default branches only**: Only commits on the default branch (main/master) are tracked
- **No feature branches**: Feature branch commits are excluded to keep the graph focused on production code
- **No commit history chain**: The PARENT relationship is omitted for simplicity

## Nodes

### Commit
Represents a single Git commit in a repository.

**Properties:**
- `id`: Unique identifier (commit_1, commit_2, etc.)
- `sha`: Git commit SHA (40-character hex string)
- `message`: Commit message
- `timestamp`: When the commit was created (datetime)
- `additions`: Total lines added across all files
- `deletions`: Total lines deleted across all files
- `files_changed`: Number of files modified in this commit

**Example:**
```cypher
(:Commit {
  id: "commit_42",
  sha: "a1b2c3d4e5f6...",
  message: "PROJ-123: Fix authentication bug in user service",
  timestamp: datetime("2025-11-15T14:30:00Z"),
  additions: 45,
  deletions: 12,
  files_changed: 3
})
```

### File
Represents a file in a repository's codebase.

**Properties:**
- `id`: Unique identifier (file_1, file_2, etc.)
- `path`: Full path to the file (src/main/java/UserService.java)
- `name`: File name only (UserService.java)
- `extension`: File extension (.java, .py, .ts, etc.)
- `language`: Programming language (Java, Python, TypeScript, etc.)
- `is_test`: Boolean indicating if this is a test file
- `size`: File size in bytes
- `created_at`: When the file was first created (datetime)

**Example:**
```cypher
(:File {
  id: "file_42",
  path: "src/services/UserService.ts",
  name: "UserService.ts",
  extension: ".ts",
  language: "TypeScript",
  is_test: false,
  size: 3420,
  created_at: datetime("2025-10-11T09:00:00Z")
})
```

## Relationships

### PART_OF: Commit → Branch
Links a commit to the branch it belongs to.

**Example:**
```cypher
(:Commit)-[:PART_OF]->(:Branch {name: "main", is_default: true})
```

### AUTHORED_BY: Commit ↔ Person (undirected)
Links a commit to the developer who authored it.

**Example:**
```cypher
(:Commit)-[:AUTHORED_BY]-(:Person {name: "Alice Johnson", role: "Engineer"})
```

### MODIFIES: Commit → File
Links a commit to a file it modifies, with per-file change statistics.

**Properties:**
- `additions`: Lines added to this specific file
- `deletions`: Lines deleted from this specific file

**Example:**
```cypher
(:Commit)-[:MODIFIES {additions: 25, deletions: 8}]->(:File {path: "src/UserService.ts"})
```

### REFERENCES: Commit → Issue
Links a commit to a Jira issue it references (extracted from commit message).

**Example:**
```cypher
(:Commit {message: "PROJ-123: Fix bug..."})-[:REFERENCES]->(:Issue {key: "PROJ-123"})
```

## Data Statistics

- **Commits**: 500 commits over 3 months (Oct 2025 - Jan 2026)
- **Files**: 286 files across 8 repositories
- **Jira Reference Rate**: 80% (400/500 commits reference issues)
- **Average Files per Commit**: 2.2
- **Average Additions per Commit**: 242 lines
- **Date Range**: 2025-10-11 to 2026-01-16

## Dependencies

This layer depends on:
- **Layer 1**: People & Teams (for commit authors)
- **Layer 4**: Stories & Bugs (for Jira issue references)
- **Layer 5**: Repositories (for file organization)
- **Layer 6**: Branches (for commit-branch relationships)

## Usage

### Generate Data
```bash
cd simulation/layer7
python generate_data.py
```

This will create `../data/layer7_commits.json` containing:
- 500 Commit nodes
- 286 File nodes
- 2488 relationships (PART_OF, AUTHORED_BY, MODIFIES, REFERENCES)

### Load to Neo4j
```bash
cd simulation/layer7
python load_to_neo4j.py
```

This will:
1. Clear any existing Layer 7 data
2. Create constraints on Commit.id, Commit.sha, File.id
3. Load all commits and files
4. Create all relationships
5. Run validation queries

## Validation Queries

### Top Contributors
```cypher
MATCH (p:Person)-[:AUTHORED_BY]-(c:Commit)
RETURN p.name as name, p.title as title, count(c) as commits
ORDER BY commits DESC
LIMIT 10
```

### Commits per Repository
```cypher
MATCH (c:Commit)-[:PART_OF]->(b:Branch)-[:BRANCH_OF]-(r:Repository)
WHERE b.is_default = true
RETURN r.name as repo, count(c) as commits
ORDER BY commits DESC
```

### Hotspot Files (Most Modified)
```cypher
MATCH (f:File)<-[:MODIFIES]-(c:Commit)
RETURN f.path as path, f.language as lang, count(c) as modifications
ORDER BY modifications DESC
LIMIT 10
```

### Commits Referencing Issues
```cypher
MATCH (c:Commit)-[:REFERENCES]->(i:Issue)
RETURN i.key as issue, i.type as type, count(c) as commits
ORDER BY commits DESC
LIMIT 10
```

### Developer Activity by Language
```cypher
MATCH (p:Person)-[:AUTHORED_BY]-(c:Commit)-[:MODIFIES]->(f:File)
RETURN p.name as developer, f.language as language, 
       count(DISTINCT c) as commits, count(f) as files_touched
ORDER BY commits DESC
```

### Code Churn (Files with Most Changes)
```cypher
MATCH (f:File)<-[m:MODIFIES]-(c:Commit)
RETURN f.path as file, f.language as language,
       sum(m.additions) as total_additions,
       sum(m.deletions) as total_deletions,
       sum(m.additions + m.deletions) as total_churn,
       count(c) as num_commits
ORDER BY total_churn DESC
LIMIT 10
```

### Test vs Production Code
```cypher
MATCH (f:File)
RETURN f.is_test as is_test, 
       count(f) as file_count,
       sum(f.size) as total_size
ORDER BY is_test
```

### Commit Timeline
```cypher
MATCH (c:Commit)-[:PART_OF]->(b:Branch)-[:BRANCH_OF]-(r:Repository)
WHERE b.is_default = true
RETURN r.name as repo,
       date(c.timestamp).month as month,
       count(c) as commits
ORDER BY repo, month
```

### Files by Language Distribution
```cypher
MATCH (f:File)
RETURN f.language as language, 
       count(f) as files,
       sum(f.size) as total_size,
       round(avg(f.size)) as avg_size
ORDER BY files DESC
```

### Sprint Velocity by Commits
```cypher
MATCH (c:Commit)-[:REFERENCES]->(i:Issue)-[:BELONGS_TO]->(s:Sprint)
WITH s, i, count(c) as commits
RETURN s.name as sprint, 
       s.start_date as start_date,
       count(DISTINCT i) as issues_with_commits,
       sum(commits) as total_commits
ORDER BY start_date
```

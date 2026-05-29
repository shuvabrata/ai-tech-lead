# Project Graph Simulation Plan

**Version**: 0.1  
**Last Updated**: January 4, 2026  
**Status**: Planning Phase  
**Timeline**: Next few weeks

---

## 1. Purpose & Goals

### 1.1 Overview
Build a realistic simulation environment using synthetic test data to validate the graph model design and visibility layer before integrating with real enterprise systems.

### 1.2 Success Criteria
- [ ] Neo4j database populated with realistic relationships
- [ ] Can execute analytical queries from high-level-design.md
- [ ] Visibility layer demonstrates value with test data
- [ ] Model design gaps identified and documented
- [ ] Performance baseline established

### 1.3 Key Benefits
- **Risk Reduction**: Validate design decisions early
- **Iterative Development**: Test queries without API rate limits
- **Demo Environment**: Show stakeholders potential insights
- **Performance Testing**: Understand graph query patterns
- **Training Data**: Use for documentation and onboarding

---

## 2. Simulation Scope

### 2.1 In Scope (Phase 1)
We will simulate a realistic mid-sized engineering organization:
- **People**: 50 engineers, 5 managers, 2 product managers
- **Teams**: 5 engineering teams
- **Jira Hierarchy**: 3 Initiatives → 12 Epics → 80 Stories/Bugs
- **Git Repositories**: 8 repositories
- **Branches**: ~40 branches across repos
- **Commits**: ~500 commits (3 months of history)
- **Pull Requests**: ~100 PRs with reviews

### 2.2 Out of Scope (Future Phases)
- Confluence pages
- Cloud infrastructure (AWS/Azure)
- Meetings and calendar data
- Incident management
- Service deployments

---

## 3. Layer-by-Layer Build Plan

We will build the simulation incrementally, validating each layer before proceeding. Each layer adds more nodes and relationships.

### 3.1 Layer 1: People & Teams Foundation
**Goal**: Establish organizational structure and identity graph

#### Nodes to Create
- **Person** (57 total):
  - 50 Software Engineers (10 Junior, 25 Mid, 10 Senior, 5 Staff)
  - 5 Engineering Managers
  - 2 Product Managers
- **Team** (5 teams):
  - Platform Team (12 people)
  - API Team (10 people)
  - Frontend Team (10 people)
  - Mobile Team (8 people)
  - Data Team (10 people)
- **IdentityMapping**: Each person will have mappings for GitHub, Jira

#### Relationships
- `MEMBER_OF`: Person ↔ Team (undirected)
- `REPORTS_TO`: Person → Person (manager)
- `MANAGES`: Person → Team
- `MAPS_TO`: IdentityMapping ↔ Person (undirected)

#### Test Data File
- `simulation/data/layer1_people_teams.json`

#### Validation Queries
```cypher
// Count people by role
MATCH (p:Person)
RETURN p.role, p.seniority, count(*) as count

// Show org hierarchy
MATCH (p:Person)-[:REPORTS_TO]->(m:Person)
RETURN p.name, m.name, p.title

// Team sizes
MATCH (t:Team)-[:MEMBER_OF]-(p:Person)
RETURN t.name, count(p) as team_size
ORDER BY team_size DESC
```

---

### 3.2 Layer 2: Jira Initiatives
**Goal**: Create high-level business initiatives

#### Nodes to Create
- **Project** (1 project): "Engineering 2026"
- **Initiative** (represented as Epic with special label):
  - Initiative 1: "Platform Modernization" (Q1-Q2 2026)
  - Initiative 2: "Customer Portal Rebuild" (Q1-Q3 2026)
  - Initiative 3: "Data Pipeline v2" (Q2-Q3 2026)

#### Relationships
- `PART_OF`: Initiative → Project
- `ASSIGNED_TO`: Initiative ↔ Person (undirected, senior/staff engineer - technical owner)
- `REPORTED_BY`: Initiative ↔ Person (undirected, PM or staff engineer - business stakeholder)

#### Test Data File
- `simulation/data/layer2_initiatives.json`

#### Validation Queries
```cypher
// List all initiatives with assignees and reporters
MATCH (i:Initiative)-[:ASSIGNED_TO]-(assignee:Person)
MATCH (i)-[:REPORTED_BY]-(reporter:Person)
RETURN i.key, i.summary, 
       assignee.name as assignee, assignee.title as assignee_title,
       reporter.name as reporter, reporter.title as reporter_title,
       i.status
ORDER BY i.key

// Timeline view
MATCH (i:Initiative)
RETURN i.summary, i.start_date, i.due_date, i.priority
ORDER BY i.start_date
```

---

### 3.3 Layer 3: Jira Epics
**Goal**: Break down initiatives into actionable epics

#### Nodes to Create
- **Epic** (12 total, distributed across 3 initiatives):
  - **Platform Modernization** (4 epics):
    - PLAT-1: "Migrate to Kubernetes"
    - PLAT-2: "Implement Service Mesh"
    - PLAT-3: "Observability Stack Upgrade"
    - PLAT-4: "CI/CD Pipeline Rewrite"
  - **Customer Portal Rebuild** (5 epics):
    - PORT-1: "Authentication & Authorization"
    - PORT-2: "Dashboard UI Components"
    - PORT-3: "API Gateway Layer"
    - PORT-4: "Mobile Responsive Design"
    - PORT-5: "Analytics Integration"
  - **Data Pipeline v2** (3 epics):
    - DATA-1: "Streaming Architecture"
    - DATA-2: "Data Warehouse Migration"
    - DATA-3: "Real-time Analytics Engine"

#### Relationships
- `PART_OF`: Epic → Initiative
- `ASSIGNED_TO`: Epic ↔ Person (undirected, epic owner - engineer or PM)
- `TEAM`: Epic ↔ Team (undirected, team working on it)

#### Test Data File
- `simulation/data/layer3_epics.json`

#### Validation Queries
```cypher
// Epics by initiative
MATCH (e:Epic)-[:PART_OF]->(i:Initiative)
RETURN i.summary, collect(e.key) as epics

// Epic ownership distribution
MATCH (e:Epic)-[:ASSIGNED_TO]-(p:Person)
RETURN p.name, p.role, count(e) as epic_count
ORDER BY epic_count DESC

// Cross-team epics
MATCH (e:Epic)-[:TEAM]-(t:Team)
WITH e, count(t) as team_count
WHERE team_count > 1
RETURN e.key, e.summary, team_count
```

---

### 3.4 Layer 4: Jira Stories & Bugs
**Goal**: Create granular work items with realistic distribution

#### Nodes to Create
- **Issue** (80 total):
  - 60 Stories (distributed across epics)
  - 15 Bugs (some linked to existing stories, some standalone)
  - 5 Tasks (technical debt, spikes)
- **Sprint** (4 sprints - 2 weeks each, covering last 2 months)

#### Distribution Strategy
- Stories: 4-8 stories per epic (varied sizes)
- Story points: Range from 1-13 (fibonacci)
- Bugs: 
  - 5 linked to specific stories (found during testing)
  - 10 production bugs (linked to components)
- Status distribution:
  - 40% Done
  - 25% In Progress
  - 20% To Do
  - 10% In Review
  - 5% Blocked

#### Relationships
- `PART_OF`: Issue → Epic
- `ASSIGNED_TO`: Issue ↔ Person (undirected)
- `REPORTED_BY`: Issue ↔ Person (undirected)
- `IN_SPRINT`: Issue → Sprint
- `BLOCKS`: Issue → Issue (dependencies)
- `DEPENDS_ON`: Issue → Issue
- `RELATES_TO`: Bug ↔ Story (undirected, bug found in story)
- `PARENT_OF`: Story → Bug (for sub-tasks)

#### Test Data File
- `simulation/data/layer4_stories_bugs.json`
- `simulation/data/layer4_sprints.json`

#### Validation Queries
```cypher
// Sprint burndown data
MATCH (s:Sprint)<-[:IN_SPRINT]-(i:Issue)
RETURN s.name, 
       sum(i.story_points) as total_points,
       sum(CASE WHEN i.status = 'Done' THEN i.story_points ELSE 0 END) as completed_points

// Find blocked work
MATCH (i:Issue {status: 'Blocked'})-[:BLOCKS]->(blocked:Issue)
RETURN i.key, i.summary, collect(blocked.key) as blocking

// Bug distribution by team
MATCH (bug:Issue {type: 'Bug'})-[:ASSIGNED_TO]-(p:Person)-[:MEMBER_OF]-(t:Team)
RETURN t.name, count(bug) as bug_count
ORDER BY bug_count DESC

// Unassigned critical issues
MATCH (i:Issue)
WHERE i.priority = 'Critical' AND NOT exists((i)-[:ASSIGNED_TO]-())
RETURN i.key, i.summary, i.status
```

---

### 3.5 Layer 5: Git Repositories
**Goal**: Create repository structure with discoverable relationships

#### Nodes to Create
- **Repository** (8 repos):
  - `platform/k8s-infrastructure` (Platform Team)
  - `platform/service-mesh` (Platform Team)
  - `api/gateway` (API Team)
  - `api/user-service` (API Team)
  - `api/order-service` (API Team)
  - `frontend/web-app` (Frontend Team)
  - `mobile/ios-app` (Mobile Team)
  - `data/streaming-pipeline` (Data Team)

#### Repository Properties
```yaml
Properties:
  - id: string (unique)
  - name: string (repo name only)
  - full_name: string (org/repo)
  - url: string (GitHub URL)
  - language: string (primary language)
  - is_private: boolean
  - created_at: timestamp
  - description: string
  - topics: string[] (e.g., ["microservices", "api", "python"])
```

#### Relationships (Directly Discoverable)
- `COLLABORATOR`: Person ↔ Repository (undirected)
  - Properties: `permission` ("READ" or "WRITE")
  - Source: GitHub collaborator API, repo settings
  - WRITE permission includes: push, merge, admin access
  - READ permission includes: pull, clone, view-only access
  
- `COLLABORATOR`: Team ↔ Repository (undirected)
  - Properties: `permission` ("READ" or "WRITE")
  - Source: GitHub team permissions in organization settings
  - Team members inherit the team's permission level

**Note**: Epic → Repository relationships are NOT directly discoverable. Instead, they will be **inferred** in Layer 7 through the commit chain: `Epic -[:PART_OF]-> Story -[:REFERENCES]<- Commit -[:PART_OF]-> Branch -[:BRANCH_OF]- Repository`

#### Permission Distribution Strategy
- Each repo will have 1 team with WRITE access (owning team)
- 2-3 people from owning team will have individual WRITE access (maintainers/tech leads)
- 1-2 other teams may have READ access (cross-team dependencies)
- 3-5 individuals from other teams may have READ access (occasional contributors)

#### Test Data File
- `simulation/data/layer5_repositories.json`

#### Validation Queries
```cypher
// Repository collaborators by team (WRITE access)
MATCH (t:Team)-[c:COLLABORATOR]-(r:Repository)
WHERE c.permission = 'WRITE'
RETURN t.name as team, collect(r.name) as repositories
ORDER BY team

// Repository maintainers (individuals with WRITE access)
MATCH (p:Person)-[c:COLLABORATOR]-(r:Repository)
WHERE c.permission = 'WRITE'
RETURN r.name as repository, 
       collect(p.name) as maintainers,
       collect(p.title) as titles
ORDER BY repository

// Cross-team access (teams with READ permission)
MATCH (t:Team)-[c:COLLABORATOR]-(r:Repository)
WHERE c.permission = 'READ'
RETURN r.name as repository, 
       collect(t.name) as teams_with_read_access
ORDER BY repository

// People collaborating across multiple repos
MATCH (p:Person)-[c:COLLABORATOR]-(r:Repository)
WITH p, c.permission as perm, collect(r.name) as repos
WHERE size(repos) > 1
RETURN p.name, p.title, perm, repos, size(repos) as repo_count
ORDER BY repo_count DESC, perm DESC

// Repos without WRITE collaborators (should be none)
MATCH (r:Repository)
WHERE NOT exists((r)-[:COLLABORATOR {permission: 'WRITE'}]-())
RETURN r.name

// Permission summary per repository
MATCH (r:Repository)-[c:COLLABORATOR]-(collaborator)
RETURN r.name as repository,
       sum(CASE WHEN c.permission = 'WRITE' THEN 1 ELSE 0 END) as write_access,
       sum(CASE WHEN c.permission = 'READ' THEN 1 ELSE 0 END) as read_access,
       count(collaborator) as total_collaborators
ORDER BY repository
```

---

### 3.6 Layer 6: Git Branches
**Goal**: Create realistic branching patterns

#### Nodes to Create
- **Branch** (~40 branches total):
  - 1 `main` branch per repo (8 default branches)
  - ~4 feature branches per repo (32 branches)
    - Pattern: `feature/EPIC-123-description`
    - Pattern: `bugfix/BUG-456-description`
    - Some long-lived, some merged
  
#### Branch Naming Strategy
- Feature branches linked to Jira keys
- Mix of active and merged branches
- Some stale branches (last commit > 30 days)

#### Branch Properties
```yaml
Properties:
  - id: string (unique, format: repo_name::branch_name)
  - name: string (branch name)
```

**Note on Branch Creation Time**: We do NOT track `created_at` for branches because:
1. GitHub API does not provide direct access to branch ref creation time
2. Finding it requires iterating through ALL commits on the branch (extremely slow)
3. For main branches with 10K+ commits, this takes minutes per branch
4. `last_commit_timestamp` is sufficient for identifying stale branches

#### Relationships (Directly Discoverable)
- `BRANCH_OF`: Branch ↔ Repository (undirected)
  - Source: Git API, each branch belongs to exactly one repository
  - Every branch must have this relationship

**Note**: Branch creation authorship and merge relationships are NOT directly discoverable in Git metadata. These will be **inferred** in Layer 7:
- Who created a branch: Inferred from the first commit author on that branch
- Merge relationships: Inferred from merge commits (Commit → Branch relationships)
- Branch activity: Inferred from commit timestamps and authors

#### Test Data File
- `simulation/data/layer6_branches.json`

#### Validation Queries
```cypher
// Total branches per repository
MATCH (b:Branch)-[:BRANCH_OF]-(r:Repository)
RETURN r.name, 
       count(b) as total_branches,
       sum(CASE WHEN b.is_default THEN 1 ELSE 0 END) as default_branches,
       sum(CASE WHEN b.is_deleted THEN 1 ELSE 0 END) as deleted_branches
ORDER BY total_branches DESC

// Active branches per repo (non-default, not deleted)
MATCH (b:Branch)-[:BRANCH_OF]-(r:Repository)
WHERE b.is_default = false AND NOT b.is_deleted
RETURN r.name, count(b) as active_branch_count
ORDER BY active_branch_count DESC

// Stale branches (last commit > 30 days ago)
MATCH (b:Branch)
WHERE b.last_commit_timestamp < datetime() - duration({days: 30})
  AND b.is_default = false
  AND NOT b.is_deleted
RETURN b.name, b.last_commit_timestamp, 
       duration.between(b.last_commit_timestamp, datetime()).days as days_old
ORDER BY days_old DESC

// Branches linked to Jira (by naming convention)
MATCH (b:Branch)-[:BRANCH_OF]-(r:Repository)
WHERE b.name =~ '.*/(PLAT|PORT|DATA)-[0-9]+.*'
RETURN b.name, r.name,
       [x in split(b.name, '/') WHERE x =~ '(PLAT|PORT|DATA)-[0-9]+'][0] as jira_key
ORDER BY r.name, b.name

// Protected branches by repository
MATCH (b:Branch)-[:BRANCH_OF]-(r:Repository)
WHERE b.is_protected = true
RETURN r.name, collect(b.name) as protected_branches
ORDER BY r.name
```

---

### 3.7 Layer 7: Git Commits
**Goal**: Create realistic commit history with relationships to people and work items

**Important**: We only track commits that made it to the **default branch** (main). Feature branch commits are not tracked - we only care about what's in production.

#### Nodes to Create
- **Commit** (~500 commits over 3 months):
  - Distribution: ~60 commits per week
  - Varied commit sizes (small fixes to large features)
  - All commits are on default branches (main) of their respective repositories

#### Commit Properties
```yaml
Properties:
  - sha: string (commit hash, unique identifier)
  - message: string (commit message text, used to extract Jira keys)
  - timestamp: timestamp (when commit was created)
  - additions: integer (total lines added across all files)
  - deletions: integer (total lines deleted across all files)
  - files_changed: integer (number of files modified in this commit)
```
  
#### Commit Patterns to Simulate
- **By Team**:
  - Platform: 100 commits (infrastructure, config-heavy)
  - API: 150 commits (most active, 3 services)
  - Frontend: 120 commits (rapid UI iterations)
  - Mobile: 80 commits (careful releases)
  - Data: 50 commits (large, complex changes)

- **By Time**:
  - Sprint 1 (Dec 9-20, 2025): 100 commits
  - Sprint 2 (Dec 23-Jan 3): 80 commits (holidays)
  - Sprint 3 (Jan 6-17): 130 commits (back to work)
  - Sprint 4 (Jan 20-31): 140 commits (sprint end push)
  - Recent week: 50 commits

- **By Author**:
  - Top 10 contributors: 60% of commits
  - Middle 30 contributors: 35% of commits
  - Remaining 17: 5% of commits
  - Managers: Occasional commits (5 total)

#### Commit Message Patterns
- Good messages: `[PLAT-1] Add k8s deployment configs for auth service`
- Bug fixes: `Fix memory leak in user service (BUG-234)`
- No reference: `Update README` (20% of commits)
- Merge commits: `Merge pull request #42 from feature/PORT-3-api-gateway` (merged to main)

#### Relationships
- `PART_OF`: Commit → Branch (always to the default/main branch)
- `AUTHORED_BY`: Commit ↔ Person (undirected)
- `MODIFIES`: Commit → File (tracks all files changed in the commit)
  - Properties: `{additions, deletions}` - per-file change stats from Git API
- `REFERENCES`: Commit → Issue (if Jira key pattern exists in commit message)
  - Distribution: 60% reference Stories, 20% reference Bugs, 20% no reference
  - Extracted from commit `message` property using regex patterns

**Note**: We do NOT track PARENT (commit history chain). Since we only track main branch commits, the chronological order is sufficient.

#### File Nodes
Track **all files** modified in commits across repositories:

**File Properties**:
- `path`: Full file path (e.g., `src/services/UserService.java`) - from Git API
- `name`: File name only (e.g., `UserService.java`) - derived from path
- `extension`: File extension (e.g., `.java`, `.tsx`, `.py`, `.md`) - derived from path
- `language`: Programming language (e.g., `Java`, `TypeScript`, `Python`) - inferred from extension
- `is_test`: Boolean indicating if this is a test file - heuristic (path contains "test", "spec", "__tests__")
- `size`: File size in bytes - current size from Git API (not historical)
- `created_at`: Timestamp when file was first created - from first commit (requires history scan)

**Note**: Properties marked "derived" or "inferred" do not require additional API calls. `created_at` requires scanning commit history for the first commit touching this file.

**File Distribution** (estimated):
- Backend services: ~100 files (.java, .py, .js files)
- Frontend: ~80 files (.tsx, .jsx, .css files)
- Config files: ~40 files (.yaml, .json, .env files)
- Documentation: ~20 files (.md files)
- Tests: ~60 files (test files)
- **Total: ~300 File nodes**

#### Test Data Files
- `simulation/data/layer7_commits.json`
- `simulation/data/layer7_files.json`

#### Validation Queries
```cypher
// Top contributors
MATCH (p:Person)-[:AUTHORED_BY]-(c:Commit)
RETURN p.name, p.title, count(c) as commit_count
ORDER BY commit_count DESC
LIMIT 10

// Commits by week
MATCH (c:Commit)
WHERE c.timestamp >= datetime() - duration({days: 90})
WITH c, duration.inWeeks(datetime(), c.timestamp) as weeks_ago
RETURN weeks_ago, count(c) as commits
ORDER BY weeks_ago DESC

// Commits linked to Jira
MATCH (c:Commit)-[:REFERENCES]->(i:Issue)
RETURN i.type, count(c) as linked_commits

// Find hotspot files (high churn + many authors)
MATCH (f:File)<-[:MODIFIES]-(c:Commit)-[:AUTHORED_BY]-(p:Person)
WHERE c.timestamp >= datetime() - duration({days: 60})
RETURN f.path, 
       count(DISTINCT c) as commit_count,
       count(DISTINCT p) as author_count,
       f.language
ORDER BY commit_count DESC, author_count DESC
LIMIT 10

// Commits per repository (main branch activity)
MATCH (c:Commit)-[:PART_OF]->(b:Branch)-[:BRANCH_OF]-(r:Repository)
WHERE b.is_default = true
RETURN r.name, 
       count(c) as commits,
       max(c.timestamp) as last_commit
ORDER BY commits DESC

// Cross-reference: Stories completed but no commits
MATCH (story:Issue {type: 'Story', status: 'Done'})
WHERE NOT exists((story)<-[:REFERENCES]-(:Commit))
RETURN story.key, story.summary
```

---

### 3.8 Layer 8: Pull Requests (Final Layer)
**Goal**: Create pull request workflow with reviews and approvals

#### Nodes to Create
- **PullRequest** (~100 PRs over 3 months):
  - Distribution: ~8 PRs per week
  - Mix of feature PRs (70%), bug fix PRs (20%), and small improvements (10%)
  - States: merged (75%), open (15%), closed without merge (10%)

#### PR Patterns to Simulate
- **By Team**:
  - Platform: 20 PRs (large infrastructure changes)
  - API: 30 PRs (most active services)
  - Frontend: 25 PRs (UI iterations)
  - Mobile: 15 PRs (careful review process)
  - Data: 10 PRs (complex changes)

- **By Size** (commits per PR):
  - Small: 1-3 commits (40% of PRs)
  - Medium: 4-8 commits (40% of PRs)
  - Large: 9-20 commits (20% of PRs)

- **Review Patterns**:
  - 90% of PRs have at least 1 reviewer
  - 60% of PRs have 2+ reviewers
  - Average review time: 1-3 days
  - 80% of PRs approved before merge

#### PR Properties
```yaml
Properties:
  - id: string (unique, from API)
  - number: integer (PR number in repo, from API)
  - title: string (from API)
  - description: string (from API: pr.body)
  - state: string ("open", "merged", "closed" - from API)
  - created_at: timestamp (from API)
  - updated_at: timestamp (from API)
  - merged_at: timestamp (null if not merged, from API)
  - closed_at: timestamp (null if still open, from API)
  - draft: boolean (is it a draft PR, from API)
  - commits_count: integer (from API: pr.commits)
  - additions: integer (total lines added, from API)
  - deletions: integer (total lines deleted, from API)
  - changed_files: integer (from API)
  - comments: integer (general PR comments count, from API)
  - review_comments: integer (inline code review comments, from API)
  - head_branch_name: string (source branch name, even if deleted, from API: pr.head.ref)
  - base_branch_name: string (target branch name, from API: pr.base.ref)
  - labels: string[] (PR labels like "bug", "feature", from API)
  - mergeable_state: string ("clean", "dirty", "blocked", "unknown" - from API)
```

**Note**: All properties directly available from GitHub API:
- Main PR data: `GET /repos/{owner}/{repo}/pulls/{pull_number}`
- Commits: `GET /repos/{owner}/{repo}/pulls/{pull_number}/commits`
- Reviews: `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews`

#### Relationships
- `INCLUDES`: PullRequest → Commit (PR contains these commits)
  - Source: `/pulls/{pr}/commits` API endpoint
  - **CRITICAL**: Only exists for merged PRs (state='merged')
  - Reason: Layer 7 only tracks commits on default branch (main)
  - Open/closed PRs have no `INCLUDES` relationship (their commits don't exist in Layer 7 yet/ever)
  
- `TARGETS`: PullRequest → Branch (base branch - always main/default)
  - Source: `pr.base.ref` from API (target branch)
  - Always exists for all PRs (merged, open, closed)
  
- `FROM`: PullRequest → Branch (source branch - feature/bugfix branch)
  - Source: `pr.head.ref` from API
  - **May not exist**: Source branches often deleted after merge
  - Fallback: `head_branch_name` property preserves branch name even if Branch node deleted
  - Only exists for PRs where source branch hasn't been deleted
  
- `CREATED_BY`: PullRequest → Person (PR author)
  - Source: `pr.user` from API
  - Exists for all PRs
  
- `REVIEWED_BY`: PullRequest → Person (reviewer, can be multiple)
  - Properties: `{submitted_at, state}` where state is "APPROVED", "CHANGES_REQUESTED", or "COMMENTED"
  - Source: `/pulls/{pr}/reviews` API endpoint
  - Note: Only people who actually submitted reviews, not just requested reviewers
  - Can exist for any PR state (merged, open, closed)
  
- `REQUESTED_REVIEWER`: PullRequest → Person (who was asked to review)
  - Source: `pr.requested_reviewers` from API
  - Captures review requests even if person never reviewed
  - Enables "ignored request" and "responsiveness" analytics
  - Can exist for any PR state (merged, open, closed)
  
- `MERGED_BY`: PullRequest → Person (who merged the PR)
  - Source: `pr.merged_by` from API (null if not merged)
  - Only exists for merged PRs

**Layer 7 Constraint Impact**:
Since Layer 7 only tracks commits on the default branch (main), the `INCLUDES` relationship only exists for merged PRs. This means:
- **Merged PRs (75%)**: Have `INCLUDES` → Commit relationships (commits now on main)
- **Open PRs (15%)**: No `INCLUDES` relationships (commits still on feature branch, not in Layer 7)
- **Closed PRs (10%)**: No `INCLUDES` relationships (commits abandoned, never merged)

However, ALL PRs retain their commit metadata as properties (`commits_count`, `additions`, `deletions`, `changed_files`) from the GitHub API, even if the actual Commit nodes don't exist in our graph.

#### Test Data File
- `simulation/data/layer8_pull_requests.json`

#### Validation Queries
```cypher
// PRs by state and repository
MATCH (pr:PullRequest)-[:TARGETS]->(b:Branch)-[:BRANCH_OF]-(r:Repository)
RETURN r.name, pr.state, count(pr) as pr_count
ORDER BY r.name, pr.state

// Verify INCLUDES only on merged PRs
MATCH (pr:PullRequest)
OPTIONAL MATCH (pr)-[:INCLUDES]->(c:Commit)
RETURN pr.state, 
       count(pr) as total_prs,
       count(c) as prs_with_commits,
       sum(CASE WHEN c IS NULL THEN 1 ELSE 0 END) as prs_without_commits
ORDER BY pr.state

// Top PR authors
MATCH (p:Person)<-[:CREATED_BY]-(pr:PullRequest)
RETURN p.name, p.title, count(pr) as prs_created
ORDER BY prs_created DESC
LIMIT 10

// Most active reviewers
MATCH (p:Person)<-[r:REVIEWED_BY]-(pr:PullRequest)
RETURN p.name, 
       count(pr) as reviews_done,
       sum(CASE WHEN r.state = 'APPROVED' THEN 1 ELSE 0 END) as approvals,
       sum(CASE WHEN r.state = 'CHANGES_REQUESTED' THEN 1 ELSE 0 END) as change_requests
ORDER BY reviews_done DESC
LIMIT 10

// Average PR review time (merged PRs only)
MATCH (pr:PullRequest {state: 'merged'})
WHERE pr.merged_at IS NOT NULL
RETURN avg(duration.between(pr.created_at, pr.merged_at).hours) as avg_review_hours,
       min(duration.between(pr.created_at, pr.merged_at).hours) as min_review_hours,
       max(duration.between(pr.created_at, pr.merged_at).hours) as max_review_hours

// Large PRs (high risk)
MATCH (pr:PullRequest)-[:CREATED_BY]->(author:Person)
WHERE pr.commits_count > 10 OR pr.changed_files > 20
RETURN pr.number, pr.title, pr.state,
       author.name, pr.commits_count, pr.changed_files
ORDER BY pr.commits_count DESC

// PRs without reviews (risky)
MATCH (pr:PullRequest {state: 'merged'})
WHERE NOT exists((pr)-[:REVIEWED_BY]->())
RETURN pr.number, pr.title, pr.created_at, pr.merged_at
ORDER BY pr.merged_at DESC

// Cross-team reviews (collaboration)
MATCH (pr:PullRequest)-[:CREATED_BY]->(author:Person)-[:MEMBER_OF]-(author_team:Team)
MATCH (pr)-[:REVIEWED_BY]->(reviewer:Person)-[:MEMBER_OF]-(reviewer_team:Team)
WHERE author_team <> reviewer_team
RETURN author_team.name as pr_team, 
       reviewer_team.name as reviewer_team,
       count(pr) as cross_team_reviews
ORDER BY cross_team_reviews DESC

// PR to Jira linkage (via commits - merged PRs only)
MATCH (pr:PullRequest {state: 'merged'})-[:INCLUDES]->(c:Commit)-[:REFERENCES]->(i:Issue)
RETURN pr.number, pr.title, 
       collect(DISTINCT i.key) as jira_keys,
       size(collect(DISTINCT i.key)) as issue_count
ORDER BY issue_count DESC

// Open PRs without commit linkage (expected - commits not on main yet)
MATCH (pr:PullRequest {state: 'open'})
WHERE NOT exists((pr)-[:INCLUDES]->())
RETURN pr.number, pr.title, pr.commits_count as commit_count_from_api,
       duration.between(pr.created_at, datetime()).days as days_open
ORDER BY days_open DESC

// Time to first review
MATCH (pr:PullRequest)-[r:REVIEWED_BY]->(reviewer:Person)
WHERE r.submitted_at IS NOT NULL
WITH pr, min(r.submitted_at) as first_review
RETURN avg(duration.between(pr.created_at, first_review).hours) as avg_hours_to_first_review

// Review request responsiveness (who ignores reviews?)
MATCH (pr:PullRequest)-[:REQUESTED_REVIEWER]->(p:Person)
WHERE NOT exists((pr)-[:REVIEWED_BY]->(p))
RETURN p.name, p.title, count(pr) as ignored_requests
ORDER BY ignored_requests DESC

// Blocked PRs requiring attention
MATCH (pr:PullRequest {mergeable_state: 'blocked'})
WHERE pr.state = 'open'
RETURN pr.number, pr.title, pr.created_at, pr.labels,
       duration.between(pr.created_at, datetime()).days as days_blocked
ORDER BY days_blocked DESC

// PR type distribution by labels
MATCH (pr:PullRequest)
UNWIND pr.labels as label
RETURN label, count(*) as pr_count, 
       avg(pr.changed_files) as avg_files_changed
ORDER BY pr_count DESC

// Team review responsiveness
MATCH (pr:PullRequest)-[:REQUESTED_REVIEWER]->(reviewer:Person)-[:MEMBER_OF]-(t:Team)
MATCH (pr)-[rev:REVIEWED_BY]->(reviewer)
WITH t, pr, rev, duration.between(pr.created_at, rev.submitted_at).hours as response_hours
RETURN t.name, 
       avg(response_hours) as avg_response_hours,
       min(response_hours) as fastest_response,
       max(response_hours) as slowest_response
ORDER BY avg_response_hours
```

---

## 4. Implementation Plan

### 4.1 Tools & Scripts

#### Data Generation Scripts
```
simulation/
├── data/
│   ├── layer1_people_teams.json
│   ├── layer2_initiatives.json
│   ├── layer3_epics.json
│   ├── layer4_stories_bugs.json
│   ├── layer5_repositories.json
│   ├── layer6_branches.json
│   ├── layer7_commits.json
│   └── layer8_pull_requests.json
├── layer1/
│   ├── generate_data.py      # Generate people, teams, identity mappings
│   ├── load_to_neo4j.py      # Load Layer 1 (clears database)
│   ├── README.md
│   └── SUMMARY.md
├── layer2/
│   ├── generate_data.py      # Generate initiatives
│   ├── load_to_neo4j.py      # Load Layer 2 (incremental)
│   └── README.md
├── layer3/
│   ├── generate_data.py      # Generate epics
│   ├── load_to_neo4j.py      # Load Layer 3 (incremental)
│   └── README.md
├── layer4/
│   ├── generate_data.py      # Generate stories, bugs, sprints
│   ├── load_to_neo4j.py      # Load Layer 4 (incremental)
│   └── README.md
├── layer5/
│   ├── generate_data.py      # Generate repositories
│   ├── load_to_neo4j.py      # Load Layer 5 (incremental)
│   ├── README.md
│   └── SUMMARY.md
├── layer6/
│   ├── generate_data.py      # Generate branches
│   ├── load_to_neo4j.py      # Load Layer 6 (incremental)
│   ├── README.md
│   └── SUMMARY.md
├── layer7/
│   ├── generate_data.py      # Generate commits and files
│   ├── load_to_neo4j.py      # Load Layer 7 (incremental)
│   ├── README.md
│   └── SUMMARY.md
├── layer8/
│   ├── generate_data.py      # Generate pull requests
│   ├── load_to_neo4j.py      # Load Layer 8 (incremental)
│   ├── README.md
│   └── SUMMARY.md
├── reload_all.sh             # Reload all layers in sequence
├── graph-simulation.md       # This file
└── QUICK-START.md
```

#### Pattern
Each layer is self-contained:
- `generate_data.py` - Creates JSON data for that layer
- `load_to_neo4j.py` - Loads data into Neo4j
- `README.md` - Usage instructions
- `SUMMARY.md` - Implementation summary (for layers 1, 5-8)
- Layer 1 clears database, Layers 2+ are incremental

### 4.2 JSON Schema Design

Each layer follows a consistent JSON structure with metadata, nodes, and relationships. The actual data structure can be seen in the generated files in `simulation/data/` directory.

### 4.3 Development Workflow

#### Week 1: Foundation (Layers 1-2)
- Day 1-2: Setup Neo4j, create Python scripts structure
- Day 3: Generate Layer 1 (People & Teams)
- Day 4: Load Layer 1, validate queries
- Day 5: Generate & load Layer 2 (Initiatives)

#### Week 2: Jira Hierarchy (Layers 3-4)
- Day 1-2: Generate Layer 3 (Epics)
- Day 3: Generate Layer 4 (Stories & Bugs)
- Day 4-5: Load layers, validate cross-references

#### Week 3: Git Structure (Layers 5-6)
- Day 1-2: Generate Layer 5 (Repositories)
- Day 3: Generate Layer 6 (Branches)
- Day 4-5: Link repos/branches to Jira, validate

#### Week 4: Git History (Layer 7)
- Day 1-3: Generate Layer 7 (Commits & Files)
- Day 4-5: Load Layer 7, validate commit patterns

#### Week 5: Pull Requests & Final Integration (Layer 8)
- Day 1-2: Generate Layer 8 (Pull Requests)
- Day 3: Load Layer 8, link to commits and branches
- Day 4: Full integration testing across all layers
- Day 5: Run analytical queries, document findings

---

## 5. Validation & Testing Strategy

### 5.1 Per-Layer Validation
After each layer, run:
1. **Schema validation**: All required properties present
2. **Relationship integrity**: All references resolve
3. **Count checks**: Expected number of nodes created
4. **Sample queries**: Spot-check data quality

### 5.2 Cross-Layer Integration Tests
- Jira → Git references (story keys in commits)
- People → Work distribution (commits per person matches activity)
- Time consistency (commits within sprint dates)
- Orphan detection (nodes without required relationships)

### 5.3 Analytical Validation
Run queries from high-level-design.md Section 2.2:
- Critical projects with junior talent
- Code hotspots analysis
- Blocked work identification
- Sprint velocity trends

### 5.4 Performance Testing
- Query response time for common patterns
- Full graph traversal performance
- Index effectiveness
- Memory usage at scale

---

## 6. Realistic Data Patterns

### 6.1 Making It Realistic

#### Work Distribution
- **Pareto Principle**: 20% of people do 80% of work
- **Specialization**: Frontend devs primarily in web-app repo
- **Managers**: Low commit volume, high review volume
- **Junior Engineers**: More bugs assigned, smaller stories

#### Time Patterns
- **Sprint Curves**: Slow start, end-of-sprint rush
- **Holiday Dip**: Lower activity Dec 23-Jan 2
- **Work Hours**: Commits during business hours (with some exceptions)
- **Code Review Lag**: PRs reviewed 1-3 days after creation

#### Jira Patterns
- **Status Transitions**: Realistic flow (To Do → In Progress → In Review → Done)
- **Story Point Accuracy**: Some stories underestimated, some overestimated
- **Scope Creep**: 10% of stories have increased estimates
- **Bug Spike**: More bugs reported after major releases

#### Git Patterns
- **Commit Size**: Mix of small fixes (1-10 lines) and features (100-500 lines)
- **Branch Lifetime**: Features 5-15 days, bugs 1-3 days
- **Merge Frequency**: Main branch gets 3-5 merges per day
- **Commit Messages**: 80% reference Jira, 20% don't

### 6.2 Edge Cases to Include
- **Stale branches**: 5 branches with no commits in 60+ days
- **Unassigned work**: 3 critical bugs with no assignee
- **Cross-team dependencies**: 2 epics blocked by other teams
- **Abandoned features**: 1 epic with no recent activity
- **Hotspot files**: 3 files touched by 10+ developers
- **Lone wolves**: 2 engineers working on isolated features
- **Context switching**: 3 people assigned to 5+ active stories

---

## 7. Success Metrics & Goals

### 7.1 Completion Criteria
- [ ] All 7 layers implemented and loaded
- [ ] Database contains ~700+ nodes
- [ ] Database contains ~2000+ relationships
- [ ] All validation queries pass
- [ ] Can answer 10+ analytical questions
- [ ] Performance: Queries complete in <500ms


### 7.3 Documentation Deliverables
- [ ] This simulation plan (this document)
- [ ] Data generation scripts with inline documentation
- [ ] Sample JSON files for each layer
- [ ] Neo4j query cookbook (useful queries)
- [ ] Findings document (design gaps, insights)
- [ ] Demo script for stakeholder presentations

---

## 8. Next Steps After Simulation

### 8.1 Design Refinements
Based on simulation learnings:
- Identify missing relationships
- Add/remove node properties
- Optimize for common query patterns
- Document performance considerations

### 8.2 Visibility Layer Design
- Dashboard wireframes
- Key metrics to surface
- Alert triggers (e.g., hotspots, blocked work)
- Drill-down navigation paths

### 8.3 Real Data Integration Planning
- API authentication requirements
- Rate limiting strategies
- Incremental sync vs full refresh
- Identity resolution testing with real data

---

# Layer 8: Pull Requests

## Overview
Layer 8 generates realistic pull request data including review workflows, approvals, and commit linkage. This is the final layer that completes the development workflow traceability from Jira to Git.

## Files in This Layer
- **generate_data.py**: Generates 100 pull requests with realistic metrics and relationships
- **load_to_neo4j.py**: Loads PR nodes and relationships into Neo4j database
- **README.md**: This documentation file
- **SUMMARY.md**: Implementation summary with statistics and validation results

## Dependencies
- **Layer 1**: People & Teams (for PR authors, reviewers, mergers)
- **Layer 6**: Branches (for TARGETS and FROM relationships)
- **Layer 7**: Commits (for INCLUDES relationship - merged PRs only)

## Generated Data

### Pull Requests (100 total)
- **Merged PRs**: 75-83 (75%)
- **Open PRs**: 10-15 (15%)
- **Closed PRs**: 7-10 (10%)

### Properties
Each PR includes:
- Basic info: id, number, title, description, state
- Timestamps: created_at, updated_at, merged_at, closed_at
- Metrics: commits_count, additions, deletions, changed_files
- Engagement: comments, review_comments
- Branch info: head_branch_name, base_branch_name
- Classification: labels, mergeable_state, draft

### Relationships (7 types, 1,033 total)

#### INCLUDES (PullRequest → Commit) - 384 relationships
- **Only for merged PRs** (constraint from Layer 7)
- Links PRs to commits that were merged to main branch
- Open/closed PRs have NO commit relationships (commits not on main yet/ever)
- Average 6.2 commits per merged PR

#### TARGETS (PullRequest → Branch) - 100 relationships
- Always points to default branch (main)
- Exists for ALL PRs (merged, open, closed)

#### FROM (PullRequest → Branch) - 100 relationships
- Points to source/head branch (feature branch)
- Exists for ALL PRs

#### CREATED_BY (PullRequest → Person) - 100 relationships
- PR author
- Exists for ALL PRs

#### REVIEWED_BY (PullRequest → Person) - 155 relationships
- People who submitted reviews
- Properties: `state` ("APPROVED", "CHANGES_REQUESTED", "COMMENTED")
- 90% of PRs have at least one reviewer
- 60% have 2+ reviewers

#### REQUESTED_REVIEWER (PullRequest → Person) - 211 relationships
- People who were asked to review
- Enables "ignored review request" analysis
- Some reviewers were requested but haven't reviewed yet (bottleneck detection)

#### MERGED_BY (PullRequest → Person) - 83 relationships
- Person who merged the PR
- Only exists for merged PRs
- Usually senior engineers or the PR author

## Usage

### Generate Data
```bash
cd simulation/layer8
python generate_data.py
```

Generates `../data/layer8_pull_requests.json` with:
- 100 pull request nodes
- 1,033 relationships across 7 types

### Load to Neo4j
```bash
python load_to_neo4j.py
```

The loader script will:
- Clear existing Layer 8 data
- Create constraints for PR uniqueness  
- Load 100 PR nodes
- Create 1,033 relationships
- Run 10 validation queries

## Data Distribution

### By Repository
- k8s-infrastructure: 20 PRs
- web-app: 25 PRs
- ios-app: 15 PRs
- gateway: 10 PRs
- user-service: 10 PRs
- order-service: 10 PRs
- service-mesh: 5 PRs
- streaming-pipeline: 5 PRs

### By Size
- Small (1-3 commits): 40%
- Medium (4-8 commits): 40%
- Large (9-20 commits): 20%

## Key Design Decisions

### Layer 7 Constraint
Since Layer 7 only tracks commits on the default branch (main), the `INCLUDES` relationship:
- ✅ Exists for **merged PRs** (commits are now on main)
- ❌ Does NOT exist for **open PRs** (commits still on feature branch)
- ❌ Does NOT exist for **closed PRs** (commits never merged)

This reflects reality: only merged code is tracked in production.

### Commit Metadata Preservation
Even without `INCLUDES` relationships, ALL PRs retain commit metadata as properties:
- commits_count
- additions
- deletions  
- changed_files

### Review Patterns
- 80% approval rate before merge
- Average review time: 1-3 days
- Cross-team reviews included for collaboration analysis

## Analytics Enabled

With Layer 8, you can now analyze:

1. **Code Review Effectiveness**
   - Who reviews the most?
   - Average time to review
   - Approval vs change-request ratios

2. **Team Collaboration**
   - Cross-team review patterns
   - Review bottlenecks

3. **PR Quality Indicators**
   - Large PRs (high risk)
   - PRs without reviews
   - Blocked PRs

4. **Developer Productivity**
   - PRs per person
   - Time from PR creation to merge
   - Draft PR usage patterns

5. **Traceability**
   - Jira Issue → Commit → PR (for merged PRs)
   - Which stories were delivered in which PRs

## Cypher Queries for Analytics

### PR Velocity by Repository
```cypher
MATCH (pr:PullRequest)-[:TARGETS]->(b:Branch)-[:BRANCH_OF]-(r:Repository)
RETURN r.name as repository,
       count(pr) as total_prs,
       sum(CASE WHEN pr.state = 'merged' THEN 1 ELSE 0 END) as merged,
       sum(CASE WHEN pr.state = 'open' THEN 1 ELSE 0 END) as open,
       round(sum(CASE WHEN pr.state = 'merged' THEN 1 ELSE 0 END) * 100.0 / count(pr), 1) as merge_rate
ORDER BY total_prs DESC
```

### Top PR Contributors
```cypher
MATCH (pr:PullRequest)-[:CREATED_BY]->(p:Person)
RETURN p.name as developer,
       p.title as title,
       count(pr) as prs_created,
       sum(CASE WHEN pr.state = 'merged' THEN 1 ELSE 0 END) as merged,
       sum(pr.additions) as total_additions,
       sum(pr.deletions) as total_deletions
ORDER BY prs_created DESC
LIMIT 10
```

### Most Active Reviewers
```cypher
MATCH (pr:PullRequest)-[:REVIEWED_BY]->(p:Person)
RETURN p.name as reviewer,
       p.title as title,
       count(pr) as reviews_given,
       sum(CASE WHEN pr.state = 'merged' THEN 1 ELSE 0 END) as reviewed_and_merged
ORDER BY reviews_given DESC
LIMIT 10
```

### Review Bottlenecks (Requested but Not Reviewed)
```cypher
MATCH (pr:PullRequest)-[:REQUESTED_REVIEWER]->(p:Person)
WHERE NOT (pr)-[:REVIEWED_BY]->(p)
WITH p, count(pr) as pending_reviews
WHERE pending_reviews > 3
RETURN p.name as reviewer,
       p.title as title,
       pending_reviews
ORDER BY pending_reviews DESC
LIMIT 15
```

### PR Cycle Time Analysis
```cypher
MATCH (pr:PullRequest)
WHERE pr.state = 'merged'
WITH duration.between(pr.created_at, pr.merged_at).days as cycle_days
RETURN min(cycle_days) as min_days,
       round(avg(cycle_days), 1) as avg_days,
       max(cycle_days) as max_days,
       percentileDisc(cycle_days, 0.5) as median_days,
       percentileDisc(cycle_days, 0.95) as p95_days
```

### Large PRs (Risk Indicators)
```cypher
MATCH (pr:PullRequest)-[:CREATED_BY]->(author:Person)
MATCH (pr)-[:TARGETS]->(b:Branch)-[:BRANCH_OF]-(r:Repository)
WHERE pr.commits_count > 10 OR (pr.additions + pr.deletions) > 2000
RETURN pr.number as pr_num,
       pr.title as title,
       r.name as repo,
       author.name as author,
       pr.commits_count as commits,
       pr.additions + pr.deletions as total_changes,
       pr.state as state
ORDER BY total_changes DESC
LIMIT 10
```

### PRs Without Reviews (Quality Risk)
```cypher
MATCH (pr:PullRequest)-[:CREATED_BY]->(author:Person)
MATCH (pr)-[:TARGETS]->(b:Branch)-[:BRANCH_OF]-(r:Repository)
WHERE NOT (pr)-[:REVIEWED_BY]->(:Person)
AND pr.state = 'merged'
RETURN pr.number as pr_num,
       pr.title as title,
       r.name as repo,
       author.name as author,
       pr.commits_count as commits,
       pr.additions + pr.deletions as changes
ORDER BY changes DESC
```

### Cross-Team Review Patterns
```cypher
MATCH (pr:PullRequest)-[:CREATED_BY]->(author:Person)-[:MEMBER_OF]-(authorTeam:Team)
MATCH (pr)-[:REVIEWED_BY]->(reviewer:Person)-[:MEMBER_OF]-(reviewerTeam:Team)
WHERE authorTeam <> reviewerTeam
RETURN authorTeam.name as author_team,
       reviewerTeam.name as reviewer_team,
       count(pr) as cross_team_reviews
ORDER BY cross_team_reviews DESC
LIMIT 10
```

### Developer Collaboration Network (Who Reviews Whom)
```cypher
MATCH (pr:PullRequest)-[:CREATED_BY]->(author:Person)
MATCH (pr)-[:REVIEWED_BY]->(reviewer:Person)
WHERE author <> reviewer
RETURN author.name as pr_author,
       reviewer.name as reviewer,
       count(pr) as reviews
ORDER BY reviews DESC
LIMIT 10
```

### PR Size Distribution
```cypher
MATCH (pr:PullRequest)
WITH pr,
     CASE 
       WHEN pr.commits_count <= 3 THEN 'Small (1-3 commits)'
       WHEN pr.commits_count <= 8 THEN 'Medium (4-8 commits)'
       ELSE 'Large (9+ commits)'
     END as size_category
RETURN size_category,
       count(pr) as pr_count,
       round(avg(pr.additions + pr.deletions)) as avg_changes,
       round(avg(pr.changed_files), 1) as avg_files
ORDER BY 
  CASE size_category
    WHEN 'Small (1-3 commits)' THEN 1
    WHEN 'Medium (4-8 commits)' THEN 2
    ELSE 3
  END
```

### Hotspot Repositories (Most PR Activity)
```cypher
MATCH (pr:PullRequest)-[:TARGETS]->(b:Branch)-[:BRANCH_OF]-(r:Repository)
RETURN r.name as repository,
       count(pr) as total_prs,
       sum(pr.additions) as total_additions,
       sum(pr.deletions) as total_deletions,
       sum(pr.commits_count) as total_commits,
       round(avg(pr.commits_count), 1) as avg_commits_per_pr
ORDER BY total_prs DESC
```

### Review Response Time (Days to First Review)
```cypher
MATCH (pr:PullRequest)-[:REVIEWED_BY]->(reviewer:Person)
WITH pr, min(duration.between(pr.created_at, pr.updated_at).days) as days_to_review
WHERE days_to_review >= 0
RETURN min(days_to_review) as min_days,
       round(avg(days_to_review), 1) as avg_days,
       max(days_to_review) as max_days,
       percentileDisc(days_to_review, 0.5) as median_days
```

### Merge Patterns by Day of Week
```cypher
MATCH (pr:PullRequest)
WHERE pr.state = 'merged' AND pr.merged_at IS NOT NULL
WITH pr, 
     CASE date(pr.merged_at).dayOfWeek
       WHEN 1 THEN 'Monday'
       WHEN 2 THEN 'Tuesday'
       WHEN 3 THEN 'Wednesday'
       WHEN 4 THEN 'Thursday'
       WHEN 5 THEN 'Friday'
       WHEN 6 THEN 'Saturday'
       WHEN 7 THEN 'Sunday'
     END as day_of_week
RETURN day_of_week,
       count(pr) as prs_merged,
       round(avg(pr.commits_count), 1) as avg_commits
ORDER BY 
  CASE day_of_week
    WHEN 'Monday' THEN 1
    WHEN 'Tuesday' THEN 2
    WHEN 'Wednesday' THEN 3
    WHEN 'Thursday' THEN 4
    WHEN 'Friday' THEN 5
    WHEN 'Saturday' THEN 6
    WHEN 'Sunday' THEN 7
  END
```

### Reviewer Workload Distribution
```cypher
MATCH (p:Person)
OPTIONAL MATCH (pr_created:PullRequest)-[:CREATED_BY]->(p)
OPTIONAL MATCH (pr_reviewed:PullRequest)-[:REVIEWED_BY]->(p)
OPTIONAL MATCH (pr_requested:PullRequest)-[:REQUESTED_REVIEWER]->(p)
WHERE NOT (pr_requested)-[:REVIEWED_BY]->(p)
RETURN p.name as person,
       p.title as title,
       count(DISTINCT pr_created) as prs_created,
       count(DISTINCT pr_reviewed) as reviews_completed,
       count(DISTINCT pr_requested) as reviews_pending,
       count(DISTINCT pr_reviewed) + count(DISTINCT pr_requested) as total_review_load
ORDER BY total_review_load DESC
LIMIT 15
```

### Commit-to-PR Traceability (Merged PRs Only)
```cypher
MATCH (pr:PullRequest)-[:INCLUDES]->(c:Commit)-[:AUTHORED_BY]-(author:Person)
MATCH (pr)-[:TARGETS]->(b:Branch)-[:BRANCH_OF]-(r:Repository)
RETURN r.name as repository,
       pr.number as pr_num,
       pr.title as pr_title,
       count(c) as commits_in_pr,
       collect(DISTINCT author.name) as commit_authors,
       pr.created_at as pr_created
ORDER BY commits_in_pr DESC
LIMIT 10
```

### Work Item to Code Traceability (Full Chain)
```cypher
MATCH (i:Issue)<-[:REFERENCES]-(c:Commit)<-[:INCLUDES]-(pr:PullRequest)
MATCH (pr)-[:CREATED_BY]->(author:Person)
MATCH (pr)-[:TARGETS]->(:Branch)-[:BRANCH_OF]-(r:Repository)
OPTIONAL MATCH (i)-[:BELONGS_TO]->(s:Story)
OPTIONAL MATCH (s)-[:BELONGS_TO]->(e:Epic)
RETURN i.key as issue,
       i.title as issue_title,
       s.title as story,
       e.title as epic,
       pr.number as pr_num,
       pr.title as pr_title,
       r.name as repository,
       author.name as pr_author,
       count(c) as commits
ORDER BY commits DESC
LIMIT 10
```

### Junior vs Senior Engineer PR Patterns
```cypher
MATCH (pr:PullRequest)-[:CREATED_BY]->(p:Person)
WITH pr, p,
     CASE 
       WHEN p.title CONTAINS 'Junior' THEN 'Junior'
       WHEN p.title CONTAINS 'Senior' OR p.title CONTAINS 'Staff' THEN 'Senior'
       ELSE 'Mid-Level'
     END as seniority
RETURN seniority,
       count(pr) as prs_created,
       round(avg(pr.commits_count), 1) as avg_commits,
       round(avg(pr.additions + pr.deletions)) as avg_changes,
       round(avg(pr.changed_files), 1) as avg_files,
       round(avg(duration.between(pr.created_at, pr.merged_at).days), 1) as avg_cycle_days
ORDER BY 
  CASE seniority
    WHEN 'Junior' THEN 1
    WHEN 'Mid-Level' THEN 2
    WHEN 'Senior' THEN 3
  END
```

### Review Quality: Approvals vs Change Requests
```cypher
MATCH (pr:PullRequest)-[r:REVIEWED_BY]->(reviewer:Person)
RETURN reviewer.name as reviewer,
       reviewer.title as title,
       count(pr) as total_reviews,
       sum(CASE WHEN r.state = 'APPROVED' THEN 1 ELSE 0 END) as approvals,
       sum(CASE WHEN r.state = 'CHANGES_REQUESTED' THEN 1 ELSE 0 END) as change_requests,
       sum(CASE WHEN r.state = 'COMMENTED' THEN 1 ELSE 0 END) as comments_only,
       round(sum(CASE WHEN r.state = 'CHANGES_REQUESTED' THEN 1 ELSE 0 END) * 100.0 / count(pr), 1) as strictness_pct
ORDER BY total_reviews DESC
LIMIT 15
```

### Abandoned PRs (Open for Too Long)
```cypher
MATCH (pr:PullRequest)-[:CREATED_BY]->(author:Person)
MATCH (pr)-[:TARGETS]->(:Branch)-[:BRANCH_OF]-(r:Repository)
WHERE pr.state = 'open'
AND duration.between(pr.created_at, datetime()).days > 7
RETURN pr.number as pr_num,
       pr.title as title,
       r.name as repo,
       author.name as author,
       duration.between(pr.created_at, datetime()).days as days_open,
       pr.commits_count as commits
ORDER BY days_open DESC
```

## Behavioral Analytics Insights

With these queries, you can analyze:

1. **Developer Productivity Patterns**
   - PR creation velocity by seniority
   - Merge success rates
   - Code change volumes

2. **Code Review Culture**
   - Review response times
   - Cross-team collaboration
   - Review thoroughness (approval vs change request ratios)

3. **Quality Indicators**
   - Large/risky PRs
   - PRs merged without reviews
   - Review bottlenecks

4. **Team Collaboration**
   - Who reviews whom (collaboration networks)
   - Cross-team review patterns
   - Reviewer workload distribution

5. **Process Efficiency**
   - PR cycle times
   - Merge patterns by day
   - Abandoned/stale PRs

6. **End-to-End Traceability**
   - Initiative → Epic → Story → Issue → Commit → PR
   - Work item to code delivery tracking

## File Output
- `simulation/data/layer8_pull_requests.json`

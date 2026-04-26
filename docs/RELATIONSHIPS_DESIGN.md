# Relationships Design: Single-Edge Same-Name Relationships (Undirected Queries)

## Overview

This document explains the design decision to implement **single-edge relationships with undirected querying** for same-name relationships in the Neo4j graph database. This approach simplifies AI-powered query generation while avoiding duplicate relationship storage.

## Rationale

### The Problem
When users ask natural language questions, they often express relationships in both directions without thinking about the underlying graph structure:

- "Show me all issues assigned to Alice" (Person ← Issue traversal)
- "Show me Alice's assigned issues" (Person → Issue traversal)
- "What repositories does the Platform Team collaborate on?" (Team → Repository)
- "Who are the collaborators on backend-api?" (Repository → Team/Person)

### Traditional Approach Limitation
In a traditional unidirectional graph model, queries would need to:
1. Know the exact direction of the relationship
2. Use reverse traversal patterns (matching in opposite direction)
3. Complicate query generation logic for AI systems

### Our Solution: Same Name, Stored Once + Undirected Queries
By creating **a single relationship and querying it without direction**, we achieve:
1. **Minimal cognitive load** - AI only needs to learn ONE relationship name, not two
2. **Simplified query patterns** - queries work naturally in either direction
3. **No semantic confusion** - the relationship means the same thing regardless of direction
4. **Lower storage/write cost** - only one edge is stored, not two

Example with same-name undirected relationships:
```cypher
// Both queries use the same relationship name
MATCH (issue:Issue)-[:ASSIGNED_TO]-(person:Person {name: "Alice"})
RETURN issue

MATCH (person:Person {name: "Alice"})-[:ASSIGNED_TO]-(issue:Issue)
RETURN issue
```

## Relationship Categories

### Category 1: Same Name, Stored Once (Undirected Traversal)

These relationships use the **exact same name** and are **stored once** because they represent symmetric or naturally bidirectional concepts. Query them with undirected patterns (`-[:REL]-`).

| Relationship Name | Usage | Example |
|------------------|-------|---------|
| `ASSIGNED_TO` | Work assignment | Issue ↔ Person, Epic ↔ Person, Initiative ↔ Person |
| `MEMBER_OF` | Team membership | Person ↔ Team |
| `TEAM` | Team ownership | Epic ↔ Team, Issue ↔ Team |
| `COLLABORATOR` | Repository access | Person/Team ↔ Repository |
| `BRANCH_OF` | Branch relationship | Branch ↔ Repository |
| `REPORTED_BY` | Issue/work reporting | Issue/Initiative ↔ Person |
| `AUTHORED_BY` | Code authorship | Commit ↔ Person |
| `MAPS_TO` | Identity mapping | IdentityMapping ↔ Person |
| `RELATES_TO` | Related issues | Issue ↔ Issue (inherently symmetric) |

### Category 2: Different Names for Directionality (Hierarchical Relationships)

These relationships maintain different names because they represent clear hierarchical or directional concepts:

| Forward Relationship | Reverse Relationship | Description |
|---------------------|---------------------|-------------|
| `PART_OF` | `CONTAINS` | Hierarchical containment |
| `REPORTS_TO` | `MANAGES` | Management hierarchy |
| `MANAGES` (Person→Team) | `MANAGED_BY` (Team→Person) | Team management |
| `BLOCKS` | `BLOCKED_BY` | Issue blocking |
| `DEPENDS_ON` | `DEPENDENCY_OF` | Issue dependencies |
| `IN_SPRINT` | `CONTAINS` | Sprint containment |
| `MODIFIES` | `MODIFIED_BY` | File modifications |
| `REFERENCES` | `REFERENCED_BY` | Issue references |
| `INCLUDES` | `INCLUDED_IN` | PR commits |
| `TARGETS` | `TARGETED_BY` | PR base branch |
| `CREATED_BY` | `CREATED` | PR creation |
| `REVIEWED_BY` | `REVIEWED` | PR reviews |
| `REQUESTED_REVIEWER` | `REVIEW_REQUESTED_BY` | Review requests |
| `MERGED_BY` | `MERGED` | PR merge action |

### Category 3: Unidirectional Relationships

These relationships exist in only one direction:

| Relationship Name | From → To | Description |
|------------------|-----------|-------------|
| `LEADS` | Person → Project | Project leadership |
| `FROM` | PullRequest → Branch | PR head branch (source) |

## Complete Relationship List by Layer

### Layer 1: People & Teams
- `MEMBER_OF` - Person ↔ Team (same name, undirected)
- `REPORTS_TO` / `MANAGES` - Person ↔ Person (different names for hierarchy)
- `MANAGES` / `MANAGED_BY` - Person ↔ Team (different names for hierarchy)
- `MAPS_TO` - IdentityMapping ↔ Person (same name, undirected)

### Layer 2: Initiatives & Projects
- `LEADS` - Person → Project (unidirectional)
- `PART_OF` / `CONTAINS` - Initiative ↔ Project (different names for hierarchy)
- `ASSIGNED_TO` - Initiative ↔ Person (same name, undirected)
- `REPORTED_BY` - Initiative ↔ Person (same name, undirected)

### Layer 3: Epics
- `PART_OF` / `CONTAINS` - Epic ↔ Initiative (different names for hierarchy)
- `ASSIGNED_TO` - Epic ↔ Person (same name, undirected)
- `TEAM` - Epic ↔ Team (same name, undirected)

### Layer 4: Stories, Bugs, Tasks & Sprints
- `PART_OF` / `CONTAINS` - Issue ↔ Epic (different names for hierarchy)
- `ASSIGNED_TO` - Issue ↔ Person (same name, undirected)
- `REPORTED_BY` - Issue ↔ Person (same name, undirected)
- `IN_SPRINT` / `CONTAINS` - Issue ↔ Sprint (different names for directionality)
- `BLOCKS` / `BLOCKED_BY` - Issue ↔ Issue (different names for directionality)
- `DEPENDS_ON` / `DEPENDENCY_OF` - Issue ↔ Issue (different names for directionality)
- `RELATES_TO` - Issue ↔ Issue (same name, undirected)
- `TEAM` - Issue ↔ Team (same name, undirected)

### Layer 5: Repositories
- `COLLABORATOR` - Person/Team ↔ Repository (same name, undirected)

### Layer 6: Branches
- `BRANCH_OF` - Branch ↔ Repository (same name, undirected)

### Layer 7: Commits & Files
- `PART_OF` / `CONTAINS` - Commit ↔ Branch (different names for hierarchy)
- `AUTHORED_BY` - Commit ↔ Person (same name, undirected)
- `MODIFIES` / `MODIFIED_BY` - Commit ↔ File (different names for directionality)
- `REFERENCES` / `REFERENCED_BY` - Commit ↔ Issue (different names for directionality)

### Layer 8: Pull Requests
- `INCLUDES` / `INCLUDED_IN` - PullRequest ↔ Commit (different names for directionality)
- `TARGETS` / `TARGETED_BY` - PullRequest ↔ Branch (different names for directionality - base branch)
- `FROM` - PullRequest → Branch (unidirectional - head branch)
- `CREATED_BY` / `CREATED` - PullRequest ↔ Person (different names for directionality)
- `REVIEWED_BY` / `REVIEWED` - PullRequest ↔ Person (different names for directionality)
- `REQUESTED_REVIEWER` / `REVIEW_REQUESTED_BY` - PullRequest ↔ Person (different names for directionality)
- `MERGED_BY` / `MERGED` - PullRequest ↔ Person (different names for directionality)

## Total Relationships Summary

- **Same-name undirected**: 9 relationship types (stored once)
- **Different-name bidirectional**: 13 relationship pairs (26 unique names total)
- **Unidirectional**: 2 relationship types (stored in one direction only)
- **Total unique relationship names**: 37 (9 + 26 + 2)

## Query Examples

### Example 1: Finding Assigned Work (Same Relationship, Undirected)

**Natural language**: "What is Alice working on?"

```cypher
// Works naturally - undirected traversal from Person to work items
MATCH (p:Person {name: "Alice"})-[:ASSIGNED_TO]-(work)
WHERE work:Issue OR work:Epic OR work:Initiative
RETURN work
```

**Natural language**: "Who is assigned to PLAT-123?"

```cypher
// Also works naturally - undirected traversal from Issue to Person
MATCH (i:Issue {key: "PLAT-123"})-[:ASSIGNED_TO]-(person:Person)
RETURN person
```

### Example 2: Repository Collaboration

**Natural language**: "What repositories can Alice access?"

```cypher
// Undirected traversal between Person and Repository
MATCH (p:Person {name: "Alice"})-[:COLLABORATOR]-(repo:Repository)
RETURN repo
```

**Natural language**: "Who has access to backend-api?"

```cypher
// Undirected traversal between Repository and Person/Team
MATCH (r:Repository {name: "backend-api"})-[:COLLABORATOR]-(collaborator)
RETURN collaborator
```

### Example 3: Code Authorship

**Natural language**: "What did Alice author?"

```cypher
// Undirected traversal between Person and Commit
MATCH (p:Person {name: "Alice"})-[:AUTHORED_BY]-(commit:Commit)
RETURN commit
```

**Natural language**: "Who authored commit abc123?"

```cypher
// Undirected traversal between Commit and Person
MATCH (c:Commit {sha: "abc123"})-[:AUTHORED_BY]-(person:Person)
RETURN person
```

### Example 4: Hierarchical Queries (Different Names for Clarity)

**Natural language**: "What epics are in this initiative?"

```cypher
// Use CONTAINS for top-down traversal
MATCH (i:Initiative {key: "PLAT-1"})-[:CONTAINS]->(epic:Epic)
RETURN epic
```

**Natural language**: "What initiative does this epic belong to?"

```cypher
// Use PART_OF for bottom-up traversal
MATCH (e:Epic {key: "PLAT-100"})-[:PART_OF]->(initiative:Initiative)
RETURN initiative
```

### Example 5: Unidirectional Relationships

**Natural language**: "Who leads the Platform project?"

```cypher
// LEADS is unidirectional - only Person -> Project
MATCH (person:Person)-[:LEADS]->(project:Project {key: "PLAT"})
RETURN person
```

**Natural language**: "What is the source branch for this PR?"

```cypher
// FROM is unidirectional - only PullRequest -> Branch (head)
MATCH (pr:PullRequest {number: 42})-[:FROM]->(branch:Branch)
RETURN branch
```

## AI Query Generation Benefits

When using Large Language Models (LLMs) to convert natural language to Cypher:

1. **Reduced vocabulary** - The model only needs to learn 37 relationship names instead of 70+
2. **Semantic clarity** - Same-name undirected relationships (9 types) work in either direction
3. **Higher accuracy** - Strategic use of shared names reduces mistakes in relationship selection
4. **Simpler prompts** - Documentation and examples are more concise
5. **Better generalization** - For symmetric concepts, direction doesn't matter

### Comparison: Traditional vs Same-Name Approach

**Traditional Unidirectional Approach (70+ names)**:
- AI must learn: `ASSIGNED_TO`, `HAS_ASSIGNEE`, `AUTHORED_BY`, `HAS_AUTHOR`, `REVIEWED_BY`, `HAS_REVIEWER`, etc.
- AI must decide: "Does user want ASSIGNED_TO or HAS_ASSIGNEE?"
- Risk: Using wrong direction requires fallback query logic or query fails

**Our Undirected Same-Name Approach (36 names)**:
- AI must learn: Fewer total names due to strategic use of same-name undirected relationships
- For symmetric relationships: AI uses same name, direction doesn't matter
- For hierarchical/directional: AI uses semantic names (PART_OF vs CONTAINS, BLOCKS vs BLOCKED_BY)
- Risk: Minimal - most common queries work naturally in either direction

## Implementation Notes

- Same-name undirected relationships are created once during data loading
- Directional pairs are still created in both directions
- Query performance is improved for common access patterns
- Relationship properties (if any) are stored once for undirected relationships

## Maintenance

When adding new relationship types:

1. **Determine relationship category**: 
   - Same-name undirected (symmetric concepts like ASSIGNED_TO)
   - Different-name bidirectional (directional but traversable both ways like PART_OF/CONTAINS)
   - Unidirectional (one-way only like LEADS or FROM)
2. **Choose names carefully**: For directional pairs, select natural names for each direction
3. **Update relationship directionality definitions**: Add to `UNDIRECTED_RELATIONSHIPS` or `DIRECTIONAL_RELATIONSHIPS` in `db/models.py`
4. **Update load scripts**: Create relationships according to category
5. **Document here**: Add to the appropriate category in this document
6. **Update tests**: Ensure validation queries work as expected

## Performance Considerations

- **Storage**: Undirected relationships store a single edge; directional pairs still store two
- **Write performance**: Faster for undirected types (1x creation), unchanged for directional pairs
- **Read performance**: Undirected queries remain fast for reverse traversal
- **Index usage**: Both directions benefit from node property indexes

## Conclusion

Same-name undirected relationships are essential for:
- Natural language query generation
- AI-powered graph analytics
- Improved developer experience
- Better query performance

The remaining overhead during data loading for directional pairs is outweighed by the benefits in query flexibility and performance.

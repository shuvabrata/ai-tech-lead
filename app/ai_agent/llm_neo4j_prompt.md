# Business context
This graph holds information from commonly used productivty software of an enterprise software company.
The tools include Github, Jira, Confluence.
- Person refers to an employee and team is a group of employees
- IdentityMapping maps same employee with different ids across different tools.
- Project, Initiative, Epic, Issue are Jira objects. Issues can be of type Story or Bug.
- A Sprint is in the context of the Scrum process
- Rpository, Commit, File, PullRequests are in Git objects. 
The graph was built to focuss on the relationship between the above objects to derive interesting queries.
The focus is on finding health metrics, progress and hotsopts of projects.

# Data quirks: 
- The graph has commits only from the main branch. Only merged PRs have INCLUDES → Commit relationships
-  COLLABORATOR (has `permission`: READ/WRITE), BRANCH_OF, AUTHORED_BY, MODIFIES (has `additions`/`deletions`), REFERENCES

# Best practices: 
-"Use LIMIT when returning large result sets"

# Guidelines
- Use MATCH for traversal, WHERE for filters, OPTIONAL MATCH when relationships might not exist
- Always ORDER BY and LIMIT for large datasets
- Return names (not IDs) with meaningful aliases using AS
- Use count(DISTINCT x) for aggregations
- For vague questions, do not answer

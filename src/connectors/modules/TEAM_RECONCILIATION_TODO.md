# Team Reconciliation & Mapping TODO

**Priority:** High  
**Status:** Not Started  
**Area:** Cross-Module (GitHub + Jira)

## Problem Statement

Team names and compositions are **not consistent** between Jira and GitHub in real-world organizations:

1. **Lexicographic Differences** - Names don't match exactly
   - Jira: "Platform Team"
   - GitHub: "platform-team" or "Platform Engineering"

2. **Organizational Inconsistencies** - Poor data hygiene across systems
   - Different teams use different naming conventions
   - Abbreviations vs full names ("Infra" vs "Infrastructure Team")
   - Historical names vs current names

3. **Membership Mismatches** - Same team name, different people
   - Jira team: 5 developers working on epics
   - GitHub team: 8 people (includes designers, PMs)
   - Scrum team composition != GitHub organization team

### Current Impact

The current implementation creates **separate Team stub nodes** for teams from each system, even when they represent the same logical team. This results in:

- Duplicate Team nodes in the graph
- Analytics split across multiple nodes
- Inaccurate team metrics and queries
- Incomplete picture of team membership and capacity

## Solution Needed

Build a **user-driven workflow** that allows users to:
1. Review teams discovered from both Jira and GitHub
2. Map teams that represent the same logical team
3. Define canonical team names and reconcile duplicate nodes
4. **Define custom teams** independent of Jira/GitHub (user-defined teams)
5. Support mixed approach: some teams from systems, some user-defined
6. Handle edge cases (one-to-many, many-to-one mappings)

This will require:
- Discovery/reporting tool to identify potential duplicates
- Configuration file for user-defined team mappings and custom team definitions
- Reconciliation script to merge duplicate nodes
- Support for creating teams that don't exist in either system
- Interactive wizard for guided mapping process

---

## Related Files

- `modules/jira/team_stub_handler.py` - Creates Jira team stubs
- `modules/github/new_team_handler.py` - Creates GitHub teams
- `db/models.py` - Team dataclass and merge_team()
- `scripts/find_stub_issues.py` - Currently shows stub teams

**Owner:** TBD  
**Estimated Effort:** 3-4 weeks  
**Dependencies:** None (can start anytime)

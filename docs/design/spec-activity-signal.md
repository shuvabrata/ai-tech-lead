# ActivitySignal Specification Document

This document defines the specification for the ActivitySignal schema and event-driven framework. ActivitySignal is a generic, extensible, and source-agnostic event format for representing and processing nodes and relationships from systems such as Jira, GitHub, and others. The specification ensures consistent, asynchronous, and decoupled ingestion and processing of graph data across producers and consumers.

---

## 2. Schema Structure

### 2.1 Minimal ActivitySignal Schema

```json
{
  "signal_id": "uuid-1234",
  "source": "jira",
  "entity_type": "Issue",
  "external_id": "PROJ-123",
  "source_config": "https://mycompany.atlassian.net",
  "connector_url": "https://wba-ai/connectors/jira/instance-1",
  "event_time": "2026-04-29T15:00:00Z",
  "ingestion_time": "2026-04-30T12:00:00Z",
  "version": "1.0",
  "attributes": {
    "summary": "Fix login bug",
    "status": "In Progress",
    "assignee": "alice@example.com"
  },
  "relationships": [
    {
      "type": "BELONGS_TO",
      "direction": "OUT",
      "target": {
        "source": "jira",
        "entity_type": "Epic",
        "external_id": "EPIC-42"
      }
    },
    {
      "type": "ASSIGNED_TO",
      "direction": "OUT",
      "target": {
        "source": "jira",
        "entity_type": "Person",
        "external_id": "alice@example.com"
      }
    }
  ]
}
```

---

## 3. Canonical Node Identity

The tuple (`source`, `entity_type`, `external_id`) MUST be treated as the unique, canonical identifier for a node. All ActivitySignal consumers MUST upsert nodes based on this composite key, ensuring no duplicates exist for the same logical entity across all sources.

**Canonical node identity (composite key):**
- `source`
- `entity_type`
- `external_id`
These three fields together uniquely identify a node in the graph.

**`external_id` format convention:**

Producers MUST construct `external_id` as `<source>_<entity_type_lower>_<raw_id>`, for example:

| Entity | `external_id` example |
|---|---|
| GitHub Repository | `github_repo_my_repo` |
| GitHub Branch | `github_branch_my_repo_main` |
| GitHub Commit | `github_commit_my_repo_abc12345` |
| GitHub PR | `github_pr_my_repo_42` |
| GitHub/Jira Person | `github_person_alice` / `jira_person_557058:abc` |
| Jira Project | `jira_project_10000` |
| Jira Initiative | `jira_initiative_10086` |
| Jira Epic | `jira_epic_10001` |
| Jira Sprint | `jira_sprint_34` |
| Jira Issue | `jira_issue_10040` |

This namespacing prevents ID collisions between sources and entity types, since all nodes share the same `id` property in Neo4j regardless of label.

---

## 4. Supported Node Types and Mandatory Attributes

| Node Type    | Mandatory Attributes (in `attributes`)         | Description/Notes                         |
|--------------|-----------------------------------------------|-------------------------------------------|
| Project      | id, key, name                                 | Jira project; may include description, type, status, url, lead (Person) |
| Initiative   | id, key, summary, priority, status, created_at | Jira initiative; may include duedate, updated_at, relationships to Project/Epics |
| Epic         | id, key, summary, priority, status, created_at | Jira epic; may include duedate, updated_at, relationships to Initiative/Issues |
| Sprint       | id, name, state, status                       | Jira sprint; may include goal, start_date, end_date, url |
| Issue        | id, key, summary, priority, status, issue_type, created | Jira issue; may include duedate, updated, relationships to Epic/Sprint/Assignee |
| Repository   | id, full_name, name, created_at, updated_at, url | GitHub repository; may include description, default_branch, owner (Person/Org), collaborators, teams, branches |
| Branch       | name, commit_sha                              | GitHub branch; may include protected, default, relationships to Repository/Commits |
| Commit       | sha, message, author, committed_date          | GitHub commit; may include committer, parents, files, relationships to Person |
| PullRequest  | id, number, title, state, created_at, user    | GitHub PR; may include updated_at, merged_at, base_branch, head_branch, commits |
| Person       | id, name                                      | User/person; may include email, login, displayName, relationships (authored/assigned/owns) |
| Team         | id, name, slug                                | GitHub team; may include description, members |

**Note:**
- All node types may include additional custom attributes in the `attributes` dict.
- Relationships are described in the `relationships` array, referencing other nodes by (source, entity_type, external_id).
- The set of supported node types is fixed and must be updated in the spec to add new types.

---

## 5. Supported Relationship Types

| Relationship Type | Description/Notes |
|-------------------|------------------|
| BELONGS_TO        | Node belongs to another entity (e.g., Issue → Epic, Epic → Initiative, Branch → Repository) |
| ASSIGNED_TO       | Node is assigned to a Person (e.g., Issue → Person) |
| AUTHORED_BY       | Node was authored by a Person (e.g., Commit → Person, PullRequest → Person) |
| MEMBER_OF         | Person is a member of a Team |
| OWNS              | Person or Team owns a Repository |
| PARENT_OF         | Parent-child relationship (e.g., Epic → Issue, Initiative → Epic) |
| PART_OF           | Node is part of another entity (e.g., File → Commit, Commit → Branch) |
| COLLABORATES_ON   | Person collaborates on a Repository or Project |
| REVIEWS           | Person reviews a PullRequest |
| MERGED_INTO       | PullRequest merged into Branch |
| RELATED_TO        | Generic related-to relationship (use sparingly; prefer specific types) |

**Note:**
- All relationships must use one of the above types.
- The set of supported relationship types is fixed and must be updated in the spec to add new types.

---

## 6. Event Metadata & Provenance

- Required metadata fields: `source_config`, `connector_url`, `event_time`, `ingestion_time`, `version`.
- All of these fields are required for every ActivitySignal.
- Ensures every signal is fully traceable to its source, connector, and time of occurrence.

---

## 7. Relationship Handling

- The `relationships` array in ActivitySignal represents the observed state of relationships for the node at the time of the event.
- Each relationship object must include:
  - `type`: The relationship type (see Supported Relationship Types)
  - `direction`: (Optional) The direction of the relationship (e.g., OUT, IN). If omitted, consumers MUST default to OUT.
  - `target`: A dict of properties sufficient to uniquely identify the target node (e.g., source, entity_type, external_id, or other identifying attributes)
- Relationship creation or deletion is NOT explicitly signaled by the producer. Instead, the ActivitySignal producer emits the current observed state at a given time.
- The consumer is responsible for inferring relationship creation or deletion by comparing the sequence of ActivitySignals over time (i.e., by diffing the time series of events).
- The event log is append-only and time-ordered. No destructive actions are performed on the event log itself.

---



---

## 9. Error Handling & Validation

- ActivitySignal consumers are responsible for validating incoming signals against the schema. Signals that fail validation (e.g., missing required fields, invalid types) must be rejected and stored in a temporary quarantine location for further inspection or remediation.
- The specification does not require or enforce validation on the producer side, but producers are encouraged to emit only valid signals.
- For out-of-order events (e.g., a relationship references a node not yet seen), consumers must create a stub node with minimal information, to be updated when the full node signal arrives.
- The schema does not include any status, error, or incompleteness hints. All signals are treated as atomic, append-only events, and completeness is managed by the consumer's event processing logic.

---

## 10. Idempotency, Deduplication, and Event Ordering

- Each ActivitySignal must have a unique, immutable `signal_id` (UUID). If not provided by the producer, the consumer must generate one upon ingestion.
- Consumers are responsible for deduplication. Duplicate signals (same `signal_id`) must be rejected or ignored.
- For logical deduplication and upsert, consumers should use the canonical node identity (`source`, `entity_type`, `external_id`).
- Event ordering is managed by `event_time` and `ingestion_time`. Consumers must process signals in time order for each node to ensure correct state reconstruction.
- The event log is strictly append-only and time-ordered. There are no explicit “replaces” or “supersedes” fields; updates are modeled as new events.

---

## 11. Security, Privacy, and Compliance

- The ActivitySignal schema does not include fields for data classification, sensitivity, or compliance requirements.
- No redaction or masking of sensitive information is required or recommended at the schema level; all relevant data should be included in the signal for full utility.
- There are no specific compliance or audit requirements imposed by this specification. Security and privacy controls are the responsibility of downstream systems and operational policies.

---

## 12. Producer and Consumer Responsibilities

### 12.1 Producer Responsibilities
- Emit ActivitySignals that conform to this specification.
- Include all required fields and use only supported node and relationship types.
- Use batch-level metadata where appropriate for efficiency.

### 12.2 Consumer Responsibilities
- Validate all incoming ActivitySignals against the schema.
- Deduplicate signals using `signal_id` and canonical node identity.
- Store invalid signals in a quarantine location for remediation.
- Create stub nodes for out-of-order references.
- Process signals in time order for each node.
- Treat each ActivitySignal as an atomic, append-only event.

---

## 13. Glossary

- **ActivitySignal:** A single event describing a node and its relationships at a point in time.
- **Node:** An entity in the graph (e.g., Issue, Project, Person).
- **Relationship:** An edge between two nodes, with a type and direction.
- **Canonical Node Identity:** The tuple (source, entity_type, external_id) uniquely identifying a node.
- **Stub Node:** A placeholder node created when a referenced node does not yet exist.

- **Consumer:** A system or process that ingests, validates, and processes ActivitySignals.
- **Producer:** A system or process that emits ActivitySignals from a source system.

---

## 14. Extensibility Process

- To propose a new node or relationship type, submit a change to this specification and notify all downstream consumers.
- All changes must be reviewed and approved before implementation.
- The set of supported types must be kept in sync across all producers and consumers.

---

## 15. Example ActivitySignals

### Example 1: Jira Issue
```json
{
  "signal_id": "uuid-5678",
  "source": "jira",
  "entity_type": "Issue",
  "external_id": "PROJ-456",
  "source_config": "https://mycompany.atlassian.net",
  "connector_url": "https://wba-ai/connectors/jira/instance-1",
  "event_time": "2026-04-29T16:00:00Z",
  "ingestion_time": "2026-04-30T12:05:00Z",
  "version": "1.0",
  "attributes": {
    "summary": "Add new login feature",
    "status": "To Do",
    "priority": "High",
    "assignee": "bob@example.com"
  },
  "relationships": [
    {
      "type": "BELONGS_TO",
      "direction": "OUT",
      "target": {
        "source": "jira",
        "entity_type": "Epic",
        "external_id": "EPIC-99"
      }
    }
  ]
}
```

### Example 2: GitHub Commit
```json
{
  "signal_id": "uuid-9012",
  "source": "github",
  "entity_type": "Commit",
  "external_id": "abc123def456",
  "source_config": "https://github.com/org/repo",
  "connector_url": "https://wba-ai/connectors/github/instance-2",
  "event_time": "2026-04-28T10:00:00Z",
  "ingestion_time": "2026-04-30T12:10:00Z",
  "version": "1.0",
  "attributes": {
    "message": "Initial commit",
    "author": "alice@example.com",
    "committed_date": "2026-04-28T10:00:00Z"
  },
  "relationships": [
    {
      "type": "AUTHORED_BY",
      "direction": "OUT",
      "target": {
        "source": "github",
        "entity_type": "Person",
        "external_id": "alice@example.com"
      }
    }
  ]
}
```

---

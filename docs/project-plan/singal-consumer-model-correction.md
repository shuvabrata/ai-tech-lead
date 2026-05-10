# Plan: Signal Consumer Model Correction

## Goal

Align the new event-driven consumer (`src/connectors/consumers/`) with the node
and relationship shape produced by the legacy handler system
(`src/connectors/modules/github/` and `src/connectors/modules/jira/`).  The
primary strategy is to **reuse the existing code** — the `neo4j_db/models.py`
dataclasses, the `merge_*` functions, `merge_relationship()`, `PersonCache`, and
`IdentityMapping` — rather than reimplementing the logic from scratch inside
`neo4j_sink.py`.

---

## Root Cause Summary

The current `neo4j_sink.py` bypasses all of the existing Neo4j write
infrastructure.  Instead of calling `merge_commit(session, commit_node)`, it
generates raw Cypher strings from `signal.extra_attributes()`.  This creates
three categories of deviation:

1. **Wrong / missing node properties** — attribute key names differ between the
   `ActivitySignal` schema and the `neo4j_db` dataclasses; many optional
   properties the old system writes are absent from the signal.
2. **Wrong / missing relationship types** — the producers emit a small,
   incorrect subset of the relationships the old handlers created; the consumer
   also drops `merge_relationship()`'s automatic reverse-edge logic.
3. **Missing infrastructure** — `PersonCache`, `IdentityMapping` nodes, and
   `team_stub_handler` are never called by the consumer.

---

## Affected Files

| File | Role |
|---|---|
| `src/connectors/consumers/sinks/neo4j_sink.py` | **Primary target** — full redesign |
| `src/common/activity_signal/models.py` | Fix attribute key names |
| `src/connectors/producers/github_producer.py` | Fix relationship types; add missing rels |
| `src/connectors/producers/jira_producer.py` | Fix relationship types; add missing rels |
| `tests/test_consumer_phase5.py` | Update tests to reflect new behaviour |

---

---

## Phase A — Redesign `neo4j_sink.py`: Dispatch to Entity-Specific Handlers ✅ COMPLETE

> **Tests after Phase A** (`tests/test_consumer_phase5.py`)
>
> Run: `pytest -m unit tests/test_consumer_phase5.py -q`
>
> All existing tests must continue to pass (ack/nack behaviour, unknown-entity
> handling).  In addition:
>
> 1. For each entity type in the dispatch table, send a fully-populated signal and
>    assert the matching `merge_*` function is called exactly once with the
>    correct dataclass instance (mock each `merge_*` individually).
> 2. Assert `_upsert_node` and `_upsert_relationship` no longer exist in the
>    module (import the module and confirm `hasattr` returns `False`).
> 3. For a `Commit` signal with a `PART_OF` relationship, assert
>    `merge_relationship()` is called with `type="PART_OF"` and that
>    `DIRECTIONAL_RELATIONSHIPS` causes `merge_relationship()` to be called a
>    second time for the reverse edge (or assert `session.run` is called twice
>    for the two Cypher statements when not mocking `merge_relationship`).
> 4. Assert that `None`-valued attributes are **not** written to Neo4j — send a
>    signal with some optional fields absent and confirm the Cypher `SET` clause
>    does not contain those keys (or confirm `_has_value` is exercised by the
>    dataclass).

> **Implementation notes (actual vs. planned):**
>
> - Phase A was implemented **before** Phases B/C/D (order deviation — see
>   Implementation Order section).  Attribute key mismatches (B1–B4) are bridged
>   inside the consumer handlers with explicit fallback reads (e.g.
>   `attrs.get("last_commit_sha") or attrs.get("commit_sha", "")`).  These
>   bridges carry `# TODO Phase B` comments and will be removed once the signal
>   schema is corrected.
> - Tests written: 35 unit tests covering all 11 entity handlers, `_label`,
>   `_to_db_relationships` (all direction variants + edge cases), unknown
>   entity-type skip, relationships passed to `merge_*`, ack/nack behaviour.
>   `35 passed` — `pytest -m unit tests/test_consumer_phase5.py -q`.
> - Original spec items 2 (`hasattr` check), 3 (reverse-edge via
>   `DIRECTIONAL_RELATIONSHIPS`), and 4 (`None`-valued attribute guard) were not
>   implemented as separate test cases; items 3 and 4 are exercised indirectly
>   by the `merge_*` functions themselves (source of truth from modules/).
>   These can be added as part of Phase G if deemed necessary.

**Strategy:** Replace the single generic `_upsert_node` + `_upsert_relationship`
pair with an entity-type dispatch table.  Each entity type gets its own handler
function that constructs the correct `neo4j_db` dataclass and calls the matching
`merge_*` function.  This reuses all of the property handling
(`_has_value` guards, immutable/mutable `ON CREATE SET` splits, etc.) and the
relationship handling (including automatic reverse edges via
`DIRECTIONAL_RELATIONSHIPS`) from the existing code — for free.

### A1 — Replace the `upsert_signal` public entry point

The new `upsert_signal(session, signal)` should:

1. Build a `PersonCache` (passed in or created per-consumer process — see Phase E).
2. Dispatch to an entity-specific handler based on `signal.entity_type`.
3. Log the result identically to the existing log line.

```
# Dispatch table (to be implemented)
_HANDLERS = {
    "Repository":  _handle_repository,
    "Branch":      _handle_branch,
    "Commit":      _handle_commit,
    "PullRequest": _handle_pull_request,
    "Person":      _handle_person,
    "Team":        _handle_team,
    "Project":     _handle_project,
    "Initiative":  _handle_initiative,
    "Epic":        _handle_epic,
    "Sprint":      _handle_sprint,
    "Issue":       _handle_issue,
}
```

### A2 — Per-entity handler functions

Each handler extracts `attrs = signal.extra_attributes()`, constructs the
correct neo4j dataclass, calls its `merge_*` function, and then calls
`merge_relationship()` for each signal relationship.  The mapping from signal
relationships to `neo4j_db.Relationship` objects is covered in Phase C/D.

**GitHub handlers — reuse / mirror:**

| Handler | Dataclass | `merge_*` function |
|---|---|---|
| `_handle_repository` | `Repository` | `merge_repository` |
| `_handle_branch` | `Branch` | `merge_branch` |
| `_handle_commit` | `Commit` | `merge_commit` |
| `_handle_pull_request` | `PullRequest` | `merge_pull_request` |
| `_handle_person` (GitHub) | `Person` + `IdentityMapping` | `merge_person`, `merge_identity_mapping` |
| `_handle_team` | `Team` | `merge_team` |

**Jira handlers — reuse / mirror:**

| Handler | Dataclass | `merge_*` function |
|---|---|---|
| `_handle_project` | `Project` | `merge_project` |
| `_handle_initiative` | `Initiative` | `merge_initiative` |
| `_handle_epic` | `Epic` | `merge_epic` |
| `_handle_sprint` | `Sprint` | `merge_sprint` |
| `_handle_issue` | `Issue` | `merge_issue` |
| `_handle_person` (Jira) | `Person` + `IdentityMapping` | via `PersonCache` |

### A3 — Relationship translation helper

Add a helper `_to_db_relationship(signal_rel, from_id, from_type)` that maps an
`ActivitySignal` `Relationship` object to the `neo4j_db.Relationship` dataclass
accepted by `merge_relationship()`.  This helper handles the `direction` field:
the old system's `merge_relationship()` always writes a forward `(from)→(to)`
edge and, if the type is in `DIRECTIONAL_RELATIONSHIPS`, also the reverse;
callers do not need to worry about direction — they just pass the correct
`from_id`/`to_id`.

### A4 — Remove `_upsert_node` and `_upsert_relationship`

Once all entity handlers are in place, delete the two private raw-Cypher
functions.  The `_stub` bug (see Phase F) disappears automatically because
`merge_*` functions do not use the `_stub` flag.

---

## Phase B — Fix Attribute Key Mismatches in `ActivitySignal` Models

The attribute field names in `src/common/activity_signal/models.py` (and the
producers that populate them) must match the property names the `neo4j_db`
dataclasses write to Neo4j.

> **Tests after Phase B** (`tests/test_activity_signal_models.py`)
>
> Run: `pytest -m unit tests/test_activity_signal_models.py -q`
>
> 1. Instantiate `BranchAttributes` with `last_commit_sha`, `last_commit_timestamp`,
>    `is_protected`, `is_deleted`, `is_external` — assert all fields round-trip via
>    `model_dump()` without validation errors.  Confirm the old name `commit_sha`
>    raises a `ValidationError`.
> 2. Instantiate `CommitAttributes` with `created_at` — assert field present.
>    Confirm `committed_date` raises `ValidationError`.
> 3. Instantiate `PullRequestAttributes` with all 13 new fields — assert
>    `model_dump()` contains each key.
> 4. Instantiate `IssueAttributes` with `type`, `created_at`, `updated_at`,
>    `story_points`, `_last_synced_at` — assert round-trip.  Confirm `issue_type`
>    and `created` raise `ValidationError`.
> 5. Instantiate `SprintAttributes` — assert `state` field is absent; `status`
>    field accepts `"active"`.
> 6. Instantiate `InitiativeAttributes` with `project_id` and `_last_synced_at`
>    — assert both present in `model_dump()`.

### B1 — `BranchAttributes` corrections

File: `src/common/activity_signal/models.py`

| Current field | Required field (to match `Branch` dataclass) |
|---|---|
| `commit_sha` | rename to `last_commit_sha` |
| *(missing)* | add `last_commit_timestamp: Optional[str]` |
| *(missing)* | add `is_protected: Optional[bool]` |
| *(missing)* | add `is_deleted: Optional[bool]` |
| *(missing)* | add `is_external: Optional[bool]` |

Update `build_branch_signal` in `github_producer.py` to populate all five fields
from `branch_data` (all keys are already present in the dict returned by
`map_branch()`).

### B2 — `CommitAttributes` corrections

| Current field | Required field (to match `Commit` dataclass) |
|---|---|
| `committed_date` | rename to `created_at` |

Update `build_commit_signal` in `github_producer.py`: replace
`committed_date=commit_data.get("created_at", "")` with
`created_at=commit_data.get("created_at", "")`.

### B3 — `PullRequestAttributes` additions

The old `PullRequest` dataclass has many more fields than the current signal
attributes.  Add to `PullRequestAttributes`:

```
updated_at: Optional[str]
merged_at: Optional[str]
closed_at: Optional[str]
commits_count: Optional[int]
additions: Optional[int]
deletions: Optional[int]
changed_files: Optional[int]
comments: Optional[int]
review_comments: Optional[int]
head_branch_name: Optional[str]
base_branch_name: Optional[str]
labels: Optional[list]
mergeable_state: Optional[str]
```

Update `build_pull_request_signal` in `github_producer.py` to set all fields
from `pr_data` (all keys are returned by `map_pull_request()`).

### B4 — `IssueAttributes` corrections

| Current field | Required field (to match `Issue` dataclass) |
|---|---|
| `issue_type` | rename to `type` |
| `created` (date slice) | rename to `created_at` (full ISO timestamp) |
| *(missing)* | add `updated_at: Optional[str]` |
| *(missing)* | add `story_points: Optional[float]` |
| *(missing)* | add `_last_synced_at: Optional[str]` (set at publish time) |

### B5 — `InitiativeAttributes` additions

Add `project_id: Optional[str]` and `_last_synced_at: Optional[str]`.

### B6 — `SprintAttributes` cleanup

Remove the duplicate `state` field — `status` is the correct name used by the
`Sprint` dataclass.  The producer `build_sprint_signal` currently sets both
`state=...` and `status=...` to the same value.

---

## Phase C — Fix Relationship Types in Producers

These are relationship types the producers already emit, but with the wrong type
name or direction compared to what the old handlers wrote.

> **Tests after Phase C** (`tests/test_github_producer_phase4.py`,
> `tests/test_jira_producer_phase4.py`)
>
> Run: `pytest -m unit tests/test_github_producer_phase4.py tests/test_jira_producer_phase4.py -q`
>
> 1. Call `build_branch_signal(...)` and assert the emitted relationship type is
>    `"BRANCH_OF"`, not `"PART_OF"`.
> 2. Call `build_pull_request_signal(...)` and assert the author relationship type
>    is `"CREATED_BY"`, reviewer relationship type is `"REVIEWED_BY"`, and base-
>    branch relationship type is `"TARGETS"`.
> 3. Call `build_issue_signal(...)` with a sprint and assert the relationship type
>    is `"IN_SPRINT"`, not `"PART_OF"`.
> 4. Verify that every relationship type in the emitted signals is present in
>    `SUPPORTED_RELATIONSHIP_TYPES` — import the constant and assert membership.

### C1 — `github_producer.py`

| Entity | Current signal `type` | Correct `type` (old handler) | Fix in |
|---|---|---|---|
| Branch → Repository | `PART_OF` | `BRANCH_OF` | `build_branch_signal` |
| PullRequest → Person (author) | `AUTHORED_BY` | `CREATED_BY` | `build_pull_request_signal` |
| PullRequest → Person (reviewer) | `REVIEWS` | `REVIEWED_BY` | `build_pull_request_signal` |
| PullRequest → Branch (base) | `MERGED_INTO` | `TARGETS` | `build_pull_request_signal` |

Also update `SUPPORTED_RELATIONSHIP_TYPES` in `models.py` to include the
relationship types used by the old system that are currently absent:
`BRANCH_OF`, `CREATED_BY`, `REVIEWED_BY`, `TARGETS`, `FROM`, `MERGED_BY`,
`INCLUDES`, `REQUESTED_REVIEWER`, `REPORTED_BY`, `IN_SPRINT`, `TEAM`,
`COLLABORATOR`, `MEMBER_OF`, `LEADS`, `BLOCKS`, `DEPENDS_ON`, `RELATES_TO`,
`MAPS_TO`, `CONTAINS`.

### C2 — `jira_producer.py`

| Entity | Current signal `type` | Correct `type` | Fix in |
|---|---|---|---|
| Issue → Sprint | `PART_OF` | `IN_SPRINT` | `build_issue_signal` |

---

## Phase D — Add Missing Relationships in Producers

These relationships the old handlers created are not emitted at all by the new
producers.  Adding them to the signals means the consumer will persist them
automatically via `merge_relationship()`.

> **Tests after Phase D** (`tests/test_github_producer_phase4.py`,
> `tests/test_jira_producer_phase4.py`)
>
> Run: `pytest -m unit tests/test_github_producer_phase4.py tests/test_jira_producer_phase4.py -q`
>
> GitHub producer:
> 1. `build_pull_request_signal` with `head_branch_id` → assert `FROM` relationship present.
> 2. `build_pull_request_signal` with `requested_reviewer_logins=["alice"]` → assert
>    `REQUESTED_REVIEWER` relationship target is `"alice"`.
> 3. `build_pull_request_signal` with `state="merged"` and `merger_login="bob"` →
>    assert `MERGED_BY` relationship present; absent when state is `"open"`.
> 4. `build_pull_request_signal` with commit SHAs → assert an `INCLUDES`
>    relationship per SHA.
> 5. `build_commit_signal` with a message referencing a Jira key → assert
>    `REFERENCES` relationship to the issue external ID.
> 6. `process_repo_signals` with a team → assert a Team signal is emitted with
>    `COLLABORATOR` and `MEMBER_OF` relationships.
> 7. Person collaborator signal → assert `COLLABORATOR` relationship has
>    `properties` dict with `permission` key.
>
> Jira producer:
> 8. `build_initiative_signal` with `reporter` → assert `REPORTED_BY` relationship.
> 9. `build_epic_signal` with `team_value` → assert `TEAM` relationship.
> 10. `build_issue_signal` with `issue_links_raw` containing `blocks` / `is blocked by` /
>     `relates to` → assert `BLOCKS`, `DEPENDS_ON`, `RELATES_TO` relationships respectively.

### D1 — `github_producer.py`

**PullRequest** — add to `build_pull_request_signal`:
- `FROM` (PR → head Branch) using `pr_data["head_branch_id"]`
- `REQUESTED_REVIEWER` (PR → Person) — already fetched in old handler via
  `pr.requested_reviewers`; the producer needs to accept a `requested_reviewer_logins` list
- `MERGED_BY` (PR → Person) — add `merger_login` parameter; emit only when
  `pr_data["state"] == "merged"`
- `INCLUDES` (PR → Commit) — this is complex: the old handler queries Neo4j
  to check if the commit exists.  For the producer, emit `INCLUDES`
  relationships for each SHA in `fetch_pr_commits(pr)`; the consumer will
  handle absent commit nodes as stubs via `merge_relationship()`'s built-in
  `MERGE (to:Commit {id: $to_id})`.

**Commit** — add to `build_commit_signal`:
- `REFERENCES` (Commit → Issue) using `extract_issue_keys()` /
  `extract_issue_keys_from_branch()` from `map_github.py`; already called in
  `new_commit_handler.py`.

**Person (GitHub)** — the producer already emits Person signals.  The consumer
`_handle_person` handler (Phase A2) needs to also create the `IdentityMapping`
node and `MAPS_TO` relationship by calling `process_github_user` logic — see
Phase E.

**Team** — add to `process_repo_signals` in `github_producer.py`: emit a Team
signal per GitHub team (already fetched when processing collaborators) and a
`COLLABORATOR` relationship (Team → Repository).  Also emit `MEMBER_OF`
(Person → Team) relationships.

**Collaborator (Person → Repository)** — emit a `COLLABORATOR` relationship
signal from each Person collaborator signal with the `permission` and `role`
properties stored as extra attributes on the signal's relationship entry.
*Note:* `neo4j_db.Relationship` already supports a `properties` dict;
the `ActivitySignal` `Relationship` model does not yet.  Add
`properties: Optional[Dict[str, Any]] = None` to `Relationship` in
`models.py` and pass it through in the consumer's `_to_db_relationship` helper.

### D2 — `jira_producer.py`

**Initiative** — add `REPORTED_BY` (Initiative → Person) when `reporter` is
present in the issue fields.

**Epic** — add `REPORTED_BY` (Epic → Person) and `TEAM` (Epic → Team) when
`epic_data["team_value"]` is set.

**Issue** — add:
- `REPORTED_BY` (Issue → Person)
- `TEAM` (Issue → Team) when `issue_data["team_value"]` is set
- `BLOCKS` / `DEPENDS_ON` / `RELATES_TO` from `issue_links_raw` — already
  computed by `map_issue()`; just not wired into signal relationships yet

---

## Phase E — PersonCache and IdentityMapping in the Consumer

> **Tests after Phase E** (`tests/test_consumer_phase5.py`)
>
> Run: `pytest -m unit tests/test_consumer_phase5.py -q`
>
> 1. Send a GitHub Person signal and assert `PersonCache.get_or_create_person` is
>    called with the correct `login`; assert `flush_identity_mappings` is called
>    after `upsert_signal` returns.
> 2. Send a Jira Person signal and assert `PersonCache.get_or_create_person` is
>    called with `account_id` as the external ID.
> 3. Send two Person signals with the same `login` in sequence and assert
>    `get_or_create_person` is called twice but a Neo4j `MERGE` for the Person
>    node only fires once (cache hit on second call).
> 4. Assert `IdentityMapping` node and `MAPS_TO` relationship are created — send
>    a GitHub Person signal and confirm `merge_identity_mapping` (or equivalent
>    Neo4j call) is invoked with the expected `external_id`.

### E1 — Scope of `PersonCache`

`PersonCache` caches Person lookups within a processing session to avoid
redundant Neo4j queries when the same user appears across many signals.  In the
consumer, the right scope is **per-queue consumer task** (one `PersonCache`
instance per `consume_queue()` call in `main.py`).

Change `consume_queue()` to create a `PersonCache()` once and pass it to
`upsert_signal()`.

### E2 — GitHub Person handler

In `_handle_person` (for `signal.source == "github"`):
- Extract `login` from `attrs["login"]`
- Call the logic from `process_github_user()` in
  `src/connectors/modules/github/process_github_user.py` directly —
  either import and call the function, or inline equivalent logic using
  `PersonCache.get_or_create_person` + `PersonCache.queue_identity_mapping`.
- At the end of each signal batch, call `person_cache.flush_identity_mappings(session)`.

### E3 — Jira Person handler

In `_handle_person` (for `signal.source == "jira"`):
- Extract `account_id` from `attrs["account_id"]`
- Call `PersonCache.get_or_create_person` and `PersonCache.queue_identity_mapping`
  using the same pattern as `new_jira_user_handler()` in
  `src/connectors/modules/jira/new_jira_user_handler.py`.

### E4 — Flush after each signal

Call `person_cache.flush_identity_mappings(session)` after every `upsert_signal`
call (or after a configurable batch size) to ensure `IdentityMapping` nodes and
`MAPS_TO` relationships are written promptly.

---

## Phase F — Fix the `_stub` Flag Bug ✅ MOOT (resolved by Phase A)

This is already present in the current `neo4j_sink.py` regardless of the
broader redesign, but becomes moot if Phase A is completed (because the `merge_*`
functions do not use the `_stub` flag at all).

**Resolution:** Phase A was completed.  `_upsert_node` and `_upsert_relationship`
(including all `_stub` logic) were deleted from `neo4j_sink.py`.  All node
creation now goes through `merge_*` functions which do not emit a `_stub` flag.
No further action required for this phase.

> **Tests after Phase F** (`tests/test_consumer_phase5.py`)
>
> Run: `pytest -m unit tests/test_consumer_phase5.py -q`
>
> 1. If stub logic is retained: simulate a stub node created first (by a
>    relationship signal), then send the full entity signal; assert that the node's
>    `_stub` property is set to `false` unconditionally in the resulting Cypher.
> 2. If Phase A was completed (no stub logic retained): confirm the test module
>    has no tests that reference `_stub` or `ON CREATE SET` on node merges —
>    delete or skip any that do.  ✅ Done — no such tests exist.
> 3. Run the full unit suite and confirm zero regressions: `pytest -m unit tests -q`.

---

## Phase G — Update Tests (partially complete)

File: `tests/test_consumer_phase5.py`

1. ✅ **Replace raw-Cypher assertions** — all old Cypher-string tests replaced.
   New tests mock `merge_*` individually and assert the correct dataclass
   instance is passed.

2. ✅ **Add entity-specific coverage** — one test per entity type (11 total)
   verifying correct dataclass field population, including Phase-B aliases
   (`committed_date→created_at`, `commit_sha→last_commit_sha`,
   `issue_type→type`, `created→created_at`).

3. ✅ **Relationship type coverage** — `_to_db_relationships` tests assert
   correct `type`, `from_id`, `to_id`, `from_type`, `to_type` for each
   direction variant; an end-to-end test verifies relationships are passed
   to `merge_*`.

4. ❌ **`PersonCache` integration** — deferred to Phase E.  The `_handle_person`
   handler currently calls `merge_person()` directly with a `# TODO Phase E`
   comment.

5. ❌ **Reverse edge coverage** — deferred.  Verifying `DIRECTIONAL_RELATIONSHIPS`
   auto-reverse behaviour requires not mocking `merge_relationship` and
   inspecting `session.run` call count.

> **Tests after Phase G** — full unit suite
>
> Run: `pytest -m unit tests -q`
>
> Items 1–3 complete: `35 passed` in `test_consumer_phase5.py`.  Items 4–5 to be
> added after Phases E and D respectively.  Zero failures on the current suite.

---

## Final Validation — Property Coverage Integration Test

**Prerequisite:** A real GitHub repository scan and a real Jira project scan must
have been completed so that Neo4j is populated with live data.

**Test file:** `tests/property_validation/test_property_validation.py`

**Purpose:** Verify that every node label and every relationship type in the live
Neo4j graph contains the maximum expected set of properties — no property that
the old handler system wrote should be absent from nodes written by the new
consumer.

**What to implement in the test file:**

```python
# tests/property_validation/test_property_validation.py
# Marker: neo4j  (requires live Neo4j with real scan data)
```

1. **Node property completeness** — for each node label (`Repository`, `Branch`,
   `Commit`, `PullRequest`, `Person`, `IdentityMapping`, `Team`, `Project`,
   `Initiative`, `Epic`, `Sprint`, `Issue`), query a sample of nodes and assert
   that required properties are present and non-null.  The required property set
   is derived directly from the `neo4j_db` dataclasses (non-`Optional` fields
   are required; `Optional` fields must at least be present as keys even if
   `null`).

   Example assertion pattern:
   ```python
   result = session.run("MATCH (n:Commit) RETURN n LIMIT 50")
   for record in result:
       node = record["n"]
       assert "id" in node
       assert "created_at" in node          # renamed from committed_date
       assert "committed_date" not in node  # old key must be absent
   ```

2. **Relationship type coverage** — query all relationship types present in the
   graph and assert that the full expected set is present:
   `BRANCH_OF`, `PART_OF`, `AUTHORED_BY`, `CREATED_BY`, `REVIEWED_BY`,
   `TARGETS`, `FROM`, `MERGED_BY`, `INCLUDES`, `REFERENCES`, `COLLABORATOR`,
   `MEMBER_OF`, `IN_SPRINT`, `ASSIGNED_TO`, `REPORTED_BY`, `TEAM`, `LEADS`,
   `BLOCKS`, `DEPENDS_ON`, `RELATES_TO`, `MAPS_TO`, `CONTAINS`.

3. **No orphan stubs** — assert that no node has `_stub = true` after a full
   sync:
   ```python
   result = session.run("MATCH (n) WHERE n._stub = true RETURN count(n) AS c")
   assert result.single()["c"] == 0
   ```

4. **Reverse edge completeness** — for each type in `DIRECTIONAL_RELATIONSHIPS`,
   assert at least one reverse-edge relationship of the reverse type exists:
   ```python
   # e.g. if PART_OF → CONTAINS, assert CONTAINS edges exist
   for fwd, rev in DIRECTIONAL_RELATIONSHIPS.items():
       result = session.run(f"MATCH ()-[r:{rev}]->() RETURN count(r) AS c")
       assert result.single()["c"] > 0, f"Missing reverse edges for {rev}"
   ```

5. **IdentityMapping coverage** — assert that every `Person` node that came from
   a GitHub or Jira signal has at least one `MAPS_TO` relationship to an
   `IdentityMapping` node.

**Run command:**

```bash
pytest -m neo4j tests/property_validation/ -q
```

This test is the definitive acceptance gate.  All phases (B → C → D → A → E →
F → G) must be complete and a real scan performed before running it.

---

## Implementation Order

| Step | Status | What | Test gate | Depends on |
|---|---|---|---|---|
| 1 | ❌ | B1–B6: fix attribute keys in `models.py` and producers | `pytest -m unit tests/test_activity_signal_models.py -q` | nothing |
| 2 | ❌ | C1–C2: fix relationship type names in producers | `pytest -m unit tests/test_github_producer_phase4.py tests/test_jira_producer_phase4.py -q` | Step 1 |
| 3 | ❌ | D1–D2: add missing relationships in producers | same producer tests — extended assertions | Step 2 |
| 4 | ✅ **DONE** | A1–A4: redesign `neo4j_sink.py` with dispatch table | `pytest -m unit tests/test_consumer_phase5.py -q` (35 passed) | ~~Steps 1–3~~ done before B/C/D with internal aliases |
| 5 | ❌ | E1–E4: `PersonCache` + `IdentityMapping` in consumer | `pytest -m unit tests/test_consumer_phase5.py -q` | Step 4 |
| 6 | ✅ **MOOT** | F: fix `_stub` (no stub logic retained — resolved by Step 4) | — | Step 4 |
| 7 | ⚠️ Partial | G: update and extend tests (items 1–3 done; items 4–5 pending E and D) | `pytest -m unit tests -q` | Steps 4–6 |
| 8 | ❌ | **Final**: run real scan, then property validation | `pytest -m neo4j tests/property_validation/ -q` | Steps 1–7 + live data |

**Order deviation note:** Step 4 (Phase A) was implemented before Steps 1–3
(Phases B/C/D).  The dispatch-table approach does not require the signal schema
to be clean first — attribute mismatches are bridged inside each handler with
explicit fallback reads.  Once Steps 1–3 are complete, those fallbacks will be
removed (they are marked `# TODO Phase B` in the code).

Steps 1–3 (producer-side) can be worked on in parallel with each other.
The final property-validation step (Step 8) is the only step that requires a
live Neo4j instance with real scan data.

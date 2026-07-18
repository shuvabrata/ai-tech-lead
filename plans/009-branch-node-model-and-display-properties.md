# Plan 009: Branch node — dataclass, display properties, and backfill

> **Executor instructions**: This plan is in **draft** stage. There is an open
> design question (see §4) that needs to be resolved before implementation
> begins. Do not implement until that decision is documented here.

## Status

- **Priority**: P2 (graph UI usability — Branch nodes show blank labels)
- **Effort**: S–M (depends on design choice in §4)
- **Risk**: LOW
- **Depends on**: none
- **Category**: feature / model completeness
- **Planned at**: 2026-07-07
- **Status**: DRAFT — **do not implement**

## Why this matters

The codebase has no `Branch` Neo4j model, but Branch nodes **do** exist in the
graph. They are created as a side-effect of `merge_relationship()` in
`src/connectors/neo4j_db/models.py`, which runs raw Cypher like:

```cypher
MERGE (to:Branch {id: $to_id})
```

This creates nodes with **only** an `id` property — no `_display_name`, no
`url`, no `_last_seen_at`. The graph UI (`neo4j_to_cytoscape()`) reads
`_display_name` to render node labels, so these nodes show up as **blank**.
They also break the identity-resolution pattern that every other entity type
follows.

## Discovery

Confirmed via code audit on 2026-07-07:

| Question | Answer |
|---|---|
| Is there a `Branch` `@dataclass` in `models.py`? | ❌ No |
| Is there a `merge_branch()` function in `models.py`? | ❌ No |
| Is there a `_handle_branch` in `neo4j_sink.py` dispatch table? | ❌ No |
| Does any producer emit a signal with `entity_type="Branch"`? | ❌ No |
| Do Branch nodes exist in Neo4j? | ✅ Yes — as stubs with only `id` |
| How are they created? | `merge_relationship()` → `MERGE (to:Branch {id: $to_id})` |
| Which relationship types target Branch nodes? | `PART_OF` (Commit→Branch), `TARGETS` (PR→base branch), `FROM` (PR→head branch) |
| Does `"FROM"` appear in `DIRECTIONAL_RELATIONSHIPS`? | ❌ No — it's not listed, so only a forward edge is created for `FROM` |

Note: The `FROM` relationship type (PR→head branch) is **not** registered in
`DIRECTIONAL_RELATIONSHIPS` nor `UNDIRECTED_RELATIONSHIPS`. It appears that
`FROM` was intentionally kept as a single-direction edge. `TARGETS` is
registered as `"TARGETS": "TARGETED_BY"` and does get a reverse edge.

## §1 Where Branch nodes are created

There are exactly three relationship types that target `entity_type="Branch"`:

| Relationship | Source | Source file | Line |
|---|---|---|---|
| `PART_OF` | Commit | `build_commit_signal.py` | 73 |
| `TARGETS` | PullRequest | `build_pull_request_signal.py` | 90 |
| `FROM` | PullRequest | `build_pull_request_signal.py` | 105 |

The target ID format is: `{repo_name}::{branch_ref}` (e.g.
`work-behavior-analytics-ai::main`).

No producer ever emits a standalone `ActivitySignal` with
`entity_type="Branch"`.

## §2 Existing pattern for other entity types

Every other labeled node type follows a consistent three-tier architecture:

1. **Model**: `@dataclass` extending `GraphNode` in `models.py` with
   `display_name()`, `to_neo4j_properties()`, and `print_cli()`.
2. **Merge function**: `merge_<type>()` in `models.py` with `_has_value()`
   guarded `SET` clauses for each property, including the 4 computed ones
   (`_display_name`, `_on_hover_name`, `_last_updated_at`, `_created_at`)
   and the operational `_last_seen_at`.
3. **Sink handler**: `_handle_<type>()` in `neo4j_sink.py` that constructs the
   dataclass, calls `set_last_observed_at()`, and delegates to `merge_<type>()`.

Branch nodes skip all three tiers.

## §3 Required components (regardless of design choice)

These are needed in all approaches:

1. **`Branch` dataclass** in `src/connectors/neo4j_db/models.py`:
   ```python
   @dataclass
   class Branch(GraphNode):
       id: str
       name: Optional[str] = None   # the branch ref, e.g. "main"
       url: Optional[str] = None     # GitHub URL to view branch
       created_at: Optional[str] = None
       last_updated_at: Optional[str] = None

       def display_name(self) -> str:
           """Extract branch ref from the id as fallback."""
           if self.name:
               return self.name
           # id format: "github::Branch::repo_name::branch_ref"
           # or:        "repo_name::branch_ref"
           parts = self.id.split("::")
           return parts[-1] if len(parts) >= 2 else self.id

       def to_neo4j_properties(self) -> Dict[str, Any]:
           props = {k: v for k, v in asdict(self).items() if v is not None}
           self._inject_computed_properties(props)
           return props
   ```

2. **`merge_branch()`** function in `models.py`:
   Standard `MERGE ... SET` pattern matching other `merge_*` functions, with
   `_has_value()` guards for all fields including the 4 computed properties.

3. **Import** in `neo4j_sink.py`: Add `Branch` and `merge_branch` to the
   import line from `connectors.neo4j_db.models`.

## §4 ⚠️ OPEN DESIGN QUESTION: How do Branch nodes get populated?

There are two viable approaches. Neither can be chosen without further analysis.

### Option A: Emit a standalone Branch signal from the producer

**What it means**: Add a new `build_branch_signal()` function and call it
whenever a new branch ref is encountered (e.g. during commit processing or PR
processing). The signal carries the branch name, a GitHub URL, and optionally
the `created_at` timestamp. The consumer's dispatch table gets a
`_handle_branch` handler.

**Pros**:
- Follows the established three-tier pattern exactly.
- Branch nodes get `_last_seen_at` via `set_last_observed_at()`.
- Branch data (URL, timestamps) is explicitly modeled.

**Cons**:
- **Requires extra GitHub API calls**. PyGithub's `repo.get_branch(name)` makes
  an API call per branch, and the branch name is often derived from commit/PR
  data rather than from an explicit branch listing. For repos with many branches
  referenced across PRs (head branches of closed PRs that may no longer exist),
  this could generate significant API traffic or 404 errors.
- **May not have enough data available**. When a PR was created from a fork
  (`is_external_head=True`), the head branch belongs to a different repo and
  can't be fetched. When a PR is old and the branch has been deleted,
  `get_branch()` returns 404.
- Requires changes in `process_repo_signals.py` and/or the commit/PR processing
  pipeline to emit Branch signals.

### Option B: Populate Branch nodes inside `merge_relationship()`

**What it means**: Modify `merge_relationship()` in `models.py` to detect when
the `to_type` is `"Branch"` and inject computed display properties directly in
the Cypher query, extracting the branch ref from the `to_id`.

```
MERGE (to:Branch {id: $to_id})
SET to._display_name = split($to_id, '::')[-1]
```

**Pros**:
- **Zero producer changes** — no new signals or API calls.
- Minimal code change — a small conditional or parameter addition in a single
  function.
- Immediate fix — every Branch node gets `_display_name` on the next sync.

**Cons**:
- **Breaks the clean separation of concerns**. `merge_relationship()` is a
  generic topological function — it shouldn't know about domain-specific
  display logic for particular node types.
- Branch nodes still won't have `url`, `created_at`, `_last_seen_at`, or any
  other rich data.
- If a future `_handle_branch` handler is added, the inline logic in
  `merge_relationship()` becomes a second code path that must be kept in sync.

### Option C: Hybrid — Option B now, Option A later

Populate `_display_name` and `_on_hover_name` inside `merge_relationship()` as
a quick fix so the graph UI renders labels immediately, then add a proper Branch
producer signal in a follow-up plan.

### Questions that need answering

Before choosing, the following should be investigated:

1. **How many unique branch references appear across all synced repos?** Run
   a Cypher query to count current Branch nodes and their relationship
   distributions. If the count is small (< 100), Option A is more practical.

2. **What GitHub API cost would Option A incur?** Can we get branch metadata
   (name, URL) from the PR/commit data we already have, without extra API
   calls? The PR object already carries `pr.head.ref` and `pr.base.ref` — can
   we construct the URL and timestamp from existing data?

3. **Do external head branches matter?** For PRs from forks, `head_branch_id`
   is `None` (see `map_github.py:337`). Branches from external forks never
   become Branch nodes at all. If this is acceptable, Option A only needs to
   handle the non-fork case.

4. **What does the graph UI actually show for Branch nodes?** Are they
   meaningful to users, or just intermediate nodes that could be de-emphasized?
   Answer affects whether a full three-tier model is worth the effort.

## §5 Implementation steps (tentative — will change based on §4)

<!-- Steps below assume Option B (quick fix). Rewrite if Option A is chosen. -->

### Step 1: Populate `_display_name` on Branch nodes in `merge_relationship()`

**File**: `src/connectors/neo4j_db/models.py` — `merge_relationship()` function.

Detect `to_type == "Branch"` (or more generically, any to_type that has no
registered handler) and add a `SET to._display_name = split($to_id, '::')[-1]`
clause to the forward MERGE query.

**Verify**: Run a test sync and check that existing Branch nodes now have
`_display_name` populated. Or run the backfill script from Step 2.

### Step 2 (if needed): Backfill existing Branch nodes

**File**: `scripts/backfill_branch_display_properties.py` (new)

One-shot Cypher to set `_display_name` on all Branch nodes that lack it:

```cypher
MATCH (n:Branch)
WHERE n._display_name IS NULL
SET n._display_name = split(n.id, '::')[-1],
    n._on_hover_name = split(n.id, '::')[-1]
RETURN count(n) AS updated
```

### Step 3: Add `Branch` model (for future use)

**File**: `src/connectors/neo4j_db/models.py`

Add the `Branch` dataclass and `merge_branch()` function. This is forward
preparation even if Option B is chosen — it makes the model complete and
unblocks Option A later.

**Verify**: `pytest tests/property_validation/` — the model inspector should
pick up Branch as a new node type if it follows the `GraphNode` ABC pattern.

### Step 4: Add Branch to `create_constraints()` if needed

**File**: `src/connectors/neo4j_db/models.py`

Add a `CREATE CONSTRAINT FOR (n:Branch) REQUIRE n.id IS UNIQUE` if not already
present.

### Step 5: Update `neo4j_to_cytoscape()` if needed

**File**: `src/app/dash_app/pages/graph/utils/data_transform.py`

Verify that the graph UI already falls back gracefully when `_display_name` is
present. Since Plan 006 switched to reading `_display_name` directly with no
fallback, this should work automatically.

**Verify**: Load the Graph page and inspect a Branch node — it should display
the branch ref (e.g. "main") instead of a blank label.

## §6 Testing

- `tests/test_neo4j_node_base.py`: Add test for the `Branch` dataclass
  covering `display_name()` (with and without explicit `name`),
  `to_neo4j_properties()`, and `_inject_computed_properties()`.
- `tests/` (neo4j integration): If Option A is chosen, add an integration test
  that publishes a Branch signal and verifies the node in Neo4j.
- Manual: Run the backfill script against a snapshot of real data and verify
  `_display_name` is populated on all existing Branch nodes.

## §7 Rollback

- If Option B: revert the `merge_relationship()` change. Existing Branch nodes
  retain whatever properties were set.
- If backfill was run: `MATCH (n:Branch) REMOVE n._display_name, n._on_hover_name`.
# Plan 003: Refactor Graph Service God Module

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 5b3a7f7..HEAD -- src/app/api/graph/v1/service.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: L
- **Risk**: HIGH
- **Depends on**: none
- **Category**: tech-debt
- **Planned at**: commit `5b3a7f7`, 2026-06-23

## Why this matters

The `src/app/api/graph/v1/service.py` file has become a God Module. It handles database querying, payload serialization, entity transformation, and complex business logic (e.g. `get_collaboration_network`). This violates single-responsibility principles and creates a high blast radius for changes. Splitting these responsibilities into distinct modules (like `serialization.py` or `transformers.py`) will improve testability, readability, and reduce PyLint errors related to too many statements/locals.

## Current state

- `src/app/api/graph/v1/service.py` is nearly 600 lines long.
- It contains serializers: `_make_serializable`, `_transform_node`, `_transform_relationship`, `_extract_graph_elements_from_value`.
- It contains query execution logic: `execute_and_format_query`, `_format_query_results`.
- It contains business logic: `expand_node`, `get_collaboration_network`.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Typecheck | `mypy src/app/api/graph/v1` | exit 0 |
| Tests     | `pytest -m unit tests/`  | all pass |
| Lint      | `pylint src/app/api/graph/v1` | fewer errors than before |

## Scope

**In scope**:
- `src/app/api/graph/v1/service.py`
- `src/app/api/graph/v1/transformers.py` (NEW)
- Any tests directly importing from `src/app/api/graph/v1/service.py` that need import updates.

**Out of scope**:
- Changing the public API contract (the endpoint schemas).
- Modifying the underlying Neo4j queries.

## Git workflow

- Branch: `advisor/003-refactor-graph-service`
- Commit message: `refactor: split graph service into transformers and logic`

## Steps

### Step 1: Create `transformers.py`

Create a new file `src/app/api/graph/v1/transformers.py`.
Move the following pure functions from `service.py` into this new file:
- `_make_serializable`
- `_transform_node`
- `_transform_relationship`
- `_extract_graph_elements_from_value`

Ensure you import all necessary types (e.g., `Node`, `Relationship`, `Path` from Neo4j, and Pydantic models) in `transformers.py`.

**Verify**: `mypy src/app/api/graph/v1/transformers.py` → exit 0

### Step 2: Update `service.py` imports

In `src/app/api/graph/v1/service.py`, remove the moved functions and import them from `.transformers`.

**Verify**: `mypy src/app/api/graph/v1/service.py` → exit 0

### Step 3: Run the test suite

Run the unit test suite to ensure the refactor hasn't broken the graph formatting logic.

**Verify**: `pytest -m unit tests/` → all pass

## Test plan

- Since this is a structural refactor, existing tests covering `service.py` and graph callbacks should serve as regression tests.
- Verification: `pytest -m unit tests/` → all pass.

## Done criteria

- [ ] `src/app/api/graph/v1/transformers.py` exists and contains the serialization logic.
- [ ] `src/app/api/graph/v1/service.py` no longer contains the serialization functions.
- [ ] `mypy src/app/api/graph/v1` exits 0.
- [ ] `pytest -m unit tests/` exits 0.
- [ ] `plans/README.md` status row updated.

## STOP conditions

- Tests fail after extracting the functions and you cannot trivially resolve the import errors.
- `service.py` has drifted significantly and the target functions no longer exist in the specified form.

## Maintenance notes

- Reviewers should ensure that the extracted functions in `transformers.py` are strictly pure and do not depend on active DB sessions or external state.

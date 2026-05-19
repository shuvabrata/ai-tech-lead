# ActivitySignal Refactoring — Project Plan

## Background

The `ActivitySignal` schema has accumulated inconsistencies across producers and consumers. This plan standardises it across four macro groups, each broken into small independently-testable phases. Every phase leaves the system in a fully working state.

## Decisions Made

| Decision | Choice |
|---|---|
| Migration strategy | Phased; one concern per phase |
| `entity_type` in model | Option C: top-level `@computed_field` via `model_validator(mode='before')` injection; excluded from `*Attributes` serialization |
| `id` uniqueness tuple | `(source, entity_type, id)` at top level of `ActivitySignal` |
| `wba_node_id` format | `"{source}::{entity_type}::{id}"` (PascalCase entity type, `::` separator) |
| `RelationshipTarget` lookup field | `id` (mirrors `ActivitySignal.id`) |
| Strict schema | `extra="forbid"` on all `*Attributes`; known optional fields promoted; `custom: Optional[Dict[str, Any]]` for arbitrary extras |
| `routing_key` | Removed from model; inlined in `rabbitmq.py` as `f"{signal.source}.{signal.entity_type}"` |
| Neo4j clearing | Clear at Macro Group 3 boundary; re-sync from scratch using `scripts/clear_all_data.sh` |

---

## Macro Group 1 — Model Layer

All changes are in `src/common/activity_signal/models.py` and `tests/test_activity_signal_models.py`. No producer or consumer code changes. Each phase ends with a passing test suite.

---

### Phase 1.1 — Promote `id` and `entity_type` to top-level `ActivitySignal`

> **Status:** Not Started

**Goal:** Add `id: str` as a required top-level field. Convert `entity_type` from a `@property` to a `@computed_field` that is injected into `attributes` via `model_validator(mode='before')` before union dispatch.

**Changes — `models.py`:**
- Add `id: str` field to `ActivitySignal` (keep `external_id` for now — it will be removed in Phase 1.15 after all producers are updated in Macro Group 2)
- Add a `@model_validator(mode='before')` on `ActivitySignal` that copies `data['entity_type']` into `data['attributes']['entity_type']` when `attributes` is a dict and `entity_type` is present at top level
- Replace `@property entity_type` with `@computed_field` returning `self.attributes.entity_type`, and mark `entity_type` in all `*Attributes` with `exclude=True` in serialization so it does not appear in the `attributes` JSON block
- Update the module-level docstring to reflect the new design

**Changes — tests:**
- Test that `ActivitySignal` accepts `entity_type` at top level and dispatches to the correct `*Attributes` submodel without setting `entity_type` inside `attributes`
- Test that `model_dump()` includes `entity_type` and `id` at the top level
- Test that `model_dump()` does NOT include `entity_type` inside the `attributes` block
- Test that a mismatch between top-level `entity_type` and the `*Attributes` literal raises a `ValidationError`

---

### Phase 1.2 — Strict schema + `custom` field on all `*Attributes`

> **Status:** Not Started

**Goal:** Enforce `extra="forbid"` on every `*Attributes` model. Add `custom: Optional[Dict[str, Any]] = None` to each one as the sanctioned escape hatch for arbitrary producer-specific data.

**Changes — `models.py`:**
- Change every `model_config = ConfigDict(extra="allow")` to `model_config = ConfigDict(extra="forbid")` on all `*Attributes` classes
- Add `custom: Optional[Dict[str, Any]] = Field(default=None, description="Arbitrary producer-specific fields not covered by the declared schema.")` to every `*Attributes` class
- Remove the `extra_attributes()` helper method from `ActivitySignal` — it is no longer meaningful and callers will be updated in Macro Group 3

**Changes — tests:**
- Test that setting an undeclared field directly on any `*Attributes` raises `ValidationError`
- Test that the same data placed in `custom` is accepted and round-trips correctly
- Test `RelationshipTarget` also gets `extra="forbid"` (see Phase 1.3 — can be combined here if preferred)

---

### Phase 1.3 — Redesign `RelationshipTarget`

> **Status:** Not Started

**Goal:** Replace the current flexible `extra="allow"` model with a strict model. Replace `external_id` with `id`. Add `email` and `url` as optional alternate lookup fields.

**Changes — `models.py`:**
- Change `RelationshipTarget.external_id` → `id: Optional[str] = None`
- Change `model_config = ConfigDict(extra="allow")` → `extra="forbid"`
- Add `email: Optional[str] = None` — consumer uses this as first-preference lookup for `Person` targets
- Add `url: Optional[str] = None` — consumer uses this as first-preference lookup for non-Person targets
- Update the class docstring: the canonical lookup tuple is `(source, entity_type, id)`; `email` overrides for Person; `url` overrides for all other types

**Changes — tests:**
- Test that extra fields on `RelationshipTarget` are rejected
- Test `(source, entity_type, id)` round-trips correctly
- Test `email` and `url` optional fields are accepted
- Test that the old `external_id` field is rejected (breaking change validation)

---

### Phase 1.4 — Update `PersonAttributes`

> **Status:** Not Started

**Goal:** Remove `id` (moves to top-level). Rename `name` → `full_name`. Add `first_name`, `last_name`. Promote known optional fields.

**Changes — `models.py`:**
- Remove `id: str` from `PersonAttributes`
- Rename `name: str` → `full_name: str`
- Add `first_name: Optional[str] = None`
- Add `last_name: Optional[str] = None`
- Promote known optional fields from producer/consumer audit: `login: Optional[str] = None`, `email: Optional[str] = None`, `avatar_url: Optional[str] = None`, `url: Optional[str] = None`

**Changes — tests:**
- Test new schema accepts `full_name` and rejects `name`
- Test `first_name`, `last_name` are optional
- Test that `id` inside `PersonAttributes` is rejected

---

### Phase 1.5 — Update `RepositoryAttributes`

> **Status:** Not Started

**Goal:** Remove `id` and `full_name` (full_name's value becomes the top-level `id`). Keep `name` (short name). Promote known optional fields.

**Changes — `models.py`:**
- Remove `id: str` from `RepositoryAttributes`
- Remove `full_name: str` from `RepositoryAttributes`
- Keep `name: str` (the short repository name, e.g. `iam-deploy`)
- Promote from audit: `language: Optional[str] = None`, `is_private: Optional[bool] = None`, `topics: Optional[list] = None`, `description: Optional[str] = None`

**Changes — tests:**
- Test schema accepts `name`, `created_at`, `updated_at`, `url`
- Test `id` and `full_name` inside attributes are rejected
- Test optional fields round-trip

---

### Phase 1.6 — Update `BranchAttributes`

> **Status:** Not Started

**Goal:** Remove `name` (branch identity moves to top-level `id = repo_name:branch_name`). Add explicit `repo_name` and `branch_name`. Promote known optional fields.

**Changes — `models.py`:**
- Remove `name: str` from `BranchAttributes`
- Add `repo_name: str` (e.g. `iam-deploy`)
- Add `branch_name: str` (e.g. `main`)
- Promote from audit: `is_default: Optional[bool] = None`, `url: Optional[str] = None`
- Keep `last_commit_sha`, `last_commit_timestamp`, `is_protected`, `is_deleted`, `is_external`

**Changes — tests:**
- Test `repo_name` and `branch_name` are required
- Test `name` is rejected
- Test optional fields round-trip

---

### Phase 1.7 — Update `CommitAttributes`

> **Status:** Not Started

**Goal:** Remove `sha` (becomes top-level `id`). Promote known optional fields.

**Changes — `models.py`:**
- Remove `sha: str` from `CommitAttributes`
- Keep `message`, `author`, `created_at`
- Promote from audit: `additions: Optional[int] = None`, `deletions: Optional[int] = None`, `files_changed: Optional[int] = None`, `url: Optional[str] = None`

**Changes — tests:**
- Test `sha` inside attributes is rejected
- Test promoted optional fields are accepted

---

### Phase 1.8 — Update `PullRequestAttributes`

> **Status:** Not Started

**Goal:** Remove `id` and `number` (identity moves to top-level `id = repo_name:pull_number`). Add `repo_name` and `pull_request_number`. Keep all existing optional metadata fields.

**Changes — `models.py`:**
- Remove `id: str` from `PullRequestAttributes`
- Remove `number: int` from `PullRequestAttributes`
- Add `repo_name: str`
- Add `pull_request_number: int`
- Keep all existing optional fields: `title`, `state`, `created_at`, `user`, `updated_at`, `merged_at`, `closed_at`, `commits_count`, `additions`, `deletions`, `changed_files`, `comments`, `review_comments`, `head_branch_name`, `base_branch_name`, `labels`, `mergeable_state`
- Promote from audit: `url: Optional[str] = None`

**Changes — tests:**
- Test `repo_name` and `pull_request_number` are required
- Test `id` and `number` inside attributes are rejected
- Test all optional metadata fields round-trip

---

### Phase 1.9 — Update `TeamAttributes`

> **Status:** Not Started

**Goal:** Remove `id` and `slug` (slug becomes top-level `id`). Keep `name`.

**Changes — `models.py`:**
- Remove `id: str` from `TeamAttributes`
- Remove `slug: str` from `TeamAttributes`
- Keep `name: str`
- Promote from audit: `url: Optional[str] = None`, `description: Optional[str] = None`

**Changes — tests:**
- Test `id` and `slug` inside attributes are rejected
- Test `name` is required

---

### Phase 1.10 — Update `ProjectAttributes`

> **Status:** Not Started

**Goal:** Remove `id`, `key`, `name` as generic field names. Replace with explicit `project_id`, `project_key`, `project_name` to be unambiguous.

**Changes — `models.py`:**
- Remove `id: str`, `key: str`, `name: str` from `ProjectAttributes`
- Add `project_id: str` (Jira's numeric project ID)
- Add `project_key: str` (e.g. `PLAT`)
- Add `project_name: str`
- Promote from audit: `status: Optional[str] = None`, `project_type: Optional[str] = None`, `url: Optional[str] = None`

**Changes — tests:**
- Test `project_id`, `project_key`, `project_name` are required
- Test old field names `id`, `key`, `name` are rejected

---

### Phase 1.11 — Update `InitiativeAttributes`

> **Status:** Not Started

**Goal:** Remove `id` (Jira issue key becomes top-level `id`). Keep `key` as an attribute.

**Changes — `models.py`:**
- Remove `id: str` from `InitiativeAttributes`
- Keep `key: str` as a declared attribute
- Keep `summary`, `priority`, `status`, `created_at`
- Keep `project_id: Optional[str]`
- Promote from audit: `updated_at: Optional[str] = None`, `assignee: Optional[str] = None`

**Changes — tests:**
- Test `id` inside attributes is rejected
- Test `key` remains required
- Test optional fields round-trip

---

### Phase 1.12 — Update `EpicAttributes`

> **Status:** Not Started

**Goal:** Remove `id` (Jira issue key becomes top-level `id`). Keep `key`.

**Changes — `models.py`:**
- Remove `id: str` from `EpicAttributes`
- Keep `key: str`, `summary`, `priority`, `status`, `created_at`
- Promote from audit: `updated_at: Optional[str] = None`, `assignee: Optional[str] = None`

**Changes — tests:**
- Test `id` inside attributes is rejected
- Test `key` remains required

---

### Phase 1.13 — Update `SprintAttributes`

> **Status:** Not Started

**Goal:** Remove `id` (Jira sprint numeric ID becomes top-level `id`). Keep `name` and `status`.

**Changes — `models.py`:**
- Remove `id: str` from `SprintAttributes`
- Keep `name: str`, `status: str`
- Promote from audit: `start_date: Optional[str] = None`, `end_date: Optional[str] = None`, `complete_date: Optional[str] = None`

**Changes — tests:**
- Test `id` inside attributes is rejected
- Test `name` and `status` remain required

---

### Phase 1.14 — Update `IssueAttributes`

> **Status:** Not Started

**Goal:** Remove `id` (Jira issue key becomes top-level `id`). Keep `key`.

**Changes — `models.py`:**
- Remove `id: str` from `IssueAttributes`
- Keep `key: str`, `summary`, `priority`, `status`, `type`, `created_at`
- Keep `updated_at: Optional[str]`, `story_points: Optional[float]`
- Promote from audit: `assignee: Optional[str] = None`, `reporter: Optional[str] = None`, `labels: Optional[list] = None`

**Changes — tests:**
- Test `id` inside attributes is rejected
- Test `key` remains required

---

### Phase 1.15 — Remove `external_id` from `ActivitySignal`

> **Status:** Not Started

**Goal:** Drop the now-redundant `external_id` field from `ActivitySignal`. This is the final model-layer change. Pre-condition: all Macro Group 2 producer phases must be complete so no producer still emits `external_id`.

**Changes — `models.py`:**
- Remove `external_id: str` field from `ActivitySignal`
- Remove any remaining references to `external_id` in docstrings or examples

**Changes — tests:**
- Test that `ActivitySignal` rejects `external_id` in input JSON
- Run full `pytest -m unit tests -q` and verify all model tests pass

---

## Macro Group 2 — Producer Updates

Each phase updates one entity type across its producer file(s). After each phase:
- The producer emits the new `id` value at top level
- The producer no longer sets `external_id`
- The producer constructs `RelationshipTarget` using `id` instead of `external_id`
- All references to `person_github_<login>` prefix patterns are replaced

Pre-condition: Macro Group 1 must be complete.

---

### Phase 2.1 — GitHub Person producer

> **Status:** Not Started

**File:** `src/connectors/producers/github/build_person_signal.py`
Also update: `build_commit_signal.py`, `build_pull_request_signal.py` (all use `person_github_<login>` for RelationshipTarget)

**Changes:**
- Set `id=login` on `ActivitySignal` (not `person_github_{login}`)
- Remove `external_id` from the signal constructor
- Update all `RelationshipTarget` constructions that reference a Person to use `id=login` instead of `external_id=f"person_github_{login}"`
- Update `PersonAttributes`: set `full_name`, `login`, `email`, `avatar_url` (not `name`, not `id`)

**Also update:**
- `src/connectors/commons/identity_resolver.py` — replace `f"person_{provider}_{external_id}"` with the new `wba_node_id` formula
- `src/connectors/commons/person_cache.py` — same

**Changes — tests:**
- Update `tests/test_github_producer_phase4.py` for Person signal: assert `signal.id == login`, no `external_id`, `RelationshipTarget.id == login`

---

### Phase 2.2 — GitHub Repository producer

> **Status:** Not Started

**File:** `src/connectors/producers/github/build_repository_signal.py`, `src/connectors/producers/map_github.py`

**Changes:**
- Set `id=full_name` on `ActivitySignal` (e.g. `flexera/iam-deploy`)
- Remove `external_id` from signal constructor
- Update `RepositoryAttributes`: set `name` (short name only); remove `full_name`, remove `id`
- Update all `RelationshipTarget(entity_type="Repository")` to use `id=full_name`

**Changes — tests:**
- Assert `signal.id == "flexera/iam-deploy"`, no `external_id`, `signal.attributes.name == "iam-deploy"`

---

### Phase 2.3 — GitHub Branch producer

> **Status:** Not Started

**File:** `src/connectors/producers/github/build_branch_signal.py`, `src/connectors/producers/map_github.py`

**Changes:**
- Set `id=f"{repo_name}:{branch_name}"` on `ActivitySignal` (e.g. `iam-deploy:main`)
- Remove `external_id`
- Update `BranchAttributes`: set `repo_name` and `branch_name`; remove `name`
- Update all `RelationshipTarget(entity_type="Branch")` to use `id=f"{repo_name}:{branch_name}"`

**Changes — tests:**
- Assert `signal.id == "iam-deploy:main"`, `signal.attributes.repo_name == "iam-deploy"`, `signal.attributes.branch_name == "main"`

---

### Phase 2.4 — GitHub Commit producer

> **Status:** Not Started

**File:** `src/connectors/producers/github/build_commit_signal.py`, `src/connectors/producers/map_github.py`

**Changes:**
- Set `id=sha` on `ActivitySignal` (full SHA)
- Remove `external_id`
- Update `CommitAttributes`: remove `sha` field (it is now top-level `id`)
- Update all `RelationshipTarget(entity_type="Commit")` to use `id=sha`

**Changes — tests:**
- Assert `signal.id == sha`, no `sha` inside `signal.attributes`

---

### Phase 2.5 — GitHub PullRequest producer

> **Status:** Not Started

**File:** `src/connectors/producers/github/build_pull_request_signal.py`

**Changes:**
- Set `id=f"{repo_name}:{pull_number}"` on `ActivitySignal`
- Remove `external_id`
- Update `PullRequestAttributes`: set `repo_name`, `pull_request_number`; remove `id`, `number`
- Update all `RelationshipTarget(entity_type="PullRequest")` to use new id format

**Changes — tests:**
- Assert `signal.id == "iam-deploy:42"`, `signal.attributes.repo_name == "iam-deploy"`, `signal.attributes.pull_request_number == 42`

---

### Phase 2.6 — GitHub Team producer

> **Status:** Not Started

**File:** `src/connectors/producers/github/build_team_signal.py`, `src/connectors/producers/map_github.py`

**Changes:**
- Set `id=slug` on `ActivitySignal`
- Remove `external_id`
- Update `TeamAttributes`: remove `id`, `slug`; keep `name`
- Update `RelationshipTarget(entity_type="Team")` to use `id=slug`

**Changes — tests:**
- Assert `signal.id == slug`, no `id` or `slug` inside attributes

---

### Phase 2.7 — Jira Project producer

> **Status:** Not Started

**File:** `src/connectors/producers/jira_producer.py`, `src/connectors/producers/map_jira.py`

**Changes:**
- Set `id=project_key` on `ActivitySignal` (e.g. `PLAT`)
- Remove `external_id`
- Update `ProjectAttributes`: set `project_id`, `project_key`, `project_name`; remove `id`, `key`, `name`
- Update all `RelationshipTarget(entity_type="Project")` to use `id=project_key`

**Changes — tests:**
- Assert `signal.id == "PLAT"`, `signal.attributes.project_key == "PLAT"`

---

### Phase 2.8 — Jira Person producer

> **Status:** Not Started

**File:** `src/connectors/producers/jira_producer.py`

**Changes:**
- Set `id=account_id` on `ActivitySignal`
- Remove `external_id`
- Update `PersonAttributes`: set `full_name`, `email`; remove `id`, `name`
- Update all `RelationshipTarget(entity_type="Person")` in Jira to use `id=account_id`

**Changes — tests:**
- Assert `signal.id == account_id`, no `id` or `name` inside attributes

---

### Phase 2.9 — Jira Initiative producer

> **Status:** Not Started

**Changes:**
- `id = issue_key` on `ActivitySignal`
- Remove `external_id`
- `InitiativeAttributes`: remove `id`; keep `key`
- Update `RelationshipTarget(entity_type="Initiative")`

**Changes — tests:** Assert `signal.id == issue_key`, `signal.attributes.key == issue_key`

---

### Phase 2.10 — Jira Epic producer

> **Status:** Not Started

**Changes:**
- `id = issue_key`
- Remove `external_id`
- `EpicAttributes`: remove `id`; keep `key`

**Changes — tests:** Assert `signal.id == issue_key`

---

### Phase 2.11 — Jira Sprint producer

> **Status:** Not Started

**Changes:**
- `id = str(sprint_id)` (Jira numeric sprint ID as string)
- Remove `external_id`
- `SprintAttributes`: remove `id`

**Changes — tests:** Assert `signal.id == str(sprint_id)`

---

### Phase 2.12 — Jira Issue producer

> **Status:** Not Started

**Changes:**
- `id = issue_key` (e.g. `PLAT-123`)
- Remove `external_id`
- `IssueAttributes`: remove `id`; keep `key`
- Update all `RelationshipTarget(entity_type="Issue")` to use `id=issue_key`

**Changes — tests:** Assert `signal.id == "PLAT-123"`, `signal.attributes.key == "PLAT-123"`

---

### Phase 2.13 — Verify `external_id` fully removed from producers

> **Status:** Not Started

**Goal:** Confirm no producer code still references or sets `external_id`.

**Changes:**
- Grep `external_id` across all `src/connectors/producers/`; fix any remaining occurrences
- Grep `person_github_` and `person_jira_` across all producer and mapping files; fix any remaining occurrences

**Changes — tests:**
- Run `pytest -m unit tests -q` on all producer tests
- Assert no test constructs an `ActivitySignal` with `external_id`
- After all producer tests pass: proceed to Phase 1.15 (remove `external_id` from model)

---

## Macro Group 3 — Consumer Updates

Pre-condition: Macro Groups 1 and 2 complete. Phase 1.15 (`external_id` removed from model) must be done.

> **Neo4j clearing:** Before executing Phase 3.3, run `scripts/clear_all_data.sh` to wipe the graph. Re-run all producers to re-populate Neo4j with new `wba_node_id` values.

---

### Phase 3.1 — Derive `wba_node_id` in `neo4j_sink.py`

> **Status:** Not Started

**File:** `src/connectors/consumers/sinks/neo4j_sink.py`

**Changes:**
- Add a helper: `def _wba_node_id(signal: ActivitySignal) -> str: return f"{signal.source}::{signal.entity_type}::{signal.id}"`
- Replace every `id=signal.external_id` in all `_handle_*` functions with `id=_wba_node_id(signal)`
- Replace `attrs = signal.extra_attributes()` calls with `attrs = signal.attributes.model_dump(exclude={"entity_type", "custom"})` for declared fields and `custom = signal.attributes.custom or {}` for extras; update each `attrs.get(...)` call accordingly

**Changes — tests:**
- Update `tests/test_consumer_phase5.py`: verify that Neo4j dataclass `id` is `"github::Repository::flexera/iam-deploy"` for a Repository signal, `"github::Person::alice"` for a Person signal, etc.

---

### Phase 3.2 — Update `RelationshipTarget` resolution in consumer

> **Status:** Not Started

**File:** `src/connectors/consumers/sinks/neo4j_sink.py` — `_to_db_relationships()` function

**Changes:**
- Replace `to_id = target.external_id` with resolution logic:
  1. If `target.entity_type == "Person"` and `target.email` is set → look up Person node by `email` property first
  2. Else if `target.url` is set → look up node by `url` property first
  3. Else → `to_id = f"{target.source}::{target.entity_type}::{target.id}"`
- Update the guard `if not target.external_id` → `if not (target.id or target.email or target.url)`

**Changes — tests:**
- Test email-first lookup path for Person targets
- Test url-first lookup path for non-Person targets
- Test fallback to `source::entity_type::id` tuple

---

### Phase 3.3 — Update `PersonCache` and `identity_resolver`

> **Status:** Not Started

**Files:** `src/connectors/commons/identity_resolver.py`, `src/connectors/commons/person_cache.py`

**Changes:**
- `identity_resolver.py`: replace `f"person_{provider}_{external_id}"` with `f"{provider}::Person::{external_id}"`
- `person_cache.py`: update `fallback_person_id` same formula
- Remove hardcoded fallbacks `"person_github_unknown"` in `new_commit_handler.py` and `new_pull_request_handler.py`; replace with `f"{source}::Person::unknown"`

**Changes — tests:**
- Test `identity_resolver` produces `"github::Person::alice"` for login `alice`, source `github`
- Test `person_cache` fallback produces `"github::Person::unknown"` not the old format

---

### Phase 3.4 — Clear Neo4j and re-sync

> **Status:** Not Started

**Steps (manual, not code):**
1. `bash scripts/clear_all_data.sh` — wipe all nodes and relationships
2. Re-run GitHub producer: `docker compose run --rm github-producer`
3. Re-run Jira producer: `docker compose run --rm jira-producer`
4. Re-run sync services: `docker compose run --rm github-sync && docker compose run --rm jira-sync`
5. Spot-check Neo4j Browser: verify node IDs use `::` format (e.g. `github::Repository::flexera/iam-deploy`)
6. Run `pytest -m neo4j tests -q` if Neo4j tests exist

---

## Macro Group 4 — Cleanup

---

### Phase 4.1 — Remove `routing_key` from `ActivitySignal`

> **Status:** Not Started

**Files:** `src/common/activity_signal/models.py`, `src/common/messaging/rabbitmq.py`, `src/connectors/producers/github/pub_callback.py`, `src/connectors/producers/jira_producer.py`

**Changes:**
- Remove `@property routing_key` from `ActivitySignal`
- In `rabbitmq.py`: replace `signal.routing_key` with `f"{signal.source}.{signal.entity_type}"`
- In producer log statements: replace `signal.routing_key` with the same inline expression
- In `init_rabbitmq.py` and `redrive_dlq.py`: verify these use literal routing key strings (not `signal.routing_key`) — if they do, no change needed

**Changes — tests:**
- Test that `ActivitySignal` has no `routing_key` attribute
- Test that `rabbitmq.py` still publishes to the correct queue (use existing messaging tests)
- Run `pytest -m unit tests -q`

---

### Phase 4.2 — Final `external_id` audit

> **Status:** Not Started

**Goal:** Confirm `external_id` is completely eradicated from the codebase.

**Steps:**
- `grep -r "external_id" src/ tests/` — must return zero matches
- `grep -r "person_github_\|person_jira_" src/ tests/` — must return zero matches
- Fix any remaining occurrences

**Changes — tests:**
- Run the full test suite: `pytest -m unit tests -q`
- Run integration tests if the server is up: `pytest -m "integration and server" tests -q`

---

### Phase 4.3 — Auto-generate spec from models

> **Status:** Not Started

**Goal:** Replace the manually-maintained `docs/design/spec-activity-signal.md` with a generated file. Eliminates documentation drift.

**Changes:**
- Create `scripts/generate_spec.py`:
  - Imports all `*Attributes` models and `ActivitySignal` from `src/common/activity_signal/models.py`
  - Uses Pydantic's `model_json_schema()` to extract field names, types, and descriptions
  - Renders a structured Markdown file covering: canonical identity tuple, all entity types with their declared fields, `RelationshipTarget` schema, `SUPPORTED_RELATIONSHIP_TYPES`, `SUPPORTED_ENTITY_TYPES`
  - Writes output to `docs/design/spec-activity-signal.md`
- Add a header comment to `spec-activity-signal.md`: `<!-- AUTO-GENERATED by scripts/generate_spec.py — do not edit manually -->`

**Changes — tests:**
- Test that running `generate_spec.py` produces output that matches the current committed spec (i.e., the spec is in sync with the models)
- This can be a simple `pytest` test that runs the generator and diffs against the committed file

---

## Summary Table

| Phase | File(s) Changed | Test Marker |
|---|---|---|
| 1.1 | `models.py` | `unit` |
| 1.2 | `models.py` | `unit` |
| 1.3 | `models.py` | `unit` |
| 1.4–1.14 | `models.py` (one entity per phase) | `unit` |
| 1.15 | `models.py` | `unit` |
| 2.1–2.12 | `producers/` (one entity per phase) | `unit` |
| 2.13 | `producers/` (audit) | `unit` |
| 3.1 | `neo4j_sink.py` | `unit` |
| 3.2 | `neo4j_sink.py` | `unit` |
| 3.3 | `identity_resolver.py`, `person_cache.py` | `unit` |
| 3.4 | Manual re-sync | `neo4j` |
| 4.1 | `models.py`, `rabbitmq.py`, producers | `unit` |
| 4.2 | Audit across all | `unit` + `integration` |
| 4.3 | `scripts/generate_spec.py` | `unit` |

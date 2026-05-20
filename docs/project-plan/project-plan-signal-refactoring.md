# ActivitySignal Refactoring — Project Plan

## Background

The `ActivitySignal` schema has accumulated inconsistencies across producers and consumers. This plan standardises it end-to-end using a **vertical-slice** approach: each phase delivers a complete model + producer + consumer change for one entity type, leaving the system in a fully working and end-to-end testable state after every phase.

## Decisions Made

| Decision | Choice |
|---|---|
| Migration strategy | Vertical slices — one entity type per phase; every phase is end-to-end testable |
| `id` in model | `Optional[str]` during migration (Phases 1–12); becomes required in Phase 13 cleanup |
| `entity_type` in model | `@computed_field` via `model_validator(mode='before')` injection; excluded from `*Attributes` serialization |
| `id` uniqueness tuple | `(source, entity_type, id)` at top level of `ActivitySignal` |
| `wba_node_id` format | `"{source}::{entity_type}::{id}"` (PascalCase entity type, `::` separator) |
| `extra="forbid"` rollout | Enabled per entity type as part of each entity's phase (not globally upfront) |
| `custom` escape hatch | `custom: Optional[Dict[str, Any]] = None` on each `*Attributes` (inline field, not base class) |
| `RelationshipTarget` lookup | `id` field; `email` overrides for Person; `url` overrides for all others |
| `routing_key` | Removed from model in Phase 13; inlined in `rabbitmq.py` as `f"{signal.source}.{signal.entity_type}"` |
| Neo4j clearing | After Phase 13 cleanup; re-sync from scratch using `scripts/clear_all_data.sh` |

---

## Phase 1 — Foundation

> **Status:** Complete

**Goal:** Establish all cross-cutting model and consumer infrastructure that every entity-specific phase depends on. No producer or entity-specific attribute changes in this phase.

**Pre-work — verify signal dumps:**
- Inspect `logs/signals/github_queue_signals_iam_deploy.json` and `logs/signals/jira_queue_signals.json`
- Confirm the current `external_id` format is `<source>_<entity_type>_<name>` for all entity types
- Document any anomalies before proceeding

**Changes — `src/common/activity_signal/models.py`:**
- Add `id: Optional[str] = None` to `ActivitySignal` (Optional during migration; made required in Phase 13)
- Add `@model_validator(mode='before')` that copies `data['entity_type']` into `data['attributes']['entity_type']` when both are present
- Replace `@property entity_type` with `@computed_field` returning `self.attributes.entity_type`; mark `entity_type` on all `*Attributes` with `exclude=True` in serialization
- Redesign `RelationshipTarget`:
  - Rename `external_id` → `id: Optional[str] = None`
  - Add `email: Optional[str] = None` (first-preference lookup for Person targets)
  - Add `url: Optional[str] = None` (first-preference lookup for non-Person targets)
  - Change `extra="allow"` → `extra="forbid"`
  - Update docstring: canonical lookup is `(source, entity_type, id)`; `email` overrides for Person; `url` overrides for all others
- Remove `extra_attributes()` helper from `ActivitySignal`

**Changes — `src/connectors/consumers/sinks/neo4j_sink.py`:**
- Add helper: `def _wba_node_id(signal: ActivitySignal) -> str` — returns `f"{signal.source}::{signal.entity_type}::{signal.id}"` if `signal.id` is set, otherwise falls back to `signal.external_id` (fallback removed in Phase 13)
- Update `_to_db_relationships()`: replace `to_id = target.external_id` with resolution logic:
  1. Person target with `target.email` → look up node by email
  2. Non-Person target with `target.url` → look up node by url
  3. Fallback → `f"{target.source}::{target.entity_type}::{target.id}"`
  - Update guard: `if not target.external_id` → `if not (target.id or target.email or target.url)`

**Changes — `src/connectors/commons/identity_resolver.py`, `person_cache.py`:**
- `identity_resolver.py`: replace `f"person_{provider}_{external_id}"` with `f"{provider}::Person::{external_id}"`
- `person_cache.py`: update `fallback_person_id` to same formula
- `new_commit_handler.py`, `new_pull_request_handler.py`: replace `"person_github_unknown"` hardcodes with `f"{source}::Person::unknown"`

**Changes — tests:**
- `ActivitySignal` accepts `entity_type` at top level; dispatches to correct `*Attributes`
- `model_dump()` includes `entity_type` and `id` at top level; `entity_type` absent inside `attributes`
- Mismatch between top-level `entity_type` and `*Attributes` literal raises `ValidationError`
- `RelationshipTarget` rejects `external_id`; accepts `id`, `email`, `url`; rejects extra fields
- `_wba_node_id()` returns `::` format when `id` set; falls back gracefully when `id` is None
- `identity_resolver` produces `"github::Person::alice"` for login `alice`, source `github`
- `person_cache` fallback produces `"github::Person::unknown"` (not old underscore format)

---

## Phase 2 — Person

> **Status:** Complete

**Goal:** Migrate the Person entity end-to-end. GitHub and Jira persons are done together since they share `PersonAttributes` and a single `_handle_person()` in the consumer.

**Pre-condition:** Phase 1 complete.

**Changes — `models.py` (`PersonAttributes`):**
- Remove `id: str`
- Rename `name: str` → `full_name: str`
- Add `first_name: Optional[str] = None`, `last_name: Optional[str] = None`
- Promote known optional fields: `login`, `email`, `avatar_url`, `url`
- Enable `extra="forbid"`; add `custom: Optional[Dict[str, Any]] = None`

**Changes — GitHub producer (`build_person_signal.py`):**
- Set `id=login` on `ActivitySignal`; remove `external_id`
- Set `full_name` (not `name`); remove `id` from `PersonAttributes`
- `build_commit_signal.py`, `build_pull_request_signal.py`: update all `RelationshipTarget(entity_type="Person")` to use `id=login` (remove `external_id=f"person_github_{login}"`)
- Confirm `identity_resolver.py` and `person_cache.py` no longer produce `person_github_` prefixed IDs

**Changes — Jira producer (`jira_producer.py`):**
- Set `id=account_id` on `ActivitySignal`; remove `external_id`
- Set `full_name` and `email` (not `name`); remove `id` from `PersonAttributes`
- Update `RelationshipTarget(entity_type="Person")` to use `id=account_id`

**Changes — consumer (`neo4j_sink.py` — `_handle_person()`):**
- Replace `id=signal.external_id` with `id=_wba_node_id(signal)`
- Replace `attrs.get('name')` with `attrs.get('full_name')`
- Update all attribute reads to new `PersonAttributes` field names
- Use `attrs = signal.attributes.model_dump(exclude={"entity_type", "custom"})` and `custom = signal.attributes.custom or {}`

**Changes — tests:**
- `PersonAttributes` rejects `name` and `id`; accepts `full_name`, `login`, `email`
- `first_name`, `last_name` optional; undeclared fields raise `ValidationError`
- GitHub Person signal: `signal.id == login`, no `external_id`, `RelationshipTarget.id == login`
- Jira Person signal: `signal.id == account_id`, no `id` or `name` inside attributes
- Consumer: Person node id is `"github::Person::alice"` / `"jira::Person::<account_id>"`

**E2E checkpoint:**
- Re-run GitHub and Jira producers; spot-check Neo4j: Person nodes use `::` format
- Confirm zero `person_github_` prefixed nodes exist in Neo4j

---

## Phase 3 — Repository

> **Status:** Complete

**Goal:** Migrate the Repository entity end-to-end.

**Pre-condition:** Phase 1 complete.

**Changes — `models.py` (`RepositoryAttributes`):**
- Remove `id: str` and `full_name: str`
- Keep `name: str` (short name, e.g. `iam-deploy`)
- Promote: `language`, `is_private`, `topics`, `description`
- Enable `extra="forbid"`; add `custom: Optional[Dict[str, Any]] = None`

**Changes — GitHub producer (`build_repository_signal.py`, `map_github.py`):**
- Set `id=full_name` (e.g. `flexera/iam-deploy`) on `ActivitySignal`; remove `external_id`
- Set `name` = short name only; remove `full_name` and `id` from `RepositoryAttributes`
- Update `RelationshipTarget(entity_type="Repository")` to use `id=full_name`

**Changes — consumer (`neo4j_sink.py` — `_handle_repository()`):**
- Replace `id=signal.external_id` with `id=_wba_node_id(signal)`
- Update attribute reads to new field names

**Changes — tests:**
- `signal.id == "flexera/iam-deploy"`, no `external_id`, `signal.attributes.name == "iam-deploy"`
- `id` and `full_name` inside attributes rejected
- Consumer: Repository node id is `"github::Repository::flexera/iam-deploy"`

**E2E checkpoint:** Re-run GitHub producer; verify Repository nodes in Neo4j.

---

## Phase 4 — Branch

> **Status:** Complete

**Goal:** Migrate the Branch entity end-to-end.

**Pre-condition:** Phase 1 complete.

**Changes — `models.py` (`BranchAttributes`):**
- Remove `name: str`
- Add `repo_name: str`, `branch_name: str`
- Promote: `is_default`, `url`
- Keep: `last_commit_sha`, `last_commit_timestamp`, `is_protected`, `is_deleted`, `is_external`
- Enable `extra="forbid"`; add `custom: Optional[Dict[str, Any]] = None`

**Changes — GitHub producer (`build_branch_signal.py`, `map_github.py`):**
- Set `id=f"{repo_name}::{branch_name}"` on `ActivitySignal`; remove `external_id`
- Set `repo_name` and `branch_name` on `BranchAttributes`; remove `name`
- Update `RelationshipTarget(entity_type="Branch")` to use new `id`

**Changes — consumer (`neo4j_sink.py` — `_handle_branch()`):**
- Replace `id=signal.external_id` with `id=_wba_node_id(signal)`
- Replace `attrs.get('name')` with `attrs.get('repo_name')` / `attrs.get('branch_name')` as appropriate

**Changes — tests:**
- `signal.id == "iam-deploy:main"`, `signal.attributes.repo_name == "iam-deploy"`, `signal.attributes.branch_name == "main"`
- `name` inside attributes rejected; `repo_name` and `branch_name` required
- Consumer: Branch node id is `"github::Branch::iam-deploy:main"`

**E2E checkpoint:** Re-run GitHub producer; verify Branch nodes in Neo4j.

---

## Phase 5 — Commit

> **Status:** Complete

**Goal:** Migrate the Commit entity end-to-end.

**Pre-condition:** Phase 1 complete.

**Changes — `models.py` (`CommitAttributes`):**
- Remove `sha: str`
- Keep `message`, `author`, `created_at`
- Promote: `additions`, `deletions`, `files_changed`, `url`
- Enable `extra="forbid"`; add `custom: Optional[Dict[str, Any]] = None`

**Changes — GitHub producer (`build_commit_signal.py`, `map_github.py`):**
- Set `id=sha` on `ActivitySignal`; remove `external_id`
- Remove `sha` from `CommitAttributes` (now top-level `id`)
- Update `RelationshipTarget(entity_type="Commit")` to use `id=sha`

**Changes — consumer (`neo4j_sink.py` — `_handle_commit()`):**
- Replace `id=signal.external_id` with `id=_wba_node_id(signal)`
- Remove reads of `attrs.get('sha')`; use `signal.id` if SHA is needed
- Update attribute reads

**Changes — tests:**
- `signal.id == sha`, `sha` inside attributes rejected
- Promoted optional fields (`additions`, `deletions`, `files_changed`) accepted
- Consumer: Commit node id is `"github::Commit::<sha>"`

**E2E checkpoint:** Re-run GitHub producer; verify Commit nodes in Neo4j.

---

## Phase 6 — PullRequest

> **Status:** Complete

**Goal:** Migrate the PullRequest entity end-to-end.

**Pre-condition:** Phase 1 complete.

**Changes — `models.py` (`PullRequestAttributes`):**
- Remove `id: str`, `number: int`
- Add `repo_name: str`, `pull_request_number: int`
- Keep all existing optional metadata fields; promote `url`
- Enable `extra="forbid"`; add `custom: Optional[Dict[str, Any]] = None`

**Changes — GitHub producer (`build_pull_request_signal.py`):**
- Set `id=f"{repo_name}:{pull_number}"` on `ActivitySignal`; remove `external_id`
- Set `repo_name` and `pull_request_number`; remove `id` and `number` from attributes
- Update `RelationshipTarget(entity_type="PullRequest")` to use new `id`

**Changes — consumer (`neo4j_sink.py` — `_handle_pull_request()`):**
- Replace `id=signal.external_id` with `id=_wba_node_id(signal)`
- Replace `attrs.get('number')` with `attrs.get('pull_request_number')`; read `repo_name` from attrs

**Changes — tests:**
- `signal.id == "iam-deploy:42"`, `signal.attributes.repo_name == "iam-deploy"`, `signal.attributes.pull_request_number == 42`
- `id` and `number` inside attributes rejected
- Consumer: PullRequest node id is `"github::PullRequest::iam-deploy:42"`

**E2E checkpoint:** Re-run GitHub producer; verify PullRequest nodes in Neo4j.

---

## Phase 7 — Team

> **Status:** Not Started

**Goal:** Migrate the Team entity end-to-end.

**Pre-condition:** Phase 1 complete.

**Changes — `models.py` (`TeamAttributes`):**
- Remove `id: str`, `slug: str`
- Keep `name: str`
- Promote: `url`, `description`
- Enable `extra="forbid"`; add `custom: Optional[Dict[str, Any]] = None`

**Changes — GitHub producer (`build_team_signal.py`, `map_github.py`):**
- Set `id=slug` on `ActivitySignal`; remove `external_id`
- Remove `id` and `slug` from `TeamAttributes`; keep `name`
- Update `RelationshipTarget(entity_type="Team")` to use `id=slug`

**Changes — consumer (`neo4j_sink.py` — `_handle_team()`):**
- Replace `id=signal.external_id` with `id=_wba_node_id(signal)`
- Update attribute reads

**Changes — tests:**
- `signal.id == slug`, no `id` or `slug` inside attributes, `name` required
- Consumer: Team node id is `"github::Team::<slug>"`

**E2E checkpoint:** Re-run GitHub producer; verify Team nodes in Neo4j.

---

## Phase 8 — Project

> **Status:** Not Started

**Goal:** Migrate the Jira Project entity end-to-end.

**Pre-condition:** Phase 1 complete.

**Changes — `models.py` (`ProjectAttributes`):**
- Remove `id: str`, `key: str`, `name: str`
- Add `project_id: str` (Jira numeric project ID), `project_key: str` (e.g. `PLAT`), `project_name: str`
- Promote: `status`, `project_type`, `url`
- Enable `extra="forbid"`; add `custom: Optional[Dict[str, Any]] = None`

**Changes — Jira producer (`jira_producer.py`, `map_jira.py`):**
- Set `id=project_key` on `ActivitySignal`; remove `external_id`
- Set `project_id`, `project_key`, `project_name`; remove `id`, `key`, `name` from attributes
- Update `RelationshipTarget(entity_type="Project")` to use `id=project_key`

**Changes — consumer (`neo4j_sink.py` — `_handle_project()`):**
- Replace `id=signal.external_id` with `id=_wba_node_id(signal)`
- Replace `attrs.get('key')` with `attrs.get('project_key')`; update all attribute reads

**Changes — tests:**
- `signal.id == "PLAT"`, `signal.attributes.project_key == "PLAT"`
- Old field names `id`, `key`, `name` inside attributes rejected
- Consumer: Project node id is `"jira::Project::PLAT"`

**E2E checkpoint:** Re-run Jira producer; verify Project nodes in Neo4j.

---

## Phase 9 — Initiative

> **Status:** Not Started

**Goal:** Migrate the Jira Initiative entity end-to-end.

**Pre-condition:** Phase 1 complete.

**Changes — `models.py` (`InitiativeAttributes`):**
- Remove `id: str`
- Keep `key: str`, `summary`, `priority`, `status`, `created_at`, `project_id`
- Promote: `updated_at`, `assignee`
- Enable `extra="forbid"`; add `custom: Optional[Dict[str, Any]] = None`

**Changes — Jira producer (`jira_producer.py`):**
- Set `id=issue_key` on `ActivitySignal`; remove `external_id`
- Remove `id` from `InitiativeAttributes`; keep `key`
- Update `RelationshipTarget(entity_type="Initiative")` to use `id=issue_key`

**Changes — consumer (`neo4j_sink.py` — `_handle_initiative()`):**
- Replace `id=signal.external_id` with `id=_wba_node_id(signal)`
- Update attribute reads

**Changes — tests:**
- `signal.id == issue_key`, `signal.attributes.key == issue_key`
- `id` inside attributes rejected; `key` required
- Consumer: Initiative node id is `"jira::Initiative::<key>"`

**E2E checkpoint:** Re-run Jira producer; verify Initiative nodes in Neo4j.

---

## Phase 10 — Epic

> **Status:** Not Started

**Goal:** Migrate the Jira Epic entity end-to-end.

**Pre-condition:** Phase 1 complete.

**Changes — `models.py` (`EpicAttributes`):**
- Remove `id: str`
- Keep `key: str`, `summary`, `priority`, `status`, `created_at`
- Promote: `updated_at`, `assignee`
- Enable `extra="forbid"`; add `custom: Optional[Dict[str, Any]] = None`

**Changes — Jira producer (`jira_producer.py`):**
- Set `id=issue_key` on `ActivitySignal`; remove `external_id`
- Remove `id` from `EpicAttributes`; keep `key`
- Update `RelationshipTarget(entity_type="Epic")` to use `id=issue_key`

**Changes — consumer (`neo4j_sink.py` — `_handle_epic()`):**
- Replace `id=signal.external_id` with `id=_wba_node_id(signal)`
- Update attribute reads

**Changes — tests:**
- `signal.id == issue_key`; `id` inside attributes rejected; `key` required
- Consumer: Epic node id is `"jira::Epic::<key>"`

**E2E checkpoint:** Re-run Jira producer; verify Epic nodes in Neo4j.

---

## Phase 11 — Sprint

> **Status:** Not Started

**Goal:** Migrate the Jira Sprint entity end-to-end.

**Pre-condition:** Phase 1 complete.

**Changes — `models.py` (`SprintAttributes`):**
- Remove `id: str`
- Keep `name: str`, `status: str`
- Promote: `start_date`, `end_date`, `complete_date`
- Enable `extra="forbid"`; add `custom: Optional[Dict[str, Any]] = None`

**Changes — Jira producer (`jira_producer.py`):**
- Set `id=str(sprint_id)` on `ActivitySignal`; remove `external_id`
- Remove `id` from `SprintAttributes`
- Update `RelationshipTarget(entity_type="Sprint")` to use `id=str(sprint_id)`

**Changes — consumer (`neo4j_sink.py` — `_handle_sprint()`):**
- Replace `id=signal.external_id` with `id=_wba_node_id(signal)`
- Update attribute reads

**Changes — tests:**
- `signal.id == str(sprint_id)`; `id` inside attributes rejected; `name` and `status` required
- Consumer: Sprint node id is `"jira::Sprint::<sprint_id>"`

**E2E checkpoint:** Re-run Jira producer; verify Sprint nodes in Neo4j.

---

## Phase 12 — Issue

> **Status:** Not Started

**Goal:** Migrate the Jira Issue entity end-to-end. This is the final entity migration phase.

**Pre-condition:** Phase 1 complete.

**Changes — `models.py` (`IssueAttributes`):**
- Remove `id: str`
- Keep `key: str`, `summary`, `priority`, `status`, `type`, `created_at`, `updated_at`, `story_points`
- Promote: `assignee`, `reporter`, `labels`
- Enable `extra="forbid"`; add `custom: Optional[Dict[str, Any]] = None`

**Changes — Jira producer (`jira_producer.py`):**
- Set `id=issue_key` on `ActivitySignal`; remove `external_id`
- Remove `id` from `IssueAttributes`; keep `key`
- Update `RelationshipTarget(entity_type="Issue")` to use `id=issue_key`

**Changes — consumer (`neo4j_sink.py` — `_handle_issue()`):**
- Replace `id=signal.external_id` with `id=_wba_node_id(signal)`
- Update attribute reads

**Changes — tests:**
- `signal.id == "PLAT-123"`, `signal.attributes.key == "PLAT-123"`
- `id` inside attributes rejected; `key` required
- Consumer: Issue node id is `"jira::Issue::PLAT-123"`

**E2E checkpoint:** Re-run Jira producer; verify Issue nodes in Neo4j.

---

## Phase 13 — Cleanup

> **Status:** Not Started

**Goal:** Remove all migration scaffolding, finalize the schema, wipe and re-sync Neo4j, and auto-generate the spec. Pre-condition: all Phases 1–12 complete and all unit tests passing.

**Changes — `src/common/activity_signal/models.py`:**
- Change `id: Optional[str] = None` → `id: str` (now required)
- Remove `external_id: str` field entirely
- Remove `@property routing_key` from `ActivitySignal`
- Remove any remaining references to `external_id` or `routing_key` in docstrings

**Changes — `src/common/messaging/rabbitmq.py` and producers:**
- `rabbitmq.py`: replace `signal.routing_key` with `f"{signal.source}.{signal.entity_type}"`
- `pub_callback.py`, `jira_producer.py`: replace `signal.routing_key` in log statements with the same inline expression
- Verify `init_rabbitmq.py` and `redrive_dlq.py` use literal routing key strings (no change needed if so)

**Changes — `neo4j_sink.py`:**
- Remove `external_id` fallback from `_wba_node_id()`: simplify to `return f"{signal.source}::{signal.entity_type}::{signal.id}"`

**Final audit:**
- `grep -r "external_id" src/ tests/` — must return zero matches
- `grep -r "person_github_\|person_jira_" src/ tests/` — must return zero matches
- Fix any remaining occurrences

**Neo4j re-sync (manual):**
1. `bash scripts/clear_all_data.sh` — wipe all nodes and relationships
2. `docker compose run --rm github-producer`
3. `docker compose run --rm jira-producer`
4. `docker compose run --rm github-sync && docker compose run --rm jira-sync`
5. Spot-check Neo4j Browser: all node IDs in `source::EntityType::id` format
6. `pytest -m neo4j tests -q`

**Auto-generate spec — `scripts/generate_spec.py`:**
- Import all `*Attributes` models and `ActivitySignal` from `src/common/activity_signal/models.py`
- Use `model_json_schema()` to extract field names, types, and descriptions
- Render `docs/design/spec-activity-signal.md` covering: canonical identity tuple, all entity types with declared fields, `RelationshipTarget` schema, `SUPPORTED_RELATIONSHIP_TYPES`, `SUPPORTED_ENTITY_TYPES`
- Add header: `<!-- AUTO-GENERATED by scripts/generate_spec.py — do not edit manually -->`

**Changes — tests:**
- `ActivitySignal` requires `id` (not Optional); rejects `external_id` in input
- `ActivitySignal` has no `routing_key` attribute
- `rabbitmq.py` still publishes to correct queue
- Running `generate_spec.py` produces output matching committed spec
- Full suite: `pytest -m unit tests -q` and `pytest -m "integration and server" tests -q`

---

## Summary Table

| Phase | Entity / Scope | Files Changed | Test Marker |
|---|---|---|---|
| 1 | Foundation (cross-cutting model + consumer infra) | `models.py`, `neo4j_sink.py`, `identity_resolver.py`, `person_cache.py` | `unit` |
| 2 | Person | `models.py`, GitHub/Jira producers, `neo4j_sink.py` | `unit` + e2e |
| 3 | Repository | `models.py`, GitHub producer, `neo4j_sink.py` | `unit` + e2e |
| 4 | Branch | `models.py`, GitHub producer, `neo4j_sink.py` | `unit` + e2e |
| 5 | Commit | `models.py`, GitHub producer, `neo4j_sink.py` | `unit` + e2e |
| 6 | PullRequest | `models.py`, GitHub producer, `neo4j_sink.py` | `unit` + e2e |
| 7 | Team | `models.py`, GitHub producer, `neo4j_sink.py` | `unit` + e2e |
| 8 | Project | `models.py`, Jira producer, `neo4j_sink.py` | `unit` + e2e |
| 9 | Initiative | `models.py`, Jira producer, `neo4j_sink.py` | `unit` + e2e |
| 10 | Epic | `models.py`, Jira producer, `neo4j_sink.py` | `unit` + e2e |
| 11 | Sprint | `models.py`, Jira producer, `neo4j_sink.py` | `unit` + e2e |
| 12 | Issue | `models.py`, Jira producer, `neo4j_sink.py` | `unit` + e2e |
| 13 | Cleanup (`id` required, `external_id` + `routing_key` removed, re-sync, spec gen) | `models.py`, `rabbitmq.py`, producers, `neo4j_sink.py`, `scripts/generate_spec.py` | `unit` + `integration` + `neo4j` |

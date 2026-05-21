# Plan: Migrate File Entity to ActivitySignal Pipeline

## Background

The `File` entity existed in the legacy Neo4j sync architecture (`new_file_handler.py`) but
was never migrated to the new event-driven ActivitySignal pipeline during the Phase 3–5
signal-consumers-and-producers rollout.

As a result, 5 query catalog files currently reference `:File` nodes and `MODIFIES`
relationships that do not exist in the graph:

| Query File | What it queries |
|---|---|
| `queries_catalog/github/hotspot_files.yaml` | `(f:File)<-[:MODIFIES]-(c:Commit)` |
| `queries_catalog/github/code_churn.yaml` | `(f:File)<-[m:MODIFIES]-(c:Commit)` |
| `queries_catalog/github/developer_activity_by_language.yaml` | `(p:Person)-[:AUTHORED_BY]-(c:Commit)-[:MODIFIES]->(f:File)` |
| `queries_catalog/github/test_vs_production_code.yaml` | `(f:File)<-[:MODIFIES]-(c:Commit)` |
| `queries_catalog/person_to_person/shared_code_hotspots.yaml` | `(c1:Commit)-[:MODIFIES]->(f:File)<-[:MODIFIES]-(c2:Commit)` |

**Why tests didn't catch this:** The test suite was written entity-first, not contract-first.
`test_consumer_phase5.py` and `test_github_producer_phase4.py` only covered entities already
in `_HANDLERS` and the signal builders. Since `File` was never added to either, there was no
test that could fail. The fix includes a migration completeness guard test to prevent this
class of regression in the future.

---

## Design Decisions

| Decision | Resolution |
|---|---|
| **Signal granularity** | One `File` signal per file per commit |
| **Raw `id`** | `{repo_name}::{file_path}` — matches Branch pattern |
| **WBA canonical key** | `github::File::my-repo::src/app/main.py` |
| **`repo_name` as attribute** | Yes — included in `FileAttributes` (mirrors `BranchAttributes`) |
| **Mandatory fields** | `path` + `repo_name` only |
| **Optional fields** | `name`, `extension`, `language`, `is_test`, `size`, `last_updated_at`, `url`, `additions`, `deletions` |
| **`additions`/`deletions`** | On `MODIFIES` relationship properties, not on the File node |
| **Timestamp field** | `last_updated_at` (not `created_at`) — reflects most recent commit that touched the file |
| **`event_time`** | Commit's `created_at` — drives idempotency guard |
| **`MODIFIES` direction** | `"IN"` on the File signal → consumer writes `(Commit)-[:MODIFIES]->(File)` — aligns with all 5 catalog queries |
| **Emit from** | `process_single_commit.py` only — sufficient for all catalog queries, no PR duplication |
| **`File` dataclass + `merge_file()`** | Replace in-place in `neo4j_db/models.py` — old format is deprecated |
| **Queue changes** | None — `github.#` wildcard routes `github.File` to `github_queue` automatically |

---

## Phase 1 — Schema Layer

*Unblocks all other phases.*

**`src/common/activity_signal/models.py`**

- [ ] Add `FileAttributes` class after `TeamAttributes`:
  ```python
  class FileAttributes(BaseModel):
      model_config = ConfigDict(extra="forbid")
      entity_type: Literal["File"] = Field(default="File", exclude=True)
      path: str
      repo_name: str
      name: Optional[str] = None
      extension: Optional[str] = None
      language: Optional[str] = None
      is_test: Optional[bool] = None
      size: Optional[int] = None
      last_updated_at: Optional[str] = None
      url: Optional[str] = None
      additions: Optional[int] = None
      deletions: Optional[int] = None
      custom: Optional[Dict[str, Any]] = None
  ```
- [ ] Add `FileAttributes` to `_AttributesUnion`
- [ ] Add `"File"` to `SUPPORTED_ENTITY_TYPES`
- [ ] Add `"MODIFIES"` to `SUPPORTED_RELATIONSHIP_TYPES`

---

## Phase 2 — Neo4j Dataclass Layer

*Replace in-place — old format is deprecated.*

**`src/connectors/neo4j_db/models.py`**

- [ ] Replace `File` dataclass:
  - `id: str` — holds WBA canonical key (`github::File::repo::path`)
  - `path: str`, `repo_name: str` — mandatory
  - All other fields Optional: `name`, `extension`, `language`, `is_test`, `size`, `last_updated_at`, `url`
  - Drop `created_at` field entirely
- [ ] Rewrite `merge_file()` to follow the Phase 5 consumer pattern:
  - `MERGE (f:File {id: $id}) SET f += $props REMOVE f.stub`
  - Accepts `relationships: Optional[List[DbRelationship]] = None`
  - Uses `merge_relationship(session, from_id, type, to_id, properties)` signature

---

## Phase 3 — Producer Layer

*Depends on Phase 1. Steps 3a, 3b, 3c can be implemented in parallel.*

### 3a — Enrich `map_commit_files()`

**`src/connectors/producers/map_github.py`**

- [ ] Extend `map_commit_files()` return dicts to include derived fields:
  - `name` — `Path(f.filename).name`
  - `extension` — `Path(f.filename).suffix`
  - `language` — from `ext_to_lang` lookup dict (same mapping as old `new_file_handler.py`)
  - `is_test` — `True` if filename contains `test`, `spec`, `__tests__`, `tests/`, `.test.`, `.spec.`

### 3b — New signal builder

**`src/connectors/producers/github/build_file_signal.py`** (NEW FILE)

- [ ] `build_file_signal(file_data, commit_data, repo_data) -> Optional[ActivitySignal]`
- [ ] `id = f"{repo_data['name']}::{file_data['filename']}"`
- [ ] `event_time` = `datetime.fromisoformat(commit_data['created_at']).replace(tzinfo=timezone.utc)`
- [ ] `FileAttributes(path=file_data['filename'], repo_name=repo_data['name'], name=..., extension=..., language=..., is_test=..., last_updated_at=commit_data['created_at'], url=..., additions=..., deletions=...)`
- [ ] Single relationship:
  ```python
  Relationship(
      type="MODIFIES",
      direction="IN",
      target=RelationshipTarget(source="github", entity_type="Commit", id=commit_data["sha"]),
      properties={"additions": file_data["additions"], "deletions": file_data["deletions"]},
  )
  ```
- [ ] Wrapped in `try/except` with `logger.warning` + `return None`

### 3c — Wire into commit processing

**`src/connectors/producers/github/process_single_commit.py`**

- [ ] Inside `extract_data()` thread block, also call `map_commit_files(commit.files)` and return alongside `commit_data`/`author_data`
- [ ] After `await pub_callback(build_commit_signal(...))`, loop over file dicts and call `await pub_callback(build_file_signal(file_data, commit_data, repo_data))` per file
- [ ] Pass `repo_data` into `process_single_commit()` (add parameter if not already present)

---

## Phase 4 — Consumer Layer

*Depends on Phases 1 and 2.*

**`src/connectors/consumers/sinks/neo4j_sink.py`**

- [ ] Add `File` and `merge_file` to the import from `connectors.neo4j_db.models`
- [ ] Add handler function:
  ```python
  def _handle_file(session, signal, person_cache):
      node_id = wba_node_id(signal)
      attrs = signal.attributes
      db_rels = _to_db_relationships(session, signal.relationships, node_id, signal.entity_type)
      node = File(
          id=node_id,
          path=attrs.path,
          repo_name=attrs.repo_name,
          name=attrs.name,
          extension=attrs.extension,
          language=attrs.language,
          is_test=attrs.is_test,
          size=attrs.size,
          last_updated_at=attrs.last_updated_at,
          url=attrs.url,
      )
      merge_file(session, node, db_rels)
  ```
- [ ] Add `"File": _handle_file` to `DISPATCH`

---

## Phase 5 — Tests

*Depends on Phases 1–4. Steps 5a and 5b can run in parallel.*

### 5a — Producer tests

**`tests/test_github_producer_phase4.py`** — add `TestBuildFileSignal` class:

- [ ] `test_build_file_signal_happy_path` — assert `signal.id == "my-repo::src/app/main.py"`, `entity_type == "File"`, `source == "github"`, one relationship with `type == "MODIFIES"`, `direction == "IN"`, `target.entity_type == "Commit"`, `target.id == sha`
- [ ] `test_build_file_signal_returns_none_on_missing_path` — pass `{}`, assert returns `None`
- [ ] `test_build_file_signal_relationship_properties_carry_additions_deletions` — assert `signal.relationships[0].properties == {"additions": 3, "deletions": 1}`

### 5b — Consumer tests

**`tests/test_consumer_phase5.py`** — add:

- [ ] `test_handle_file_upserts_correct_node` — mock session, assert `merge_file` called with `node.id == "github::File::my-repo::src/app/main.py"`
- [ ] `test_handle_file_creates_modifies_relationship` — assert relationship written with correct from/to IDs
- [ ] **Migration completeness guard** (prevents future misses):
  ```python
  @pytest.mark.unit
  def test_all_supported_entity_types_have_handlers():
      """Every entity type in the schema must have a consumer handler."""
      # Person is handled directly in upsert_signal, not via DISPATCH
      covered = set(DISPATCH.keys()) | {"Person"}
      missing = SUPPORTED_ENTITY_TYPES - covered
      assert not missing, f"No consumer handler for entity types: {missing}"
  ```

---

## Phase 6 — Verification

- [ ] `pytest -m unit tests -q` — all pass including new File tests and completeness guard
- [ ] `docker compose run --rm github-producer` — exits 0, logs show `File: N` in signal counts
- [ ] Neo4j Browser verification:
  ```cypher
  -- Canonical node IDs
  MATCH (f:File) RETURN f.id LIMIT 20
  -- All IDs must be: github::File::repo-name::path/to/file.ext

  -- Directed MODIFIES edges exist
  MATCH (c:Commit)-[:MODIFIES]->(f:File) RETURN c.id, f.id LIMIT 10

  -- No stubs remain after full sync
  MATCH (n) WHERE n.stub = true AND 'File' IN labels(n) RETURN count(n)
  -- Must return 0
  ```
- [ ] Verify all 5 previously broken catalog queries now return results in the Graph UI

---

## Files Changed

| File | Change type |
|---|---|
| `src/common/activity_signal/models.py` | Modify — add `FileAttributes`, update union and constants |
| `src/connectors/neo4j_db/models.py` | Modify — replace `File` dataclass + `merge_file()` in-place |
| `src/connectors/producers/map_github.py` | Modify — enrich `map_commit_files()` return dict |
| `src/connectors/producers/github/build_file_signal.py` | **New file** |
| `src/connectors/producers/github/process_single_commit.py` | Modify — wire File signal emission |
| `src/connectors/consumers/sinks/neo4j_sink.py` | Modify — add `_handle_file` + dispatch entry |
| `tests/test_github_producer_phase4.py` | Modify — add `TestBuildFileSignal` |
| `tests/test_consumer_phase5.py` | Modify — add File handler tests + completeness guard |

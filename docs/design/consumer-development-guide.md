# ActivitySignal Consumer Development Guide

> **Certification checklist** for extending the ActivitySignal consumer to handle
> a new entity type or a new source system.
> The consumer reads `ActivitySignal` events from RabbitMQ and writes them to Neo4j.
>
> **Core files to understand before starting:**
> - `src/connectors/consumers/sinks/neo4j_sink.py` — dispatch router and relationship builder
> - `src/connectors/neo4j_db/models.py` — `merge_*` functions and Neo4j dataclasses
> - `src/connectors/commons/person_cache.py` — cross-source Person deduplication
> - `src/connectors/consumers/main.py` — RabbitMQ consumption loop and entry point
> - `src/common/activity_signal/wba_node_id.py` — `wba_node_id()` and `wba_format()`

---

## How to use this checklist

Work through each phase in order. Mark items `[x]` as you go.
Phases 5 and 6 apply **only to `Person` entity types** — skip them for all other entities.

---

## Phase 1 — Pre-flight: Understand the Pipeline

```
RabbitMQ
  └─► main.py (_sync_upsert)
        └─► neo4j_sink.dispatch_signal(driver, signal, person_cache)
              ├─ looks up entity_type in DISPATCH dict
              ├─ calls _handle_<entity>(session, signal, person_cache)
              │     ├─ node_id = wba_node_id(signal)   →  {source}::{EntityType}::{id}
              │     ├─ builds Neo4j dataclass from signal.attributes
              │     ├─ _to_db_relationships(session, signal.relationships, node_id, entity_type)
              │     └─ merge_<entity>(session, node, relationships)
              └─► Neo4j (MERGE on id property)
```

- [ ] Understand `wba_node_id(signal)` → `{source}::{entity_type}::{id}` — this is the Neo4j `id` property
- [ ] Understand `wba_format(source, entity_type, raw_id)` — used to compute canonical keys for
  relationship targets and `IdentityMapping` nodes
- [ ] Read `src/connectors/neo4j_db/models.py` — understand existing `merge_*` function signatures
- [ ] Read `src/connectors/consumers/sinks/neo4j_sink.py` — understand `DISPATCH`, `_to_db_relationships`,
  and the direction-handling logic
- [ ] Confirm your entity type is in `SUPPORTED_ENTITY_TYPES` in `models.py` — add it before starting
- [ ] Read `docs/design/spec-activity-signal.md` for the full schema reference

---

## Phase 2 — Neo4j Dataclass and `merge_*` Function

Add to `src/connectors/neo4j_db/models.py`.

### 2.1 — Dataclass

```python
@dataclass
class MyEntity:
    id: str           # WBA canonical key: {source}::{EntityType}::{raw_id}
    name: str         # Human-readable display name
    source: str
    # ... all fields from the corresponding *Attributes model
    updated_at: Optional[str] = None
```

- [ ] `id` field holds the **WBA canonical key** (not the raw id)
  — this is the value returned by `wba_node_id(signal)`
- [ ] Include all non-None fields from the corresponding `*Attributes` model
- [ ] Use `Optional[str] = None` for optional fields

### 2.2 — `merge_<entity>()` function

```python
def merge_<entity>(
    session: Session,
    node: MyEntity,
    relationships: Optional[List[Relationship]] = None,
) -> None:
    props = {k: v for k, v in dataclasses.asdict(node).items() if v is not None}
    session.run(
        """
        MERGE (n:MyEntity {id: $id})
        SET n += $props
        REMOVE n.stub
        """,
        id=node.id,
        props=props,
    )
    for rel in (relationships or []):
        merge_relationship(session, node.id, rel.type, rel.to_id, rel.properties)
```

- [ ] `MERGE` on `id` property — all other properties set via `SET n += $props`
- [ ] `REMOVE n.stub` — clears the stub flag when a full signal arrives for a previously-stubbed node
- [ ] Each relationship written via `merge_relationship(session, from_id, type, to_id, properties)`
- [ ] Export the new class and function from the module

---

## Phase 3 — `neo4j_sink.py` Handler and Dispatch Entry

Add to `src/connectors/consumers/sinks/neo4j_sink.py`.

### 3.1 — Import

```python
from connectors.neo4j_db.models import (
    ...,
    MyEntity,
    merge_<entity>,
)
```

### 3.2 — Handler function

```python
def _handle_<entity>(
    session: Session,
    signal: ActivitySignal,
    person_cache: PersonCache,
) -> None:
    node_id = wba_node_id(signal)                        # {source}::{EntityType}::{raw_id}
    attrs = signal.attributes                            # already validated *Attributes instance
    db_rels = _to_db_relationships(
        session, signal.relationships, node_id, signal.entity_type
    )
    node = MyEntity(
        id=node_id,
        name=attrs.<name_field>,
        source=signal.source,
        # ... map remaining attributes
    )
    merge_<entity>(session, node, db_rels)
```

### 3.3 — Dispatch entry

```python
DISPATCH: dict[str, Callable] = {
    ...,
    "MyEntity": _handle_<entity>,
}
```

Checklist:
- [ ] `node_id = wba_node_id(signal)` — always the first line of the handler
- [ ] `signal.attributes` is accessed as the typed `*Attributes` instance (no dict access needed)
- [ ] `_to_db_relationships()` called before constructing the Neo4j dataclass
- [ ] Entity type string in `DISPATCH` exactly matches the `entity_type` value in signals

---

## Phase 4 — RelationshipTarget Resolution

`_to_db_relationships()` in `neo4j_sink.py` resolves each `RelationshipTarget` to a Neo4j node ID
using this priority order:

| Priority | Condition | Resolution |
|----------|-----------|------------|
| 1 | `entity_type == "Person"` and `target.email` set | Query Neo4j: `MATCH (p:Person {email: $email})` |
| 2 | `target.url` set | Query Neo4j: `MATCH (n {url: $url})` |
| 3 | `target.id` set | Compute `wba_format(target.source, target.entity_type, target.id)` |

- [ ] Confirm all `RelationshipTarget` entries from your producer set at least one of: `email`, `url`, `id`
- [ ] For cross-source references (e.g. a GitHub commit referencing a Jira issue), verify
  `target.source` is set to the correct source (`"jira"`, not `"github"`)
- [ ] Targets with no resolvable identifier are **skipped** with a warning — ensure producers
  always supply at least one identifier on every `RelationshipTarget`
- [ ] Stub nodes are created automatically when a target is not yet in Neo4j — no code change needed

---

## Phase 5 — Person Deduplication (Person signals only)

> **Skip this phase** if your new entity type is not `Person`.

`PersonCache` merges GitHub and Jira persons that share the same email address into a single
`Person` node. The cache is created once per consumer batch and passed to every handler.

```python
# In _handle_person():
canonical_person_id = person_cache.resolve(
    source=signal.source,
    login_or_account_id=signal.id,    # raw id from the signal
    email=attrs.email,
)
# Use canonical_person_id (not wba_node_id(signal)) as the Neo4j Person node id
```

- [ ] `person_cache.resolve()` called **before** computing the final Neo4j `id` for the Person node
- [ ] The returned `canonical_person_id` is used as `node.id` when merging the Person node
  — it may differ from `wba_node_id(signal)` when a cross-source merge occurs
- [ ] `PersonCache` is **not** instantiated inside the handler — it is injected by `main.py`
- [ ] Cross-source merges are logged by `PersonCache` — no extra logging needed

Reference: `src/connectors/commons/person_cache.py`

---

## Phase 6 — IdentityMapping Node (Person signals only)

> **Skip this phase** if your new entity type is not `Person`.

Every `Person` signal must produce an `IdentityMapping` node that links the provider identity
(login or account_id) to the canonical `Person` node.

```python
# In _handle_person(), after resolving canonical_person_id:

# Compute the canonical IdentityMapping node ID
identity_id = wba_format(signal.source, "IdentityMapping", signal.id)
# e.g. "github::IdentityMapping::alice"  or  "jira::IdentityMapping::557058:abc"

# MERGE the IdentityMapping node
session.run(
    """
    MERGE (i:IdentityMapping {id: $identity_id})
    SET i.provider = $source,
        i.username = $username,
        i.updated_at = $updated_at
    """,
    identity_id=identity_id,
    source=signal.source,
    username=signal.id,
    updated_at=datetime.now(timezone.utc).isoformat(),
)

# Create undirected MAPS_TO edge between IdentityMapping and Person
merge_relationship(session, identity_id, "MAPS_TO", canonical_person_id, properties=None)
```

- [ ] `identity_id = wba_format(source, "IdentityMapping", raw_login_or_account_id)`
  — format: `github::IdentityMapping::alice` / `jira::IdentityMapping::557058:abc`
- [ ] **Never** use old-format IDs: `identity_github_*` or `identity_jira_*` must not appear
- [ ] `MAPS_TO` edge is undirected (no direction argument, or `direction=None`)
- [ ] `IdentityMapping` node has at minimum: `id`, `provider`, `username`

Reference implementations:
- GitHub: `src/connectors/modules/github/new_commit_handler.py` (line ~98)
- Jira: `src/connectors/modules/jira/new_jira_user_handler.py`
- Sink: `src/connectors/consumers/sinks/neo4j_sink.py` (existing `_handle_person`)

---

## Phase 7 — Stub Node Handling

Stub nodes are created automatically by `_to_db_relationships()` when a relationship target
does not yet exist in Neo4j. No code changes are needed unless you require custom stub behaviour.

- [ ] Run your producer **before** the consumer at least once to verify stub creation works
  — stub nodes appear in Neo4j with `stub=True` and only the `id` property set
- [ ] Confirm stubs are backfilled when the full signal arrives later
  — the `REMOVE n.stub` in your `merge_*` function handles this (Phase 2)
- [ ] If stub nodes persist after a full sync, check that the producer is setting `id` on
  `RelationshipTarget` matching the raw id used in the target entity's `ActivitySignal`

---

## Phase 8 — Tests

Create or extend `tests/test_consumer_<source>.py`.
Reference: `tests/test_consumer_phase5.py`.

Mark all test functions with `@pytest.mark.unit`.

```python
@pytest.mark.unit
def test_handle_<entity>_upserts_correct_node(mock_session, mock_person_cache):
    signal = ActivitySignal(
        source="<source>",
        id="<raw_id>",
        ...,
        attributes=<Entity>Attributes(...),
        relationships=[
            Relationship(type="...", target=RelationshipTarget(source="...", entity_type="...", id="...")),
        ],
    )
    _handle_<entity>(mock_session, signal, mock_person_cache)
    # Assert merge was called with the WBA canonical key as node id
    merge_call_args = mock_merge.call_args
    assert merge_call_args[0][1].id == f"<source>::<EntityType>::<raw_id>"


@pytest.mark.unit
def test_handle_person_creates_identity_mapping_with_canonical_id(...):
    # For Person signals only:
    # Assert IdentityMapping node id == "github::IdentityMapping::alice"
    # Assert NOT "identity_github_alice" (old format)
    ...
```

- [ ] Test `_handle_<entity>()` with a mock `Session`
- [ ] Assert the `merge_<entity>` function is called with `node.id == wba_node_id(signal)`
- [ ] Assert correct number of relationships passed
- [ ] For Person tests: assert `IdentityMapping` `id` uses canonical format
- [ ] Test that `RelationshipTarget` with `id=None`, `email=None`, `url=None` is skipped with a warning
- [ ] `pytest -m unit tests -q` passes with no failures

---

## Phase 9 — End-to-End Verification

Run the full sync pipeline and verify in Neo4j Browser.

- [ ] `docker compose run --rm <source>-sync` (or trigger the consumer) exits with code 0
- [ ] Verify canonical node IDs:
  ```cypher
  MATCH (n:<EntityType>) RETURN n.id LIMIT 20
  ```
  All IDs must match `{source}::{EntityType}::{raw_id}` format.
- [ ] Verify **zero** old-format IDs exist:
  ```cypher
  MATCH (n)
  WHERE n.id STARTS WITH 'identity_github_'
     OR n.id STARTS WITH 'identity_jira_'
  RETURN count(n)
  ```
  Result must be **0**.
- [ ] Verify `IdentityMapping` nodes (Person entities only):
  ```cypher
  MATCH (i:IdentityMapping)-[:MAPS_TO]-(p:Person)
  RETURN i.id, p.id LIMIT 10
  ```
  Both `i.id` and `p.id` must be in canonical format.
- [ ] Verify cross-source Person deduplication (if applicable):
  ```cypher
  MATCH (p:Person)-[:MAPS_TO]-(i:IdentityMapping)
  WITH p, collect(i.id) AS ids WHERE size(ids) > 1
  RETURN p.id, ids LIMIT 5
  ```
  Shows persons merged across sources (both `github::IdentityMapping::*` and `jira::IdentityMapping::*`).
- [ ] Verify no stub nodes remain after a full sync:
  ```cypher
  MATCH (n) WHERE n.stub = true RETURN n.id, labels(n) LIMIT 10
  ```

---

*Last updated: 2026-05-20*

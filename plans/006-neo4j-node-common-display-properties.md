# Plan 006: Common node display/time properties via `GraphNode` ABC

> **Executor instructions**: Follow this plan step by step. Each step has a
> **Verify** command — do not proceed to the next step until it passes.
>
> **Drift check (run first)**: `git diff --stat 264fedf..HEAD -- src/connectors/neo4j_db/models.py tests/property_validation/model_inspector.py`

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MEDIUM (touches every node dataclass + every merge_* function + producer/consumer call sites)
- **Depends on**: none
- **Category**: refactor / feature enablement
- **Planned at**: commit `264fedf`, 2026-07-05
- **Reached via**: interactive grill-me session with the repo owner (see decisions log below)

## Why this matters

The Graph UI (`src/app/dash_app/pages/graph/utils/data_transform.py`) and the
hover-tooltip feature (`src/app/dash_app/pages/graph/callbacks/navigation.py`)
currently derive a node's display label ad-hoc, per-render, via a hardcoded
`name or title or key or label` fallback chain. There is no stored concept of
"when was this node last synced" or "when was the underlying entity last
updated" on most node types, which blocks building a time-based filter for the
Graph page. This plan introduces four common, always-present, computed
properties — `_display_name`, `_on_hover_name`, `_last_seen_at`,
`_last_updated_at` — persisted as real Neo4j node properties at write-time via
an ABC (`GraphNode`) that all 15 node dataclasses in
`src/connectors/neo4j_db/models.py` inherit from.

**Explicitly out of scope for this plan**: the actual time-based filter UI on
the Graph page (a future plan will consume `_last_seen_at`/`_last_updated_at`
client-side, consistent with the existing local-only filtering architecture —
see repo memory `graph-filtering-architecture.md`). This plan only lands the
data model + backfill + indexes + the display-name wiring into
`neo4j_to_cytoscape()`.

## Key decisions (from the grill-me session)

1. **Materialization**: computed at write-time inside `to_neo4j_properties()`
   and persisted as real Neo4j node properties — not computed on-the-fly at
   read time. The Graph page runs arbitrary raw/catalog Cypher, so read-time
   computation would need to be duplicated in every query path.
2. **Mechanism**: plain (non-`@property`) methods on an ABC mixin, matching
   the existing method-based style (`to_neo4j_properties()`, `print_cli()`).
   No `__post_init__`, no `init=False`, no stored redundant fields for the 4
   computed values — they're derived from existing fields via `getattr`
   fallback chains and only materialize as dict keys inside
   `to_neo4j_properties()`.
3. **Base class also gains two literal fields**: `id: str` (already 100%
   consistent — zero risk) and `url: str` (now **mandatory**, no default —
   every construction call site must explicitly pass a value, empty string
   `""` allowed when no real URL exists; `_has_value()` already treats `""`
   as absent when writing to Neo4j, so this is a type-honesty fix, not a
   behavior change). `Repository.url` today is incorrectly typed as
   required-but-already-treated-as-optional — this normalizes it.
4. **Naming**: `_last_seen_at` / `_last_updated_at` (matching the existing
   `_last_synced_at` naming convention), not `_last_seen_time` /
   `_last_updated_time`.
5. **Default computation, overridable**: base class provides sensible
   generic defaults (getattr fallback across common field names) so most
   subclasses need zero overrides; only a few special cases override.
6. **Relationship dataclass**: untouched — out of scope, "Nodes" only.
7. **ABC location**: new file `src/connectors/neo4j_db/node_base.py`.
8. **Test discovery fix**: `tests/property_validation/model_inspector.py`
   currently hardcodes a name-based skip for `JiraIssueBase`. Switch to
   `inspect.isabstract(obj)` so `GraphNode` (and any future ABC) is
   automatically excluded.
9. **Backfill**: one-time Cypher backfill script for nodes already in Neo4j
   (simulation + real data) that predate this change.
10. **Indexing**: add indexes for `_display_name`, `_last_seen_at`,
    `_last_updated_at` now, per `docs/design/INDEX_STRATEGY.md` conventions
    (Priority 3 date/time tier + lookup tier), even though the filter UI
    itself is a future plan.
11. **Graph UI wiring**: `neo4j_to_cytoscape()` switches to reading
    `properties['_display_name']` / `_on_hover_name` directly — **no
    fallback** to the old ad-hoc logic (explicit simplicity trade-off:
    queries whose `RETURN` clause excludes these properties will render a
    blank label; this is accepted).
12. **Testing**: new dedicated `tests/test_neo4j_node_base.py` covering all
    15 node types' computed-method behavior (defaults + overrides), the
    mandatory-`url` constructor enforcement, and `to_neo4j_properties()`
    output.

## Current state

`src/connectors/neo4j_db/models.py` — 15 independent `@dataclass` node types
(`Person`, `Team`, `IdentityMapping`, `Project`, `Initiative`/`JiraIssueBase`,
`Epic`, `Issue`, `Sprint`, `Repository`, `Commit`, `File`, `PullRequest`,
`Space`, `Page`, `Blogpost`), each with its own `to_neo4j_properties()` and no
shared base class. 13 of the corresponding `merge_*` functions manually
enumerate which properties get a Cypher `SET` clause via a `_has_value()`
guard; `merge_file` (and the Confluence snapshot-interaction path) instead
uses `SET n += $props`.

## Scope

**In scope**:
- `src/connectors/neo4j_db/node_base.py` (new)
- `src/connectors/neo4j_db/models.py` (all 15 dataclasses + all `merge_*` functions except `merge_relationship`)
- `src/connectors/commons/person_cache.py` (add `url` to `IdentityMapping` construction)
- `src/connectors/commons/identity_resolver.py`, `src/connectors/consumers/sinks/neo4j_sink.py` (verify `url=` present; fix any gaps mypy/tests surface)
- `simulation/layer*/load_to_neo4j.py`, `simulation/layer1/example_usage.py` (verify/fix `url=` construction gaps)
- `tests/property_validation/model_inspector.py` (discovery fix)
- `tests/test_neo4j_node_base.py` (new)
- `src/app/dash_app/pages/graph/utils/data_transform.py` (`neo4j_to_cytoscape` display wiring)
- `simulation/create_indixes.sh` / index creation script (add 3 new indexes)
- One-time backfill script (new, e.g. `scripts/backfill_node_display_properties.py`)

**Out of scope**: `Relationship` dataclass, the actual time-based filter UI/controls on the Graph page, any backend filter API.

## Steps

### Step 1: Create the `GraphNode` ABC

New file `src/connectors/neo4j_db/node_base.py`:

```python
"""Common base for all Neo4j node dataclasses in models.py.

Provides the four always-present, computed display/time properties:
_display_name, _on_hover_name, _last_seen_at, _last_updated_at. These are
never stored as redundant dataclass fields — they are derived from each
subclass's own existing fields and materialize only as dict keys inside
to_neo4j_properties(), where they become real, queryable Neo4j properties.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Any, Dict, Optional


class GraphNode(ABC):
    """Mixin enforcing common identity/display/time metadata on node dataclasses."""

    id: str
    url: str

    def display_name(self) -> str:
        """Default: first non-empty of name/title/summary/key, else id.

        Override for node types needing custom composition (e.g. PullRequest).
        """
        for attr in ("name", "title", "summary", "key"):
            value = getattr(self, attr, None)
            if value:
                return str(value)
        return self.id

    def on_hover_name(self) -> str:
        """Default: same as display_name(). Override for a richer tooltip."""
        return self.display_name()

    def last_seen_at(self) -> Optional[str]:
        """Default: the _last_synced_at field, if the subclass has one."""
        return getattr(self, "_last_synced_at", None)

    def last_updated_at(self) -> Optional[str]:
        """Default: first non-empty of updated_at/last_updated_at, else None.

        Override for immutable entities (e.g. Commit -> created_at).
        """
        for attr in ("updated_at", "last_updated_at"):
            value = getattr(self, attr, None)
            if value:
                return str(value)
        return None

    def to_neo4j_properties(self) -> Dict[str, Any]:
        """Default to_neo4j_properties(): asdict() + the 4 computed keys.

        Subclasses with custom filtering (e.g. dropping empty lists) should
        call this via super() and layer their own filtering on top, or
        replicate the same 4-key injection if they can't call super() cleanly.
        """
        props = {k: v for k, v in asdict(self).items() if v is not None}
        props["_display_name"] = self.display_name()
        props["_on_hover_name"] = self.on_hover_name()
        last_seen = self.last_seen_at()
        if last_seen is not None:
            props["_last_seen_at"] = last_seen
        last_updated = self.last_updated_at()
        if last_updated is not None:
            props["_last_updated_at"] = last_updated
        return props

    @abstractmethod
    def print_cli(self) -> None:
        """Every node type must implement its own CLI pretty-printer (existing convention)."""
```

**Verify**: `python -c "from connectors.neo4j_db.node_base import GraphNode"` → no import error.

### Step 2: Update each of the 15 dataclasses to inherit `GraphNode`

For each class in `models.py`:
- Add `GraphNode` as base: `class Person(GraphNode):` (and `class Epic(GraphNode):`, etc. — `Initiative` already extends `JiraIssueBase`, so make `JiraIssueBase(GraphNode)` instead).
- Remove the class's own `id: str` field declaration (inherited) — keep it first conceptually, no code change needed since dataclass field order still resolves correctly (`id` from base, then the subclass's own fields).
- Change the class's own `url` field from `Optional[str] = None` (or `str` required, for `Repository`) to simply removing the field declaration entirely (inherited as required `url: str` from base).
- Keep each class's existing `to_neo4j_properties()` override as-is *except*: it must now also inject the 4 computed keys. Simplest approach: call `super().to_neo4j_properties()` isn't safe where a subclass does custom key-filtering (e.g. dropping empty lists) — instead, each override should build its filtered dict as today, then add:
  ```python
  props["_display_name"] = self.display_name()
  props["_on_hover_name"] = self.on_hover_name()
  if self.last_seen_at() is not None:
      props["_last_seen_at"] = self.last_seen_at()
  if self.last_updated_at() is not None:
      props["_last_updated_at"] = self.last_updated_at()
  ```
- Add per-class overrides only where the defaults are insufficient (propose reviewing during implementation; likely candidates: `PullRequest.on_hover_name()` → `f"PR #{self.number}: {self.title}"`; `Commit.last_updated_at()` → `return self.created_at` since commits are immutable).
- Add a minimal `print_cli(self) -> None` if a class doesn't already have one (all currently do).

**Verify**: `python -m pytest tests/property_validation/ -v -k "not neo4j"` → discovery still succeeds (no crash), and `python -c "import connectors.neo4j_db.models"` → no import error.

### Step 3: Update `model_inspector.py` discovery to use `inspect.isabstract()`

Replace the hardcoded name-based skips:
```python
        if name == 'Relationship':
            continue
        if name.startswith('_'):
            continue
        if name == 'JiraIssueBase':
            continue
```
with:
```python
        if name == 'Relationship':
            continue
        if name.startswith('_'):
            continue
        if inspect.isabstract(obj):
            continue
```

**Verify**: `python tests/property_validation/model_inspector.py` → prints all 15 concrete entities, `GraphNode` and `JiraIssueBase` excluded.

### Step 4: Add the 4 new `SET` clauses to each `merge_*` function

For the 13 `merge_*` functions that manually enumerate `set_clauses` (all except `merge_file`, which already uses `SET f += $props` and needs no change), add:
```python
    if _has_value(props, '_display_name'):
        set_clauses.append("p._display_name = $_display_name")
    if _has_value(props, '_on_hover_name'):
        set_clauses.append("p._on_hover_name = $_on_hover_name")
    if _has_value(props, '_last_seen_at'):
        set_clauses.append("p._last_seen_at = datetime($_last_seen_at)")
    if _has_value(props, '_last_updated_at'):
        set_clauses.append("p._last_updated_at = datetime($_last_updated_at)")
```
(substituting the correct node-variable letter per function, e.g. `i.` for issue/initiative, `e.` for epic, `c.` for commit, etc.)

**Verify**: `grep -c "_display_name = \$_display_name" src/connectors/neo4j_db/models.py` → 13.

### Step 5: Fix construction call sites now missing mandatory `url`

- `src/connectors/commons/person_cache.py` (`add_identity_mapping`, ~line 251): add `url=""` (or thread a real profile URL through if available at the call site — implementer's judgment) to the `IdentityMapping(...)` call.
- Update the `IdentityMapping` docstring example in `models.py` similarly.
- Run mypy + full test suite; fix any other construction call sites (simulation loaders, other tests) that mypy/pytest surface as missing `url`.

**Verify**: `mypy src/connectors/neo4j_db/models.py src/connectors/commons/ src/connectors/consumers/` → no "missing argument url" errors. `pytest -m unit tests -q` → all pass.

### Step 6: New unit tests — `tests/test_neo4j_node_base.py`

Cover, for all 15 node types:
- `display_name()` default fallback chain + at least one override case (`PullRequest`).
- `on_hover_name()` default (== display_name) + override case.
- `last_seen_at()` returns `_last_synced_at` where present, `None` otherwise.
- `last_updated_at()` fallback chain + `Commit` override (if added in Step 2).
- `to_neo4j_properties()` includes all 4 keys with expected values.
- Constructing any node type without `url` raises `TypeError`.

Mark all new tests `@pytest.mark.unit`.

**Verify**: `pytest -m unit tests/test_neo4j_node_base.py -v` → all pass.

### Step 7: Add Neo4j indexes for the 3 new properties

Extend the index creation script (`simulation/create_indixes.sh` / the Python
index script it calls) with per-label indexes for `_display_name`,
`_last_seen_at`, `_last_updated_at` across all 15 node labels, following the
existing Priority 3 (date/time) and Priority 1 (lookup) conventions in
`docs/design/INDEX_STRATEGY.md`.

**Verify**: run the index script against a local Neo4j instance; `SHOW INDEXES` includes the new entries.

### Step 8: One-time backfill script for existing nodes

New script (e.g. `scripts/backfill_node_display_properties.py`) that, per
node label, runs a Cypher `SET` using `coalesce()` across the same candidate
field names as the Python defaults (e.g.
`SET n._display_name = coalesce(n.name, n.title, n.summary, n.key, n.id)`,
`SET n._last_seen_at = n._last_synced_at`,
`SET n._last_updated_at = coalesce(n.updated_at, n.last_updated_at)`), so
existing nodes get the new properties without waiting for re-sync. Use direct
Cypher (not Python dataclass reconstruction) since historical nodes may be
missing fields that are now mandatory in the dataclass (e.g. `url`).

**Verify**: run against local/simulation Neo4j; spot-check via
`MATCH (n:Person) RETURN n._display_name LIMIT 5` (and similarly for a few
other labels) → non-null values.

### Step 9: Wire `neo4j_to_cytoscape()` to the new properties

In `src/app/dash_app/pages/graph/utils/data_transform.py`, replace:
```python
        display_name = (
            node.get("properties", {}).get("name") or
            node.get("properties", {}).get("title") or
            node.get("properties", {}).get("key") or
            node_label
        )
```
with:
```python
        display_name = node.get("properties", {}).get("_display_name", "")
```
and thread `_on_hover_name` into the tooltip data (`cyto_node_data['onHoverName'] = node.get("properties", {}).get("_on_hover_name", "")`), then update
`navigation.py`'s hover-tooltip clientside callback to read `onHoverName`
instead of the current full `label`.

**Verify**: manual check on the Graph page — nodes from a query whose `RETURN`
includes full node properties show the expected label and hover text; run
existing Dash graph tests (`pytest tests/test_collaboration_network_page.py tests/test_collab_spotlight.py -v` or equivalent graph UI tests) → all pass.

### Step 10: Full regression pass

**Verify**: `pytest -m unit tests -q` → all pass. `pytest tests/property_validation/test_property_validation.py -v` (if `NEO4J_ENABLED`) → no new EMPTY required-property regressions. `mypy src/connectors src/app/dash_app/pages/graph` → clean. `pylint src/connectors/neo4j_db/models.py src/connectors/neo4j_db/node_base.py` → no new warnings.

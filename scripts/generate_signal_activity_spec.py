#!/usr/bin/env python3
"""Auto-generate docs/design/spec-activity-signal.md from models.py.

The output file is fully rewritten on every run.
This script is the single source of truth for all code-derived sections
of the spec (field tables, entity types, relationship types, examples).
Narrative sections are maintained as strings inside this file.

Run:
    PYTHONPATH=src python scripts/generate_signal_activity_spec.py
"""

from __future__ import annotations

import json
import sys
import typing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, get_args, get_origin

# ---------------------------------------------------------------------------
# Path setup — works with or without PYTHONPATH=src
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from common.activity_signal.models import (  # noqa: E402
    ActivitySignal,
    BranchAttributes,
    CommitAttributes,
    EpicAttributes,
    InitiativeAttributes,
    IssueAttributes,
    PersonAttributes,
    ProjectAttributes,
    PullRequestAttributes,
    Relationship,
    RelationshipTarget,
    RepositoryAttributes,
    SprintAttributes,
    TeamAttributes,
    SUPPORTED_ENTITY_TYPES,
    SUPPORTED_RELATIONSHIP_TYPES,
)

# ---------------------------------------------------------------------------
# Entity type → Attributes class mapping (display order)
# ---------------------------------------------------------------------------

_ENTITY_ATTRS: list[tuple[str, type]] = [
    ("Project", ProjectAttributes),
    ("Initiative", InitiativeAttributes),
    ("Epic", EpicAttributes),
    ("Sprint", SprintAttributes),
    ("Issue", IssueAttributes),
    ("Repository", RepositoryAttributes),
    ("Branch", BranchAttributes),
    ("Commit", CommitAttributes),
    ("PullRequest", PullRequestAttributes),
    ("Person", PersonAttributes),
    ("Team", TeamAttributes),
]


# ---------------------------------------------------------------------------
# Type annotation formatter
# ---------------------------------------------------------------------------

def _fmt_type(tp: Any) -> str:
    """Return a concise, human-readable string for a type annotation."""
    if tp is type(None):
        return "None"

    origin = get_origin(tp)
    args = get_args(tp)

    # Annotated[X, ...] → unwrap to X
    if origin is not None:
        origin_str = getattr(origin, "__name__", str(origin))
        if "Annotated" in str(origin):
            return _fmt_type(args[0]) if args else "Any"

    # Also check for Annotated via typing module directly
    try:
        if hasattr(typing, "Annotated") and origin is typing.get_origin(
            typing.Annotated[int, "x"]
        ):
            return _fmt_type(args[0]) if args else "Any"
    except Exception:
        pass

    # Union / Optional
    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and len(args) == 2:
            return f"Optional[{_fmt_type(non_none[0])}]"
        return " | ".join(_fmt_type(a) for a in non_none)

    # list[X]
    if origin is list:
        return f"list[{_fmt_type(args[0])}]" if args else "list"

    # dict[K, V]
    if origin is dict:
        if args and len(args) == 2:
            return f"Dict[{_fmt_type(args[0])}, {_fmt_type(args[1])}]"
        return "dict"

    # Literal[...]
    if args and origin is not None and "Literal" in str(origin):
        return f"Literal[{', '.join(repr(a) for a in args)}]"

    # Plain type with __name__
    if hasattr(tp, "__name__"):
        return tp.__name__

    # Fallback: stringify and strip noisy module paths
    s = str(tp)
    for prefix in [
        "typing.",
        "common.activity_signal.models.",
        "datetime.",
        "builtins.",
    ]:
        s = s.replace(prefix, "")
    # Truncate very long union strings
    if len(s) > 60:
        s = s[:57] + "..."
    return s


# ---------------------------------------------------------------------------
# Markdown table builder
# ---------------------------------------------------------------------------

def _fields_table(model_cls: type, skip_fields: Optional[set[str]] = None) -> str:
    """Return a Markdown table for the model's declared fields.

    Columns: Field | Type | Required | Notes
    - Required = ✓ when the field has no default.
    - Notes = Field(description=...) value, blank when absent.
    """
    skip = skip_fields or set()
    rows = [
        "| Field | Type | Required | Notes |",
        "|-------|------|:--------:|-------|",
    ]
    for name, field in model_cls.model_fields.items():
        if name in skip:
            continue
        tp = _fmt_type(field.annotation)
        required = "✓" if field.is_required() else ""
        notes = field.description or ""
        rows.append(f"| `{name}` | `{tp}` | {required} | {notes} |")

    # Include computed fields (e.g. entity_type on ActivitySignal)
    if hasattr(model_cls, "model_computed_fields"):
        for name, cf in model_cls.model_computed_fields.items():
            if name in skip:
                continue
            tp = _fmt_type(cf.return_type) if hasattr(cf, "return_type") else "str"
            notes = cf.description or "*(computed property)*"
            rows.append(f"| `{name}` | `{tp}` | | {notes} |")

    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Synthetic examples
# ---------------------------------------------------------------------------

def _issue_example() -> str:
    """Build a realistic Jira Issue ActivitySignal and return it as JSON."""
    signal = ActivitySignal(
        signal_id="a1b2c3d4-0000-1111-2222-333344445555",
        source="jira",
        id="PROJ-123",
        source_config="https://mycompany.atlassian.net",
        connector_url="http://localhost:8000/connectors/jira",
        event_time=datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc),
        ingestion_time=datetime(2026, 5, 1, 12, 0, 5, tzinfo=timezone.utc),
        version="1.0",
        attributes=IssueAttributes(
            key="PROJ-123",
            summary="Fix login bug on mobile",
            priority="High",
            status="In Progress",
            type="Bug",
            created_at="2026-04-01T09:00:00Z",
            updated_at="2026-05-01T12:00:00Z",
            story_points=3.0,
            url="https://mycompany.atlassian.net/browse/PROJ-123",
        ),
        relationships=[
            Relationship(
                type="PART_OF",
                direction=None,
                target=RelationshipTarget(
                    source="jira", entity_type="Epic", id="EPIC-10"
                ),
            ),
            Relationship(
                type="IN_SPRINT",
                direction=None,
                target=RelationshipTarget(
                    source="jira", entity_type="Sprint", id="42"
                ),
            ),
            Relationship(
                type="ASSIGNED_TO",
                direction=None,
                target=RelationshipTarget(
                    source="jira", entity_type="Person", id="557058:abc123"
                ),
            ),
        ],
    )
    return json.dumps(signal.model_dump(mode="json"), indent=2)


def _pull_request_example() -> str:
    """Build a realistic GitHub PullRequest ActivitySignal and return it as JSON."""
    signal = ActivitySignal(
        signal_id="b2c3d4e5-1111-2222-3333-444455556666",
        source="github",
        id="my-repo::99",
        source_config="https://github.com",
        connector_url="http://localhost:8000/connectors/github",
        event_time=datetime(2026, 5, 10, 15, 30, 0, tzinfo=timezone.utc),
        ingestion_time=datetime(2026, 5, 10, 15, 30, 5, tzinfo=timezone.utc),
        version="1.0",
        attributes=PullRequestAttributes(
            repo_name="my-repo",
            pull_request_number=99,
            title="Add two-factor authentication",
            state="merged",
            created_at="2026-05-08T10:00:00Z",
            updated_at="2026-05-10T15:30:00Z",
            merged_at="2026-05-10T15:30:00Z",
            user="alice",
            commits_count=4,
            additions=120,
            deletions=30,
            changed_files=5,
            head_branch_name="feature/2fa",
            base_branch_name="main",
            url="https://github.com/myorg/my-repo/pull/99",
        ),
        relationships=[
            Relationship(
                type="CREATED_BY",
                direction=None,
                target=RelationshipTarget(
                    source="github", entity_type="Person", id="alice"
                ),
            ),
            Relationship(
                type="REVIEWED_BY",
                direction=None,
                target=RelationshipTarget(
                    source="github", entity_type="Person", id="bob"
                ),
            ),
            Relationship(
                type="TARGETS",
                direction="OUT",
                target=RelationshipTarget(
                    source="github", entity_type="Branch", id="my-repo::main"
                ),
            ),
        ],
    )
    return json.dumps(signal.model_dump(mode="json"), indent=2)


# ---------------------------------------------------------------------------
# Spec assembler
# ---------------------------------------------------------------------------

def _build_spec() -> str:
    """Assemble the complete spec document as a Markdown string."""
    lines: list[str] = []

    # ---- Auto-gen header ----
    lines += [
        "<!-- AUTO-GENERATED by scripts/generate_signal_activity_spec.py — do not edit manually -->",
        "<!-- To regenerate: PYTHONPATH=src python scripts/generate_signal_activity_spec.py -->",
        "",
        "# ActivitySignal Specification",
        "",
        "> **This document is auto-generated.**",
        "> Source of truth: `src/common/activity_signal/models.py`.",
        "> To update: edit the models, then run:",
        "> ```",
        "> PYTHONPATH=src python scripts/generate_signal_activity_spec.py",
        "> ```",
        "> Do not edit this file manually — changes will be overwritten on the next run.",
        "",
        "---",
        "",
    ]

    # ---- 1. Introduction ----
    lines += [
        "## 1. Introduction",
        "",
        "ActivitySignal is a generic, extensible, source-agnostic event format for representing",
        "nodes and relationships ingested from systems such as Jira, GitHub, and others.",
        "Each signal describes one entity and its observed relationships at a point in time.",
        "Producers emit signals to RabbitMQ; consumers upsert them into Neo4j.",
        "",
        "The schema is defined as Pydantic models in `src/common/activity_signal/models.py`.",
        "This spec is derived directly from those models — the code is authoritative.",
        "",
        "---",
        "",
    ]

    # ---- 2. ActivitySignal Schema ----
    lines += [
        "## 2. ActivitySignal Schema",
        "",
        "### 2.1 Top-Level Fields (`ActivitySignal`)",
        "",
        _fields_table(ActivitySignal),
        "",
        "> `entity_type` is a **computed field** derived from the `attributes` discriminator.",
        "> It appears in serialized output (`model_dump()`) but is not a constructor argument.",
        "",
        "### 2.2 Relationship Fields (`Relationship`)",
        "",
        _fields_table(Relationship),
        "",
        "### 2.3 RelationshipTarget Fields (`RelationshipTarget`)",
        "",
        _fields_table(RelationshipTarget),
        "",
        "> `extra='forbid'` — no fields beyond those listed above are accepted.",
        "> At least one of `id`, `email`, or `url` must be set for the consumer to resolve the target.",
        "",
        "---",
        "",
    ]

    # ---- 3. Canonical Node Identity ----
    lines += [
        "## 3. Canonical Node Identity",
        "",
        "The tuple `(source, entity_type, id)` uniquely identifies a node.",
        "Consumers compute the **WBA canonical key** as:",
        "",
        "```",
        "{source}::{entity_type}::{id}",
        "```",
        "",
        "This key is stored as the `id` property on every Neo4j node.",
        "Use `wba_node_id(signal)` from `common.activity_signal.wba_node_id` to compute it.",
        "",
        "| Entity | `id` value on signal | WBA canonical key (Neo4j `id` property) |",
        "|--------|----------------------|-----------------------------------------|",
        "| GitHub Repository | `org/repo` | `github::Repository::org/repo` |",
        "| GitHub Branch | `repo::main` | `github::Branch::repo::main` |",
        "| GitHub Commit | `abc123` (SHA) | `github::Commit::abc123` |",
        "| GitHub PR | `repo::42` | `github::PullRequest::repo::42` |",
        "| GitHub Person | `alice` (login) | `github::Person::alice` |",
        "| GitHub Team | `backend-team` (slug) | `github::Team::backend-team` |",
        "| Jira Project | `AB` (project key) | `jira::Project::AB` |",
        "| Jira Initiative | `AB-1` (issue key) | `jira::Initiative::AB-1` |",
        "| Jira Epic | `AB-10` (issue key) | `jira::Epic::AB-10` |",
        "| Jira Sprint | `34` (sprint id) | `jira::Sprint::34` |",
        "| Jira Issue | `AB-42` (issue key) | `jira::Issue::AB-42` |",
        "| Jira Person | `557058:abc...` (account_id) | `jira::Person::557058:abc...` |",
        "| GitHub IdentityMapping | `alice` (login) | `github::IdentityMapping::alice` |",
        "| Jira IdentityMapping | `557058:abc` (account_id) | `jira::IdentityMapping::557058:abc` |",
        "",
        "> **Rule for producers:** Set `id=<raw_identifier>` on `ActivitySignal` and `RelationshipTarget`.",
        "> Do **not** pass the full WBA canonical key — the consumer computes it.",
        "",
        "---",
        "",
    ]

    # ---- 4. Supported Entity Types ----
    lines += [
        "## 4. Supported Entity Types",
        "",
        "Defined in `SUPPORTED_ENTITY_TYPES` in `models.py`.",
        "All `ActivitySignal.attributes` must use one of these types as the discriminator.",
        "",
        "| Entity Type | Source |",
        "|-------------|--------|",
        "| `Project` | Jira |",
        "| `Initiative` | Jira |",
        "| `Epic` | Jira |",
        "| `Sprint` | Jira |",
        "| `Issue` | Jira |",
        "| `Repository` | GitHub |",
        "| `Branch` | GitHub |",
        "| `Commit` | GitHub |",
        "| `PullRequest` | GitHub |",
        "| `Person` | GitHub / Jira |",
        "| `Team` | GitHub |",
        "",
        "---",
        "",
    ]

    # ---- 5. Entity Attribute Schemas ----
    lines += [
        "## 5. Entity Attribute Schemas",
        "",
        "Each entity type has a corresponding `*Attributes` Pydantic model.",
        "Required fields (✓) must be supplied by every producer.",
        "Optional fields default to `None` and may be omitted.",
        "The `entity_type` discriminator field is internal and excluded from these tables.",
        "",
    ]
    for entity_type, model_cls in _ENTITY_ATTRS:
        doc = (model_cls.__doc__ or "").strip().split("\n")[0]
        lines += [
            f"### {entity_type}",
            "",
            f"*{doc}*",
            "",
            _fields_table(model_cls, skip_fields={"entity_type"}),
            "",
        ]
    lines += ["---", ""]

    # ---- 6. Supported Relationship Types ----
    lines += [
        "## 6. Supported Relationship Types",
        "",
        "All `Relationship.type` values must be from `SUPPORTED_RELATIONSHIP_TYPES` in `models.py`.",
        "The set is fixed; add new types by updating `models.py` and re-running this script.",
        "",
        "| Relationship Type |",
        "|-------------------|",
    ]
    for rt in sorted(SUPPORTED_RELATIONSHIP_TYPES):
        lines.append(f"| `{rt}` |")
    lines += ["", "---", ""]

    # ---- 7. Relationship Direction Semantics ----
    lines += [
        "## 7. Relationship Direction Semantics",
        "",
        "The `direction` field on `Relationship` controls how the edge is stored in Neo4j:",
        "",
        "| `direction` value | Neo4j edge stored | When to use |",
        "|-------------------|-------------------|-------------|",
        "| `None` *(default)* | undirected `(a)-[:REL]-(b)` — stored once, queried from either end | Default for most relationships: `ASSIGNED_TO`, `AUTHORED_BY`, `MEMBER_OF`, `PART_OF`, etc. |",
        "| `\"OUT\"` | `(signal_node)-[:REL]->(target)` | When directionality is semantically required (e.g. `TARGETS` for PR → base branch) |",
        "| `\"IN\"` | `(signal_node)<-[:REL]-(target)` | Rare; consumer swaps from/to before writing |",
        "",
        "> **Default:** omit `direction` (leave as `None`) unless you have an explicit reason for a directed edge.",
        "> See `docs/design/RELATIONSHIPS_DESIGN.md` for the full undirected-edge design rationale.",
        "",
        "---",
        "",
    ]

    # ---- 8. Event Metadata & Provenance ----
    lines += [
        "## 8. Event Metadata & Provenance",
        "",
        "| Field | Required | Description |",
        "|-------|:--------:|-------------|",
        "| `signal_id` | auto | UUID; auto-generated by `ActivitySignal` constructor if not supplied |",
        "| `source_config` | ✓ | Base URL of the source system instance (e.g. `https://mycompany.atlassian.net`) |",
        "| `connector_url` | ✓ | URL of the connector that produced this signal |",
        "| `event_time` | ✓ | UTC timestamp of the event in the source system (`updated_at` or `created_at`) |",
        "| `ingestion_time` | consumer | `None` when emitted by a producer; set by the consumer on receipt |",
        "| `version` | defaults `1.0` | Schema version string |",
        "",
        "---",
        "",
    ]

    # ---- 9. Error Handling & Validation ----
    lines += [
        "## 9. Error Handling & Validation",
        "",
        "- Consumers validate incoming signals via Pydantic.",
        "  Signals that fail validation are rejected and logged; they must not crash the consumer.",
        "- For out-of-order events (relationship targets not yet in Neo4j), consumers create",
        "  **stub nodes** with minimal properties (`id`, `stub=True`) to be backfilled when the",
        "  full signal arrives.",
        "- All `*Attributes` models use `extra='forbid'` — unknown fields are rejected at parse time.",
        "- Producers must wrap each signal builder in `try/except` and return `None` on failure,",
        "  logging the error via `logger.warning`.",
        "",
        "---",
        "",
    ]

    # ---- 10. Idempotency & Deduplication ----
    lines += [
        "## 10. Idempotency & Deduplication",
        "",
        "- Neo4j upserts use `MERGE` on the WBA canonical key (`id` property).",
        "  Re-processing the same signal is safe.",
        "- Duplicate `signal_id` values are rejected or ignored by consumers.",
        "- **Cross-source Person deduplication** is handled by `PersonCache`",
        "  (`src/connectors/commons/person_cache.py`) using email as the merge key.",
        "  A GitHub Person with the same email as a Jira Person is merged to the same",
        "  `Person` node, with separate `IdentityMapping` nodes:",
        "  - `github::IdentityMapping::alice` and `jira::IdentityMapping::557058:abc`",
        "  - both connected to the same `Person` node via undirected `MAPS_TO` edges.",
        "",
        "---",
        "",
    ]

    # ---- 11. Producer & Consumer Responsibilities ----
    lines += [
        "## 11. Producer & Consumer Responsibilities",
        "",
        "### 11.1 Producer",
        "",
        "- Emit `ActivitySignal` objects conforming to this spec.",
        "- Set `id=<raw_identifier>` — the raw entity ID within its type, **not** the full WBA key.",
        "- Use only types from `SUPPORTED_ENTITY_TYPES` and `SUPPORTED_RELATIONSHIP_TYPES`.",
        "- Set `direction=None` for symmetric relationships; `\"OUT\"` only when required.",
        "- Leave `ingestion_time=None` (the consumer sets it).",
        "- See `docs/design/producer-development-guide.md` for the certification checklist.",
        "",
        "### 11.2 Consumer",
        "",
        "- Validate signals with Pydantic before processing.",
        "- Compute the WBA canonical key via `wba_node_id(signal)` and store as the Neo4j `id`.",
        "- Resolve `RelationshipTarget` in priority order: `email` → `url` → `id`.",
        "- Create stub nodes for unresolved targets.",
        "- Deduplicate `Person` nodes by email using `PersonCache`.",
        "- Create `IdentityMapping` nodes for all `Person` signals.",
        "- Set `ingestion_time` on receipt.",
        "- See `docs/design/consumer-development-guide.md` for the certification checklist.",
        "",
        "---",
        "",
    ]

    # ---- 12. Examples ----
    lines += [
        "## 12. Examples",
        "",
        "The following examples are constructed from real `ActivitySignal` objects",
        "via `model_dump(mode='json')` — they always reflect the current schema.",
        "",
        "### 12.1 Jira Issue",
        "",
        "```json",
        _issue_example(),
        "```",
        "",
        "### 12.2 GitHub PullRequest",
        "",
        "```json",
        _pull_request_example(),
        "```",
        "",
        "---",
        "",
    ]

    # ---- 13. Glossary ----
    lines += [
        "## 13. Glossary",
        "",
        "| Term | Definition |",
        "|------|-----------|",
        "| **ActivitySignal** | A single event describing one entity and its relationships at a point in time. |",
        "| **WBA canonical key** | `{source}::{entity_type}::{id}` — stored as the `id` property on every Neo4j node. |",
        "| **Canonical identity tuple** | `(source, entity_type, id)` — uniquely identifies a logical node. |",
        "| **Stub node** | Placeholder node created when a referenced target does not yet exist; `stub=True`. |",
        "| **IdentityMapping** | Node linking a provider identity (login / account_id) to a `Person` node via `MAPS_TO`. |",
        "| **Producer** | Service that fetches data from a source system and emits `ActivitySignal` events to RabbitMQ. |",
        "| **Consumer** | Service that ingests, validates, and writes `ActivitySignal` events to Neo4j. |",
        "| **PersonCache** | In-memory cross-source deduplication cache; merges persons sharing the same email. |",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    output_path = _REPO_ROOT / "docs" / "design" / "spec-activity-signal.md"
    spec = _build_spec()
    output_path.write_text(spec, encoding="utf-8")
    print(f"Written: {output_path}")

    # Quick sanity check
    line_count = spec.count("\n")
    entity_count = len(_ENTITY_ATTRS)
    rel_count = len(SUPPORTED_RELATIONSHIP_TYPES)
    print(f"  {line_count} lines | {entity_count} entity types | {rel_count} relationship types")


if __name__ == "__main__":
    main()

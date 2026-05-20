"""ActivitySignal Pydantic schema models.

Implements the ActivitySignal specification (docs/spec-activity-signal.md).

Key design decisions:
- A single ``ActivitySignal`` class covers both producer and consumer usage.
  ``ingestion_time`` is ``None`` when emitted by a producer and is set by the
  consumer upon receipt.
- Per-entity ``*Attributes`` sub-models validate mandatory attributes for each
  ``entity_type`` and allow arbitrary extra fields (``extra='allow'``).
- Discriminated union on ``entity_type`` enforces the correct attributes
  sub-model at parse time.
- ``RelationshipTarget`` uses a strict schema (``extra='forbid'``); canonical
  identity is ``(source, entity_type, id)`` with email/url as alternate lookups.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Dict, List, Literal, Optional, Union, cast

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


# ---------------------------------------------------------------------------
# Relationship target
# ---------------------------------------------------------------------------


class RelationshipTarget(BaseModel):
    """Identifies the target node of a relationship.

    Canonical identity tuple: ``(source, entity_type, id)``.
    Consumers resolve the target node using this priority order:

    1. ``entity_type == "Person"`` and ``email`` is set → look up node by email.
    2. ``url`` is set → look up node by url.
    3. ``id`` is set → form the WBA canonical key ``{source}::{entity_type}::{id}``.
    4. ``external_id`` is set → use directly (backward-compat; removed Phase 13).

    No extra fields are permitted; use the declared fields only.
    """

    model_config = ConfigDict(extra="forbid")

    source: Optional[str] = None
    entity_type: Optional[str] = None
    id: Optional[str] = None
    email: Optional[str] = None
    url: Optional[str] = None
    external_id: Optional[str] = None  # backward-compat; removed in Phase 13


# ---------------------------------------------------------------------------
# Supported relationship types
# ---------------------------------------------------------------------------

SUPPORTED_RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    {
        "ASSIGNED_TO",
        "AUTHORED_BY",
        "BELONGS_TO",
        "BLOCKS",
        "BRANCH_OF",
        "COLLABORATES_ON",
        "COLLABORATOR",
        "CONTAINS",
        "CREATED_BY",
        "DEPENDS_ON",
        "FROM",
        "IN_SPRINT",
        "INCLUDES",
        "LEADS",
        "MAPS_TO",
        "MEMBER_OF",
        "MERGED_BY",
        "MERGED_INTO",
        "OWNS",
        "PARENT_OF",
        "PART_OF",
        "REFERENCES",
        "RELATED_TO",
        "RELATES_TO",
        "REPORTED_BY",
        "REQUESTED_REVIEWER",
        "REVIEWED_BY",
        "REVIEWS",
        "TARGETS",
        "TEAM",
    }
)


class Relationship(BaseModel):
    """A single relationship entry inside an ActivitySignal.

    ``direction`` encodes three distinct storage semantics for Neo4j:

    * ``"OUT"``  — directed edge ``(source)-[:REL]->(target)``
    * ``"IN"``   — directed edge ``(source)<-[:REL]-(target)``
    * ``None``   — undirected edge ``(source)-[:REL]-(target)``, stored once
                   and queryable from either end without specifying direction.
                   Use this for Category-1 relationships defined in
                   ``docs/RELATIONSHIPS_DESIGN.md`` (e.g. ``ASSIGNED_TO``,
                   ``AUTHORED_BY``, ``MEMBER_OF``).
    """

    type: str = Field(..., description="One of SUPPORTED_RELATIONSHIP_TYPES.")
    direction: Optional[Literal["OUT", "IN"]] = Field(
        default=None,
        description=(
            "Direction of the relationship edge. "
            "None = undirected (stored once, queried without direction). "
            "OUT = (source)-[:REL]->(target). "
            "IN = (source)<-[:REL]-(target)."
        ),
    )
    target: RelationshipTarget = Field(
        ..., description="Flexible dict sufficient to identify the target node."
    )
    properties: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional key-value properties stored on the relationship edge in Neo4j.",
    )


# ---------------------------------------------------------------------------
# Per-entity attribute sub-models
# ---------------------------------------------------------------------------
# Each sub-model:
#   - declares a Literal ``entity_type`` field used as discriminator
#   - lists mandatory attributes as required fields
#   - sets ``extra='allow'`` so additional custom fields pass through


class ProjectAttributes(BaseModel):
    """Mandatory attributes for a Jira Project node."""

    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["Project"] = Field(default="Project", exclude=True)
    project_id: str
    project_key: str
    project_name: str
    status: Optional[str] = None
    project_type: Optional[str] = None
    url: Optional[str] = None
    custom: Optional[Dict[str, Any]] = None


class InitiativeAttributes(BaseModel):
    """Mandatory attributes for a Jira Initiative node."""

    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["Initiative"] = Field(default="Initiative", exclude=True)
    key: str
    summary: str
    priority: str
    status: str
    created_at: str
    project_id: Optional[str] = None
    updated_at: Optional[str] = None
    duedate: Optional[str] = None
    labels: Optional[list] = None
    components: Optional[list] = None
    url: Optional[str] = None
    custom: Optional[Dict[str, Any]] = None


class EpicAttributes(BaseModel):
    """Mandatory attributes for a Jira Epic node."""

    model_config = ConfigDict(extra="allow")

    entity_type: Literal["Epic"] = Field(default="Epic", exclude=True)
    id: str
    key: str
    summary: str
    priority: str
    status: str
    created_at: str


class SprintAttributes(BaseModel):
    """Mandatory attributes for a Jira Sprint node."""

    model_config = ConfigDict(extra="allow")

    entity_type: Literal["Sprint"] = Field(default="Sprint", exclude=True)
    id: str
    name: str
    status: str


class IssueAttributes(BaseModel):
    """Mandatory attributes for a Jira Issue node."""

    model_config = ConfigDict(extra="allow")

    entity_type: Literal["Issue"] = Field(default="Issue", exclude=True)
    id: str
    key: str
    summary: str
    priority: str
    status: str
    type: str
    created_at: str
    updated_at: Optional[str] = None
    story_points: Optional[float] = None


class RepositoryAttributes(BaseModel):
    """Mandatory attributes for a GitHub Repository node."""

    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["Repository"] = Field(default="Repository", exclude=True)
    name: str
    description: Optional[str] = None
    language: Optional[str] = None
    is_private: Optional[bool] = None
    topics: Optional[List[str]] = None
    url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    custom: Optional[Dict[str, Any]] = None


class BranchAttributes(BaseModel):
    """Mandatory attributes for a GitHub Branch node."""

    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["Branch"] = Field(default="Branch", exclude=True)
    repo_name: str
    branch_name: str
    last_commit_sha: str
    last_commit_timestamp: Optional[str] = None
    is_default: Optional[bool] = None
    is_protected: Optional[bool] = None
    is_deleted: Optional[bool] = None
    is_external: Optional[bool] = None
    url: Optional[str] = None
    custom: Optional[Dict[str, Any]] = None


class CommitAttributes(BaseModel):
    """Mandatory attributes for a GitHub Commit node."""

    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["Commit"] = Field(default="Commit", exclude=True)
    sha: str
    message: str
    author: str
    created_at: str
    additions: Optional[int] = None
    deletions: Optional[int] = None
    files_changed: Optional[int] = None
    url: Optional[str] = None
    custom: Optional[Dict[str, Any]] = None


class PullRequestAttributes(BaseModel):
    """Mandatory attributes for a GitHub PullRequest node."""

    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["PullRequest"] = Field(default="PullRequest", exclude=True)
    repo_name: str
    pull_request_number: int
    title: str
    state: str
    created_at: str
    user: str
    updated_at: Optional[str] = None
    merged_at: Optional[str] = None
    closed_at: Optional[str] = None
    commits_count: Optional[int] = None
    additions: Optional[int] = None
    deletions: Optional[int] = None
    changed_files: Optional[int] = None
    comments: Optional[int] = None
    review_comments: Optional[int] = None
    head_branch_name: Optional[str] = None
    base_branch_name: Optional[str] = None
    labels: Optional[list] = None
    mergeable_state: Optional[str] = None
    url: Optional[str] = None
    custom: Optional[Dict[str, Any]] = None


class PersonAttributes(BaseModel):
    """Mandatory attributes for a Person node."""

    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["Person"] = Field(default="Person", exclude=True)
    full_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    login: Optional[str] = None
    email: Optional[str] = None
    url: Optional[str] = None
    avatar_url: Optional[str] = None
    account_id: Optional[str] = None
    custom: Optional[Dict[str, Any]] = None


class TeamAttributes(BaseModel):
    """Mandatory attributes for a GitHub Team node."""

    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["Team"] = Field(default="Team", exclude=True)
    name: str
    url: Optional[str] = None
    description: Optional[str] = None
    custom: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Discriminated union of all attributes models
# ---------------------------------------------------------------------------

# The bare Union — used as the type annotation on ActivitySignal.attributes so
# that type-checkers can see all member attributes (e.g. .entity_type).
_AttributesUnion = Union[
    ProjectAttributes,
    InitiativeAttributes,
    EpicAttributes,
    SprintAttributes,
    IssueAttributes,
    RepositoryAttributes,
    BranchAttributes,
    CommitAttributes,
    PullRequestAttributes,
    PersonAttributes,
    TeamAttributes,
]

# Annotated alias used in the field declaration to attach the discriminator.
AttributesUnion = Annotated[_AttributesUnion, Field(discriminator="entity_type")]

# Set of known entity type strings (derived from the union) for fast validation.
SUPPORTED_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "Project",
        "Initiative",
        "Epic",
        "Sprint",
        "Issue",
        "Repository",
        "Branch",
        "Commit",
        "PullRequest",
        "Person",
        "Team",
    }
)


# ---------------------------------------------------------------------------
# ActivitySignal — top-level event model
# ---------------------------------------------------------------------------


class ActivitySignal(BaseModel):
    """A single ActivitySignal event.

    Covers both producer-emitted signals (``ingestion_time=None``) and
    consumer-enriched signals (``ingestion_time`` set after receipt).

    The ``attributes`` field is a discriminated union keyed on ``entity_type``
    so the correct mandatory attribute set is enforced at parse time.

    Usage (producer)::

        signal = ActivitySignal(
            source="github",
            external_id="repo/123",
            source_config="https://github.com",
            connector_url="https://wba-ai/connectors/github/1",
            event_time=datetime.utcnow(),
            version="1.0",
            attributes=RepositoryAttributes(
                entity_type="Repository",
                id="123",
                full_name="org/repo",
                name="repo",
                created_at="...",
                updated_at="...",
                url="https://github.com/org/repo",
            ),
        )

    Usage (consumer — inject ingestion_time)::

        signal = signal.model_copy(update={"ingestion_time": datetime.utcnow()})
    """

    signal_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique immutable identifier for this signal (UUID).",
    )
    source: str = Field(..., description="Origin system (e.g. 'github', 'jira').")
    id: Optional[str] = Field(
        default=None,
        description=(
            "Unique identifier for the entity within its entity type. "
            "Forms the canonical identity tuple (source, entity_type, id). "
            "Optional during migration; required from Phase 13."
        ),
    )
    external_id: str = Field(
        ..., description="Unique identifier for the entity within the source system."
    )
    source_config: str = Field(
        ...,
        description="Base URL / identifier of the source system instance.",
    )
    connector_url: str = Field(
        ..., description="URL of the connector that produced this signal."
    )
    event_time: datetime = Field(
        ...,
        description="Timestamp of the event in the source system (updated_at / created_at).",
    )
    ingestion_time: Optional[datetime] = Field(
        default=None,
        description=(
            "Timestamp set by the consumer when the message is received. "
            "Must be None when emitted by a producer."
        ),
    )
    version: str = Field(default="1.0", description="Schema version string.")
    attributes: Annotated[
        _AttributesUnion,
        Field(
            discriminator="entity_type",
            description="Entity-specific attributes.  Discriminated by entity_type.",
        ),
    ]
    relationships: list[Relationship] = Field(
        default_factory=list,
        description="Observed relationships for this node at event_time.",
    )

    @model_validator(mode='before')
    @classmethod
    def _inject_entity_type_into_attributes(cls, data: Any) -> Any:
        """Copy root-level entity_type into attributes for discriminated union dispatch.

        Required for round-trip deserialization: model_dump() emits entity_type at
        root (via @computed_field) but not inside attributes (Field exclude=True).
        This validator restores it so Pydantic can dispatch the union correctly.
        """
        if isinstance(data, dict):
            entity_type = data.get('entity_type')
            attrs = data.get('attributes')
            if entity_type and isinstance(attrs, dict) and 'entity_type' not in attrs:
                data = {**data, 'attributes': {**attrs, 'entity_type': entity_type}}
        return data

    @computed_field
    @property
    def entity_type(self) -> str:
        """Exposes entity_type at the root level of ActivitySignal.

        Reads the Literal value from the underlying *Attributes model and includes
        it in model_dump() output. Excluded from attributes serialization via
        Field(exclude=True) on each *Attributes.entity_type field.
        """
        return cast(_AttributesUnion, self.attributes).entity_type  # type: ignore[union-attr]

    @property
    def routing_key(self) -> str:
        """RabbitMQ routing key: ``<source>.<entity_type>``."""
        return f"{self.source}.{self.entity_type}"

    def with_ingestion_time(self, ts: Optional[datetime] = None) -> "ActivitySignal":
        """Return a copy of this signal with ``ingestion_time`` set.

        Args:
            ts: Timestamp to use.  Defaults to ``datetime.utcnow()``.
        """
        from datetime import timezone  # local import to avoid circular imports

        return self.model_copy(
            update={"ingestion_time": ts or datetime.now(tz=timezone.utc)}
        )

    def extra_attributes(self) -> dict[str, Any]:
        """Return the full attributes dict including any extra fields.

        .. deprecated::
            Use ``signal.attributes.model_dump()`` directly. This helper will
            be removed in Phase 13 of the ActivitySignal refactoring.
        """
        return cast(_AttributesUnion, self.attributes).model_dump()  # type: ignore[union-attr]

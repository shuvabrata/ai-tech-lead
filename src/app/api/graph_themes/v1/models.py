"""Pydantic models for the graph-themes API.

Defines request/response schemas for the ``/api/v1/graph-themes/`` endpoints.

The override document classes (``NodeOverride`` / ``EdgeOverride`` /
``GlobalOverride`` / ``ThemeOverrides``) are **not** redefined here — they live
in :mod:`app.common.graph_theme` as the single source of truth, shared by the
pure merge/translation core and this API layer. This module only adds the
request/response wrappers around them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.common.graph_theme import ThemeOverrides

# Explicit literal of the valid base modes (Pylance cannot unpack a runtime
# tuple inside ``Literal``). Kept in sync with ``VALID_BASE_THEMES`` in
# ``app.db.models.graph_theme``.
BaseThemeLiteral = Literal["executive-light", "executive-dark"]

__all__ = [
    "BaseThemeLiteral",
    "CloneResponse",
    "EffectiveThemeResponse",
    "GraphThemeBase",
    "GraphThemeCreate",
    "GraphThemeResponse",
    "GraphThemeUpdate",
    "SetDefaultResponse",
    "ThemeOverrides",
]


class GraphThemeBase(BaseModel):
    """Shared request fields for creating/updating a theme."""

    name: str = Field(min_length=1, max_length=100)
    base_theme: BaseThemeLiteral = "executive-light"
    overrides: ThemeOverrides = Field(default_factory=ThemeOverrides)


class GraphThemeCreate(GraphThemeBase):
    """Request body for POST /api/v1/graph-themes/."""


class GraphThemeUpdate(BaseModel):
    """Request body for PATCH /api/v1/graph-themes/{id}.

    ``is_default`` is managed through the dedicated ``/set-default`` action, so
    it is not part of the mutable update. ``name`` / ``base_theme`` /
    ``overrides`` are optional on update (a no-op if omitted is allowed).
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_theme: BaseThemeLiteral | None = None
    overrides: ThemeOverrides | None = None


class GraphThemeResponse(BaseModel):
    """Response body for a single graph theme."""

    id: int
    name: str
    base_theme: str
    is_default: bool
    overrides: dict[str, object]
    source: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SetDefaultResponse(BaseModel):
    """Response body for POST /api/v1/graph-themes/{id}/set-default."""

    id: int
    name: str
    base_theme: str
    is_default: bool

    model_config = ConfigDict(from_attributes=True)


class CloneResponse(GraphThemeResponse):
    """Response body for POST /api/v1/graph-themes/{id}/clone."""


class EffectiveThemeResponse(BaseModel):
    """Response body for GET /api/v1/graph-themes/effective.

    Contains the *merged* tokens (base ⊕ overrides) using the canonical
    override-document shape — ``nodes`` keys are Cytoscape properties
    (``background-color``, ``border-color``, ...) produced by
    :func:`merge_theme_overrides`, not semantic keys. The client turns these
    into a Cytoscape stylesheet via :func:`overrides_to_cytoscape_rules`.
    """

    base_theme: str
    nodes: dict[str, object]
    edges: dict[str, object]
    global_: dict[str, object] = Field(alias="global")
"""Pydantic models for normalized query catalog entries."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CatalogView = Literal["tabular", "graph"]
CatalogStatus = Literal["active", "draft", "deprecated"]
_SAFE_ID_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9_]*$")


class CatalogNamespace(BaseModel):
    """A top-level query catalog namespace."""

    name: str = Field(..., min_length=1)
    directory: str = Field(..., min_length=1)
    order: int = Field(..., ge=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("directory")
    @classmethod
    def validate_directory(cls, value: str) -> str:
        if not _SAFE_ID_SEGMENT.fullmatch(value):
            raise ValueError("namespace directory must be a path-safe id segment")
        return value


class CatalogParameter(BaseModel):
    """A parameter required or accepted by a catalog query."""

    name: str = Field(..., min_length=1)
    env_var: str | None = None
    required: bool
    label: str | None = Field(default=None, min_length=1)
    type: str | None = Field(default=None, min_length=1)
    placeholder: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)

    model_config = ConfigDict(extra="forbid")


class CatalogQuery(BaseModel):
    """Normalized catalog query definition."""

    id: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=1)
    namespace: CatalogNamespace
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    summary: str | None = Field(default=None, min_length=1)
    queries: dict[CatalogView, str]
    available_views: list[CatalogView]
    default_view: CatalogView | None = None
    parameters: list[CatalogParameter] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    owner: str | None = Field(default=None, min_length=1)
    status: CatalogStatus | None = None
    source_path: str

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_queries(self) -> "CatalogQuery":
        if not self.queries:
            raise ValueError("catalog query must define at least one query variant")

        for view, query_text in self.queries.items():
            if view not in ("tabular", "graph"):
                raise ValueError(f"unsupported query view: {view}")
            if not query_text or not query_text.strip():
                raise ValueError(f"{view} query cannot be empty")

        expected_views = list(self.queries.keys())
        if self.available_views != expected_views:
            raise ValueError("available_views must match query variant order")

        if self.default_view is not None and self.default_view not in self.queries:
            raise ValueError("default_view must match an available query variant")

        return self

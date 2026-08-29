"""SQLAlchemy model for the ``graph_themes`` table.

Stores user-configurable, named graph themes. Each theme carries *deltas* —
partial overrides that are merged over the hardcoded base tokens
(``THEME_TOKENS`` in ``app.dash_app.styles``) at render time. The ``is_default``
flag is scoped per ``base_theme`` and enforced by a PostgreSQL partial unique
index so only one default can exist per base mode.

``source`` distinguishes immutable seed rows (``builtin``) from user-created
rows (``user``); editing a builtin must go through an explicit clone
(copy-on-write).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base

# Valid values for the ``base_theme`` column. They mirror the keys of the
# hardcoded ``THEME_TOKENS`` registry (``executive-light`` / ``executive-dark``).
BASE_THEME_LIGHT = "executive-light"
BASE_THEME_DARK = "executive-dark"
VALID_BASE_THEMES: tuple[str, ...] = (BASE_THEME_LIGHT, BASE_THEME_DARK)

# Valid values for the ``source`` column.
SOURCE_BUILTIN = "builtin"
SOURCE_USER = "user"
VALID_SOURCES: tuple[str, ...] = (SOURCE_BUILTIN, SOURCE_USER)


class GraphTheme(Base):
    """A named, user-configurable graph theme (delta overrides)."""

    __tablename__ = "graph_themes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_theme: Mapped[str] = mapped_column(String(30), nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    overrides: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=True), nullable=False, default=dict
    )
    source: Mapped[str] = mapped_column(
        String(10), nullable=False, default=SOURCE_USER
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False  # pylint: disable=not-callable
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),  # pylint: disable=not-callable
        onupdate=func.now(),  # pylint: disable=not-callable
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"GraphTheme(id={self.id}, name={self.name!r}, "
            f"base_theme={self.base_theme!r}, source={self.source!r}, "
            f"is_default={self.is_default})"
        )

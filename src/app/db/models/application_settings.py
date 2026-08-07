"""SQLAlchemy model for the application_settings table.

Stores the catalog of runtime-configurable settings and their optional DB
overrides.  The table is seeded by Alembic migrations and the UI/API can
update or reset ``value`` but must not create or delete rows.

See ``docs/project-plan/runtime-settings-design and plan.md`` for the full
design.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class ApplicationSettings(Base):
    """Catalog of runtime-configurable application settings.

    Each row represents one setting that can be changed from the UI without
    restarting the application.  The ``value`` column holds the user override
    (nullable); when ``NULL`` the effective value falls back to the environment
    variable or the code default.

    ``key`` values are ``UPPER_CASE`` matching the corresponding environment
    variable names.
    """

    __tablename__ = "application_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    value: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    apply_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"ApplicationSettings(key={self.key!r}, "
            f"value_type={self.value_type!r}, "
            f"apply_mode={self.apply_mode!r})"
        )
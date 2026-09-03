"""SQLAlchemy model for the ``catalog_metadata`` table.

Stores per-query metadata for the Graph page's Query Catalog. Currently the
only metadata is the favourite flag, which lets users surface frequently-run
catalog queries. Rows are created lazily (upsert on toggle) — a row only
exists for queries the user has interacted with.

``catalog_id`` is the stable id of a catalog query (``<namespace.directory>/<slug>``)
as defined by ``app.query_catalog.loader``. It is unique so each catalog query
maps to at most one metadata row.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class CatalogMetadata(Base):
    """Per-query metadata for the query catalog (currently the favourite flag)."""

    __tablename__ = "catalog_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    is_favourite: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
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

    def __init__(  # pylint: disable=useless-parent-delegation
        self,
        *,
        catalog_id: str,
        is_favourite: bool = False,
        **kwargs: object,
    ) -> None:
        """Construct a row, defaulting ``is_favourite`` to ``False``.

        SQLAlchemy's ``default`` only applies at flush time, so an explicit
        ``__init__`` keeps the default visible at construction time too.
        """
        super().__init__(catalog_id=catalog_id, is_favourite=is_favourite, **kwargs)

    def __repr__(self) -> str:
        return (
            f"CatalogMetadata(id={self.id}, catalog_id={self.catalog_id!r}, "
            f"is_favourite={self.is_favourite})"
        )
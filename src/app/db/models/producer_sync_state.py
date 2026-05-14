from datetime import datetime

from sqlalchemy import String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProducerSyncState(Base):
    """Tracks the last successful sync timestamp per source/resource for producers.

    Producers (github_producer, jira_producer) read this to determine the
    incremental sync window and write it after a successful run.

    The ``(source, resource_id)`` pair is unique:
    - GitHub: source="github", resource_id=repo.full_name  (e.g. "org/repo")
    - Jira:   source="jira",   resource_id=project_key     (e.g. "PROJ")
    """

    __tablename__ = "producer_sync_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(500), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("source", "resource_id", name="uq_producer_sync_state_source_resource"),
    )

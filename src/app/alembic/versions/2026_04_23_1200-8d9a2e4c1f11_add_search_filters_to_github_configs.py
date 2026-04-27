# pylint: disable=no-member

"""add search_filters to github configs

Revision ID: 8d9a2e4c1f11
Revises: 5c6a3b1f9e7d
Create Date: 2026-04-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "8d9a2e4c1f11"
down_revision: Union[str, Sequence[str], None] = "5c6a3b1f9e7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "github_configs",
        sa.Column("search_filters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("github_configs", "search_filters")

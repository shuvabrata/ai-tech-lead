# pylint: disable=no-member

"""add importance column to application_settings

Revision ID: a1b2c3d4e5f6
Revises: 7e8f9a0b1c2d
Create Date: 2026-08-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "7e8f9a0b1c2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ``importance`` column and backfill recommended settings."""
    op.add_column(
        "application_settings",
        sa.Column(
            "importance",
            sa.String(20),
            nullable=False,
            server_default="optional",
        ),
    )

    op.execute(
        """
        UPDATE application_settings
        SET importance = 'recommended'
        WHERE key IN ('OPENAI_API_KEY', 'GITHUB_MCP_TOKEN')
        """
    )


def downgrade() -> None:
    """Drop the ``importance`` column."""
    op.drop_column("application_settings", "importance")

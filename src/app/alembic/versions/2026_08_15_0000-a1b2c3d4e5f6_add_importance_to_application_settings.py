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
    """Add ``importance`` column and backfill recommended/mandatory settings."""
    op.add_column(
        "application_settings",
        sa.Column(
            "importance",
            sa.String(20),
            nullable=False,
            server_default="optional",
        ),
    )

    # Recommended: optional-but-encouraged settings flagged by the banner.
    op.execute(
        """
        UPDATE application_settings
        SET importance = 'recommended'
        WHERE key IN ('OPENAI_API_KEY', 'GITHUB_MCP_TOKEN')
        """
    )

    # Mandatory: catalog settings the app requires to function.  Bootstrap-only
    # keys (POSTGRES_*, DATABASE_URL, RABBITMQ_USER/PASSWORD,
    # CONNECTOR_ENCRYPTION_KEY) are intentionally absent from the catalog and
    # are therefore not marked here.
    op.execute(
        """
        UPDATE application_settings
        SET importance = 'mandatory'
        WHERE key IN ('NEO4J_USERNAME', 'NEO4J_PASSWORD', 'RABBITMQ_URL',
                      'ELASTIC_PASSWORD')
        """
    )


def downgrade() -> None:
    """Drop the ``importance`` column."""
    op.drop_column("application_settings", "importance")

# pylint: disable=no-member

"""mark inactive connectors as coming_soon

Revision ID: 7e8f9a0b1c2d
Revises: 3f1a2b4c5d6e
Create Date: 2026-08-12 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7e8f9a0b1c2d"
down_revision: Union[str, Sequence[str], None] = "3f1a2b4c5d6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        UPDATE connectors
        SET status = 'coming_soon'
        WHERE connector_type IN (
            'teams',
            'google_docs',
            'sharepoint',
            'email',
            'slack'
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        UPDATE connectors
        SET status = 'not_configured'
        WHERE connector_type IN (
            'teams',
            'google_docs',
            'sharepoint',
            'email',
            'slack'
        )
        """
    )

# pylint: disable=no-member

"""seed connectors

Revision ID: 5c6a3b1f9e7d
Revises: 31c15cb26b13
Create Date: 2026-03-15 20:52:00.000000

"""
from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5c6a3b1f9e7d"
down_revision: Union[str, Sequence[str], None] = "31c15cb26b13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        INSERT INTO connectors (connector_type, status, enabled)
        VALUES
            ('github', 'not_configured', false),
            ('jira', 'not_configured', false),
            ('slack', 'not_configured', false),
            ('teams', 'not_configured', false),
            ('confluence', 'not_configured', false),
            ('google_docs', 'not_configured', false),
            ('sharepoint', 'not_configured', false),
            ('email', 'not_configured', false)
        ON CONFLICT (connector_type) DO NOTHING
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DELETE FROM connectors
        WHERE connector_type IN (
            'github',
            'jira',
            'slack',
            'teams',
            'confluence',
            'google_docs',
            'sharepoint',
            'email'
        )
        """
    )

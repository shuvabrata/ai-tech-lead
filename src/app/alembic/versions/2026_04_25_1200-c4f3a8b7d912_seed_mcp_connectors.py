# pylint: disable=no-member

"""seed mcp connectors

Revision ID: c4f3a8b7d912
Revises: 8d9a2e4c1f11
Create Date: 2026-04-25 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c4f3a8b7d912"
down_revision: Union[str, Sequence[str], None] = "8d9a2e4c1f11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        INSERT INTO connectors (connector_type, status, enabled)
        VALUES
            ('atlassian_mcp', 'not_configured', false),
            ('github_mcp', 'not_configured', false)
        ON CONFLICT (connector_type) DO NOTHING
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DELETE FROM connectors
        WHERE connector_type IN (
            'atlassian_mcp',
            'github_mcp'
        )
        """
    )

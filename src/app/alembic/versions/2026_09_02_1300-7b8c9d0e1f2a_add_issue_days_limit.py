"""add ISSUE_DAYS_LIMIT to application_settings catalog

Revision ID: 7b8c9d0e1f2a
Revises: 6a7b8c9d0e1f
Create Date: 2026-09-02 13:00:00.000000

Seeds one runtime-configurable setting that controls the GitHub producer's
first-time issue sync lookback window.  It is a non-secret, ``dynamic``
setting under the ``connectors`` category.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b8c9d0e1f2a"
down_revision: Union[str, Sequence[str], None] = "6a7b8c9d0e1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — seed the ISSUE_DAYS_LIMIT catalog row."""
    op.execute(
        """
        INSERT INTO application_settings (key, value_type, category, description, apply_mode, is_sensitive)
        VALUES
            ('ISSUE_DAYS_LIMIT', 'integer', 'connectors',
             'Lookback days for GitHub issue sync on first-time sync.', 'dynamic', false)
        ON CONFLICT (key) DO UPDATE SET
            value_type = EXCLUDED.value_type,
            category = EXCLUDED.category,
            description = EXCLUDED.description,
            apply_mode = EXCLUDED.apply_mode,
            is_sensitive = EXCLUDED.is_sensitive,
            updated_at = now()
        """
    )


def downgrade() -> None:
    """Downgrade schema — remove the ISSUE_DAYS_LIMIT catalog row."""
    op.execute(
        """
        DELETE FROM application_settings WHERE key = 'ISSUE_DAYS_LIMIT'
        """
    )
"""add retry-with-backoff settings to application_settings catalog

Revision ID: 6a7b8c9d0e1f
Revises: 0a1b2c3d4e55
Create Date: 2026-09-02 12:00:00.000000

Seeds three runtime-configurable settings that control the producer
``retry_with_backoff`` behaviour (total retry budget, per-sleep backoff cap,
and initial base delay).  These are non-secret, ``dynamic`` settings under
the ``connectors`` category.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6a7b8c9d0e1f"
down_revision: Union[str, Sequence[str], None] = "0a1b2c3d4e55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — seed the three retry settings catalog rows."""
    op.execute(
        """
        INSERT INTO application_settings (key, value_type, category, description, apply_mode, is_sensitive)
        VALUES
            ('RETRY_BUDGET_SECONDS', 'integer', 'connectors',
             'Total retry budget in seconds for transient producer API failures (rate-limit 429 and network errors).', 'dynamic', false),
            ('RETRY_BACKOFF_CAP_SECONDS', 'integer', 'connectors',
             'Maximum per-sleep delay in seconds during exponential backoff.', 'dynamic', false),
            ('RETRY_BASE_DELAY_SECONDS', 'integer', 'connectors',
             'Initial backoff delay in seconds (doubles each retry).', 'dynamic', false)
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
    """Downgrade schema — remove the three retry settings catalog rows."""
    op.execute(
        """
        DELETE FROM application_settings WHERE key IN (
            'RETRY_BUDGET_SECONDS',
            'RETRY_BACKOFF_CAP_SECONDS',
            'RETRY_BASE_DELAY_SECONDS'
        )
        """
    )

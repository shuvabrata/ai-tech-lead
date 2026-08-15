"""remove_github_token_for_public_repos

Revision ID: 9e8c3e08ae33
Revises: a1b2c3d4e5f6
Create Date: 2026-08-15 22:14:54.578642

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e8c3e08ae33'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove unused GITHUB_TOKEN_FOR_PUBLIC_REPOS setting."""
    op.execute(
        "DELETE FROM application_settings WHERE key = 'GITHUB_TOKEN_FOR_PUBLIC_REPOS'"
    )


def downgrade() -> None:
    """Re-add GITHUB_TOKEN_FOR_PUBLIC_REPOS setting."""
    op.execute(
        """
        INSERT INTO application_settings (key, value_type, category, description, apply_mode, is_sensitive)
        VALUES ('GITHUB_TOKEN_FOR_PUBLIC_REPOS', 'string', 'connectors',
                'GitHub token for accessing public repos.', 'dynamic', true)
        """
    )

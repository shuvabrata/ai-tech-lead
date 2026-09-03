"""add catalog_metadata table

Revision ID: 0c1d2e3f4a5b
Revises: 7b8c9d0e1f2a
Create Date: 2026-09-03 12:00:00.000000

Creates the ``catalog_metadata`` table storing per-query metadata for the
Graph page's Query Catalog. Currently the only metadata is the favourite flag
(``is_favourite``), which lets users surface frequently-run catalog queries.
Rows are created lazily (upsert on toggle) — a row only exists for queries the
user has interacted with. ``catalog_id`` is unique so each catalog query maps
to at most one metadata row.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0c1d2e3f4a5b"
down_revision: Union[str, Sequence[str], None] = "7b8c9d0e1f2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('catalog_metadata',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('catalog_id', sa.String(length=255), nullable=False),
        sa.Column('is_favourite', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_catalog_metadata'))
    )

    # Each catalog query maps to at most one metadata row.
    op.create_unique_constraint(
        'uq_catalog_metadata_catalog_id', 'catalog_metadata', ['catalog_id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_catalog_metadata_catalog_id', 'catalog_metadata', type_='unique')
    op.drop_table('catalog_metadata')
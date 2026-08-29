"""add graph_themes table

Revision ID: 0a1b2c3d4e55
Revises: 5f4a3b2c1d0e
Create Date: 2026-08-28 12:00:00.000000

Creates the ``graph_themes`` table storing user-configurable graph theme
deltas (partial overrides merged over the hardcoded base tokens) and seeds
two immutable "Default" anchors plus one illustrative example theme per base
mode.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0a1b2c3d4e55"
down_revision: Union[str, Sequence[str], None] = "5f4a3b2c1d0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _seed_rows() -> str:
    """Insert the four seed theme rows idempotently.

    Two base modes (executive-light / executive-dark); each gets one empty
    immutable "Default" anchor (source=builtin) plus one illustrative example
    theme (source=builtin). Examples only touch a couple of properties so they
    compose cleanly over the base palette.
    """
    return """
    INSERT INTO graph_themes (name, base_theme, is_default, overrides, source)
    VALUES
        ('Default', 'executive-light', true,
         '{"nodes": {}, "edges": {}, "global": {}}', 'builtin'),
        ('Default', 'executive-dark', true,
         '{"nodes": {}, "edges": {}, "global": {}}', 'builtin'),
        ('Ocean Light', 'executive-light', false,
         '{"nodes": {"Person": {"color": "#0EA5E9", "border": "#0284C7", '
         '"shape": "octagon", "width": 70, "height": 60}, '
         '"Project": {"color": "#6366F1", "border": "#4F46E5", '
         '"shape": "round-rectangle"}}, '
         '"edges": {"line_color": "#94A3B8", "width": 2}, '
         '"global": {"node_label_color": "#0F172A"}}', 'builtin'),
        ('Midnight Dark', 'executive-dark', false,
         '{"nodes": {"Person": {"color": "#38BDF8", "border": "#0EA5E9", '
         '"shape": "octagon"}, "Issue": {"color": "#FB7185", '
         '"border": "#F43F5E", "shape": "triangle"}}, '
         '"edges": {"line_color": "#64748B", "width": 2}, '
         '"global": {"node_label_color": "#F1F5F9", '
         '"edge_label_background": "#1F262F"}}', 'builtin')
    ON CONFLICT (name, base_theme) DO NOTHING
    """


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('graph_themes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('base_theme', sa.String(length=30), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('overrides', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False, server_default=sa.text("'user'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_graph_themes'))
    )

    # A theme name must be unique per base mode.
    op.create_unique_constraint(
        'uq_graph_themes_name_base_theme', 'graph_themes', ['name', 'base_theme']
    )

    # Partial unique index: only one default theme per base mode. Postgres
    # treats NULLs as distinct, so is_default must be a plain NOT NULL boolean
    # (false for non-default rows) — a WHERE is_default predicate then permits
    # only a single TRUE row per base_theme.
    op.create_index(
        'uq_graph_themes_default_per_base',
        'graph_themes',
        ['base_theme'],
        unique=True,
        postgresql_where=sa.text('is_default'),
    )

    op.execute(_seed_rows())


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_graph_themes_default_per_base', table_name='graph_themes')
    op.drop_constraint('uq_graph_themes_name_base_theme', 'graph_themes', type_='unique')
    op.drop_table('graph_themes')
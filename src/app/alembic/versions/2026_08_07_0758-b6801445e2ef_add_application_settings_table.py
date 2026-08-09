"""add application_settings table

Revision ID: b6801445e2ef
Revises: 44e8b55d5de9
Create Date: 2026-08-07 07:58:37.501796

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b6801445e2ef'
down_revision: Union[str, Sequence[str], None] = '44e8b55d5de9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('application_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('value_type', sa.String(length=20), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('apply_mode', sa.String(length=20), nullable=False),
        sa.Column('is_sensitive', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_application_settings'))
    )
    op.create_index(op.f('ix_application_settings_key'), 'application_settings', ['key'], unique=True)

    # Seed initial catalog of runtime-configurable settings.
    # Uses idempotent upsert that preserves existing user override values.
    op.execute(
        """
        INSERT INTO application_settings (key, value_type, category, description, apply_mode, is_sensitive)
        VALUES
            ('HTTP_REQUEST_TIMEOUT', 'integer', 'network',
             'HTTP request timeout in seconds.', 'dynamic', false),
            ('NEO4J_QUERY_TIMEOUT', 'integer', 'network',
             'Neo4j query timeout in seconds.', 'dynamic', false),
            ('GRAPH_UI_MAX_NODES_TO_EXPAND', 'integer', 'graph',
             'Maximum number of nodes expandable in graph UI.', 'dynamic', false),
            ('GRAPH_UI_MAX_NODE_LABEL_CHARS', 'integer', 'graph',
             'Maximum characters for node labels in graph UI.', 'dynamic', false),
            ('CONNECTOR_SCAN_POLL_INTERVAL', 'integer', 'connectors',
             'Poll interval for connector scan status in milliseconds.', 'dynamic', false),
            ('RECENT_ACTIONS_LIMIT', 'integer', 'connectors',
             'Maximum number of recent actions to display.', 'dynamic', false),
            ('TIMEZONE', 'string', 'ui',
             'Application timezone (IANA name, e.g. America/Los_Angeles).', 'dynamic', false),
            ('UI_DATETIME_FORMAT', 'string', 'ui',
             'strftime format for UI datetimes.', 'dynamic', false),
            ('UI_DATE_FORMAT', 'string', 'ui',
             'strftime format for UI dates (no time).', 'dynamic', false),
            ('AUGMENTATION_HISTORY_TURNS', 'integer', 'ai',
             'Number of augmentation history turns to include in context.', 'dynamic', false),
            ('ES_CHAIN_MAX_RESULTS', 'integer', 'ai',
             'Maximum results from Elasticsearch augmentation chain.', 'dynamic', false),
            ('MAX_MCP_ITERATIONS', 'integer', 'ai',
             'Maximum tool-call iterations per MCP request.', 'dynamic', false),
            ('FF_NEO4J_USE_PROVIDER_PIPELINE', 'boolean', 'feature_flags',
             'Use provider-native Neo4j pipeline instead of custom chain.', 'dynamic', false)
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
    """Downgrade schema."""
    op.drop_index(op.f('ix_application_settings_key'), table_name='application_settings')
    op.drop_table('application_settings')

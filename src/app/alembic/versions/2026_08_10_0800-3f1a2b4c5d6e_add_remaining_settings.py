"""add remaining runtime settings to application_settings catalog

Revision ID: 3f1a2b4c5d6e
Revises: b6801445e2ef
Create Date: 2026-08-10 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3f1a2b4c5d6e'
down_revision: Union[str, Sequence[str], None] = 'b6801445e2ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — seed remaining runtime settings catalog rows."""
    op.execute(
        """
        INSERT INTO application_settings (key, value_type, category, description, apply_mode, is_sensitive)
        VALUES
            -- AI / LLM
            ('LLM_PROVIDER', 'string', 'ai',
             'LLM provider selection (openai, custom).', 'restart', false),
            ('LLM_MODEL', 'string', 'ai',
             'Model name for the LLM provider.', 'dynamic', false),
            ('OPENAI_API_KEY', 'string', 'ai',
             'OpenAI API key.', 'restart', true),
            ('OPENAI_API_URL', 'string', 'ai',
             'OpenAI API endpoint URL.', 'restart', false),
            ('CUSTOM_API_TOKEN', 'string', 'ai',
             'Custom provider API token.', 'restart', true),
            ('CUSTOM_API_URL', 'string', 'ai',
             'Custom provider endpoint URL.', 'restart', false),
            ('CUSTOM_LLM_MODEL', 'string', 'ai',
             'Custom provider model name.', 'dynamic', false),
            ('MAX_TOKENS', 'integer', 'ai',
             'Maximum tokens before history pruning.', 'dynamic', false),
            ('GITHUB_MCP_ENABLED', 'boolean', 'ai',
             'Enable GitHub MCP chain.', 'dynamic', false),
            ('GITHUB_MCP_SERVER_URL', 'string', 'ai',
             'GitHub MCP server URL.', 'restart', false),
            ('GITHUB_MCP_TOKEN', 'string', 'ai',
             'GitHub PAT for MCP server.', 'restart', true),
            ('ATLASSIAN_MCP_ENABLED', 'boolean', 'ai',
             'Enable Atlassian MCP chain.', 'dynamic', false),
            ('ATLASSIAN_MCP_SERVER_URL', 'string', 'ai',
             'Atlassian MCP server URL.', 'restart', false),
            ('ATLASSIAN_MCP_TOKEN', 'string', 'ai',
             'Atlassian MCP API token.', 'restart', true),

            -- System
            ('NEO4J_ENABLED', 'boolean', 'system',
             'Enable Neo4j graph database integration.', 'restart', false),
            ('NEO4J_URI', 'string', 'system',
             'Neo4j Bolt URI.', 'restart', false),
            ('NEO4J_USERNAME', 'string', 'system',
             'Neo4j username.', 'restart', false),
            ('NEO4J_PASSWORD', 'string', 'system',
             'Neo4j password.', 'restart', true),
            ('ELASTICSEARCH_ENABLED', 'boolean', 'system',
             'Enable Elasticsearch integration.', 'restart', false),
            ('ELASTICSEARCH_URL', 'string', 'system',
             'Elasticsearch endpoint URL.', 'restart', false),
            ('ELASTIC_PASSWORD', 'string', 'system',
             'Elasticsearch password.', 'restart', true),
            ('RABBITMQ_URL', 'string', 'system',
             'RabbitMQ AMQP connection URL.', 'restart', true),

            -- Logging
            ('LOG_LEVEL', 'string', 'system',
             'Logging level (DEBUG, INFO, WARNING, ERROR).', 'restart', false),
            ('LOG_FORMAT', 'string', 'system',
             'Log format (JSON or TEXT).', 'restart', false),
            ('ENABLE_FILE_LOGGING', 'boolean', 'system',
             'Enable persistent file logging.', 'restart', false),
            ('LOG_DIR', 'string', 'system',
             'Log file directory path.', 'restart', false),
            ('LOG_SIGNAL_DUMPS', 'boolean', 'system',
             'Enable signal payload dumps to disk.', 'restart', false),

            -- Connectors
            ('COMMIT_DAYS_LIMIT', 'integer', 'connectors',
             'Lookback days for commit sync.', 'dynamic', false),
            ('PULL_REQUEST_DAYS_LIMIT', 'integer', 'connectors',
             'Lookback days for PR sync.', 'dynamic', false),
            ('IDENTITY_REFRESH_DAYS', 'integer', 'connectors',
             'Days before re-scanning identity data.', 'dynamic', false),
            ('MAX_TEAM_SIZE', 'integer', 'connectors',
             'Max team members before skipping.', 'dynamic', false),
            ('JIRA_LOOKBACK_DAYS', 'integer', 'connectors',
             'Lookback days for Jira issue sync.', 'dynamic', false),
            ('JIRA_MAX_RESULTS_PER_PAGE', 'integer', 'connectors',
             'Max results per Jira API page.', 'dynamic', false),
            ('CONFLUENCE_LOOKBACK_DAYS', 'integer', 'connectors',
             'Lookback days for Confluence sync.', 'dynamic', false),
            ('JIRA_EPIC_TEAM_FIELD', 'string', 'connectors',
             'Jira custom field name for epic team.', 'dynamic', false),
            ('JIRA_ISSUE_TEAM_FIELD', 'string', 'connectors',
             'Jira custom field name for issue team.', 'dynamic', false),
            ('JIRA_EPIC_START_DATE_FIELD', 'string', 'connectors',
             'Jira field name for epic start date.', 'dynamic', false),
            ('JIRA_EPIC_DUE_DATE_FIELD', 'string', 'connectors',
             'Jira field name for epic due date.', 'dynamic', false),
            ('API_SERVER', 'string', 'connectors',
             'Base URL for the API server.', 'restart', false),
            ('CONFIGURATION_SOURCE', 'string', 'connectors',
             'Config source (SERVER or FILE).', 'restart', false)
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
    """Downgrade schema — remove the 41 new catalog rows."""
    op.execute(
        """
        DELETE FROM application_settings WHERE key IN (
            'LLM_PROVIDER', 'LLM_MODEL', 'OPENAI_API_KEY', 'OPENAI_API_URL',
            'CUSTOM_API_TOKEN', 'CUSTOM_API_URL', 'CUSTOM_LLM_MODEL', 'MAX_TOKENS',
            'GITHUB_MCP_ENABLED', 'GITHUB_MCP_SERVER_URL', 'GITHUB_MCP_TOKEN',
            'ATLASSIAN_MCP_ENABLED', 'ATLASSIAN_MCP_SERVER_URL', 'ATLASSIAN_MCP_TOKEN',
            'NEO4J_ENABLED', 'NEO4J_URI', 'NEO4J_USERNAME', 'NEO4J_PASSWORD',
            'ELASTICSEARCH_ENABLED', 'ELASTICSEARCH_URL', 'ELASTIC_PASSWORD',
            'RABBITMQ_URL',
            'LOG_LEVEL', 'LOG_FORMAT', 'ENABLE_FILE_LOGGING', 'LOG_DIR', 'LOG_SIGNAL_DUMPS',
            'COMMIT_DAYS_LIMIT', 'PULL_REQUEST_DAYS_LIMIT', 'IDENTITY_REFRESH_DAYS',
            'MAX_TEAM_SIZE', 'JIRA_LOOKBACK_DAYS', 'JIRA_MAX_RESULTS_PER_PAGE',
            'CONFLUENCE_LOOKBACK_DAYS', 'JIRA_EPIC_TEAM_FIELD', 'JIRA_ISSUE_TEAM_FIELD',
            'JIRA_EPIC_START_DATE_FIELD', 'JIRA_EPIC_DUE_DATE_FIELD',
            'API_SERVER', 'CONFIGURATION_SOURCE'
        )
        """
    )
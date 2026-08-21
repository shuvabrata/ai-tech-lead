"""update application_settings descriptions

Revision ID: 5f4a3b2c1d0e
Revises: 9e8c3e08ae33
Create Date: 2026-08-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f4a3b2c1d0e"
down_revision: Union[str, Sequence[str], None] = "9e8c3e08ae33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# New, more descriptive and end-user friendly descriptions for every setting.
# Source of truth: src/tips.json
NEW_DESCRIPTIONS: dict[str, str] = {
    "HTTP_REQUEST_TIMEOUT": "Value in seconds. Use in all HTTP external calls. Update this if you see timeouts.",
    "NEO4J_QUERY_TIMEOUT": "Value in seconds. Used in graph queries. Update this if you see timeouts.",
    "GRAPH_UI_MAX_NODE_LABEL_CHARS": "If you want to change the maximum number of characters displayed for node labels in the graph UI.",
    "GRAPH_UI_MAX_NODES_TO_EXPAND": "If you want to change the maximum number of nodes that can be expanded in the graph UI on double click or via Expand option.",
    "API_SERVER": "The base URL of the API server used by connectors and support WBA container services.",
    "COMMIT_DAYS_LIMIT": "For github connector this specifies the number of days to look back for commits for the first full scan. All subsequent scans are incremental scan and older data is not deleted. Example: If set to 30, then for the first scan, all commits in the last 30 days will be fetched. For subsequent scans, only new commits will be fetched.",
    "ATLASSIAN_MCP_ENABLED": "Turn on the Atlassian MCP integration so the AI assistant can query your Jira and Confluence data to answer questions. Enable this if you want the assistant to pull live project and issue context from Atlassian tools.",
    "ATLASSIAN_MCP_SERVER_URL": "The web address of the Atlassian MCP server that the app connects to for Jira and Confluence queries. Leave this as the default unless your MCP server is hosted at a different location.",
    "ATLASSIAN_MCP_TOKEN": "Your Atlassian API token with Rovo MCP scopes used to authenticate with the MCP server. Go to https://github.com/atlassian/atlassian-mcp-server for more details. Leave blank when editing to preserve the existing stored token.",
    "AUGMENTATION_HISTORY_TURNS": "Controls how many previous conversation turns the AI assistant remembers and uses as context when answering. A higher number gives the assistant more memory of the conversation but uses more tokens. Lower it if you want faster responses or to reduce token usage.",
    "CONFIGURATION_SOURCE": "Determines where the application reads its configuration from. Choose SERVER to manage settings through the app's database and UI, or FILE to load them from a configuration file. SERVER is recommended for most users. The FILE option is used for developer debugging.",
    "CONFLUENCE_LOOKBACK_DAYS": "Specifies how many days back the Confluence connector looks when syncing pages and content. Increase it to capture older content, or decrease it to speed up syncs. Note: reducing this value for a later scan does not delete previously fetched data — older content already synced will be kept.",
    "CONNECTOR_SCAN_POLL_INTERVAL": "How often (in milliseconds) the app checks for updates to connector scan status to refresh status in UI. A lower value gives more up-to-date status but uses more resources. The default is fine for most users; only change it if you notice performance issues.",
    "CUSTOM_API_TOKEN": "The API token used to authenticate with your custom LLM provider. This is a secret — keep it private and never share it. Required only if you use a custom provider.",
    "CUSTOM_API_URL": "The web address of your custom LLM provider's API endpoint. The app sends its requests to this URL when a custom provider is selected. Leave blank if you're not using a custom provider.",
    "CUSTOM_LLM_MODEL": "The name of the model to use with your custom LLM provider (for example, the model identifier your provider expects). Only needed if you use a custom provider.",
    "ELASTIC_PASSWORD": "The password used to authenticate with your Elasticsearch instance. This is a secret — keep it private and never share it. Elasticsearch is always enabled; only change this if an external Elasticsearch server was configured during deployment.",
    "ELASTICSEARCH_ENABLED": "Turns the Elasticsearch integration on or off. Elasticsearch powers search and log analytics across the app. It is enabled by default; disable it only if you're troubleshooting or running without Elasticsearch.",
    "ELASTICSEARCH_URL": "The web address of your Elasticsearch instance. The app connects to this URL for search and log analytics. Only change this if an external Elasticsearch server was configured during deployment.",
    "ENABLE_FILE_LOGGING": "Turns file-based logging on or off. When enabled, the app writes logs to files on disk so you can review them later. This is recommended to be enabled. Disable it only if you want to reduce disk usage or if file logging is causing issues.",
    "ES_CHAIN_MAX_RESULTS": "Controls how many search results the AI assistant can pull from Elasticsearch to enrich its answers. A higher number gives the assistant more context to work with but may slow down responses. Lower it if responses feel slow.",
    "FF_NEO4J_USE_PROVIDER_PIPELINE": "Set this to True if you're using a custom LLM provider that cannot be used with LangChain's provider-native Neo4j pipeline. When True, the app falls back to the custom augmentation chain for graph queries.",
    "GITHUB_MCP_ENABLED": "Turn on the GitHub MCP integration so the AI assistant can query your GitHub repositories, issues, and pull requests to answer questions. Enable this if you want the assistant to pull live repository context from GitHub.",
    "GITHUB_MCP_SERVER_URL": "The web address of the GitHub MCP server that the app connects to for repository queries. By default, this is a local container app. Leave it as the default unless your MCP server is hosted at a different location.",
    "GITHUB_MCP_TOKEN": "Your GitHub personal access token (PAT) used to authenticate with the GitHub MCP server. This is a secret — keep it private and never share it. Its scopes or permissions can vary based on what actions you want the AI chat interface to perform; read-only permissions are recommended. Leave blank when editing to preserve the existing stored token.",
    "IDENTITY_REFRESH_DAYS": "Specifies how often (in days) the connectors re-scan identity data, such as team member profiles and relationships. A lower value keeps identity data fresher but uses more API calls. Increase it to reduce API usage.",
    "JIRA_EPIC_DUE_DATE_FIELD": "The name of the Jira custom field that holds the due date for epics. Only change this if your Jira instance uses a different field name for epic due dates.",
    "JIRA_EPIC_START_DATE_FIELD": "The name of the Jira custom field that holds the start date for epics. Only change this if your Jira instance uses a different field name for epic start dates.",
    "JIRA_EPIC_TEAM_FIELD": "The name of the Jira custom field that identifies the team associated with an epic. Only change this if your Jira instance uses a different field name for the epic team.",
    "JIRA_ISSUE_TEAM_FIELD": "The name of the Jira custom field that identifies the team associated with an issue. Only change this if your Jira instance uses a different field name for the issue team.",
    "JIRA_LOOKBACK_DAYS": "Specifies how many days back the Jira connector looks when syncing issues. Increase it to capture older issues, or decrease it to speed up syncs. Note: reducing this value for a later scan does not delete previously fetched data — older issues already synced will be kept.",
    "JIRA_MAX_RESULTS_PER_PAGE": "Controls how many issues the Jira connector requests per API page during sync. A higher value fetches more data per request, which can speed up syncs but may hit Jira API limits. Lower it if you encounter API errors.",
    "LLM_MODEL": "The name of the model the AI assistant uses for chat responses (for example, gpt-5 or gpt-4o). If you use a custom provider, set the model name in CUSTOM_LLM_MODEL instead.",
    "LLM_PROVIDER": "Selects which LLM provider the AI chat interface uses. Choose openai for OpenAI's models, or custom to connect to your own in-house LLM provider. This setting requires a restart to take effect.",
    "LOG_DIR": "The folder where the app writes its log files when file logging is enabled. Changing this requires an understanding of the container mount paths, so avoid changing it unless really needed.",
    "LOG_FORMAT": "Controls how log entries are formatted. Choose TEXT for human-readable logs, or JSON for structured logs that are easier to parse by tools.",
    "LOG_LEVEL": "Controls how much detail the app writes to its logs. Choose DEBUG for the most detail (useful for troubleshooting), INFO for normal operation, or WARNING/ERROR to log only problems.",
    "LOG_SIGNAL_DUMPS": "When enabled, the signal-consumer application writes the raw Activity Signal payloads to disk as they are processed, under its LOG_DIR/signals/ folder. This is useful for debugging connector data. Disable it in normal operation to avoid filling up disk space.",
    "MAX_MCP_ITERATIONS": "Controls how many times the AI assistant can call MCP tools in a single request before stopping. A higher value lets the assistant perform more steps to answer complex questions but may slow down responses. Lower it if responses take too long.",
    "MAX_TEAM_SIZE": "The maximum number of team members the connectors will process before skipping. If a team is larger than this value, the connector skips it to avoid excessive API usage. Increase it if you have large teams that should be synced.",
    "MAX_TOKENS": "The approximate maximum number of tokens the AI assistant can use for conversation history before older messages are trimmed. A higher value keeps more context but uses more tokens and may slow responses. Lower it to reduce token usage.",
    "NEO4J_ENABLED": "Turns the Neo4j graph database integration on or off. Neo4j powers the collaboration graph and relationship analytics, and is a core requirement of the application, so it is highly recommended to keep it ON. Turn it off only for debugging purposes.",
    "NEO4J_PASSWORD": "The password used to authenticate with your Neo4j database. This is a secret — keep it private and never share it. Only change this if your Neo4j password has changed.",
    "NEO4J_URI": "The connection address of your Neo4j database, using the Bolt protocol (for example, bolt://localhost:7687). Only change this if your Neo4j database is hosted at a different location.",
    "NEO4J_USERNAME": "The username used to authenticate with your Neo4j database (usually neo4j). Only change this if your Neo4j username is different.",
    "OPENAI_API_KEY": "Your OpenAI API key used to authenticate with OpenAI's models. This is a secret — keep it private and never share it. Required only if you use the OpenAI provider.",
    "OPENAI_API_URL": "The web address of the OpenAI API endpoint the app sends its requests to. Leave this as the default unless you're using a compatible OpenAI-compatible endpoint.",
    "PULL_REQUEST_DAYS_LIMIT": "Specifies how many days back the GitHub connector looks when syncing pull requests. Increase it to capture older pull requests, or decrease it to speed up syncs. Note: reducing this value for a later scan does not delete previously fetched data — older pull requests already synced will be kept.",
    "RABBITMQ_URL": "The connection address of your RabbitMQ message broker, using the AMQP protocol. Connectors use this to publish and consume activity signals. Only change this if your RabbitMQ server is hosted at a different location.",
    "RECENT_ACTIONS_LIMIT": "Controls how many recent user commands (such as scan start or stop) are shown in the Recent Actions list. A higher value displays more command history but may make the list longer. Lower it to keep the list shorter.",
    "TIMEZONE": "The timezone the app uses to display dates and times in the UI. Use an IANA timezone name (for example, America/Los_Angeles or Asia/Kolkata). Change this to match your local timezone.",
    "UI_DATE_FORMAT": "Controls how dates (without time) are displayed in the UI. Uses strftime format codes — for example, %b %d, %Y shows dates like Mar 15, 2026. See the Python strftime documentation for available codes: https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes",
    "UI_DATETIME_FORMAT": "Controls how dates and times are displayed in the UI. Uses strftime format codes — for example, %b %d, %Y %I:%M %p shows dates like Mar 15, 2026 10:00 AM. See the Python strftime documentation for available codes: https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes",
}


def upgrade() -> None:
    """Update the description column for all application_settings rows."""
    for key, description in NEW_DESCRIPTIONS.items():
        # Escape single quotes in the description for safe SQL interpolation.
        escaped = description.replace("'", "''")
        op.execute(
            f"""
            UPDATE application_settings
            SET description = '{escaped}', updated_at = now()
            WHERE key = '{key}'
            """
        )


def downgrade() -> None:
    """Restore the original brief descriptions for all updated rows."""
    # Original descriptions as seeded by the initial migrations.
    original_descriptions: dict[str, str] = {
        "HTTP_REQUEST_TIMEOUT": "HTTP request timeout in seconds.",
        "NEO4J_QUERY_TIMEOUT": "Neo4j query timeout in seconds.",
        "GRAPH_UI_MAX_NODES_TO_EXPAND": "Maximum number of nodes expandable in graph UI.",
        "GRAPH_UI_MAX_NODE_LABEL_CHARS": "Maximum characters for node labels in graph UI.",
        "CONNECTOR_SCAN_POLL_INTERVAL": "Poll interval for connector scan status in milliseconds.",
        "RECENT_ACTIONS_LIMIT": "Maximum number of recent actions to display.",
        "TIMEZONE": "Application timezone (IANA name, e.g. America/Los_Angeles).",
        "UI_DATETIME_FORMAT": "strftime format for UI datetimes.",
        "UI_DATE_FORMAT": "strftime format for UI dates (no time).",
        "AUGMENTATION_HISTORY_TURNS": "Number of augmentation history turns to include in context.",
        "ES_CHAIN_MAX_RESULTS": "Maximum results from Elasticsearch augmentation chain.",
        "MAX_MCP_ITERATIONS": "Maximum tool-call iterations per MCP request.",
        "FF_NEO4J_USE_PROVIDER_PIPELINE": "Use provider-native Neo4j pipeline instead of custom chain.",
        "LLM_PROVIDER": "LLM provider selection (openai, custom).",
        "LLM_MODEL": "Model name for the LLM provider.",
        "OPENAI_API_KEY": "OpenAI API key.",
        "OPENAI_API_URL": "OpenAI API endpoint URL.",
        "CUSTOM_API_TOKEN": "Custom provider API token.",
        "CUSTOM_API_URL": "Custom provider endpoint URL.",
        "CUSTOM_LLM_MODEL": "Custom provider model name.",
        "MAX_TOKENS": "Maximum tokens before history pruning.",
        "GITHUB_MCP_ENABLED": "Enable GitHub MCP chain.",
        "GITHUB_MCP_SERVER_URL": "GitHub MCP server URL.",
        "GITHUB_MCP_TOKEN": "GitHub PAT for MCP server.",
        "ATLASSIAN_MCP_ENABLED": "Enable Atlassian MCP chain.",
        "ATLASSIAN_MCP_SERVER_URL": "Atlassian MCP server URL.",
        "ATLASSIAN_MCP_TOKEN": "Atlassian MCP API token.",
        "NEO4J_ENABLED": "Enable Neo4j graph database integration.",
        "NEO4J_URI": "Neo4j Bolt URI.",
        "NEO4J_USERNAME": "Neo4j username.",
        "NEO4J_PASSWORD": "Neo4j password.",
        "ELASTICSEARCH_ENABLED": "Enable Elasticsearch integration.",
        "ELASTICSEARCH_URL": "Elasticsearch endpoint URL.",
        "ELASTIC_PASSWORD": "Elasticsearch password.",
        "RABBITMQ_URL": "RabbitMQ AMQP connection URL.",
        "LOG_LEVEL": "Logging level (DEBUG, INFO, WARNING, ERROR).",
        "LOG_FORMAT": "Log format (JSON or TEXT).",
        "ENABLE_FILE_LOGGING": "Enable persistent file logging.",
        "LOG_DIR": "Log file directory path.",
        "LOG_SIGNAL_DUMPS": "Enable signal payload dumps to disk.",
        "COMMIT_DAYS_LIMIT": "Lookback days for commit sync.",
        "PULL_REQUEST_DAYS_LIMIT": "Lookback days for PR sync.",
        "IDENTITY_REFRESH_DAYS": "Days before re-scanning identity data.",
        "MAX_TEAM_SIZE": "Max team members before skipping.",
        "JIRA_LOOKBACK_DAYS": "Lookback days for Jira issue sync.",
        "JIRA_MAX_RESULTS_PER_PAGE": "Max results per Jira API page.",
        "CONFLUENCE_LOOKBACK_DAYS": "Lookback days for Confluence sync.",
        "JIRA_EPIC_TEAM_FIELD": "Jira custom field name for epic team.",
        "JIRA_ISSUE_TEAM_FIELD": "Jira custom field name for issue team.",
        "JIRA_EPIC_START_DATE_FIELD": "Jira field name for epic start date.",
        "JIRA_EPIC_DUE_DATE_FIELD": "Jira field name for epic due date.",
        "API_SERVER": "Base URL for the API server.",
        "CONFIGURATION_SOURCE": "Config source (SERVER or FILE).",
    }
    for key, description in original_descriptions.items():
        escaped = description.replace("'", "''")
        op.execute(
            f"""
            UPDATE application_settings
            SET description = '{escaped}', updated_at = now()
            WHERE key = '{key}'
            """
        )
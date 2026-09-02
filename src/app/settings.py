from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # PostgreSQL configuration
    DATABASE_URL: str
    
    # Neo4j configuration
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = ""
    NEO4J_ENABLED: bool = False
    FF_NEO4J_USE_PROVIDER_PIPELINE: bool = False

    # RabbitMQ configuration
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"

    # Elasticsearch configuration
    ELASTICSEARCH_ENABLED: bool = False
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    ELASTIC_PASSWORD: str = ""

    # Augmentation chain configuration
    AUGMENTATION_HISTORY_TURNS: int = 5  # prior turns passed to all chains for context resolution
    ES_CHAIN_MAX_RESULTS: int = 5  # max ES hits included in the LLM context block

    # MCP configuration
    GITHUB_MCP_ENABLED: bool = False
    ATLASSIAN_MCP_ENABLED: bool = False
    MAX_MCP_ITERATIONS: int = 3
    GITHUB_MCP_TOKEN: str = ""
    ATLASSIAN_MCP_TOKEN: str = ""
    GITHUB_MCP_SERVER_URL: str = "http://github-mcp:8082/"
    ATLASSIAN_MCP_SERVER_URL: str = "https://mcp.atlassian.com/v1/mcp"
    
    # LLM configuration (provider-agnostic)
    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "gpt-5"
    MAX_TOKENS: int = 16000
    OPENAI_API_KEY: str = ""
    OPENAI_API_URL: str = "https://api.openai.com/v1/chat/completions"
    CUSTOM_API_TOKEN: str = ""
    CUSTOM_API_URL: str = ""
    CUSTOM_LLM_MODEL: str = ""

    # Connector encryption
    CONNECTOR_ENCRYPTION_KEY: str = ""

    # Logging configuration
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "JSON"
    ENABLE_FILE_LOGGING: bool = False
    LOG_DIR: str = "logs"
    LOG_SIGNAL_DUMPS: bool = False

    # Connector / Producer configuration
    COMMIT_DAYS_LIMIT: int = 60
    PULL_REQUEST_DAYS_LIMIT: int = 60
    ISSUE_DAYS_LIMIT: int = 60
    IDENTITY_REFRESH_DAYS: int = 7
    MAX_TEAM_SIZE: int = 100
    JIRA_LOOKBACK_DAYS: int = 90
    JIRA_MAX_RESULTS_PER_PAGE: int = 100
    CONFLUENCE_LOOKBACK_DAYS: int = 60
    JIRA_EPIC_TEAM_FIELD: str = "Team"
    JIRA_ISSUE_TEAM_FIELD: str = "Team"
    JIRA_EPIC_START_DATE_FIELD: str = "created"
    JIRA_EPIC_DUE_DATE_FIELD: str = "duedate"
    API_SERVER: str = "http://app:8000/"
    CONFIGURATION_SOURCE: str = "SERVER"
    
    # HTTP request timeout configuration (in seconds)
    HTTP_REQUEST_TIMEOUT: int = 60
    
    # Neo4j query timeout (should be less than HTTP_REQUEST_TIMEOUT to allow overhead)
    NEO4J_QUERY_TIMEOUT: int = 10
    
    # Graph UI configuration
    GRAPH_UI_MAX_NODES_TO_EXPAND: int = 20
    GRAPH_UI_MAX_NODE_LABEL_CHARS: int = 10
    
    # Number of milliseconds between scan status polls in the connector UI
    CONNECTOR_SCAN_POLL_INTERVAL: int = 5000
    
    # Max recent action rows to display in the connector UI
    RECENT_ACTIONS_LIMIT: int = Field(default=5, ge=1, le=50)

    # Retry-with-backoff configuration for producer API calls (in seconds)
    RETRY_BUDGET_SECONDS: int = Field(default=3600, ge=1)
    RETRY_BACKOFF_CAP_SECONDS: int = Field(default=30, ge=1)
    RETRY_BASE_DELAY_SECONDS: int = Field(default=1, ge=1)

    # UI Configuration
    TIMEZONE: str = Field(default="UTC", validation_alias=AliasChoices("TIMEZONE", "TZ"))
    UI_DATETIME_FORMAT: str = "%b %d, %Y %I:%M %p"
    UI_DATE_FORMAT: str = "%b %d, %Y"

    @field_validator("TIMEZONE")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Invalid timezone: {value}") from exc
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

settings = Settings()

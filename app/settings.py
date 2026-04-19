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

    # MCP configuration
    GITHUB_MCP_ENABLED: bool = False
    JIRA_MCP_ENABLED: bool = False
    MAX_MCP_ITERATIONS: int = 3
    GITHUB_MCP_TOKEN: str = ""
    JIRA_MCP_URL: str = ""
    JIRA_MCP_USERNAME: str = ""
    JIRA_MCP_API_TOKEN: str = ""
    GITHUB_MCP_SERVER_URL: str = "http://github-mcp:8082/mcp"
    JIRA_MCP_SERVER_URL: str = "http://jira-mcp:9090/sse"
    
    # LLM configuration (provider-agnostic)
    LLM_MODEL: str = "gpt-5"
    OPENAI_API_KEY: str = ""

    # Connector encryption
    CONNECTOR_ENCRYPTION_KEY: str = ""
    
    # HTTP request timeout configuration (in seconds)
    HTTP_REQUEST_TIMEOUT: int = 60
    
    # Neo4j query timeout (should be less than HTTP_REQUEST_TIMEOUT to allow overhead)
    NEO4J_QUERY_TIMEOUT: int = 10
    
    # Graph UI configuration
    GRAPH_UI_MAX_NODES_TO_EXPAND: int = 20
    GRAPH_UI_MAX_NODE_LABEL_CHARS: int = 10
    
    # UI Configuration
    UI_DATETIME_FORMAT: str = "%b %d, %Y %I:%M %p"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

settings = Settings()

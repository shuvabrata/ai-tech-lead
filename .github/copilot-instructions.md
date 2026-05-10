# GitHub Copilot Instructions - Work Behavior Analytics AI

Always activate the virtual environment before running the application or tests:
```bash
source .venv/bin/activate
```

## Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.x)
- **Web Server**: Uvicorn with hot-reload for development
- **Database**: PostgreSQL (via Docker Compose)
- **ORM**: SQLAlchemy (async) with Alembic for migrations
- **AI/LLM**: Provider-agnostic LLM abstraction (OpenAI or custom) via `ai_agent/providers/`
- **Graph Database**: Neo4j (bundled in docker-compose)
- **Message Queue**: RabbitMQ (for connector producers/sync pipeline)
- **Time-series DB**: InfluxDB
- **Search**: Elasticsearch

### Frontend
- **Framework**: Dash (Python-based web framework)
- **UI Components**: dash-bootstrap-components
- **Layout**: Left-side menu navigation with pages:
  - Chat: GenAI-like conversational interface
  - People: Team member information and relationships
  - Progress: Project progress tracking and visualization
  - Graph: Neo4j graph visualization and query execution
  - Analytics: Collaboration analytics
  - Connectors: Connector configuration and management
  - Settings: Application configuration

### Infrastructure
- **Containerization**: Docker with docker-compose
- **Environment Management**: pydantic-settings with `.env` file
- **Async I/O**: asyncpg for PostgreSQL async operations
- **Deployment Model**: Single-user local deployment (laptop/desktop)

### Code Quality Tools
- **Type Checking**: mypy
- **Linting**: pylint

## Import Convention

Code lives in `src/` but is imported as top-level packages. `PYTHONPATH=src` is set in `pytest.ini` and all Docker containers.

```python
# Correct — always use these import paths
from app.common.logger import logger
from app.settings import settings
from app.ai_agent.providers import get_provider
```

Never use relative imports like `from ..common.logger` across package boundaries.

## Project Structure

```
src/
├── app/                             # Main application (FastAPI + Dash)
│   ├── main.py                      # FastAPI entry point; registers all routers, mounts Dash
│   ├── settings.py                  # Pydantic settings (env file loading)
│   ├── ai_agent/                    # AI agent core
│   │   ├── ai_agent.py              # Chat session management, LLM interaction
│   │   ├── chains/                  # Message augmentation chains
│   │   │   ├── chains.py            # Orchestrator: fans out to active chains
│   │   │   ├── neo4j_chain.py       # Neo4j context augmentation
│   │   │   └── mcp_chain.py         # MCP tool-call augmentation
│   │   ├── mcp_integration/         # MCP client layer
│   │   │   ├── client_manager.py    # MCP server connection management
│   │   │   ├── tool_executor.py     # Tool invocation against MCP servers
│   │   │   └── atlassian_config_loader.py
│   │   ├── providers/               # LLM provider abstraction
│   │   │   ├── base.py              # LLMProvider abstract base class
│   │   │   ├── factory.py           # get_provider() factory (cached singleton)
│   │   │   ├── openai/              # OpenAI implementation
│   │   │   └── custom/              # Custom/in-house LLM implementation
│   │   └── utils/                   # Token counting utilities
│   ├── api/                         # REST API endpoints
│   │   ├── endpoints.py             # /api/health and base routes
│   │   ├── chats/v1/                # Chat API
│   │   ├── projects/v1/             # Projects API
│   │   ├── graph/v1/                # Graph query execution API
│   │   ├── connectors/v1/           # Connector CRUD API
│   │   └── queries/v1/              # Query catalog API
│   ├── db/                          # Database layer
│   │   ├── base.py                  # SQLAlchemy Base
│   │   ├── session.py               # AsyncSession factory
│   │   └── models/                  # ORM models
│   │       ├── project.py
│   │       ├── connector.py
│   │       ├── connector_configs.py
│   │       └── producer_sync_state.py
│   ├── analytics/                   # Collaboration analytics
│   │   ├── collaboration/
│   │   └── registry.py
│   ├── dash_app/                    # Dash UI
│   │   ├── layout.py                # create_dash_app() factory; sidebar nav
│   │   ├── styles.py                # Centralized design tokens
│   │   ├── components/              # Shared UI components
│   │   └── pages/                   # Page modules
│   │       ├── chat.py
│   │       ├── people.py
│   │       ├── progress.py
│   │       ├── analytics.py
│   │       ├── graph/               # Graph page (callbacks, components, layout)
│   │       ├── connectors/          # Connectors page (callbacks, components, layout)
│   │       └── settings.py
│   ├── common/                      # App-level shared utilities
│   │   ├── logger.py
│   │   ├── encryption.py
│   │   ├── timezone.py
│   │   └── node_size.py
│   └── query_catalog/               # Query catalog loader
├── connectors/                      # Data connector services (separate Dockerfiles)
│   ├── producers/                   # Fetch from APIs → publish to RabbitMQ
│   │   ├── github_producer.py
│   │   ├── jira_producer.py
│   │   ├── fetch_github.py / fetch_jira.py
│   │   └── map_github.py / map_jira.py
│   └── modules/                     # Neo4j sync modules
│       ├── github/
│       └── jira/
├── common/                          # Cross-service shared code
│   ├── activity_signal/
│   └── messaging/
└── activity-signal/                 # Activity signal service
```

## Development Guidelines

### API Design
- **Versioning**: Use `/api/v1/` prefix for all API endpoints
- **Async/Await**: All database operations must use async/await
- **Layer Separation**:
  - Router: HTTP concerns only (validation, request/response)
  - Service: Business logic
  - Query: Database access
- **Models**: Use Pydantic models for request/response validation

### LLM Provider Pattern
Always use the factory — never instantiate a provider directly:

```python
from app.ai_agent.providers import get_provider

provider = get_provider()  # reads LLM_PROVIDER env var; returns cached singleton
```

To add a new provider: implement the `LLMProvider` base class in `providers/`, register it in `factory.py`.

### AI Agent / Chain of Augmentation
User messages are enriched before reaching the LLM:
1. `ai_agent.py` calls `augment_message_stream()` from `chains/chains.py`
2. `chains.py` fans out to active chains (Neo4j, MCP) based on feature flags in `settings`
3. Each chain returns a context envelope `{"source": "...", "context": "..."}`
4. Envelopes are composed into a single bounded prompt block
5. Augmented message is streamed to the LLM provider

### MCP Integration Pattern
The application itself (not Copilot) connects to MCP servers at runtime to enrich AI responses. These are internal application components — Copilot should write code for them, not call them.

The `mcp_integration/` layer manages the application's outbound MCP server connections:
- `client_manager.py` — creates and caches MCP server connections
- `tool_executor.py` — invokes tools on connected MCP servers
- `mcp_chain.py` — chain that calls `tool_executor` and formats results as a context envelope

Feature flags: `GITHUB_MCP_ENABLED`, `ATLASSIAN_MCP_ENABLED`

### Database Patterns
- **Migrations**: Use Alembic for all schema changes
- **Async Sessions**: Use `AsyncSession` from SQLAlchemy
- **Models**: Define using SQLAlchemy 2.0+ style with `Mapped` and `mapped_column`
- **Transactions**: Service layer manages transaction boundaries

### Code Style
- **Type Hints**: All function parameters and returns
- **Docstrings**: Modules, classes, and public functions
- **Logging**: Use `from app.common.logger import logger` — never `print()`
- **Error Handling**: Raise appropriate exceptions with clear messages
- **Python Code Style**: All Python code you generate must be PEP 8 compliant. 
- **Python 3.6+ Conventions**: Always use modern Python 3.6+ conventions. Specifically, use f-strings (f'...') for variable interpolation instead of % formatting or .format().

### UI Alert Design Standards
- **Placement**: Render alerts in a dedicated feedback region near the top of the active section; use sticky containers for long scrollable sections.
- **Dismissable by Default**: `dismissable=True` unless the alert must persist for safety reasons.
- **Typography**: Use centralized tokens from `src/app/dash_app/styles.py` — no ad-hoc inline sizes.
- **Spacing**: Use standardized spacing classes; avoid mixing arbitrary `mb-*` and `mt-*` patterns.
- **Semantic Colors**: success = completed, danger = failure, warning = recoverable, info = guidance/neutral.
- **Reusable Helpers**: Use shared alert builder functions for icon + message + dismiss patterns.
- **Auto-Dismiss**: Only for transient success notifications; keep error alerts persistent.

### Testing
Tests are in `tests/`. Markers are defined in `pytest.ini`: `unit`, `integration`, `server`, `neo4j`, `rabbitmq`.

```bash
# Unit tests only (no external services)
pytest -m unit tests -q

# Integration tests (requires running app server in another terminal)
PYTHONPATH=src uvicorn app.main:app --reload
pytest -m "integration and server" tests -q

# Neo4j tests (requires live Neo4j)
pytest -m neo4j tests -q
```

## Running the Application

### Development Setup (local app, Docker services)
```bash
# Start backing services
docker compose up -d postgres neo4j rabbitmq

# Activate virtual environment
source .venv/bin/activate

# Run migrations
cd src/app && alembic upgrade head && cd ../..

# Run application
PYTHONPATH=src uvicorn app.main:app --reload

# Access points:
# - API health: http://localhost:8000/api/health
# - Dash UI:    http://localhost:8000/app
```

### Full Docker Deployment
```bash
docker compose up -d
```

### Docker Compose Services

| Service | Purpose | Port(s) |
|---|---|---|
| `app` | FastAPI + Dash | 8000 |
| `postgres` | Primary database | 5432 |
| `neo4j` | Graph database | 7474, 7687 |
| `rabbitmq` | Message queue for producers | 5672, 15672 (mgmt UI) |
| `influxdb` | Time-series metrics | 8086 |
| `elasticsearch` | Search / log analytics | 9200 |
| `github-mcp` | GitHub MCP server | 8082 |
| `github-producer` | Fetch GitHub → RabbitMQ (one-shot) | — |
| `jira-producer` | Fetch Jira → RabbitMQ (one-shot) | — |
| `github-sync` | Sync GitHub → Neo4j (one-shot) | — |
| `jira-sync` | Sync Jira → Neo4j (one-shot) | — |

One-shot services are run manually: `docker compose run --rm <service>`

## Environment Configuration

### Core
| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL async connection string | required |
| `LLM_PROVIDER` | `openai` or `custom` | `openai` |
| `LLM_MODEL` | Model name | `gpt-5` |
| `OPENAI_API_KEY` | Required for OpenAI provider | — |
| `CUSTOM_API_TOKEN` | Required for custom provider | — |
| `CUSTOM_API_URL` | Custom provider endpoint | — |
| `MAX_TOKENS` | Chat history token limit | `16000` |

### Neo4j
| Variable | Description | Default |
|---|---|---|
| `NEO4J_ENABLED` | Enable Neo4j chain | `false` |
| `NEO4J_URI` | Bolt URI | `bolt://localhost:7687` |
| `NEO4J_USERNAME` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | — |
| `FF_NEO4J_USE_PROVIDER_PIPELINE` | Use provider-native Neo4j pipeline | `false` |
| `NEO4J_QUERY_TIMEOUT` | Query timeout (seconds) | `10` |

### MCP
| Variable | Description | Default |
|---|---|---|
| `GITHUB_MCP_ENABLED` | Enable GitHub MCP chain | `false` |
| `ATLASSIAN_MCP_ENABLED` | Enable Atlassian MCP chain | `false` |
| `MAX_MCP_ITERATIONS` | Max tool-call iterations per request | `3` |
| `GITHUB_MCP_TOKEN` | GitHub PAT for MCP server | — |
| `GITHUB_MCP_SERVER_URL` | GitHub MCP server URL | `http://github-mcp:8082/mcp` |
| `ATLASSIAN_MCP_SERVER_URL` | Atlassian MCP server URL | — |

### Infrastructure & UI
| Variable | Description | Default |
|---|---|---|
| `RABBITMQ_URL` | RabbitMQ AMQP URL | `amqp://guest:guest@localhost:5672/` |
| `CONNECTOR_ENCRYPTION_KEY` | Fernet key for connector secrets | required |
| `HTTP_REQUEST_TIMEOUT` | Outbound HTTP timeout (seconds) | `60` |
| `TIMEZONE` | UI timezone (IANA name, e.g. `America/Los_Angeles`) | `UTC` |
| `UI_DATETIME_FORMAT` | strftime format for UI dates | `%b %d, %Y %I:%M %p` |
| `GRAPH_UI_MAX_NODES_TO_EXPAND` | Max nodes expandable in graph UI | `20` |
| `GRAPH_UI_MAX_NODE_LABEL_CHARS` | Max chars for node labels in graph UI | `10` |

## Common Tasks

### Adding a New API Endpoint
1. Define Pydantic models in `src/app/api/<domain>/v1/model.py`
2. Create database queries in `query.py` (if needed)
3. Implement business logic in `service.py`
4. Define routes in `router.py`
5. Include router in `src/app/main.py`

### Adding a Database Model
1. Create model in `src/app/db/models/`
2. Import in `src/app/db/models/__init__.py`
3. Generate migration: `cd src/app && alembic revision --autogenerate -m "description"`
4. Apply: `alembic upgrade head`

### Adding a New Augmentation Chain
1. Create file in `src/app/ai_agent/chains/`
2. Implement an async generator that yields context envelopes `{"source": "...", "context": "..."}`
3. Register it in `chains.py` `augment_message_stream()`, guarded by the relevant feature flag from `settings`

### Adding a New UI Page
1. Create page module in `src/app/dash_app/pages/`
2. Add nav link in `src/app/dash_app/layout.py` sidebar
3. Register the page route in the layout URL callback

## Architecture Notes

### Service Layer Pattern
- Routers handle HTTP concerns only
- Services contain business logic
- Query layer manages database access

### Factory Pattern for Dash App
The Dash application is created via `create_dash_app()` in `dash_app/layout.py` and mounted on FastAPI using WSGI middleware.

### Neo4j Integration
Neo4j runs as a Docker Compose service. `neo4j_chain.py` augments user messages with graph query results. The sync services (`github-sync`, `jira-sync`) load data into Neo4j from RabbitMQ.

### Connectors Architecture
`src/connectors/producers/` contains one-shot scripts that fetch data from GitHub/Jira APIs and publish `ActivitySignal` events to RabbitMQ. Run via `docker compose run --rm github-producer` (or `jira-producer`). Sync modules in `src/connectors/modules/` consume from RabbitMQ and write to Neo4j.

### Authentication & Multi-Tenancy
Out of scope. Designed for single-user local deployment; assumes a trusted local environment.

### Development Workflow
- Solo developer with AI-assisted development
- Code quality gates: `mypy` (type checking), `pylint` (linting)
- Testing: automated for regression prevention; manual for new concept validation; prioritize practical coverage over metrics

## Reference Documents

Consult these when working in the relevant areas. They define patterns and constraints that must be followed.

| Document | When to consult |
|---|---|
| [docs/design/design-system.md](docs/design/design-system.md) | Any UI work — canonical design tokens (colors, typography, spacing, components). Do not invent styles; use what is defined here and in `src/app/dash_app/styles.py`. |
| [docs/design/frontend-design-skill.md](docs/design/frontend-design-skill.md) | Any UI work — specifies the "Executive Dashboard" aesthetic: Cormorant Garamond + Inter fonts, navy/charcoal palette, 2px border-radius. Use this to ensure visual consistency. |
| [docs/design/spec-activity-signal.md](docs/design/spec-activity-signal.md) | Any connector/producer/sync work — defines the canonical `ActivitySignal` JSON schema. All producers must emit this format; all sync modules must consume it. |
| [docs/design/RELATIONSHIPS_DESIGN.md](docs/design/RELATIONSHIPS_DESIGN.md) | Any Neo4j schema or Cypher work — explains the single-edge undirected relationship design. Do not add bidirectional edges; queries use undirected traversal instead. |
| [docs/design/github-api-optimization.md](docs/design/github-api-optimization.md) | GitHub producer or sync work — documents the incremental sync pattern (`_last_synced_at`, `fully_synced` flag) that avoids redundant API calls. New GitHub sync code must honour these flags. |

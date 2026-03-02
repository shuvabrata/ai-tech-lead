# GitHub Copilot Instructions - AI Tech Lead Assistant

Always activate the virual environment before running the application or tests:
```bash
source .venv/bin/activate
```

## Project Overview

**AI Tech Lead Assistant** is an AI-powered tool designed to help senior tech leaders make data-driven decisions for project management. The system analyzes project data from various sources (GitHub, Jira, Confluence, etc.) and provides actionable insights through a natural language chat interface.

### Core Purpose
- Assist tech leaders in prioritizing tasks and making objective decisions
- Analyze project inputs (scope, resources, time) and track outputs (progress, blockers)
- Answer tactical questions about team performance, code quality, and project health
- Provide weekly analysis with forecasting and recommendations
- Remove human bias from tactical decision-making through data-driven insights

## Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.x)
- **Web Server**: Uvicorn with hot-reload for development
- **Database**: PostgreSQL (via Docker Compose)
- **ORM**: SQLAlchemy (async) with Alembic for migrations
- **AI/LLM**: OpenAI API with LangChain framework
- **Graph Database**: Neo4j (external module, developed in separate repo)

### Frontend
- **Framework**: Dash (Python-based web framework)
- **UI Components**: dash-bootstrap-components
- **Layout**: Left-side menu navigation with pages:
  - Chat: GenAI-like conversational interface
  - Projects: Project management and switching
  - People: Team member information and relationships
  - Progress: Project progress tracking and visualization
  - Settings: Configuration management

### Infrastructure
- **Containerization**: Docker with docker-compose for PostgreSQL
- **Environment Management**: python-dotenv for configuration
- **Async I/O**: asyncpg for PostgreSQL async operations
- **Deployment Model**: Single-user local deployment (laptop/desktop)

### Code Quality Tools
- **Type Checking**: mypy for static type analysis
- **Linting**: pylint for code quality checks
- **AI Review**: GitHub Copilot for code review assistance

## Project Structure

```
app/
├── main.py              # FastAPI app entry point, includes routers and mounts Dash
├── settings.py          # Pydantic settings with env file loading
├── ai_agent/            # AI agent core functionality
│   ├── ai_agent.py      # Chat session management and LLM interaction
│   ├── chains/          # LangChain chains for data augmentation
│   │   ├── chains.py    # Base chain functionality
│   │   └── neo4j_chain.py  # Neo4j-specific chain
│   └── utils/           # Token counting and utilities
├── api/                 # REST API endpoints
│   ├── endpoints.py     # Base API routes
│   ├── chats/v1/        # Chat API v1
│   │   ├── router.py    # FastAPI router
│   │   ├── service.py   # Business logic
│   │   └── model.py     # Pydantic models
│   └── projects/v1/     # Projects API v1
│       ├── router.py    # FastAPI router
│       ├── service.py   # Business logic
│       ├── query.py     # Database queries
│       └── model.py     # Pydantic models
├── db/                  # Database layer
│   ├── base.py          # SQLAlchemy Base
│   ├── session.py       # Database session management
│   └── models/          # SQLAlchemy ORM models
│       └── project.py   # Project model
├── dash_app/            # Dash UI application
│   ├── layout.py        # Main layout and app creation
│   └── pages/           # Individual page components
└── common/              # Shared utilities
    └── logger.py        # Logging configuration
```

## Development Guidelines

### API Design
- **Versioning**: Use `/api/v1/` prefix for all API endpoints
- **Async/Await**: All database operations should use async/await patterns
- **Layer Separation**: 
  - Router: HTTP layer (validation, request/response)
  - Service: Business logic layer
  - Query: Database access layer
- **Models**: Use Pydantic models for request/response validation

### AI Agent Design
- **Session Management**: In-memory chat sessions with GUID session IDs
- **Message Augmentation**: User messages are augmented with relevant data from chains (e.g., Neo4j)
- **Token Management**: Monitor token usage and prune old messages when approaching limits (default: 16k tokens)
- **System Prompts**: Configurable system prompts per chat session
- **Model Configuration**: LLM model and parameters configurable via environment variables

### Database Patterns
- **Migrations**: Use Alembic for all schema changes
- **Async Sessions**: Use `AsyncSession` from SQLAlchemy
- **Models**: Define using SQLAlchemy 2.0+ style with `Mapped` and `mapped_column`
- **Transactions**: Service layer manages transaction boundaries

### Environment Configuration
Required environment variables:
- `DATABASE_URL`: PostgreSQL connection string
- `LLM_PROVIDER`: LLM provider to use (openai, custom)
- `LLM_MODEL`: Model name to use (e.g., gpt-3.5-turbo, gpt-4, or custom model name)
- `OPENAI_API_KEY`: OpenAI API key (required for OpenAI provider)
- `CUSTOM_API_TOKEN`: Custom API token (required for Custom provider)
- `MAX_TOKENS`: Maximum tokens for chat history (default: 16000)

### Code Style
- **Type Hints**: Use type hints for all function parameters and returns
- **Docstrings**: Document modules, classes, and functions with clear docstrings
- **Logging**: Use the centralized logger from `app.common.logger`
- **Error Handling**: Raise appropriate exceptions with clear error messages

### Testing
- Tests located in `tests/` directory
- Test server should be running: `uvicorn app.main:app --reload`
- Run tests: `pytest ./tests/test_projects.py`
- **Testing Strategy**:
  - **Automated tests**: For regression prevention and critical paths
  - **Manual testing**: For new concept validation and exploratory testing
  - Focus on practical test coverage rather than 100% coverage

## Running the Application

### Development Setup
```bash
# Start PostgreSQL only (for local development)
docker compose up -d postgres

# Activate virtual environment
source .venv/bin/activate

# Run migrations
cd app && alembic upgrade head && cd ..

# Run application
uvicorn app.main:app --reload

# Access points:
# - FastAPI: http://localhost:8000/api/hello
# - Dash UI: http://localhost:8000/app
```

### Docker Deployment
```bash
# Start both PostgreSQL and app
docker compose up -d
```

### Docker Deployment
```bash
docker build -t ai-tech-lead .
docker run -p 8000:8000 ai-tech-lead
```

## Project Phases (8-Phase Roadmap)

### Current Status: Phases 1-3 In Progress

1. **Phase 1**: Technical Prototype with Simulated Data 🔄 (In Progress)
2. **Phase 2**: Real Data Integration (GitHub & Jira) 🔄 (In Progress)
3. **Phase 3**: Employee Relationship Graph 🔄 (In Progress)
4. **Phase 4**: MCP Servers & Advanced Chains ⏳ (Not Started)
5. **Phase 5**: Custom UI Reports & Charts ⏳ (Planned)
6. **Phase 6**: Graph Visualization UI ⏳ (Planned)
7. **Phase 7**: Conversation Persistence ⏳ (Planned)
8. **Phase 8**: Configuration & Connector Management UI ⏳ (Planned)

**Note**: MCP (Model Context Protocol) servers are planned for Phase 4 but not yet implemented.

## Key Design Patterns

### Chain of Augmentation
User messages are augmented with relevant context before being sent to the LLM:
1. User submits a message
2. Message passes through chain(s) (e.g., Neo4j chain)
3. Chain adds relevant data/context to the message
4. Augmented message sent to LLM
5. Response returned to user

### Service Layer Pattern
- Routers handle HTTP concerns only
- Services contain business logic
- Query layer manages database access
- Clear separation of concerns

### Factory Pattern for Dash App
The Dash application is created via `create_dash_app()` factory function and mounted on FastAPI using WSGI middleware.

## Common Tasks

### Adding a New API Endpoint
1. Define Pydantic models in `model.py`
2. Create database queries in `query.py` (if needed)
3. Implement business logic in `service.py`
4. Define routes in `router.py`
5. Include router in `main.py`

### Adding a Database Model
1. Create model class in `app/db/models/`
2. Import in `app/db/models/__init__.py`
3. Generate migration: `alembic revision --autogenerate -m "description"`
4. Review and apply migration: `alembic upgrade head`

### Adding a New Chain
1. Create chain file in `app/ai_agent/chains/`
2. Implement chain logic (e.g., query Neo4j, format data)
3. Register chain in `chains.py` augment_message function
4. Add prompt template in markdown file if needed

## Architecture Notes

### Neo4j Integration
- **External Module**: Neo4j database and integration logic are developed in a separate GitHub repository
- **Setup**: Neo4j will be set up and configured separately from this project
- **Integration**: This project treats Neo4j as an external dependency/service
- **Chain Pattern**: Neo4j chains in `app/ai_agent/chains/neo4j_chain.py` interact with the external Neo4j instance

### Authentication & Multi-Tenancy
- **Out of Scope**: Authentication and multi-tenancy are not planned for the foreseeable future
- **Use Case**: Designed for single-user local deployment on laptop/desktop
- **Security Model**: Assumes trusted local environment

### Development Workflow
- **Solo Developer**: Single developer working with AI-assisted development
- **Code Quality Gates**:
  - Type checking with `mypy`
  - Linting with `pylint`
  - AI-assisted code review via GitHub Copilot
- **Testing Approach**:
  - Write automated tests for regression prevention
  - Use manual testing for validating new concepts
  - Prioritize practical coverage over metrics

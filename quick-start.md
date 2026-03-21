# work-behavior-analytics-ai

# First time dev setup
Setup python environment
```
pyenv local 3.12.12 # optional
python -m venv .venv
source .venv/bin/activate\n
pip install -r requirements.txt
 ```

 Make a copy of .env.example to .env and update the values.

## Environment Configuration

### LLM Provider Selection
The system supports multiple LLM providers through an abstraction layer. Configure via the `LLM_PROVIDER` environment variable:

```bash
# Choose your LLM provider (openai or custom)
LLM_PROVIDER=openai  # Default
```

### LLM Model Configuration
Set the model to use with your selected provider:
```bash
LLM_MODEL=gpt5  # For OpenAI: gpt-3.5-turbo, gpt-4, gpt-4-turbo, etc.
                         # For Custom: your custom model name (e.g., gpt4)
MAX_TOKENS=16000  # Maximum conversation history tokens
```

### OpenAI Configuration (Default Provider)
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

### Custom Provider Configuration (Optional)
For using a custom/in-house LLM provider:
```bash
LLM_PROVIDER=custom
CUSTOM_API_TOKEN=your_custom_api_token
CUSTOM_API_URL=https://api.yourcompany.com/chat  # Your custom API endpoint
```

### Neo4j Configuration (Optional)
```bash
NEO4J_ENABLED=true  # Set to false to disable
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

# Start Services with Docker Compose

## Option 1: Using Docker Compose (Recommended)
Start both PostgreSQL and the application together:
```bash
docker compose up -d
```

This will:
- Start PostgreSQL database
- Build and start the application
- Automatically run database migrations
- Mount .env file and logs directory

To stop all services:
```bash
docker compose down
```

To view logs:
```bash
docker compose logs -f app
```

## Option 2: PostgreSQL Only (For Local Development)
If you want to run the app locally but use PostgreSQL in Docker:
```bash
docker compose up -d postgres
```

Then run the app locally:
```bash
uvicorn app.main:app --reload
```

Access the services:
- FastAPI API: http://localhost:8000/api/hello
- Dash UI: http://localhost:8000/app

## Running Migrations Manually (Local Development)
If running locally, you'll need to run migrations manually:
```bash
cd app
alembic upgrade head
cd ..
```
To create a new migration:
```bash
docker compose exec app bash -c "cd app && alembic revision --autogenerate -m 'description'"
```


# Run tests
- Start the server
```
uvicorn app.main:app --reload
```
In another window
```
 pytest ./tests/test_projects.py
```

# ai-tech-lead

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

# Start PostgreSQL docker container
To start
```
docker compose -f docker-compose-psql.yml up -d
```
To stop
```
docker compose -f docker-compose-psql.yml down
```

# Running
```
uvicorn app.main:app --reload

```
Access the services:

FastAPI API: http://localhost:8000/api/hello
Dash UI: http://localhost:8000/app

 # Docker 
Build the image:
```
docker build -t ai-tech-lead .
```

Run the container:
```
docker run -p 8000:8000 ai-tech-lead
```

Your app will be available at http://localhost:8000/app and http://localhost:8000/api/hello

# Run tests
- Start the server
```
uvicorn app.main:app --reload
```
In another window
```
 pytest ./tests/test_projects.py
```

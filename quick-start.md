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

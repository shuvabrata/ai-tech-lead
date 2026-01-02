# ai-tech-lead

# Tech Stack choice
- Backend
  - FastAPI
  - AI / analytics services
  - Async job execution
  - Caching (Redis)

- UI
  - Dash
  - Plotly figures
  - Parameter controls (sliders, dropdowns)

- Integration
  - Dash mounted under /app
  - FastAPI under /api
  - Shared auth and config

- This keeps:
  - Python end-to-end
  - browser-based UI
  - minimal tech sprawl
 
- Deployment
  - Docker for containairization
  - Qeuue Event based backend processing for long taking tasks.
  - AWS RDS Postgres SQL for DB
  - AWS for hosting



# Notes
If I take this route (Dash + FAST API) what are my deployment options? My preference is to deploy it in AWS. I want to host multiple pages under a web portal with top or side bar based navigation.

This is a good, realistic stack, and AWS gives you several clean deployment paths. I’ll walk through this from architecture → deployment → navigation, focusing on options that scale without over-engineering.

1. First: Dash + FastAPI deployment model (important)

Dash is also ASGI-compatible (via Flask/Werkzeug internally, mounted through WSGI → ASGI adapters). In practice, there are two sane deployment shapes:

Model A — Single ASGI app (recommended)
    FastAPI = /api
    Dash = /app (or /)
    One container, one process model
    One load balancer target

This is simplest and works very well up to moderate traffic.

Model B — Separate services
    FastAPI service
    Dash service
    Shared auth, same domain
    More scalable, more ops work

For a side project, Model A is strongly preferred.

2. AWS deployment options (ranked best → worst for your case)
✅ Option 1: AWS ECS (Fargate) – Best overall choice

This is the sweet spot between control and simplicity.

Why ECS Fargate fits you
    No server management
    Native Docker workflow
    Scales horizontally
    Plays nicely with ASGI apps
    Easy to attach ALB + HTTPS
    Long-running analytics jobs supported

Typical setup

    Docker container running:
    Uvicorn / Gunicorn
    FastAPI + Dash mounted
    Application Load Balancer
    ACM TLS certificate
    Route53 DNS

Scaling
    Scale by CPU / memory
    Later split API & UI if needed

This is the most common production choice for Dash + FastAPI.


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

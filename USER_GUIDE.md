# AI Tech Lead - User Guide

## Prerequisites

1. **Docker and Docker Compose installed** on your system
2. **Environment file configured**: Copy `.env.example` to `.env` and update the values:
   ```bash
   cp .env.example .env
   # Edit .env with your actual configuration (database credentials, API keys, etc.)
   ```

## Starting the Application

### Start All Services
To start both PostgreSQL and the application:

```bash
docker compose up -d
```

The `-d` flag runs containers in detached mode (background).

**What happens:**
- PostgreSQL database starts first
- Application waits for PostgreSQL to be healthy
- Database migrations run automatically
- Application starts and listens on port 8000

**Access the application:**
- FastAPI API: http://localhost:8000/api/hello
- Dash UI: http://localhost:8000/app

### Start Only PostgreSQL (For Local Development)
If you want to run the app locally but use PostgreSQL in Docker:

```bash
docker compose up -d postgres
```

Then run the app locally:
```bash
source .venv/bin/activate
cd app && alembic upgrade head && cd ..
uvicorn app.main:app --reload
```

## Stopping the Application

### Stop All Services
```bash
docker compose down
```

This stops and removes containers, but **preserves data** in the PostgreSQL volume.

### Stop and Remove Volumes (Clean Reset)
⚠️ **Warning**: This deletes all database data!

```bash
docker compose down -v
```

### Stop Without Removing Containers
```bash
docker compose stop
```

To restart stopped containers:
```bash
docker compose start
```

## Viewing Logs

### View All Service Logs
```bash
docker compose logs
```

### View App Logs Only
```bash
docker compose logs app
```

### View PostgreSQL Logs Only
```bash
docker compose logs postgres
```

### Follow Logs in Real-Time
```bash
docker compose logs -f app
```

Press `Ctrl+C` to stop following logs.

### View Last N Lines
```bash
docker compose logs app --tail 50
```

### View Logs with Timestamps
```bash
docker compose logs -f -t app
```

## Checking Status

### Check Running Containers
```bash
docker compose ps
```

### Check Container Details
```bash
docker ps
```

### Check PostgreSQL Health
```bash
docker compose exec postgres pg_isready -U <your_postgres_user>
```

## Rebuilding the Application

### Rebuild After Code Changes
```bash
docker compose up -d --build
```

### Force Rebuild Without Cache
```bash
docker compose build --no-cache
docker compose up -d
```

## Accessing Containers

### Open a Shell in the App Container
```bash
docker compose exec app bash
```

### Open a PostgreSQL Shell
```bash
docker compose exec postgres psql -U <your_postgres_user> -d <your_postgres_db>
```

## Troubleshooting

### Container Keeps Restarting
Check the logs:
```bash
docker compose logs app
```

Common issues:
- **Database connection errors**: Ensure `DATABASE_URL` uses `postgres` as hostname (not `localhost`)
- **Missing environment variables**: Check your `.env` file
- **Port conflicts**: Ensure ports 5432 and 8000 are not in use

### View Container Resource Usage
```bash
docker stats
```

### Inspect Network Configuration
```bash
docker network inspect ai-tech-lead_ai-tech-lead-network
```

### Remove Everything and Start Fresh
```bash
docker compose down -v
docker compose up -d --build
```

## File Locations

### Logs Directory
Application logs are written to `./logs/` on your host machine (mounted from container).

To view log files:
```bash
ls -la logs/
cat logs/logger_*.log
```

### Environment Configuration
The `.env` file is mounted read-only into the container at `/app/.env`.

⚠️ **Note**: After changing `.env`, restart the containers:
```bash
docker compose restart app
```

## Running Database Migrations Manually

If needed, you can run migrations manually:

```bash
docker compose exec app bash -c "cd app && alembic upgrade head"
```

To create a new migration:
```bash
docker compose exec app bash -c "cd app && alembic revision --autogenerate -m 'description'"
```

## Quick Reference

| Task | Command |
|------|---------|
| Start services | `docker compose up -d` |
| Stop services | `docker compose down` |
| View logs | `docker compose logs -f app` |
| Check status | `docker compose ps` |
| Rebuild | `docker compose up -d --build` |
| Restart app | `docker compose restart app` |
| Shell access | `docker compose exec app bash` |
| Clean reset | `docker compose down -v && docker compose up -d --build` |

## Support

For issues or questions:
1. Check the logs: `docker compose logs -f app`
2. Review the [quick-start.md](quick-start.md) guide
3. Ensure your `.env` file is properly configured

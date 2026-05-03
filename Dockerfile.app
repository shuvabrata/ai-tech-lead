# Use official Python image
FROM python:3.11-slim

# Install PostgreSQL client for database readiness check
RUN apt-get update && apt-get install -y postgresql-client curl && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.app.txt ./requirements.txt 
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code (includes alembic/, alembic.ini, entrypoint.sh)
COPY src/app/ ./app/

# Copy shipped query catalog used by the graph query workbench
COPY queries_catalog/ ./queries_catalog/

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    mkdir -p /var/log/app && \
    chown -R appuser:appuser /var/log/app /app

# Expose port
EXPOSE 8000

# Switch to non-root user
USER appuser

# Use entrypoint script
ENTRYPOINT ["app/entrypoint.sh"]

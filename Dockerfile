# Use official Python image
FROM python:3.11-slim

# Install PostgreSQL client for database readiness check
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code (includes alembic/, alembic.ini, entrypoint.sh)
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Use entrypoint script
ENTRYPOINT ["app/entrypoint.sh"]

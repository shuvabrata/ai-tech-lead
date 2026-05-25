#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."

# Wait for PostgreSQL to be ready
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q'; do
  >&2 echo "PostgreSQL is unavailable - sleeping"
  sleep 1
done

>&2 echo "PostgreSQL is up - executing migrations"

# Run database migrations
cd /app/app && alembic upgrade head

>&2 echo "Migrations complete - initializing RabbitMQ"

# Initialize RabbitMQ exchanges and queues for the ActivitySignal pipeline
cd /app && python app/scripts/init_rabbitmq.py

>&2 echo "RabbitMQ initialization complete - creating Neo4j indexes"

# Create Neo4j indexes (idempotent)
cd /app && python app/scripts/create_neo4j_indexes.py

>&2 echo "Neo4j indexes ready - creating Elasticsearch indexes"

# Create Elasticsearch indexes and wba_all alias (idempotent, skipped if disabled)
if [ "$ELASTICSEARCH_ENABLED" = "true" ]; then
  cd /app && python app/scripts/create_es_indexes.py
  >&2 echo "Elasticsearch indexes ready - starting application"
else
  >&2 echo "Elasticsearch disabled - skipping index creation"
fi

# Start the application
cd /app && uvicorn app.main:app --host 0.0.0.0 --port 8000

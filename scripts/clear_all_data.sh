#!/bin/bash
# Reset Neo4j Database
# Clears all nodes and relationships from the database

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Navigate to project root (parent of scripts/)
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Navigate to simulation/layer1 and run reset
cd "$PROJECT_ROOT/simulation/layer1"
python3 reset_db.py

# Clear PostgreSQL producer_sync_state table
echo "Clearing producer_sync_state table..."
docker compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T postgres \
  psql -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" \
  -c "DELETE FROM producer_sync_state;"
echo "producer_sync_state cleared."

# Flush RabbitMQ queues
echo "Flushing RabbitMQ queues..."
bash "$SCRIPT_DIR/flush_rabbitmq_queues.sh"
echo "RabbitMQ queues flushed."

# Clear all Elasticsearch documents (delete and recreate all managed indexes)
echo "Clearing Elasticsearch indexes..."
cd "$PROJECT_ROOT" && PYTHONPATH=src ELASTICSEARCH_URL="${ELASTICSEARCH_URL:-http://localhost:9200}" \
  python scripts/clear_es_data.py
echo "Elasticsearch cleared."

# Clear log files (keep directory structure intact)
echo "Clearing log files..."
find "$PROJECT_ROOT/logs" -type f \( -name "*.log" -o -name "*.jsonl" \) -delete
echo "Log files cleared."

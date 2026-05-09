#!/bin/bash
# Flush (purge) all RabbitMQ queues by deleting all queued messages.
#
# Uses RabbitMQ Management HTTP API:
# - List queues: GET /api/queues/{vhost}
# - Purge queue contents: DELETE /api/queues/{vhost}/{name}/contents
#
# Environment variables:
#   RABBITMQ_MGMT_URL   Base management API URL (default: http://localhost:15672/api)
#   RABBITMQ_USER       Management username (default: guest)
#   RABBITMQ_PASSWORD   Management password (default: guest)
#   RABBITMQ_VHOST      Vhost name (default: /)
#
# Usage:
#   ./scripts/flush_rabbitmq_queues.sh
#   ./scripts/flush_rabbitmq_queues.sh --dry-run

set -euo pipefail

RABBITMQ_MGMT_URL="${RABBITMQ_MGMT_URL:-http://localhost:15672/api}"
RABBITMQ_USER="${RABBITMQ_USER:-guest}"
RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-guest}"
RABBITMQ_VHOST="${RABBITMQ_VHOST:-/}"
DRY_RUN=0

usage() {
  cat <<EOF
Flush all RabbitMQ queues (delete all messages in each queue).

Usage:
  $0 [--dry-run] [--help]

Options:
  --dry-run   Show what would be purged without deleting messages.
  --help      Show this help text.

Environment:
  RABBITMQ_MGMT_URL   Default: http://localhost:15672/api
  RABBITMQ_USER       Default: guest
  RABBITMQ_PASSWORD   Default: guest
  RABBITMQ_VHOST      Default: /
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage
      exit 1
      ;;
  esac
done

url_encode() {
  python3 - "$1" <<'PY'
import sys
import urllib.parse
print(urllib.parse.quote(sys.argv[1], safe=''))
PY
}

ENCODED_VHOST="$(url_encode "$RABBITMQ_VHOST")"

echo "RabbitMQ Management API: $RABBITMQ_MGMT_URL"
echo "VHost: $RABBITMQ_VHOST"

QUEUE_JSON="$(curl -fsS -u "$RABBITMQ_USER:$RABBITMQ_PASSWORD" "$RABBITMQ_MGMT_URL/queues/$ENCODED_VHOST")"

mapfile -t QUEUES < <(
  printf '%s' "$QUEUE_JSON" | python3 -c '
import json
import sys

queues = json.load(sys.stdin)
for q in queues:
    name = q.get("name")
    if name:
        print(name)
'
)

if [ "${#QUEUES[@]}" -eq 0 ]; then
  echo "No queues found in vhost '$RABBITMQ_VHOST'."
  exit 0
fi

echo "Found ${#QUEUES[@]} queue(s)."

PURGED=0
FAILED=0

for queue in "${QUEUES[@]}"; do
  encoded_queue="$(url_encode "$queue")"
  endpoint="$RABBITMQ_MGMT_URL/queues/$ENCODED_VHOST/$encoded_queue/contents"

  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[DRY-RUN] Would purge queue: $queue"
    continue
  fi

  status_code="$(curl -sS -o /dev/null -w "%{http_code}" -u "$RABBITMQ_USER:$RABBITMQ_PASSWORD" -X DELETE "$endpoint")"
  if [ "$status_code" = "204" ]; then
    echo "Purged queue: $queue"
    PURGED=$((PURGED + 1))
  else
    echo "Failed to purge queue: $queue (HTTP $status_code)" >&2
    FAILED=$((FAILED + 1))
  fi
done

if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry-run completed."
  exit 0
fi

echo "Done. Purged: $PURGED, Failed: $FAILED"

if [ "$FAILED" -gt 0 ]; then
  exit 1
fi

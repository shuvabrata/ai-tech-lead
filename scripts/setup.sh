#!/usr/bin/env bash
# =============================================================================
# setup.sh — First-time setup wizard for Work Behavior Analytics AI
#
# Usage:
#   ./setup.sh        Interactive guided wizard
#
# Every setting is prompted with a sensible default (press Enter to accept).
# The script is idempotent: it never overwrites an existing .env unless the
# user explicitly chooses to reset, and already-set values are offered as the
# pre-filled answer on re-runs.
# =============================================================================

set -euo pipefail

# ── Colour helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Colour

info()    { printf "${CYAN}ℹ${NC}  %s\n" "$*"; }
success() { printf "${GREEN}✓${NC}  %s\n" "$*"; }
warn()    { printf "${YELLOW}⚠${NC}  %s\n" "$*"; }
error()   { printf "${RED}✗${NC}  %s\n" "$*"; }
heading() { printf "\n${BOLD}${CYAN}%s${NC}\n" "$*"; }

# ── Paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_EXAMPLE="${PROJECT_DIR}/.env.example"
ENV_FILE="${PROJECT_DIR}/.env"

# ── Default values for mandatory settings ───────────────────────────────────
DEFAULT_POSTGRES_USER="postgres"
DEFAULT_POSTGRES_PASSWORD="postgres"
DEFAULT_POSTGRES_DB="postgres"
DEFAULT_NEO4J_USERNAME="neo4j"
DEFAULT_NEO4J_PASSWORD="password"
DEFAULT_RABBITMQ_USER="guest"
DEFAULT_RABBITMQ_PASSWORD="guest"

# ── Optional settings that get commented out when skipped ───────────────────
# These are the keys the script prompts for.  When the user skips, the line
# is written commented-out so the app never sees it but a human gets a hint.
OPTIONAL_KEYS=("OPENAI_API_KEY" "GITHUB_MCP_TOKEN")

usage() {
    cat <<EOF
Usage: $0

First-time setup wizard for Work Behavior Analytics AI.
Creates a working .env from .env.example and optionally starts the app.

Every prompt accepts a value or Enter to accept the suggested default.
EOF
    exit 0
}

# ── Prerequisite checks ─────────────────────────────────────────────────────
heading "Work Behavior Analytics AI — Setup"

if ! command -v docker &>/dev/null; then
    error "Docker is not installed or not on PATH."
    error "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi
success "Docker found: $(docker --version)"

if ! docker compose version &>/dev/null; then
    error "Docker Compose (v2) is not available."
    error "Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi
success "Docker Compose found: $(docker compose version --short 2>/dev/null || echo 'v2')"

if ! command -v python3 &>/dev/null; then
    error "Python 3 is required to generate the encryption key."
    error "Please install Python 3: https://www.python.org/downloads/"
    exit 1
fi
success "Python 3 found: $(python3 --version)"

if [[ ! -f "$ENV_EXAMPLE" ]]; then
    error ".env.example not found at $ENV_EXAMPLE"
    exit 1
fi

# ── Handle existing .env ────────────────────────────────────────────────────
RESET_ENV=false

if [[ -f "$ENV_FILE" ]]; then
    heading "Existing .env detected"
    echo ""
    echo "  An existing .env file was found."
    echo "  [k] Keep it (only fill missing/FIXME values)"
    echo "  [r] Reset — regenerate from .env.example (loses custom values)"
    echo ""
    read -r -p "  Your choice [k]: " CHOICE
    CHOICE="${CHOICE:-k}"
    if [[ "$CHOICE" == "r" || "$CHOICE" == "R" ]]; then
        RESET_ENV=true
        warn "Resetting .env — a backup will be saved to .env.bak"
        cp "$ENV_FILE" "${ENV_FILE}.bak"
    else
        info "Keeping existing .env — only filling missing/FIXME values"
    fi
else
    RESET_ENV=true
    info "No .env found — creating from .env.example"
fi

# ── Generate Fernet key ─────────────────────────────────────────────────────
generate_fernet_key() {
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null
}

# ── Create / reset .env ─────────────────────────────────────────────────────
if $RESET_ENV; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
fi

# ── Helper: read the current value of a key (empty if absent) ───────────────
get_env_value() {
    local key="$1"
    local file="$2"
    # Match only active (uncommented) lines: KEY=value
    sed -n "s|^${key}=||p" "$file" | head -n 1
}

# ── Helper: prompt for a value, defaulting to the given fallback ────────────
# Prints the user's answer (or the fallback when they press Enter).
prompt_for_value() {
    local label="$1"
    local fallback="$2"

    local answer
    read -r -p "  ${label} [${fallback}]: " answer
    if [[ -z "$answer" ]]; then
        echo "$fallback"
    else
        echo "$answer"
    fi
}

# ── Helper: true when a value is a placeholder (FIXME/fixme/empty) ──────────
is_placeholder() {
    local value="$1"
    [[ -z "$value" || "$value" == "FIXME" || "$value" == "fixme" || "$value" == *FIXME* || "$value" == *fixme* ]]
}

# ── Helper: set a value in .env (always overwrites) ─────────────────────────
set_env_value() {
    local key="$1"
    local value="$2"
    local file="$3"

    if grep -q "^${key}=" "$file"; then
        # Replace existing line (handles FIXME and already-set values)
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|^${key}=.*|${key}=${value}|" "$file"
        else
            sed -i "s|^${key}=.*|${key}=${value}|" "$file"
        fi
    else
        echo "${key}=${value}" >> "$file"
    fi
}

# ── Helper: set a value only if currently a placeholder (FIXME/empty) ───────
set_env_value_if_unset() {
    local key="$1"
    local value="$2"
    local file="$3"

    local current
    current="$(get_env_value "$key" "$file")"
    if is_placeholder "$current"; then
        set_env_value "$key" "$value" "$file"
    fi
}

# ── Helper: comment out a line in .env ──────────────────────────────────────
comment_out_key() {
    local key="$1"
    local file="$2"

    if grep -q "^${key}=" "$file"; then
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|^${key}=|# ${key}=|" "$file"
        else
            sed -i "s|^${key}=|# ${key}=|" "$file"
        fi
    fi
}

# ── Helper: comment out a key only if its value is a placeholder ────────────
# Preserves any real value the user has already set.
comment_out_if_placeholder() {
    local key="$1"
    local file="$2"

    local current
    current="$(get_env_value "$key" "$file")"
    if is_placeholder "$current"; then
        comment_out_key "$key" "$file"
    fi
}

# ── Helper: uncomment a line in .env ────────────────────────────────────────
uncomment_key() {
    local key="$1"
    local file="$2"

    if grep -q "^# ${key}=" "$file"; then
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|^# ${key}=|${key}=|" "$file"
        else
            sed -i "s|^# ${key}=|${key}=|" "$file"
        fi
    fi
}

# ── Configure mandatory settings ───────────────────────────────────────────
heading "Mandatory settings"
echo ""
echo "  Press Enter to accept the suggested value, or type a custom value."
echo ""

# Resolve a value for a mandatory key: prefer the existing value when it is
# already set (so re-runs re-offer it), otherwise use the provided default.
resolve_mandatory() {
    local key="$1"
    local default="$2"

    local current
    current="$(get_env_value "$key" "$ENV_FILE")"
    if is_placeholder "$current"; then
        echo "$default"
    else
        echo "$current"
    fi
}

info "PostgreSQL credentials"
PG_USER="$(prompt_for_value "PostgreSQL user" "$(resolve_mandatory "POSTGRES_USER" "$DEFAULT_POSTGRES_USER")")"
PG_PASS="$(prompt_for_value "PostgreSQL password" "$(resolve_mandatory "POSTGRES_PASSWORD" "$DEFAULT_POSTGRES_PASSWORD")")"
PG_DB="$(prompt_for_value "PostgreSQL database" "$(resolve_mandatory "POSTGRES_DB" "$DEFAULT_POSTGRES_DB")")"
set_env_value "POSTGRES_USER" "$PG_USER" "$ENV_FILE"
set_env_value "POSTGRES_PASSWORD" "$PG_PASS" "$ENV_FILE"
set_env_value "POSTGRES_DB" "$PG_DB" "$ENV_FILE"
set_env_value "DATABASE_URL" "postgresql+asyncpg://${PG_USER}:${PG_PASS}@postgres:5432/${PG_DB}" "$ENV_FILE"
echo ""

info "Neo4j credentials"
NEO4J_USER="$(prompt_for_value "Neo4j username" "$(resolve_mandatory "NEO4J_USERNAME" "$DEFAULT_NEO4J_USERNAME")")"
NEO4J_PASS="$(prompt_for_value "Neo4j password" "$(resolve_mandatory "NEO4J_PASSWORD" "$DEFAULT_NEO4J_PASSWORD")")"
set_env_value "NEO4J_USERNAME" "$NEO4J_USER" "$ENV_FILE"
set_env_value "NEO4J_PASSWORD" "$NEO4J_PASS" "$ENV_FILE"
echo ""

info "RabbitMQ credentials"
RABBIT_USER="$(prompt_for_value "RabbitMQ user" "$(resolve_mandatory "RABBITMQ_USER" "$DEFAULT_RABBITMQ_USER")")"
RABBIT_PASS="$(prompt_for_value "RabbitMQ password" "$(resolve_mandatory "RABBITMQ_PASSWORD" "$DEFAULT_RABBITMQ_PASSWORD")")"
set_env_value "RABBITMQ_USER" "$RABBIT_USER" "$ENV_FILE"
set_env_value "RABBITMQ_PASSWORD" "$RABBIT_PASS" "$ENV_FILE"
echo ""

# Elasticsearch security is disabled (xpack.security.enabled=false in the
# compose file), so no password is needed.  Prompt with empty default.
echo ""
info "Elasticsearch password (security is disabled in Docker Compose)"
ES_PASS="$(prompt_for_value "Elasticsearch password (leave empty)" "$(resolve_mandatory "ELASTIC_PASSWORD" "")")"
set_env_value "ELASTIC_PASSWORD" "$ES_PASS" "$ENV_FILE"

# LLM model — defaults to gpt-5 in the app, but prompt so the user can
# choose a different model (e.g. gpt-4o, gpt-4-turbo).
echo ""
info "LLM model"
LLM_MODEL_VAL="$(prompt_for_value "LLM model" "$(resolve_mandatory "LLM_MODEL" "gpt-5-mini")")"
set_env_value "LLM_MODEL" "$LLM_MODEL_VAL" "$ENV_FILE"

# Generate the encryption key only if it is not already set (a re-run must
# not rotate the key, or existing encrypted connector secrets would break).
info "Checking connector encryption key..."
if is_placeholder "$(get_env_value "CONNECTOR_ENCRYPTION_KEY" "$ENV_FILE")"; then
    FERNET_KEY=$(generate_fernet_key)
    if [[ -z "$FERNET_KEY" ]]; then
        error "Failed to generate Fernet key. Is 'cryptography' installed?"
        error "Run: pip install cryptography"
        exit 1
    fi
    set_env_value "CONNECTOR_ENCRYPTION_KEY" "$FERNET_KEY" "$ENV_FILE"
    success "Encryption key generated"
else
    info "Encryption key already set — preserving it"
fi

# ── Optional prompts ────────────────────────────────────────────────────────
heading "Optional settings"

# ── GitHub token ────────────────────────────────────────────────────────────
echo ""
echo "  GitHub Personal Access Token"
echo "  ─────────────────────────────"
echo "  Needed for GitHub MCP server (AI-powered GitHub queries)."
echo "  Create one at: https://github.com/settings/tokens"
echo "  Scopes needed: read:org, repo"
echo ""
read -r -p "  GitHub token (press Enter to skip): " INPUT_TOKEN
if [[ -n "$INPUT_TOKEN" ]]; then
    uncomment_key "GITHUB_MCP_TOKEN" "$ENV_FILE"
    set_env_value "GITHUB_MCP_TOKEN" "$INPUT_TOKEN" "$ENV_FILE"
    success "GitHub MCP token set"
else
    info "Skipped — GitHub MCP token left as-is in .env"
    comment_out_if_placeholder "GITHUB_MCP_TOKEN" "$ENV_FILE"
fi

# ── OpenAI key ──────────────────────────────────────────────────────────────
echo ""
echo "  OpenAI API Key"
echo "  ──────────────"
echo "  Needed for the AI Chat feature."
echo "  Get one at: https://platform.openai.com/api-keys"
echo ""
read -r -p "  OpenAI API key (press Enter to skip): " INPUT_KEY
if [[ -n "$INPUT_KEY" ]]; then
    uncomment_key "OPENAI_API_KEY" "$ENV_FILE"
    set_env_value "OPENAI_API_KEY" "$INPUT_KEY" "$ENV_FILE"
    success "OpenAI API key set"
else
    info "Skipped — OpenAI API key left as-is in .env"
    comment_out_if_placeholder "OPENAI_API_KEY" "$ENV_FILE"
fi

# ── Summary ─────────────────────────────────────────────────────────────────
heading "Setup complete"
echo ""
echo "  .env file:  $ENV_FILE"
echo ""
echo "  Quick reference:"
echo "    • Database:       ${PG_USER}:${PG_PASS}@postgres:5432/${PG_DB}"
echo "    • Neo4j:          ${NEO4J_USER} / ${NEO4J_PASS}  (bolt://neo4j:7687)"
echo "    • RabbitMQ:       ${RABBIT_USER} / ${RABBIT_PASS}      (mgmt UI: http://localhost:15672)"
echo "    • LLM model:      ${LLM_MODEL_VAL}"
echo "    • Encryption key: auto-generated"
echo ""

# ── Offer to start ──────────────────────────────────────────────────────────
echo ""
read -r -p "  Start the application now? (docker compose up -d) [Y/n]: " START
START="${START:-y}"

if [[ "$START" != "y" && "$START" != "Y" ]]; then
    echo ""
    info "To start later, run:"
    echo "    docker compose up -d"
    echo ""
    echo "  Then open: http://localhost:8000/app"
    exit 0
fi

# ── Start Docker Compose ────────────────────────────────────────────────────
heading "Starting services (docker compose up -d)"
echo ""

cd "$PROJECT_DIR"
docker compose up -d

echo ""
info "Waiting for the app to become healthy..."
echo "  (This may take a minute on first run — images are being pulled and built.)"
echo ""

# Wait for the app healthcheck to pass (up to 5 minutes)
MAX_WAIT=300
ELAPSED=0
INTERVAL=5

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    if curl -sf http://localhost:8000/api/health &>/dev/null; then
        echo ""
        success "Application is healthy!"
        echo ""
        echo "  ${BOLD}Open:${NC}  http://localhost:8000/app"
        echo ""
        exit 0
    fi
    printf "."
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

echo ""
warn "App did not become healthy within ${MAX_WAIT}s."
echo ""
echo "  Check logs:  docker compose logs app"
echo "  Check status: docker compose ps"
echo ""
echo "  Once healthy, open: http://localhost:8000/app"
exit 1
#!/usr/bin/env bash
# =============================================================================
# SLO Recommendation Engine - Demo Setup Script
# Sets up everything needed to run the Streamlit interactive demo.
# =============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'

info()    { echo -e "${YELLOW}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
fail()    { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

DB_URL="postgresql+asyncpg://slo_user:slo_password_dev@localhost:5432/slo_engine"
PSQL_URL="postgresql://slo_user:slo_password_dev@localhost:5432/slo_engine"
API_KEY_RAW="demo-api-key-for-testing"

echo ""
echo -e "${BOLD}${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║   SLO Recommendation Engine — Demo Setup         ║${NC}"
echo -e "${BOLD}${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: Start Docker services ──────────────────────────────────
info "Step 1/5: Starting Docker services..."
if ! command -v docker &>/dev/null; then
    fail "Docker is not installed. Please install Docker first."
fi

docker compose up -d --build
success "Docker services started"

# ── Step 2: Wait for Postgres to be ready ──────────────────────────
info "Step 2/5: Waiting for PostgreSQL to be ready..."
RETRIES=30
until docker compose exec -T db pg_isready -U slo_user -d slo_engine &>/dev/null; do
    RETRIES=$((RETRIES - 1))
    if [ $RETRIES -le 0 ]; then
        fail "PostgreSQL did not become ready in time."
    fi
    sleep 1
done
success "PostgreSQL is ready"

# ── Step 3: Run Alembic migrations ─────────────────────────────────
info "Step 3/5: Running database migrations..."
DATABASE_URL="$DB_URL" alembic upgrade head
success "Migrations applied"

# ── Step 4: Seed demo API key ──────────────────────────────────────
info "Step 4/5: Creating demo API key..."

# Generate bcrypt hash at runtime using the project's Python environment
API_KEY_HASH=$(.venv/bin/python -c "
import bcrypt
h = bcrypt.hashpw(b'${API_KEY_RAW}', bcrypt.gensalt(12))
print(h.decode())
")

# Use psql inside the container to avoid local psql dependency
docker compose exec -T db psql -U slo_user -d slo_engine -c "
  INSERT INTO api_keys (id, name, key_hash, created_by, is_active)
  VALUES (gen_random_uuid(), 'demo', '${API_KEY_HASH}', 'demo-setup', true)
  ON CONFLICT (name) DO UPDATE SET key_hash = EXCLUDED.key_hash;
" >/dev/null 2>&1

success "API key ready"

# ── Step 5: Install Python demo dependencies ───────────────────────
info "Step 5/5: Installing demo Python dependencies..."
uv sync --extra demo
success "Dependencies installed"

# ── Wait for API to be healthy ─────────────────────────────────────
info "Waiting for API to be healthy..."
RETRIES=30
until curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; do
    RETRIES=$((RETRIES - 1))
    if [ $RETRIES -le 0 ]; then
        fail "API did not become healthy in time. Check: docker compose logs app"
    fi
    sleep 2
done
success "API is healthy"

# ── Done ───────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║   Setup Complete!                                 ║${NC}"
echo -e "${BOLD}${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Run the demo:"
echo -e "    ${BOLD}streamlit run scripts/streamlit_demo.py${NC}"
echo ""
echo -e "  API Key (paste into sidebar):"
echo -e "    ${BOLD}${API_KEY_RAW}${NC}"
echo ""
echo -e "  Useful URLs:"
echo -e "    API:        http://localhost:8000"
echo -e "    Swagger UI: http://localhost:8000/docs"
echo -e "    Prometheus: http://localhost:9090"
echo ""

# Interactive Streamlit Demo

Visual, interactive walkthrough of the SLO Recommendation Engine features (FR-1 through FR-7).

## Quick Start (one command)

```bash
./scripts/setup_demo.sh
```

This script handles everything:
1. Starts Docker services (API, PostgreSQL, Redis, Prometheus)
2. Waits for PostgreSQL to be ready
3. Runs database migrations
4. Seeds a demo API key
5. Installs Python demo dependencies

Once complete, run:

```bash
streamlit run scripts/streamlit_demo.py
```

Paste the API key shown by the setup script into the sidebar (`demo-api-key-for-testing`).

## Prerequisites

- **Docker** (with `docker compose`)
- **Python 3.12+**
- **uv** (Python package manager) -- install with `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Manual Setup (if you prefer step-by-step)

```bash
# 1. Start services
docker compose up -d --build

# 2. Wait for DB, then run migrations
DATABASE_URL="postgresql+asyncpg://slo_user:slo_password_dev@localhost:5432/slo_engine" \
  alembic upgrade head

# 3. Create a demo API key in the database
#    Generate the bcrypt hash first:
API_KEY_HASH=$(.venv/bin/python -c "import bcrypt; print(bcrypt.hashpw(b'demo-api-key-for-testing', bcrypt.gensalt(12)).decode())")
docker compose exec db psql -U slo_user -d slo_engine -c "
  INSERT INTO api_keys (id, name, key_hash, created_by, is_active)
  VALUES (gen_random_uuid(), 'demo', '${API_KEY_HASH}', 'demo-setup', true)
  ON CONFLICT (name) DO UPDATE SET key_hash = EXCLUDED.key_hash;"

# 4. Install demo dependencies
uv sync --extra demo

# 5. Run the demo
streamlit run scripts/streamlit_demo.py
```

API key to use: `demo-api-key-for-testing`

## Demo Walkthrough

The app has 7 steps -- work through them sequentially:

| Step | Feature | What it does |
|------|---------|--------------|
| 1 | FR-1: Ingest Graph | Ingests 8 services and 10 dependency edges |
| 2 | FR-1: Query Subgraph | Queries and visualizes the dependency graph |
| 3 | FR-2 + FR-7: Recommendations | Generates 3-tier SLO recommendations with explainability |
| 4 | FR-5: Accept SLO | Accepts a recommendation as the active SLO |
| 5 | FR-5: Modify SLO | Modifies an active SLO target |
| 6 | FR-4: Impact Analysis | Analyzes upstream impact of a proposed SLO change |
| 7 | FR-5: Audit History | Views the full audit trail of SLO lifecycle actions |

## Teardown

```bash
docker compose down        # Stop services (keeps data)
docker compose down -v     # Stop services and delete all data
```

After `docker compose down -v`, you'll need to run `./scripts/setup_demo.sh` again.

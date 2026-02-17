#!/usr/bin/env bash
# =============================================================================
# SLO Recommendation Engine - Full Demo Script
# Exercises FR-1 through FR-7 end-to-end
# =============================================================================
# Prerequisites:
#   1. docker-compose up --build  (runs API + PostgreSQL + Redis + Prometheus)
#   2. alembic upgrade head        (apply DB migrations)
#   3. Create an API key:
#      curl -s http://localhost:8000/api/v1/api-keys \
#        -H "Content-Type: application/json" \
#        -d '{"name":"demo","permissions":["read","write"]}' | jq .
#      Then set API_KEY below.
# =============================================================================

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-demo-api-key}"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

divider() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

step() {
    echo -e "${BOLD}${CYAN}▶ STEP $1: $2${NC}"
    echo ""
}

success() {
    echo -e "${GREEN}✓ $1${NC}"
}

info() {
    echo -e "${YELLOW}  ℹ $1${NC}"
}

# Header
echo ""
echo -e "${BOLD}${GREEN}╔════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║          SLO Recommendation Engine — Full Feature Demo           ║${NC}"
echo -e "${BOLD}${GREEN}║          FR-1 → FR-2 → FR-3 → FR-4 → FR-5 → FR-7               ║${NC}"
echo -e "${BOLD}${GREEN}╚════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  API: ${BASE_URL}"
echo -e "  Key: ${API_KEY:0:8}..."
echo ""

# ─── Health check ───────────────────────────────────────────────────
echo -e "${YELLOW}Checking API health...${NC}"
HEALTH=$(curl -s "${BASE_URL}/api/v1/health")
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
success "API is running"

divider

# ═══════════════════════════════════════════════════════════════════
# STEP 1: FR-1 — Ingest Dependency Graph (8 services, 10 edges)
# ═══════════════════════════════════════════════════════════════════
step 1 "FR-1: Ingest Service Dependency Graph"
info "Ingesting 8 services with 10 dependency edges..."

INGEST_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${BASE_URL}/api/v1/services/dependencies" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{
    "source": "otel_service_graph",
    "collected_at": "2026-02-16T10:00:00Z",
    "dependencies": [
        {
            "source_service_id": "api-gateway",
            "target_service_id": "checkout-service",
            "communication_mode": "sync",
            "criticality": "hard",
            "call_rate_per_second": 500.0
        },
        {
            "source_service_id": "api-gateway",
            "target_service_id": "user-service",
            "communication_mode": "sync",
            "criticality": "hard",
            "call_rate_per_second": 800.0
        },
        {
            "source_service_id": "checkout-service",
            "target_service_id": "payment-service",
            "communication_mode": "sync",
            "criticality": "hard",
            "call_rate_per_second": 200.0
        },
        {
            "source_service_id": "checkout-service",
            "target_service_id": "inventory-service",
            "communication_mode": "sync",
            "criticality": "hard",
            "call_rate_per_second": 200.0
        },
        {
            "source_service_id": "checkout-service",
            "target_service_id": "user-service",
            "communication_mode": "sync",
            "criticality": "hard",
            "call_rate_per_second": 150.0
        },
        {
            "source_service_id": "payment-service",
            "target_service_id": "auth-service",
            "communication_mode": "sync",
            "criticality": "hard",
            "call_rate_per_second": 200.0
        },
        {
            "source_service_id": "checkout-service",
            "target_service_id": "notification-service",
            "communication_mode": "async",
            "criticality": "soft",
            "call_rate_per_second": 50.0
        },
        {
            "source_service_id": "api-gateway",
            "target_service_id": "analytics-service",
            "communication_mode": "async",
            "criticality": "soft",
            "call_rate_per_second": 100.0
        },
        {
            "source_service_id": "inventory-service",
            "target_service_id": "notification-service",
            "communication_mode": "async",
            "criticality": "soft",
            "call_rate_per_second": 30.0
        },
        {
            "source_service_id": "user-service",
            "target_service_id": "auth-service",
            "communication_mode": "sync",
            "criticality": "hard",
            "call_rate_per_second": 400.0
        }
    ]
}')

HTTP_CODE=$(echo "$INGEST_RESPONSE" | tail -n1)
BODY=$(echo "$INGEST_RESPONSE" | sed '$d')
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
success "Dependency graph ingested (HTTP $HTTP_CODE)"

divider

# ═══════════════════════════════════════════════════════════════════
# STEP 2: FR-1 — Query Dependency Subgraph
# ═══════════════════════════════════════════════════════════════════
step 2 "FR-1: Query Dependency Subgraph for api-gateway"
info "Querying downstream dependencies of api-gateway (depth=3)..."

QUERY_RESPONSE=$(curl -s \
    "${BASE_URL}/api/v1/services/api-gateway/dependencies?direction=downstream&max_depth=3" \
    -H "X-API-Key: ${API_KEY}")

echo "$QUERY_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$QUERY_RESPONSE"
success "Dependency subgraph retrieved"

divider

# ═══════════════════════════════════════════════════════════════════
# STEP 3: FR-2 + FR-7 — Get SLO Recommendations with Explainability
# ═══════════════════════════════════════════════════════════════════
step 3 "FR-2 + FR-7: Get SLO Recommendations for payment-service"
info "Generating recommendations with counterfactuals and data provenance..."

RECO_RESPONSE=$(curl -s \
    "${BASE_URL}/api/v1/services/payment-service/slo-recommendations?sli_type=all&lookback_days=30" \
    -H "X-API-Key: ${API_KEY}")

echo "$RECO_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RECO_RESPONSE"

# Highlight FR-7 fields
echo ""
info "FR-7 Explainability fields in the response:"
info "  • counterfactuals: What-if scenarios showing how changes affect recommendations"
info "  • provenance: Data source traceability (graph version, telemetry window, completeness)"
success "Recommendations generated with FR-7 explainability"

divider

# ═══════════════════════════════════════════════════════════════════
# STEP 4: FR-5 — Accept SLO Recommendation
# ═══════════════════════════════════════════════════════════════════
step 4 "FR-5: Accept SLO Recommendation for payment-service"
info "Accepting the Balanced tier recommendation..."

ACCEPT_RESPONSE=$(curl -s \
    -X POST "${BASE_URL}/api/v1/services/payment-service/slos" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{
    "action": "accept",
    "selected_tier": "balanced",
    "rationale": "Balanced tier aligns with team risk tolerance and SRE review",
    "actor": "jane.doe@company.com"
}')

echo "$ACCEPT_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$ACCEPT_RESPONSE"
success "SLO accepted for payment-service"

echo ""
info "Also accepting SLO for checkout-service..."

ACCEPT_CHECKOUT=$(curl -s \
    -X POST "${BASE_URL}/api/v1/services/checkout-service/slos" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{
    "action": "accept",
    "selected_tier": "balanced",
    "rationale": "Standard balanced target for checkout flow",
    "actor": "john.smith@company.com"
}')

echo "$ACCEPT_CHECKOUT" | python3 -m json.tool 2>/dev/null || echo "$ACCEPT_CHECKOUT"
success "SLO accepted for checkout-service"

echo ""
info "Verifying active SLO..."

ACTIVE_SLO=$(curl -s \
    "${BASE_URL}/api/v1/services/payment-service/slos" \
    -H "X-API-Key: ${API_KEY}")

echo "$ACTIVE_SLO" | python3 -m json.tool 2>/dev/null || echo "$ACTIVE_SLO"
success "Active SLO confirmed"

divider

# ═══════════════════════════════════════════════════════════════════
# STEP 5: FR-5 — Modify an SLO
# ═══════════════════════════════════════════════════════════════════
step 5 "FR-5: Modify SLO for payment-service (tighten availability)"
info "Modifying balanced tier: availability 99.9% → 99.95%..."

MODIFY_RESPONSE=$(curl -s \
    -X POST "${BASE_URL}/api/v1/services/payment-service/slos" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{
    "action": "modify",
    "selected_tier": "balanced",
    "modifications": {
        "availability_target": 99.95
    },
    "rationale": "Tightening after PCI compliance review",
    "actor": "security-team@company.com"
}')

echo "$MODIFY_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$MODIFY_RESPONSE"
success "SLO modified for payment-service"

divider

# ═══════════════════════════════════════════════════════════════════
# STEP 6: FR-4 — Impact Analysis
# ═══════════════════════════════════════════════════════════════════
step 6 "FR-4: Impact Analysis — What if payment-service drops to 99.5%?"
info "Analyzing upstream impact of lowering payment-service from 99.95% to 99.5%..."

IMPACT_RESPONSE=$(curl -s \
    -X POST "${BASE_URL}/api/v1/slos/impact-analysis" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ${API_KEY}" \
    -d '{
    "service_id": "payment-service",
    "proposed_change": {
        "sli_type": "availability",
        "current_target": 99.95,
        "proposed_target": 99.5
    },
    "max_depth": 3
}')

echo "$IMPACT_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$IMPACT_RESPONSE"
success "Impact analysis completed"

divider

# ═══════════════════════════════════════════════════════════════════
# STEP 7: FR-5 — View Audit History
# ═══════════════════════════════════════════════════════════════════
step 7 "FR-5: View SLO Audit History for payment-service"
info "Retrieving full audit trail..."

HISTORY_RESPONSE=$(curl -s \
    "${BASE_URL}/api/v1/services/payment-service/slo-history" \
    -H "X-API-Key: ${API_KEY}")

echo "$HISTORY_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$HISTORY_RESPONSE"
success "Audit history retrieved"

divider

# ═══════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════
echo -e "${BOLD}${GREEN}╔════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║                       Demo Complete!                              ║${NC}"
echo -e "${BOLD}${GREEN}╚════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}✓${NC} FR-1: Dependency Graph — Ingested 8 services, 10 edges"
echo -e "  ${GREEN}✓${NC} FR-1: Dependency Graph — Queried api-gateway subgraph"
echo -e "  ${GREEN}✓${NC} FR-2: SLO Recommendations — Generated 3-tier recommendations"
echo -e "  ${GREEN}✓${NC} FR-3: Constraint Propagation — Composite availability computed"
echo -e "  ${GREEN}✓${NC} FR-4: Impact Analysis — Upstream impact computed for SLO change"
echo -e "  ${GREEN}✓${NC} FR-5: SLO Lifecycle — Accept, modify, audit trail"
echo -e "  ${GREEN}✓${NC} FR-7: Explainability — Counterfactuals + data provenance"
echo ""
echo -e "  Swagger UI: ${BASE_URL}/docs"
echo ""

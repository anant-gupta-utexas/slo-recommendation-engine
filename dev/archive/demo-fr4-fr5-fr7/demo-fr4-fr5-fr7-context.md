# Demo FR-4 + FR-5 + FR-7 — Context

## Key Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Active SLO storage | In-memory dict (no DB) | Demo prototype; avoids migration complexity |
| Audit log storage | In-memory list (no DB) | Append-only list sufficient for demo |
| FR-4 SLO lookup | In-memory store, fallback to recommendation balanced tier | Supports both accepted and new services |
| FR-4 direction | Upstream only | Core demo use case |
| FR-4 latency | Qualitative note, no math propagation | Percentiles are non-additive |
| FR-4 persistence | Stateless / compute-only | No need to persist analysis results |
| FR-4 SCC handling | Supernode with weakest-link | Simple approach for demo |
| FR-4 depth | Configurable via API, default 3, max 10 | Flexible for different graph sizes |
| FR-7 counterfactuals | Top-3 features, perturb +/- one step | Lightweight; no ML needed |
| Telemetry source | Reuse MockPrometheusClient | Consistent with FR-2 |
| Testing | Minimal smoke tests only | Demo priority over coverage |

## Key Files Created

### FR-5 (Recommendation Lifecycle)
- `src/domain/entities/active_slo.py` — ActiveSlo + SloAuditEntry entities
- `src/infrastructure/stores/in_memory_slo_store.py` — In-memory store
- `src/application/dtos/slo_lifecycle_dto.py` — Request/response DTOs
- `src/application/use_cases/manage_slo_lifecycle.py` — Accept/modify/reject logic
- `src/infrastructure/api/schemas/slo_lifecycle_schema.py` — Pydantic models
- `src/infrastructure/api/routes/slo_lifecycle.py` — API routes

### FR-4 (Impact Analysis)
- `src/domain/entities/impact_analysis.py` — Domain entities
- `src/domain/services/impact_analysis_service.py` — Core computation
- `src/application/dtos/impact_analysis_dto.py` — DTOs
- `src/application/use_cases/run_impact_analysis.py` — Orchestration
- `src/infrastructure/api/schemas/impact_analysis_schema.py` — Pydantic models
- `src/infrastructure/api/routes/impact_analysis.py` — API route

### FR-7 (Explainability)
- `src/domain/services/counterfactual_service.py` — Counterfactual generation

### Key Files Modified
- `src/domain/entities/slo_recommendation.py` — Added Counterfactual + DataProvenance
- `src/application/dtos/slo_recommendation_dto.py` — Added CounterfactualDTO + DataProvenanceDTO
- `src/application/use_cases/generate_slo_recommendation.py` — Integrated counterfactuals
- `src/infrastructure/api/schemas/slo_recommendation_schema.py` — Added API models
- `src/infrastructure/api/routes/recommendations.py` — Map new fields
- `src/infrastructure/api/main.py` — Registered new routers
- `src/infrastructure/telemetry/seed_data.py` — Added 4 new services

### Demo
- `demo/streamlit_demo.py` — Interactive Streamlit demo application
- `demo/setup_demo.sh` — Setup script for demo environment
- `demo/DEMO_README.md` — Demo documentation and instructions

## Dependencies
- FR-5 must be built first (FR-4 reads from in-memory SLO store)
- FR-7 extends FR-2 (modifies existing recommendation pipeline)
- FR-4 depends on FR-1 (graph traversal) + FR-2 (telemetry) + FR-5 (active SLOs)

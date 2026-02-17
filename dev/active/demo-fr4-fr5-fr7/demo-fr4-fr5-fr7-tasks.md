# Demo FR-4 + FR-5 + FR-7 — Task Checklist

## Phase 1: FR-5 Recommendation Lifecycle
- [x] Create `ActiveSlo` and `SloAuditEntry` domain entities
- [x] Create in-memory SLO store
- [x] Create lifecycle DTOs (request/response)
- [x] Create `ManageSloLifecycleUseCase`
- [x] Create Pydantic schemas for API
- [x] Create API routes: POST /{id}/slos, GET /{id}/slos, GET /{id}/slo-history
- [x] Register router in main.py

## Phase 2: FR-4 Impact Analysis
- [x] Create `ImpactedService` and `ImpactAnalysisResult` domain entities
- [x] Create `ImpactAnalysisService` domain service
- [x] Create impact analysis DTOs
- [x] Create `RunImpactAnalysisUseCase`
- [x] Create Pydantic schemas for API
- [x] Create API route: POST /api/v1/slos/impact-analysis
- [x] Wire DI + register router

## Phase 3: FR-7 Explainability Enhancement
- [x] Create `CounterfactualService` domain service
- [x] Add `Counterfactual` and `DataProvenance` to slo_recommendation.py
- [x] Extend `Explanation` entity with counterfactuals + provenance
- [x] Add `CounterfactualDTO` and `DataProvenanceDTO` to recommendation DTOs
- [x] Integrate counterfactual service into `GenerateSloRecommendationUseCase`
- [x] Add counterfactual + provenance Pydantic models to recommendation schema
- [x] Update recommendation API route to include new fields

## Phase 4: Demo Script + Seed Data
- [x] Add api-gateway, checkout-service, user-service, inventory-service to seed data
- [x] Create `scripts/demo.sh` end-to-end demo script
- [ ] Manual smoke test via docker-compose up + demo.sh

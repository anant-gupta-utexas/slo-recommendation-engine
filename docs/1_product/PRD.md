# Product Requirements Document (PRD)

## Overview

**Product Name:** SLO Recommendation Engine

An AI-assisted system that analyzes metrics, telemetry, and structural dependencies across interconnected microservices to recommend appropriate Service Level Objectives (SLOs) for each service. The system accounts for upstream/downstream dependencies, datastores, external APIs, and infrastructure components — moving organizations from static, manually-configured reliability targets to dynamic, dependency-aware objectives.

The engine exposes a REST API designed for integration into an internal developer platform (e.g., Spotify's Backstage) where engineering teams manage their services, deployments, and operational data.

**Automation Philosophy:** The system launches in a **semi-automated (human-on-the-loop)** mode where all recommendations require explicit SRE/team approval, with a clear graduation path to full automation as the system builds a track record of accurate, trusted recommendations.

---

## Problem Statement

### The Core Problem

In modern cloud-native organizations operating at scale (500+ microservices), setting and maintaining SLOs is a manual, error-prone process that fails to account for the interconnected nature of distributed systems. Specifically:

1. **Manual SLO setting is unsustainable at scale.** Engineering teams set SLOs based on intuition or copy-paste from similar services, without systematic analysis of historical performance data or dependency constraints. With hundreds of services, this process cannot keep pace with topology changes.

2. **Dependencies are invisible in SLO decisions.** A checkout service depending on an unreliable external payment API inherits that unreliability, yet its SLO is often set independently. When the payment API consumes 50% of the checkout path's error budget, the SLO was unrealistic from the start.

3. **Cascading failures are not modeled.** Serial dependencies compound unavailability multiplicatively (e.g., four services at 99.9% each yield ~99.6% composite), but current SLO-setting practices treat services in isolation.

4. **SLOs become stale.** Code deployments, traffic growth, infrastructure changes, and seasonal patterns continuously shift performance baselines. Static SLOs become dangerously misaligned within weeks, leading to either meaningless targets (too loose) or constant alert fatigue (too tight).

5. **Latency composition is non-linear.** Tail latency (p99) does not add linearly across call chains — it amplifies. Five parallel calls each with p99 < 100ms yield only a 95% chance all finish under 100ms. Teams setting latency SLOs without modeling this create unachievable targets.

### The Opportunity

By combining dependency graph analysis, historical telemetry, and ML-driven forecasting, the system can recommend SLOs that are mathematically grounded, dependency-aware, and continuously adapted — transforming reliability from a reactive burden into a proactive, data-driven practice.

---

## Goals and Objectives

### Primary Goals

| Goal | Description | Key Metric |
|------|-------------|------------|
| **Dependency-Aware SLOs** | Every SLO recommendation accounts for the service's position in the dependency graph, including upstream/downstream constraints and external API reliability | 100% of recommendations include dependency impact analysis |
| **Reduce SLO Violations** | Recommend achievable targets grounded in historical performance, reducing breach frequency from poorly set SLOs | Target: <5% of SLO windows result in breach (the "well-set" threshold) |
| **Error Budget Optimization** | Recommendations should land in the "Goldilocks zone" where error budgets are neither wasted (too loose) nor constantly exhausted (too tight) | Average error budget utilization: 50-80% |
| **Accelerate SLO Adoption** | Lower the barrier to SLO adoption by providing data-driven starting points for teams that have no SLOs today | >80% of onboarded services have active SLOs within 90 days |
| **Build Trust for Automation** | Start semi-automated, graduate to full automation as confidence builds | Recommendation acceptance rate >70% within 6 months |

### Non-Goals (Explicit Exclusions for MVP)

- **Throughput and correctness SLOs** — MVP focuses on availability and latency only
- **Auto-remediation** — The system recommends SLOs; it does not take remediation actions (e.g., scaling, circuit-breaking)
- **Multi-cloud / multi-region topology** — Assumes a single logical deployment topology initially
- **SLA generation** — SLOs are internal targets; contractual SLA generation is out of scope
- **Real-time alerting** — The system recommends SLO targets and burn-rate alert configurations, but does not replace existing alerting infrastructure (Prometheus Alertmanager)

---

## Target Users

### Primary Users

| Persona | Role | Needs | Interaction Mode |
|---------|------|-------|-----------------|
| **SRE / Platform Engineer** | Defines and governs SLOs across the organization | Dependency-aware recommendations, bulk analysis, confidence scoring, audit trails | Power user — API + Dashboard, reviews/approves recommendations |
| **Service Owner / Developer** | Owns one or more microservices, responsible for meeting reliability targets | Clear, explainable SLO suggestions for their service, impact analysis when changing SLOs | Consumer — views recommendations via developer platform (Backstage), accepts/modifies/rejects |

### Secondary Users

| Persona | Role | Needs |
|---------|------|-------|
| **Engineering Manager / VP** | Oversees reliability posture across multiple teams | Aggregated views of SLO health, error budget trends, coverage gaps |
| **Incident Responder** | Investigates production incidents | Historical SLO context, dependency maps showing blast radius |

### User Characteristics

- Operating at large scale: **500+ microservices** across multiple teams
- Existing observability stack: **OpenTelemetry + Prometheus + Grafana**
- Varying SLO maturity: some teams have well-defined SLOs, many have none or outdated ones
- Skeptical of black-box AI — need explainability and the ability to override

---

## User Stories

### SRE / Platform Engineer

1. **As an SRE**, I want to ingest our service dependency graph so that the system understands how services are interconnected and can model cascading failure risks.

2. **As an SRE**, I want to request SLO recommendations for any service and receive availability and latency targets grounded in historical data and dependency analysis, so that I don't have to manually compute achievable targets.

3. **As an SRE**, I want each recommendation to include a confidence score, contributing factors (SHAP-based feature attribution), and historical comparison, so that I can evaluate the recommendation's rationale before approving it.

4. **As an SRE**, I want to run an impact analysis before changing an SLO, so that I can understand how the change propagates to upstream and downstream services.

5. **As an SRE**, I want to see three recommendation tiers (Conservative / Balanced / Aggressive) for each service, so that I can choose the target that matches our risk tolerance.

6. **As an SRE**, I want the system to detect when performance baselines drift (due to deployments, traffic changes, or infrastructure shifts) and proactively suggest SLO re-evaluation, so that targets don't go stale.

7. **As an SRE**, I want to configure auto-approval rules for non-critical services (e.g., "auto-accept Balanced tier for services tagged `criticality: low`"), so that I can focus review effort on high-impact services as we graduate toward full automation.

### Service Owner / Developer

8. **As a service owner**, I want to view SLO recommendations for my service in the developer platform (Backstage), so that I don't need to use a separate tool.

9. **As a service owner**, I want to accept, modify, or reject a recommendation with a reason, so that my feedback improves future suggestions.

10. **As a service owner**, I want to understand why a specific target was recommended (e.g., "your service achieved 99.92% availability over 30 days; the recommended 99.9% provides 0.02% margin"), so that I trust the system's output.

11. **As a service owner**, I want to see how my service's SLO relates to its dependencies (e.g., "your checkout-service targets 99.9% but depends on payment-service at 99.95% and external-payment-api at 99.5%"), so that I can identify reliability bottlenecks.

### Engineering Leadership

12. **As an engineering manager**, I want a dashboard showing SLO coverage (% of services with active SLOs), error budget health across my org, and recommendation acceptance rates, so that I can track reliability posture.

---

## Functional Requirements

### Must Have (MVP)

#### F1: Service Dependency Graph Ingestion & Management
- Accept service dependency graphs via API (`POST /api/v1/services/dependencies`)
- Support multiple discovery sources: manual API submission, OpenTelemetry Service Graph Connector (automatic trace-based discovery), and Kubernetes manifest parsing
- Store the graph with edge annotations: communication mode (sync/async), criticality (hard/soft/degraded), protocol, and discovery source
- Detect circular dependencies using Tarjan's algorithm for strongly connected components and flag them for architectural review
- Detect divergence between runtime-observed graph and declared configuration

#### F2: SLO Recommendation Generation
- Generate **availability SLO** recommendations using composite reliability math (serial: `R = R1 x R2 x ... x Rn`, parallel: `R = 1 - (1-R1)(1-R2)`)
- Generate **latency SLO** recommendations (p95, p99) using end-to-end trace-based measurement rather than mathematical composition (since percentiles don't add linearly)
- Present three tiers per recommendation: **Conservative** (p99.9 historical, minimal breach risk), **Balanced** (p99, recommended default), **Aggressive** (p95, higher tolerance)
- Each recommendation includes:
  - Confidence score with confidence interval
  - SHAP-based feature attribution (top contributing factors)
  - Historical comparison ("achieved X% over N days, recommending Y% with Z% margin")
  - Dependency impact summary
  - What-if simulation data (estimated breach frequency at different targets)

#### F3: Dependency-Aware Constraint Propagation
- Model serial and parallel dependency chains to compute composite availability bounds
- Account for external API unreliability: recommend internal SLOs with adaptive buffers below the external provider's published SLA
- Identify when external dependencies consume disproportionate error budget (e.g., "external-payment-api consumes 50% of checkout-service's error budget")
- Flag services whose desired SLO is mathematically unachievable given their dependency chain

#### F4: Impact Analysis
- Given a proposed SLO change for a service, compute the cascading impact on all upstream and downstream services (`POST /api/v1/slos/impact-analysis`)
- Show which upstream services' composite SLOs would be affected and by how much
- Identify services at risk of SLO breach if the proposed change is applied

#### F5: Recommendation Lifecycle (Accept / Modify / Reject)
- SREs and service owners can accept, modify, or reject recommendations via API (`POST /api/v1/services/{service-id}/slos`)
- Capture rationale for modify/reject as structured feedback for model improvement
- Maintain full audit trail of all recommendation actions (who, when, what, why)
- Accepted SLOs are stored as the active target; modified SLOs record the delta from the original recommendation

#### F6: Telemetry Ingestion Pipeline
- Ingest metrics from **Prometheus** (via PromQL remote read or federation) and **OpenTelemetry** (OTLP)
- Derive RED metrics (Rate, Errors, Duration) per service from trace spans using the OTel Span Metrics Connector
- Ingest USE metrics (Utilization, Saturation, Errors) from infrastructure sources (cAdvisor, node_exporter, kube-state-metrics)
- Data tiering: raw telemetry (7 days), aggregated capsules (90 days), pre-computed SLI/SLO series (1 year)

#### F7: Explainability
- Every recommendation discloses: reasoning, data sources, confidence level, and contributing features
- Counterfactual analysis: "if P99 latency were 50ms lower, we'd recommend 99.99% instead of 99.9%"
- Link each recommendation to specific telemetry windows and dependency graph snapshots used in computation

#### F8: REST API for Developer Platform Integration
- RESTful API with OpenAPI 3.0 specification for integration into Backstage or similar platforms
- Core endpoints:
  - `POST /api/v1/services/dependencies` — Ingest/update service dependency graph
  - `GET /api/v1/services/{service-id}/slo-recommendations` — Get SLO recommendations
  - `POST /api/v1/services/{service-id}/slos` — Accept or modify a recommendation
  - `POST /api/v1/slos/impact-analysis` — Check dependency impact of proposed SLO change
  - `GET /api/v1/services/{service-id}/dependencies` — Get dependency graph for a service
  - `GET /api/v1/services/{service-id}/slo-history` — Get historical SLO performance
- Authentication via API keys or OAuth2/OIDC tokens
- Rate limiting per client

### Should Have

#### F9: Drift Detection & Proactive Re-evaluation
- Run drift detectors (Page-Hinkley + ADWIN + KS-test ensemble with majority voting) continuously on service performance baselines
- When drift is confirmed, trigger automatic SLO re-evaluation and notify the service owner
- Re-baselining protocol after deployments: capture pre-deployment baseline, monitor canary, detect stable new regime, suggest updated targets after 24-72 hour observation window

#### F10: Multi-Window Burn-Rate Alert Configuration
- For each accepted SLO, generate recommended multi-window, multi-burn-rate alert configurations following Google SRE best practices:
  - Critical: 14.4x burn rate over 1 hour / 5 min short window
  - High: 6x burn rate over 6 hours / 30 min short window
  - Warning: 1x burn rate over 3 days / 6 hour short window
- Export alert configurations as Prometheus recording rules (compatible with Sloth/Pyrra format)

#### F11: Auto-Approval Rules
- Allow SREs to configure policies for automatic SLO acceptance (e.g., "auto-accept Balanced tier for services with `criticality: low` tag and confidence > 0.85")
- All auto-approved actions are logged with full audit trail
- Graduation path: start with no auto-approval, enable for low-criticality services, expand as trust builds

#### F12: Organizational Dashboard
- SLO coverage: percentage of services with active SLOs vs. total registered services
- Error budget health: aggregate view across services/teams, services in danger of budget exhaustion
- Recommendation quality: acceptance rate, modification frequency, breach rate of accepted recommendations
- Dependency risk map: services with highest cascading failure risk

### Could Have

#### F13: Chaos Engineering Integration
- Validate recommended SLOs by integrating with chaos engineering tools (e.g., LitmusChaos, Chaos Mesh)
- Suggest fault injection experiments to stress-test whether a service can realistically meet its SLO under failure conditions

#### F14: SLO-as-Code Export
- Export accepted SLOs in OpenSLO YAML format for GitOps workflows
- Generate Sloth-compatible YAML for Prometheus recording rules and alerts
- Support pull-request-based workflow: recommendations submitted as PRs to an SLO config repository

#### F15: Composite / Journey-Level SLOs
- Define composite SLOs that aggregate multiple service SLOs into a single user-journey SLO (e.g., "checkout journey" = api-gateway + checkout-service + payment-service)
- Use Monte Carlo simulation for complex mixed topologies where simple serial/parallel math is insufficient

#### F16: What-If Scenario Modeling
- Interactive what-if tool: "What happens to composite availability if we add a fallback payment provider at 98% availability?"
- Model the impact of architectural changes (adding circuit breakers, async queues, caching layers) on achievable SLOs

---

## Technical Requirements

### Performance Requirements

| Metric | Target | Rationale |
|--------|--------|-----------|
| API response time (p95) | < 500ms for recommendation retrieval | Recommendations are pre-computed; retrieval should be fast |
| API response time (p95) | < 5s for on-demand recommendation generation | Involves graph traversal + ML inference; acceptable for async UX |
| Impact analysis response (p95) | < 10s | Requires full graph propagation computation |
| Dependency graph ingestion | < 30s for full graph of 1000 services | Batch operation, can be async |
| Recommendation freshness | < 24 hours from telemetry to updated recommendation | Batch pipeline; near-real-time not required for SLO setting |
| Concurrent API users | Support 200+ concurrent users | Platform integration means many services polling |

### Scalability Requirements

| Dimension | Target | Approach |
|-----------|--------|----------|
| Number of services | 500 - 5,000+ | Horizontally scalable graph storage and ML inference |
| Telemetry volume | Millions of time series | Leverage existing Prometheus/Mimir stack; system queries, not stores raw metrics |
| Dependency graph edges | 10,000+ edges | Graph database or PostgreSQL with recursive CTEs |
| Multi-team / multi-org | Support organizational hierarchy for access control and aggregation | Tenant-aware data model |
| Historical data | 1 year of SLI/SLO history for trend analysis | Tiered storage with aggregation |

### Security Requirements

- **Authentication:** OAuth2/OIDC integration with existing identity provider; API key support for service-to-service calls
- **Authorization:** Role-based access control (RBAC) — SREs can approve/reject for any service; service owners only for their own services
- **Data Protection:** TLS 1.3 for all API communication; encryption at rest for stored SLO data and telemetry aggregates
- **PII/Sensitive Data:** The system processes infrastructure metrics only — no user PII. Metric labels must be validated to prevent accidental PII leakage (e.g., no user IDs in metric labels)
- **Audit Logging:** Immutable audit trail for all recommendation actions, configuration changes, and access events
- **Rate Limiting:** Per-client rate limiting on all API endpoints to prevent abuse

### Compliance Requirements

- **EU AI Act Alignment:** As the system provides automated recommendations that influence operational decisions, it should maintain human oversight capability (satisfied by the semi-automated approval model), explainability for all outputs, and an audit trail
- **SOC 2 Compatibility:** Audit logging, access control, and encryption align with SOC 2 trust principles

> **Assumption:** No industry-specific regulatory requirements (e.g., HIPAA, PCI-DSS) apply directly to the SLO recommendation engine itself, since it processes operational metrics rather than user data. If the organization is in a regulated industry, compliance requirements for the platform hosting this service would be inherited.

### Integration Requirements

| Integration Point | Protocol | Direction | Priority |
|-------------------|----------|-----------|----------|
| **Prometheus / Grafana Mimir** | PromQL remote read API | Inbound (read metrics) | MVP |
| **OpenTelemetry Collector** | OTLP gRPC/HTTP | Inbound (receive traces/metrics) | MVP |
| **Backstage (Developer Platform)** | REST API (OpenAPI 3.0) | Outbound (serve recommendations) | MVP |
| **Kubernetes API** | Kubernetes client | Inbound (discover services, read manifests) | MVP |
| **Service Mesh (Istio/Linkerd)** | Mesh telemetry APIs | Inbound (topology, traffic metrics) | Should Have |
| **Git Repository (SLO-as-Code)** | Git API (GitHub/GitLab) | Outbound (submit PRs) | Could Have |
| **Chaos Engineering Tools** | Tool-specific APIs | Outbound (trigger experiments) | Could Have |

---

## Success Metrics

### Quantitative Metrics

| Metric | Measurement | 6-Month Target | 12-Month Target |
|--------|-------------|----------------|-----------------|
| **SLO Coverage** | % of registered services with active SLOs | 60% | >80% |
| **Recommendation Acceptance Rate** | Accepted / (Accepted + Rejected) | >50% | >70% |
| **SLO Breach Rate** | % of SLO windows with breach (for accepted recommendations) | <10% | <5% |
| **Error Budget Utilization** | Average budget consumed across services | 40-90% (initial) | 50-80% (Goldilocks zone) |
| **Time to First SLO** | Time from service registration to first active SLO | <1 hour | <15 minutes |
| **Recommendation Freshness** | Lag between baseline drift and updated recommendation | <48 hours | <24 hours |
| **Dependency Coverage** | % of service-to-service edges captured in graph | >70% | >90% |

### Qualitative Metrics

| Metric | Measurement Method | Target |
|--------|-------------------|--------|
| **SRE Trust** | Quarterly survey: "I trust the system's recommendations" | >3.5/5 at 6 months |
| **Explainability Satisfaction** | Survey: "Recommendations are easy to understand" | >4/5 at 6 months |
| **Reduced Toil** | SRE time spent on manual SLO computation (before/after) | >50% reduction |

---

## Timelines / Milestones

### Phase 1: Foundation (Weeks 1-4)

- [ ] Define API contract (OpenAPI 3.0 spec) and data models
- [ ] Set up project scaffolding: Clean Architecture layers, CI/CD pipeline, test infrastructure
- [ ] Implement service registry and dependency graph storage (PostgreSQL with recursive CTEs)
- [ ] Implement dependency graph ingestion API (`POST /api/v1/services/dependencies`)
- [ ] Implement circular dependency detection (Tarjan's algorithm)
- [ ] Set up telemetry ingestion: Prometheus remote read integration for historical metrics

### Phase 2: Core Recommendation Engine (Weeks 5-10)

- [ ] Implement availability SLO recommendation using composite reliability math (serial/parallel)
- [ ] Implement latency SLO recommendation using historical trace percentile analysis
- [ ] Build three-tier recommendation output (Conservative / Balanced / Aggressive)
- [ ] Implement SHAP-based explainability for each recommendation
- [ ] Implement recommendation retrieval API (`GET /api/v1/services/{service-id}/slo-recommendations`)
- [ ] Implement accept/modify/reject workflow (`POST /api/v1/services/{service-id}/slos`)
- [ ] Implement impact analysis API (`POST /api/v1/slos/impact-analysis`)
- [ ] Build audit trail logging for all recommendation lifecycle events

### Phase 3: Intelligence & Adaptation (Weeks 11-16)

- [ ] Implement drift detection ensemble (Page-Hinkley + ADWIN + KS-test)
- [ ] Build re-baselining protocol for post-deployment SLO re-evaluation
- [ ] Implement burn-rate alert configuration generation (Prometheus recording rules)
- [ ] Implement auto-approval rules engine for semi-automated graduation
- [ ] Build organizational dashboard: SLO coverage, error budget health, acceptance rates
- [ ] Integrate OTel Service Graph Connector for automatic dependency discovery

### Phase 4: Integration & Hardening (Weeks 17-20)

- [ ] Build Backstage plugin / integration layer
- [ ] Load testing and performance optimization for 500+ service scale
- [ ] Security hardening: RBAC, rate limiting, audit log review
- [ ] End-to-end testing with production-like topology
- [ ] Documentation: API docs, onboarding guide, SRE playbook
- [ ] Controlled rollout to pilot teams (5-10 services)

### Phase 5: Scale & Graduate (Weeks 21+)

- [ ] Expand to full service catalog
- [ ] Introduce GNN-based structural models for improved dependency-aware predictions
- [ ] Implement SLO-as-Code export (OpenSLO YAML, Sloth compatibility)
- [ ] Begin graduation to auto-approval for low-criticality services
- [ ] Composite / journey-level SLO support
- [ ] What-if scenario modeling

> **Note:** Timeline assumes a team of 2-3 backend engineers and 1 ML/data engineer. Adjust proportionally for larger or smaller teams.

---

## Dependencies

| Dependency | Type | Risk Level | Notes |
|------------|------|------------|-------|
| **Prometheus / Mimir with 30+ days of historical data** | Data prerequisite | High | Recommendations quality is directly proportional to historical data depth. Need at least 30 days; 90 days preferred. |
| **OpenTelemetry instrumentation across services** | Infrastructure prerequisite | High | Trace-based dependency discovery and latency SLO computation require OTel instrumentation. Partial coverage degrades graph completeness. |
| **Service catalog / registry** | Platform prerequisite | Medium | Need a canonical list of services with ownership metadata. Can bootstrap from Kubernetes namespaces if Backstage catalog isn't ready. |
| **Backstage instance (or equivalent)** | Integration target | Medium | For developer-facing UX. API-first design means the engine works standalone; Backstage integration is additive. |
| **Kubernetes cluster access** | Infrastructure | Medium | For service discovery, manifest parsing, and infrastructure metrics. |
| **SRE team buy-in** | Organizational | High | System adoption requires SRE champions willing to pilot, provide feedback, and advocate. |

---

## Risks and Mitigation

| Risk | Impact | Probability | Mitigation Strategy |
|------|--------|-------------|---------------------|
| **Insufficient historical telemetry** — Services lack 30+ days of metrics, especially newly deployed ones | High | Medium | Implement cold-start strategy: use longer time windows (90 days), aggregate from similar service archetypes, synthetic monitoring for baseline generation. Clearly flag low-confidence recommendations. |
| **Incomplete dependency graph** — Not all service-to-service calls are instrumented with OTel, leading to missing edges | High | High | Multi-source discovery: combine traces, service mesh telemetry, Kubernetes manifests, and manual declaration. Alert when runtime graph diverges from declared config. Assign confidence scores per edge based on source count. |
| **SRE distrust of AI recommendations** — Engineers ignore or reject recommendations if they seem opaque or inaccurate | High | Medium | Prioritize explainability from day one (SHAP, counterfactuals, historical comparisons). Start with non-critical services to build track record. Capture feedback loop. Never auto-apply without explicit opt-in. |
| **Noisy neighbor effects on shared infrastructure** — Latency spikes from co-located workloads create misleading baselines | Medium | High | Add 5-10% noise margin to latency targets on shared infrastructure. Monitor `container_cpu_cfs_throttled_seconds_total` as a signal. Account for CFS bandwidth control throttling in recommendations. |
| **External API reliability data is unreliable** — Third-party SLAs are overstated; actual availability differs from published numbers | Medium | High | Use observed historical performance of external APIs (not published SLAs) as the input for dependency calculations. Track external API health independently. |
| **High cardinality metric explosion** — Unbounded labels (user IDs, request IDs) in metrics cause storage and cost issues | High | Medium | Enforce bounded cardinality at ingestion: SLO metrics use only low-cardinality labels (service, method, endpoint_template, status_class). Validate label sets before processing. |
| **Model drift** — ML models become stale as system topology and traffic patterns evolve | Medium | High | Hybrid retraining triggers: performance-based (prediction error threshold), event-based (deployment/infra changes), and scheduled (monthly). Shadow deployment validation before updating live models. |
| **Circular dependencies in service graph** — Violate DAG assumption, complicate SLO math | Medium | Medium | Detect with Tarjan's algorithm. Contract strongly connected components into supernodes for SLO computation. Flag for architectural remediation (async boundaries). |

---

## Assumptions

The following assumptions underpin this PRD. Changes to these assumptions may require re-evaluation of scope and approach.

1. **Data Availability:** Services emit metrics in Prometheus exposition format and are instrumented with OpenTelemetry for distributed tracing. At least 30 days of historical metrics are available for most services.

2. **Metric Granularity:** Prometheus metrics are scraped at 15-30 second intervals. Trace sampling retains at least 10% of spans probabilistically, with 100% retention of error and slow traces via tail-based sampling.

3. **Scale:** The system will serve an organization with 500-5,000+ microservices, generating millions of time series. The recommendation engine queries existing metric stores rather than storing raw telemetry itself.

4. **Developer Platform:** A Backstage instance (or equivalent) exists as the primary developer-facing interface. The SLO engine integrates as a backend plugin, not a standalone UI.

5. **Team Structure:** Service ownership is well-defined — each microservice has a known owning team. Organizational metadata (team, criticality tier, business domain) is available in the service catalog.

6. **Operational Maturity:** The organization has a functioning SRE practice, even if SLO adoption is inconsistent. Concepts like error budgets and burn rates are understood, even if not universally applied.

7. **Single Deployment Topology:** MVP assumes a single logical cluster/region. Multi-region support is a post-MVP concern.

> **Trade-off:** We chose **availability + latency** for MVP scope because these are the two most universal SLI types and cover the majority of reliability concerns. Throughput and correctness SLOs are deferred because they are more domain-specific and require additional feature engineering.

> **Trade-off:** We chose a **semi-automated** approval model over full automation because trust is earned, not assumed. The auto-approval rules engine (F11) provides a clear graduation path without requiring architectural changes to move toward full automation.

> **Trade-off:** We chose to **query existing metric stores** (Prometheus/Mimir) rather than building a separate telemetry pipeline because it avoids data duplication, leverages existing infrastructure investment, and reduces the system's operational footprint. The trade-off is dependency on the existing stack's availability and query performance.

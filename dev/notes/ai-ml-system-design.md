# AI/ML System Design: Combining Structural and Temporal Models

> High-level architecture of the Recommendation Intelligence Engine — data sources,
> feature engineering, model components, and output heads.

---

## System Overview

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                                       │
│                                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ OpenTelemetry│  │ Service Mesh │  │  Kubernetes  │  │   Business   │    │
│  │   (Traces,   │  │  (Istio/     │  │  (cAdvisor,  │  │  (KPIs,      │    │
│  │   Metrics,   │  │  Linkerd     │  │  kube-state- │  │  calendars,  │    │
│  │   Logs)      │  │  Envoy)      │  │  metrics)    │  │  metadata)   │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         │                 │                 │                 │            │
│         └────────┬────────┴────────┬────────┴────────┬───────┘             │
│                  ▼                 ▼                 ▼                     │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │                    KAFKA BUFFER LAYER                            │      │
│  │         (traces topic | metrics topic | logs topic)              │      │
│  └──────────────────────────┬───────────────────────────────────────┘      │
└─────────────────────────────┼──────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     STORAGE & PROCESSING                                    │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ Grafana Mimir │  │ Grafana Tempo│  │ Grafana Loki │  │ PostgreSQL   │    │
│  │  (Metrics)    │  │  (Traces)    │  │  (Logs)      │  │ (Dep. Graph) │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         └────────┬────────┴────────┬────────┴────────┬───────┘              │
│                  ▼                                                           │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │                 FEATURE ENGINEERING PIPELINE                     │       │
│  └──────────────────────────┬───────────────────────────────────────┘       │
└─────────────────────────────┼───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                 RECOMMENDATION INTELLIGENCE ENGINE                          │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                STAGE 1: CANDIDATE GENERATION                    │        │
│  │  Structural fingerprinting + trace analysis → critical paths    │        │
│  └────────────────────────────┬────────────────────────────────────┘        │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                STAGE 2: SCORING                                 │        │
│  │                                                                 │        │
│  │  ┌─────────────────────┐    ┌─────────────────────┐            │        │
│  │  │  SPATIAL ENCODER    │    │  TEMPORAL ENCODER    │            │        │
│  │  │  (Graph Neural Net) │    │  (Time-Series Model) │            │        │
│  │  │                     │    │                      │            │        │
│  │  │  2-3 GAT Layers     │    │  TFT-style LSTM      │            │        │
│  │  │  Message Passing     │    │  Variable Selection   │            │        │
│  │  │  Attention Weights   │    │  Quantile Forecasts   │            │        │
│  │  │                     │    │                      │            │        │
│  │  │  Node Features:     │    │  Input Features:      │            │        │
│  │  │  • CPU utilization  │    │  • Historical SLIs    │            │        │
│  │  │  • Memory usage     │    │  • Holiday flags      │            │        │
│  │  │  • RPS              │    │  • Promo calendars    │            │        │
│  │  │  • Latency p50-p99  │    │  • Day-of-week        │            │        │
│  │  │  • Queue depth      │    │  • Seasonal signals   │            │        │
│  │  │                     │    │                      │            │        │
│  │  │  Edge Features:     │    │  Static Covariates:   │            │        │
│  │  │  • Call volume      │    │  • Service type       │            │        │
│  │  │  • Edge latency     │    │  • Service tier       │            │        │
│  │  │  • Error rates      │    │  • Criticality class  │            │        │
│  │  └──────────┬──────────┘    └──────────┬───────────┘            │        │
│  │             └──────────┬───────────────┘                        │        │
│  │                        ▼                                        │        │
│  │             ┌──────────────────────┐                            │        │
│  │             │    FUSION LAYER      │                            │        │
│  │             │  Multi-Head Cross-   │                            │        │
│  │             │  Attention between   │                            │        │
│  │             │  spatial & temporal  │                            │        │
│  │             │  representations     │                            │        │
│  │             └──────────┬───────────┘                            │        │
│  └────────────────────────┼────────────────────────────────────────┘        │
│                           ▼                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                STAGE 3: RE-RANKING                              │        │
│  │  Business constraints + policy rules + RL dynamic optimization  │        │
│  │  (TD3 reward: -α·violation - β·cost + γ·slack)                 │        │
│  └────────────────────────┬────────────────────────────────────────┘        │
│                           ▼                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │                     OUTPUT HEADS                                │        │
│  │                                                                 │        │
│  │  ┌─────────────────┐ ┌────────────────┐ ┌────────────────────┐ │        │
│  │  │ Quantile        │ │ Violation      │ │ Resource           │ │        │
│  │  │ Regression      │ │ Probability    │ │ Allocation         │ │        │
│  │  │ (p50/p95/p99    │ │ Classification │ │ Recommendations    │ │        │
│  │  │ latency)        │ │                │ │                    │ │        │
│  │  └─────────────────┘ └────────────────┘ └────────────────────┘ │        │
│  └─────────────────────────────────────────────────────────────────┘        │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     EXPLAINABILITY & OUTPUT                                  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │                THREE RECOMMENDATION TIERS                        │       │
│  │                                                                  │       │
│  │  Conservative (p99.9)  │  Balanced (p99)  │  Aggressive (p95)   │       │
│  │  Minimal breach risk   │  Recommended     │  Higher tolerance   │       │
│  └──────────────────────────────────────────────────────────────────┘       │
│                                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌─────────────────────┐        │
│  │  SHAP    │ │  LIME    │ │ Counterfactual│ │ Confidence          │        │
│  │ (global  │ │ (per-svc │ │ Analysis     │ │ Intervals           │        │
│  │  feature │ │  explain)│ │ (what-if)    │ │ (range estimates)   │        │
│  │  import.)│ │          │ │              │ │                     │        │
│  └──────────┘ └──────────┘ └──────────────┘ └─────────────────────┘        │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      FEEDBACK LOOP                                          │
│                                                                             │
│  SRE accept/reject/modify → captured as training data                       │
│  Drift detectors (Page-Hinkley + ADWIN + KS ensemble) → retrain trigger    │
│  Deployment events → dependency graph refresh + canary analysis             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## End-to-End Walkthrough: Checkout Path Example

To make the architecture concrete, here is a complete trace of how the system generates
an SLO recommendation for `checkout-service` in an e-commerce platform.

### The Setup

```
User Browser
    │
    ▼
api-gateway ──→ auth-service
    │
    ▼
checkout-service ──→ payment-service ──→ Stripe API (external)
    │
    ▼
inventory-service ──→ PostgreSQL
```

- `checkout-service` depends on `payment-service` (synchronous, hard dependency)
- `payment-service` depends on Stripe (external, 99.95% availability)
- `checkout-service` also calls `inventory-service` (synchronous, hard dependency)

### Step 1 — Data Collection (What happens in the background)

Every request flowing through this system generates telemetry:

**A single checkout request produces:**

| Source | What It Captures | Example |
|--------|-----------------|---------|
| OTel SDK in `checkout-service` | A trace span with start/end timestamps, status code, parent span ID | `span_id=abc, parent=gateway_span, duration=420ms, status=OK` |
| OTel SDK in `payment-service` | A child span showing the Stripe call took most of the time | `span_id=def, parent=abc, duration=380ms, status=OK` |
| Envoy sidecar (Istio) | L7 metrics: source=checkout, dest=payment, latency=385ms, status=200 | Automatically discovered dependency edge |
| cAdvisor on the Kubernetes node | `checkout-service` pod used 0.4 CPU cores, 256MB memory during this period | Container-level resource consumption |
| kube-state-metrics | `checkout-service` has 3 replicas, 0 restarts, HPA target CPU=70% | Kubernetes object state |

**Span Metrics Connector** (runs inside OTel Collector) watches every span — even ones
that get sampled out for trace storage — and derives aggregate RED metrics:
- `calls_total{service="checkout-service", status="ok"}` +1
- `duration_milliseconds_bucket{service="checkout-service", le="500"}` +1

This means SLI accuracy is based on 100% of traffic, not sampled data.

### Step 2 — Feature Engineering (Raw telemetry becomes model inputs)

The Feature Engineering Pipeline queries the storage backends to compute features.
Here is what it produces for `checkout-service` over a 28-day window:

**Service-Level (RED) Features:**

| Feature | Value | What It Means |
|---------|-------|---------------|
| `error_rate_mean_28d` | 0.08% | On average, 0.08% of checkout requests fail over 28 days |
| `error_rate_variance_28d` | 0.003 | Error rate is relatively stable (low variance) |
| `latency_p50_28d` | 120ms | Half of all requests complete in under 120ms |
| `latency_p95_28d` | 350ms | 95% of requests complete in under 350ms |
| `latency_p99_28d` | 480ms | 99% of requests complete in under 480ms — the 1% tail is much slower |
| `throughput_mean_1h` | 850 req/s | Current traffic rate (varies by time of day) |

**Infrastructure (USE) Features:**

| Feature | Value | What It Means |
|---------|-------|---------------|
| `cpu_utilization` | 0.62 | Pods are using 62% of their CPU limit — moderate headroom |
| `memory_saturation` | 0.45 | 45% memory usage — healthy |
| `cfs_throttle_seconds` | 0.02 | Very low CPU throttling — not resource-constrained |

**Graph Features (computed from the dependency graph in PostgreSQL):**

| Feature | Value | What It Means |
|---------|-------|---------------|
| `downstream_count` | 2 | `checkout-service` calls 2 other services |
| `upstream_count` | 1 | Only `api-gateway` calls `checkout-service` |
| `graph_depth` | 2 | It is 2 hops from the deepest leaf (Stripe) |
| `has_external_dep` | true | Transitive dependency on an external API |
| `criticality_class` | "revenue-critical" | Tagged by business metadata |

**Temporal Features:**

| Feature | Value | What It Means |
|---------|-------|---------------|
| `hour_of_day` | 14 | 2 PM — peak shopping hours |
| `day_of_week` | 5 | Friday — historically 1.3x normal traffic |
| `is_holiday_window` | false | No holidays in the next 7 days |
| `upcoming_promo` | "spring_sale_in_12d" | A promotional event is 12 days away |

**Derived Signals:**

| Feature | Value | What It Means |
|---------|-------|---------------|
| `error_budget_burn_rate_1h` | 0.8x | Consuming error budget at 0.8x the sustainable rate — healthy |
| `composite_avail_bound` | 99.70% | Math: `0.999 × 0.999 × 0.9995 = 99.70%` — even if checkout is perfect, the *path* can only achieve 99.70% due to its dependencies |

### Step 3 — Stage 1: Candidate Generation (Which services need SLOs?)

The system analyzes distributed traces to identify **critical paths** — sequences of
service calls that directly affect user-visible outcomes.

**How structural fingerprinting works:**

1. Collect 10,000 recent checkout traces
2. Decompose each into a "backbone" (the stable, always-present call chain) and
   "deviation subgraphs" (optional calls that happen conditionally)
3. The backbone for checkout is: `gateway → checkout → payment → Stripe`
4. A deviation might be: `checkout → recommendation-service` (only called 30% of the time for upsells)

**Output:** The candidate set for the checkout journey includes:
- `api-gateway` (entry point)
- `checkout-service` (orchestrator)
- `payment-service` (hard dependency)
- `inventory-service` (hard dependency)

`recommendation-service` is excluded from this critical path because it is a soft
dependency — checkout succeeds even if recommendations fail.

### Step 4 — Stage 2: Scoring (What SLO target is achievable?)

This is where the two neural network encoders work together.

#### Spatial Encoder: "How do my neighbors affect me?"

The GAT processes the dependency graph. Think of it as a structured rumor network —
each service "asks" its neighbors how they are doing:

```
Round 1 (Layer 1):
  checkout-service asks payment-service:  "How reliable are you?"
  checkout-service asks inventory-service: "How reliable are you?"

  payment-service asks Stripe API:  "How reliable are you?"

Round 2 (Layer 2):
  checkout-service now knows:
    - payment-service has 99.9% availability
    - payment-service ALSO knows Stripe is at 99.95%
    - inventory-service has 99.95% availability

  The GAT assigns ATTENTION WEIGHTS:
    - payment-service gets weight 0.72 (high — it's the riskiest dependency)
    - inventory-service gets weight 0.28 (lower — it's more reliable)
```

**Why this matters:** The attention weight of 0.72 on `payment-service` directly becomes
part of the SHAP explanation: "Payment service reliability contributed 72% to the
availability target recommendation."

After 2 layers, the spatial encoder outputs a 64-dimensional vector for
`checkout-service` that encodes "I am a revenue-critical service, 2 hops deep, with a
risky external dependency through payment-service."

#### Temporal Encoder: "What will my traffic look like next week?"

The TFT processes the historical time series for `checkout-service`:

```
Inputs:
  Past (observed):     28 days of [error_rate, latency_p99, throughput] at 5-min granularity
  Future (known):      Next 7 days of [is_friday=1, is_holiday=0, promo_in_12d=1]
  Static (unchanging): [type="api", tier="gold", criticality="revenue-critical"]

Variable Selection Network output (learned importance):
  - latency_p99: weight 0.35     ← "p99 latency is the most informative signal"
  - throughput:  weight 0.28     ← "traffic volume matters a lot"
  - error_rate:  weight 0.20     ← "error rate matters moderately"
  - day_of_week: weight 0.12     ← "day-of-week pattern is relevant"
  - hour_of_day: weight 0.05     ← "time-of-day matters less at this granularity"

Quantile forecasts for next 7 days:
  - p10 latency: 380ms   (optimistic — 90% chance actual p99 is higher)
  - p50 latency: 450ms   (median expectation)
  - p90 latency: 620ms   (pessimistic — only 10% chance actual p99 exceeds this)
```

**Why quantile forecasts, not point estimates?** A point estimate of "p99 will be 450ms"
gives false confidence. Quantiles say "we're 80% sure p99 will be between 380-620ms,"
which lets the system offer different risk-tolerance tiers.

#### Fusion Layer: "Combine structure and time"

```
Spatial embedding:  [0.23, -0.81, 0.45, ...]   (64-dim, encodes dependency risk)
Temporal embedding: [0.67, 0.12, -0.33, ...]   (64-dim, encodes traffic forecast)
                              │
                    Multi-Head Cross-Attention
                              │
                              ▼
Fused embedding:    [0.41, -0.29, 0.18, ...]   (64-dim)
```

Cross-attention lets the model learn interactions like:
- "When the temporal encoder predicts a traffic spike AND the spatial encoder shows
  a risky dependency chain, the latency forecast should be more pessimistic"
- "When traffic is low (temporal) and all dependencies are healthy (spatial),
  the availability target can be more aggressive"

### Step 5 — Stage 3: Re-Ranking (Apply business rules)

The raw model scores get adjusted by business constraints:

```
Before re-ranking:
  checkout-service:  99.85% availability, p99 < 500ms
  recommendation-svc: 99.90% availability, p99 < 200ms

After re-ranking:
  checkout-service:  99.85% availability, p99 < 500ms  (BOOSTED priority — revenue-critical)
  recommendation-svc: 99.70% availability, p99 < 300ms (RELAXED — non-revenue-critical)
```

The RL agent (TD3) also checks: "If I tighten checkout's SLO to 99.9%, how much
additional compute cost would that require?" The reward function balances violation
risk against resource cost.

### Step 6 — Output (What the SRE team sees)

```json
{
  "service": "checkout-service",
  "recommendations": {
    "availability": {
      "conservative": { "target": "99.9%",  "breach_probability": "2%" },
      "balanced":     { "target": "99.85%", "breach_probability": "8%" },
      "aggressive":   { "target": "99.7%",  "breach_probability": "15%" }
    },
    "latency_p99": {
      "conservative": { "target": "620ms", "breach_probability": "3%" },
      "balanced":     { "target": "500ms", "breach_probability": "10%" },
      "aggressive":   { "target": "400ms", "breach_probability": "22%" }
    }
  },
  "explanation": {
    "primary_factors": [
      "payment-service dependency contributes 72% of availability risk",
      "Stripe external API consumes 50% of checkout path error budget",
      "p99 latency variance contributed 35% to availability target"
    ],
    "composite_bound": "Path max availability: 99.70% (gateway × checkout × payment × Stripe)",
    "counterfactual": "If payment-service p99 improved from 1800ms to 900ms, we'd recommend 99.9% availability instead of 99.85%",
    "confidence_range": "99.80% - 99.90%",
    "epistemic_level": "Level 1 (Inference) — derived from 28 days of historical data, not yet load-tested"
  },
  "what_if_simulations": [
    { "scenario": "Black Friday (3x traffic)", "predicted_p99": "780ms", "breach_risk": "34%" },
    { "scenario": "Add payment queue fallback",  "predicted_avail": "99.92%", "breach_risk": "3%" }
  ]
}
```

### Step 7 — Feedback Loop (The system learns from humans)

```
SRE reviews recommendation:
  "99.85% is too low for checkout — we committed to 99.9% in our SLA."
  Action: MODIFY → sets target to 99.9%
  Rationale captured: "Business SLA commitment overrides model recommendation"

This feedback is stored as training data:
  - The model learns that SLA commitments are a constraint
  - Next time, for services with SLA metadata, it weights the business context higher

Meanwhile, drift detectors run continuously:
  - A deployment to payment-service changes its p99 from 1800ms to 900ms
  - Page-Hinkley detects the shift within 15 minutes
  - ADWIN confirms it 30 minutes later (2/3 majority vote)
  - System triggers SLO re-evaluation for checkout-service
  - New recommendation: 99.9% availability (up from 99.85%)
```

---

## Glossary of Technical Terms

### ML Architecture Terms

| Term | What It Is | Why It Matters Here |
|------|-----------|-------------------|
| **GNN (Graph Neural Network)** | A neural network that operates on graph-structured data. Instead of processing flat tables of numbers, it processes nodes (services) connected by edges (dependencies). | Microservice architectures are naturally graphs. A GNN can learn that "payment-service being slow causes checkout-service to be slow" by propagating information along edges. |
| **GAT (Graph Attention Network)** | A specific type of GNN where each node learns to pay *different amounts of attention* to each of its neighbors. Think: not all dependencies are equally important. | The attention weight directly tells us "payment-service matters 72% to checkout's reliability, inventory-service matters 28%." This is interpretable. |
| **GraphSAGE** | A GNN variant that can generate embeddings for nodes it has never seen before (inductive learning), by learning to *sample and aggregate* neighbor features. | When a new microservice is deployed, GraphSAGE can produce an embedding for it immediately without retraining the entire model. |
| **Message Passing** | The core mechanism of GNNs: each node sends a "message" (its current feature vector) to its neighbors, and each node aggregates the messages it receives to update its own representation. After K rounds, each node "knows about" services K hops away. | After 2 rounds, `checkout-service` has indirect information about Stripe (2 hops away), even though it never calls Stripe directly. |
| **TFT (Temporal Fusion Transformer)** | A time-series forecasting model from Google that can accept three types of input: past observations, known future inputs (like holiday calendars), and static metadata. It uses attention to learn which inputs matter at each timestep. | SLO forecasting needs to account for "next Friday is Black Friday" (known future) and "this is a gold-tier service" (static), not just past metrics. TFT handles all three natively. |
| **Variable Selection Network (VSN)** | A component inside TFT that learns which input features are important at each timestep. It outputs an importance weight per feature. | At 3 AM, `throughput` may be unimportant (low traffic), but `error_rate` may be critical (batch jobs running). VSN adapts feature importance over time. |
| **Multi-Head Cross-Attention** | An attention mechanism where two different representations (spatial and temporal) "attend" to each other. Each "head" can focus on a different aspect of the relationship. | Lets the model learn interactions like "high-traffic-period + risky-dependency-chain = extra pessimistic latency forecast." Neither encoder alone captures this. |
| **Quantile Regression** | Instead of predicting a single value ("p99 will be 450ms"), predicts multiple quantiles ("there's a 10% chance p99 exceeds 620ms, 50% chance it exceeds 450ms"). | Gives SREs a range of risk levels. The conservative tier uses p90 of the forecast, the aggressive tier uses p10. |
| **Pinball Loss (Quantile Loss)** | The loss function for quantile regression. For the p90 quantile: under-predictions are penalized 9x more than over-predictions, naturally pushing the model to produce correct upper bounds. | Ensures the p90 forecast actually covers 90% of outcomes. Asymmetry is critical — under-estimating latency (false safety) is worse than over-estimating (being cautious). |

### Reinforcement Learning Terms

| Term | What It Is | Why It Matters Here |
|------|-----------|-------------------|
| **TD3 (Twin Delayed DDPG)** | A reinforcement learning algorithm that learns a policy (what action to take) by interacting with an environment. "Twin" means it uses two critic networks to reduce overestimation. "Delayed" means it updates the policy less frequently than the critics for stability. | SLO targets are not static — they should adapt as traffic and infrastructure change. TD3 learns to adjust targets dynamically without manual intervention. |
| **State Space** | The information the RL agent observes before making a decision. | Per-service metrics (CPU=62%, latency_p99=480ms, RPS=850) + system-wide E2E latency. |
| **Action Space** | The set of possible actions the agent can take. | Adjust each service's SLO target up/down by 0.01-0.1%, adjust resource quotas. |
| **Reward Function** | The signal telling the agent whether its action was good or bad. | `-α·violations - β·cost + γ·slack` balances three goals: avoid SLO breaches, minimize compute cost, maintain healthy slack in error budgets. |

### Explainability Terms

| Term | What It Is | Example Output |
|------|-----------|---------------|
| **SHAP (SHapley Additive exPlanations)** | Measures each feature's contribution to the model's output using game theory. Assigns a "Shapley value" showing how much each feature pushed the prediction up or down from a baseline. | "P99 latency variance pushed the target from 99.9% down to 99.85% (contribution: -0.05%). Payment-service dependency pushed it down further by -0.03%." |
| **LIME (Local Interpretable Model-agnostic Explanations)** | Creates a simple, human-readable model (like a linear regression) that approximates the complex model's behavior for a single prediction. | For `checkout-service` specifically: "availability target = 99.95% - 0.05*(payment_error_rate) - 0.03*(latency_p99_variance)." This local approximation is easy for SREs to reason about. |
| **Counterfactual Analysis** | Answers "what would need to change for the recommendation to be different?" by perturbing inputs and observing output changes. | "If payment-service p99 improved from 1800ms to 900ms, we'd recommend 99.9% instead of 99.85%." Gives SREs a concrete improvement target. |
| **Confidence Interval** | A range expressing the model's uncertainty. A wide interval means the model is less sure. | "Recommended 99.85%, confidence range 99.80%–99.90%." A narrow range means the model has seen enough similar data to be confident. |

### Drift Detection Terms

| Term | What It Is | When It Fires |
|------|-----------|--------------|
| **Page-Hinkley Test** | A sequential statistical test that monitors the cumulative sum of deviations from the running mean. When the cumulative deviation exceeds a threshold, drift is declared. Very fast (detects within minutes) but can false-alarm. | A deployment changes `payment-service` p99 from 1800ms to 900ms. Page-Hinkley detects the mean shift within 15 minutes. |
| **ADWIN (Adaptive Windowing)** | Maintains a variable-length window of recent data and uses Hoeffding's bound to test whether the mean of two sub-windows differs significantly. Adapts its window size automatically — shorter for rapid changes, longer for stability. | Gradual traffic growth over 3 weeks causes `checkout-service` throughput to increase from 600 to 900 req/s. ADWIN detects the trend after ~2 weeks by comparing window means. |
| **KSWIN (Kolmogorov-Smirnov Windowed)** | Compares the full distribution (not just the mean) of recent data against a reference window using the KS test. Catches changes in variance or shape even when the mean stays the same. | `checkout-service` latency p50 stays at 120ms, but the distribution becomes bimodal (most at 100ms, some at 800ms due to cold starts). KSWIN detects the distributional shift that Page-Hinkley and ADWIN miss. |
| **Majority Voting Ensemble** | Drift is confirmed only when at least 2 of the 3 detectors agree. Reduces false positives. | Page-Hinkley fires on a brief traffic spike, but ADWIN and KSWIN don't — no action taken. When a real deployment changes behavior, all three fire — drift confirmed, SLO re-evaluation triggered. |
| **BOCD (Bayesian Online Changepoint Detection)** | Maintains a probability distribution over "how long since the last changepoint." Unlike the detectors above (which give binary yes/no), BOCD gives a probability — "there's a 92% chance a regime change happened 45 minutes ago." | After a deployment rollout, BOCD identifies exactly when the new performance regime stabilized, allowing the system to compute an accurate new baseline excluding the transition period. |

### SRE / Observability Terms

| Term | What It Is | Example |
|------|-----------|---------|
| **RED Metrics** | Rate (requests/sec), Errors (failed requests/sec), Duration (latency histogram). The standard user-facing metrics for any request-driven service. | `checkout-service`: Rate=850 req/s, Errors=0.7 req/s (0.08%), Duration p99=480ms |
| **USE Metrics** | Utilization (% time busy), Saturation (queue depth / backlog), Errors (hardware/resource errors). The standard resource metrics for infrastructure. | `checkout-service` pod: CPU Utilization=62%, Memory Saturation=45%, CFS Throttle=0.02s |
| **Error Budget** | The amount of allowed unreliability: `1 - SLO_target`. A 99.9% SLO gives a 0.1% error budget, roughly 43 minutes/month of allowed downtime. | `checkout-service` at 99.85% has a 0.15% budget = ~65 minutes/month. If it's consumed 40 minutes already, only 25 minutes remain. |
| **Burn Rate** | How fast the error budget is being consumed relative to the SLO window. A burn rate of 1x means the budget will be exactly exhausted at the end of the window. 14.4x means the budget will be gone in ~1 hour. | Current burn rate = 0.8x means checkout is consuming its budget slower than allowed — healthy. If a payment outage pushes it to 6x, a ticket is created. |
| **Composite Availability** | For serial dependencies: multiply individual availabilities. `gateway(99.95%) × checkout(99.9%) × payment(99.9%) × Stripe(99.95%) = 99.70%`. This is the mathematical ceiling — no SLO can be set higher than this bound. | `checkout-service` can't promise 99.9% if the composite path is 99.70%. The system uses this bound to prevent unrealistic targets. |
| **Span Metrics Connector** | An OpenTelemetry Collector component that derives aggregate metrics (counters, histograms) from 100% of trace spans, even when the spans themselves are sampled for storage. | Ensures SLI accuracy: even if only 10% of traces are stored for debugging, RED metrics are computed from all traffic. |

---

## Feature Categories

Features are engineered from raw telemetry and fed into both the spatial and temporal encoders.

| Category | Features | Used By | Source |
|----------|----------|---------|--------|
| **Service-Level (RED)** | Error rate mean/variance, latency p50/p95/p99, throughput (rolling 1h/1d/7d/28d) | Temporal Encoder, GNN node features | Mimir (Prometheus metrics), Span Metrics Connector |
| **Infrastructure (USE)** | CPU utilization, memory saturation, I/O wait, CFS throttle seconds | GNN node features | cAdvisor, node_exporter |
| **Graph / Structural** | Upstream/downstream count, graph depth, fan-out degree, criticality class, edge communication mode (sync/async) | GNN node + edge features | Dependency Graph (PostgreSQL), Service Mesh |
| **Edge / Inter-Service** | Call volume, edge latency, error rate, retry count, timeout budget | GNN edge features | OTel Service Graph Connector, Istio Envoy |
| **Temporal / Seasonal** | Time-of-day, day-of-week, holiday flags, promotional calendar events, seasonal indicators | Temporal Encoder (known future inputs) | Business metadata, calendar APIs |
| **Change Events** | Deployment frequency, rollback rate, incident count, config changes | Both encoders | CI/CD webhooks, incident management |
| **Derived Signals** | Error budget burn rate, freshness (recent transient events), composite availability bound | Both encoders | Computed from SLI time series |
| **Business Context** | Transaction value, user segment, revenue criticality tier, service type | Re-ranking stage, TFT static covariates | Business KPIs, service metadata |

---

## Model Components Detail

### Spatial Encoder (GAT-based GNN)

```
Input: Dependency graph G(V, E) with annotated node/edge features

For each layer k (2-3 layers):
  h_v^(k) = UPDATE(h_v^(k-1), AGGREGATE({h_u^(k-1) : u ∈ N(v)}))

  - GAT attention weights reveal which neighbors matter most
  - After K layers, each node encodes K-hop neighborhood
  - GraphSAGE variant used for inductive learning on new services

Output: Per-node structural embeddings capturing cascading effects
```

**Why GAT over other GNNs:** Learned attention weights are directly interpretable — they show which downstream service most influences an upstream SLO. This powers the SHAP explanations in the output layer.

### Temporal Encoder (TFT-style)

```
Input per node:
  - Observed past:    [error_rate, latency_p99, throughput] × rolling windows
  - Known future:     [holiday_flag, promo_event, day_of_week]
  - Static covariates:[service_type, tier, criticality]

Architecture:
  - Variable Selection Networks → learn feature importance per timestep
  - LSTM encoder-decoder → capture temporal dynamics
  - Quantile output → p10/p50/p90 forecasts (not point estimates)
```

### Fusion Layer

```
Spatial embedding (per node)  ──┐
                                ├──→ Multi-Head Cross-Attention ──→ Fused representation
Temporal embedding (per node) ──┘

Cross-attention allows each node's temporal forecast to be
conditioned on its structural context (and vice versa).
```

### Loss Function

```
L = L_quantile + λ₁·L_violation + λ₂·L_resource

Where:
  L_quantile   = pinball loss for p50/p95/p99 latency predictions
  L_violation  = asymmetric penalty (under-estimation penalized 3-5× more)
  L_resource   = resource efficiency regularizer (avoid over-provisioning)
```

---

## Reinforcement Learning Layer (Dynamic Optimization)

Sits on top of the spatio-temporal model to dynamically adjust targets.

| Component | Detail |
|-----------|--------|
| **State** | Per-service metrics (CPU, memory, RPS, latency) + global E2E latency |
| **Action** | Adjust SLO targets and resource quotas per service |
| **Reward** | `-α·SLO_violation_penalty - β·resource_cost + γ·SLO_slack_bonus` |
| **Algorithm** | TD3 (Twin Delayed DDPG) with GCN state encoder |
| **Adaptation** | Dynamic weight shifting — α increases as services approach SLO breach |

---

## Key References

| System | Origin | Contribution |
|--------|--------|-------------|
| GRAF | KAIST, CoNEXT 2021 | Message-passing GNN for proactive resource allocation (14-19% CPU savings) |
| DeepScaler | Ant Group, 2023 | Temporal attention GCN + adaptive graph learning |
| STEAM | AAAI 2025 | Non-stationary decomposition + contrastive learning for workload prediction |
| MSARS | 2024 | GCN + TD3 for auto-scaling (40% faster adaptation) |
| CASLO | 2025 | Per-service latency SLO decomposition (61% fewer violations) |
| AutoMan | 2023 | Multi-agent DDPG for inter-microservice SLO derivation |

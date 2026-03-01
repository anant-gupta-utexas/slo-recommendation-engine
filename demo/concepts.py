"""
Concept definitions for the SLO Engine demo.
Single source of truth for all educational content displayed in-step and on the reference page.
"""

from dataclasses import dataclass


@dataclass
class Concept:
    title: str
    icon: str
    summary: str  # 2-3 sentences for in-step expanders
    detail: str  # Full markdown for reference page


# ---------------------------------------------------------------------------
# Step 1: Ingest Dependency Graph
# ---------------------------------------------------------------------------

HARD_VS_SOFT_DEPS = Concept(
    title="Hard vs Soft Dependencies",
    icon="🔗",
    summary=(
        "A **hard** dependency (sync + critical) means the caller fails completely if the dep is down. "
        "A **soft** dependency (async, or non-critical) means the caller degrades gracefully. "
        "Only hard deps participate in SLO math — soft deps are excluded entirely."
    ),
    detail="""\
Edge criticality describes **failure propagation semantics**:

| Value | Meaning |
|---|---|
| `hard` | Caller fails completely without this dep |
| `soft` | Caller degrades gracefully, still functions |
| `degraded` | Caller runs in reduced-capability mode |

**The critical rule** for SLO math:

```
is_hard = (criticality == HARD) AND (communication_mode == SYNC)
```

Everything else — soft, degraded, or async+hard — is treated as soft and **excluded from composite availability calculations**.

**Watch out:** `async/await` in code is a runtime detail, not architectural async. A DB query via `await db.execute()` is still architecturally sync — mark it `criticality=hard, mode=sync`.
""",
)

MULTI_SOURCE_DISCOVERY = Concept(
    title="Multi-Source Auto-Discovery",
    icon="🔍",
    summary=(
        "The engine discovers dependencies from multiple sources (OTel traces, service mesh, K8s manifests, manual API). "
        "Each source has a confidence score — when the same edge is reported by multiple sources, the highest-priority source wins. "
        "Unknown services referenced in edges are auto-created as placeholders."
    ),
    detail="""\
| Source | Confidence | Priority | Frequency |
|--------|------------|----------|-----------|
| **Manual API** | 1.0 | Highest | On-demand |
| **Service Mesh** | 0.9 | High | Real-time |
| **OTel Service Graph** | 0.7 | Medium | Every 15 min |
| **Kubernetes** | 0.5 | Lowest | On manifest change |

**Auto-discovery** is the production standard. Services appear automatically when they start making/receiving calls — no deployment or manual config required.

**Unknown services** referenced in edges are auto-created with `criticality=MEDIUM` and a `discovered=True` flag. They can be enriched later via manual API calls.

**Conflict resolution:** When the same edge (A -> B) is reported by multiple sources, the highest-priority source's attributes win. All observations are tracked for audit.
""",
)

# ---------------------------------------------------------------------------
# Step 2: Query Subgraph
# ---------------------------------------------------------------------------

COMPOSITE_AVAILABILITY = Concept(
    title="Composite Availability Math",
    icon="📐",
    summary=(
        "Composite availability is the product of all hard dependencies' availability. "
        "For example, if checkout-service (99.9%) depends on payment-service (99.5%) and fraud-service (99.8%), "
        "the composite bound is 99.9% x 99.5% x 99.8% = 99.2%. Soft deps like recommendation-service are excluded."
    ),
    detail="""\
Only **hard** (sync + critical) dependencies multiply into the composite bound:

```
composite = service_avail x dep1_avail x dep2_avail x ...
```

**Example** — `checkout-service` (own: 99.9%) with three deps:

| Dep | Criticality | Mode | Availability |
|---|---|---|---|
| payment-service | hard | sync | 99.5% |
| fraud-service | hard | sync | 99.8% |
| recommendation-service | soft | sync | 97.0% |

```
composite = 0.999 x 0.995 x 0.998 = 99.2%
```

`recommendation-service` at 97.0% contributes **nothing** — if it goes down, checkout still works.

If `recommendation-service` were reclassified as hard: `99.2% x 97.0% = 96.2%` — a dramatic drop.
""",
)

NODE_CRITICALITY_COLORS = Concept(
    title="Node Criticality Colors",
    icon="🎨",
    summary=(
        "Node colors in the graph show **business importance**: red = high, orange = medium, green = low. "
        "This is purely visual — node criticality is NOT used in any SLO math. "
        "Only edge criticality (hard/soft) affects calculations."
    ),
    detail="""\
Node (service) criticality describes **business importance**:

| Color | Criticality | Meaning |
|---|---|---|
| 🔴 Red | High | Business-critical service |
| 🟠 Orange | Medium | Important but not critical |
| 🟢 Green | Low | Supporting / non-critical |

**Important:** This is used **only for visualization**. It does NOT affect SLO calculations.

Edge (dependency) criticality (`hard`/`soft`/`degraded`) is what drives the math. A high-criticality node with all soft edges contributes nothing to composite availability.
""",
)

CIRCULAR_DEPS_TARJAN = Concept(
    title="Circular Dependency Detection",
    icon="🔄",
    summary=(
        "Tarjan's algorithm finds strongly connected components (SCCs) — groups of services that form cycles. "
        "It runs automatically after every graph ingestion in O(V+E) time. "
        "Cycles don't block ingestion; they're flagged as alerts for architectural review."
    ),
    detail="""\
**Tarjan's algorithm** finds **Strongly Connected Components** — groups of nodes where you can reach any node from any other by following directed edges.

**How it works:** Depth-first search tracking discovery order (`index`) and the lowest reachable ancestor (`lowlink`). When `lowlink == index`, you've found an SCC root — pop the stack to get the full cycle.

**Key properties:**
- **O(V+E)** time — linear in graph size
- **Non-blocking** — graph ingestion succeeds, cycles flagged for review
- Only multi-node SCCs are reported as cycles (single-node SCCs are normal)

**SLO impact:** Cycles are contracted into **supernodes** — the cycle is treated as one unit with joint availability equal to the weakest member:

```
[checkout] -> [A] <-> [B]   becomes   [checkout] -> [(A+B) supernode]
composite = checkout_avail x min(A_avail, B_avail)
```
""",
)

# ---------------------------------------------------------------------------
# Step 3: SLO Recommendations
# ---------------------------------------------------------------------------

ERROR_RATE_VS_BUDGET = Concept(
    title="Error Rate vs Error Budget",
    icon="💰",
    summary=(
        "Error rate is a measurement (% of requests failing now). "
        "Error budget is an allowance (how many errors you can afford and still meet your SLO). "
        "A 99.9% SLO gives you 43.2 minutes of downtime per month — if you're down 50 min, you've burned 115% of budget."
    ),
    detail="""\
**Error Rate** = percentage of requests failing right now.
**Error Budget** = how many errors you can afford and still meet your SLO.

```
SLO target 99.9%  ->  error budget = 0.1%
```

Two views of the same budget:

| View | 99.9% SLO over 30 days |
|---|---|
| Time-based | 43,200 min x 0.1% = **43.2 min of downtime** |
| Request-based | 1M requests x 0.1% = **1,000 failed requests** |

If you're down 50 min -> you burned 50/43.2 = **115% of budget (breach)**.
""",
)

RECOMMENDATION_TIERS = Concept(
    title="Recommendation Tiers",
    icon="🎯",
    summary=(
        "Three tiers represent different risk tolerances: Conservative (safest, for customer SLAs), "
        "Balanced (internal team targets), and Aggressive (stretch goals). "
        "Conservative and Balanced are capped by the composite availability bound; Aggressive is not."
    ),
    detail="""\
| Tier | Percentile | Capped by composite? | Who it's for |
|---|---|---|---|
| **Conservative** | p0.1 (worst 0.1% of days) | Yes | Customer SLAs, legal |
| **Balanced** | p1 (worst 1% of days) | Yes | Internal team targets |
| **Aggressive** | p5 (worst 5% of days) | **No** | Stretch goals |

**Why aggressive isn't capped:** It's aspirational — shows what the service achieved independent of dependency risk. Useful for "if we commit to this, we need to fix dep X."

**Latency tiers** follow a similar pattern:

| Tier | Based on | Buffer |
|---|---|---|
| Conservative | p999 | +5% |
| Balanced | p99 | +5% |
| Aggressive | p95 | none |
""",
)

ERROR_BUDGET_CONSUMPTION = Concept(
    title="Error Budget Consumption",
    icon="🔥",
    summary=(
        "Consumption = dep_unavailability / your_error_budget. "
        "A dependency at 99.5% against a 99.9% SLO consumes 500% of your budget — making the SLO impossible. "
        "If total consumption exceeds 100%, the SLO is mathematically unachievable."
    ),
    detail="""\
```
consumption = (1 - dep_availability) / (1 - slo_target)
```

**Example** with SLO target = 99.9% (error budget = 0.1%):

| Dep | Availability | Consumption |
|---|---|---|
| payment-service | 99.5% | 0.5% / 0.1% = **500%** |
| fraud-service | 99.8% | 0.2% / 0.1% = **200%** |
| recommendation-service (soft) | 97.0% | **not computed** (excluded) |

**Golden rule:** If total consumption across all hard deps exceeds 100%, your SLO is **mathematically unachievable**. Options: improve dep reliability, make deps async/soft, or lower your SLO target.
""",
)

COLD_START_TIMELINE = Concept(
    title="Cold Start & SLO Timeline",
    icon="⏱️",
    summary=(
        "New services go through a cold start period: Day 0-7 (low confidence, archetype-based SLOs), "
        "Day 7-30 (warming, increasing confidence), Day 30+ (mature baseline, high confidence >0.85). "
        "The system can even provide a theoretical SLO ceiling before deployment using dependency data alone."
    ),
    detail="""\
| Phase | Data | Confidence | Strategy |
|---|---|---|---|
| **Pre-deploy** | 0 days | Low (theory) | Dependency-only theoretical max |
| **Cold start** | 0-7 days | Low (0.4-0.6) | Archetype-based or manual temporary SLO |
| **Warming** | 7-30 days | Medium | Increasing confidence daily |
| **Mature** | 30+ days | High (0.85+) | Full recommendation with all tiers |

**Pre-deployment insight:** You can get a theoretical SLO ceiling before writing any code! If your deps limit you to 99.5%, promising 99.99% is impossible regardless of implementation quality.
""",
)

# ---------------------------------------------------------------------------
# Step 5: Modify SLO
# ---------------------------------------------------------------------------

RISK_CLASSIFICATION = Concept(
    title="Risk Classification Thresholds",
    icon="⚠️",
    summary=(
        "Error budget consumption is classified as LOW (<20%, healthy), MODERATE (20-30%, watch), "
        "or HIGH (>30%, priority for investment). A single dep consuming >30% is a reliability risk; "
        "total consumption >100% means guaranteed SLO breach."
    ),
    detail="""\
| Risk Level | Consumption | Action |
|---|---|---|
| **LOW** | < 20% | Healthy, no action needed |
| **MODERATE** | 20-30% | Watch and monitor |
| **HIGH** | > 30% | Priority for reliability investment |

**Operational thresholds:**

| Metric | Threshold | Action |
|---|---|---|
| Error rate | > 1% | Likely incident |
| Budget used in first 2 weeks | > 70% | Burning too fast |
| Total consumption | > 100% | SLO breach guaranteed |
| Any single dep | > 30% | High risk |
| Total consumption | > 150% | Critical emergency |
""",
)

BURN_RATE = Concept(
    title="Burn Rate",
    icon="📈",
    summary=(
        "Burn rate = observed error rate / acceptable error rate. "
        "A burn rate of 5x means you'll exhaust your monthly error budget in 6 days. "
        "It normalizes the signal across services with different SLO thresholds."
    ),
    detail="""\
```
Burn Rate = observed error rate / acceptable error rate (from SLO)
```

**Example:** SLO allows 1% errors, seeing 5% -> burn rate = 5x.

| Burn Rate | Budget exhausted in | Meaning |
|---|---|---|
| 1x | 30 days | Exactly sustainable |
| 2x | 15 days | Double speed |
| 10x | 3 days | Critical |
| 14.4x | ~2 days | Exhausts 2% in 1 hour |

**Google SRE multi-window alerting:**

| Burn Rate | Window | Severity |
|---|---|---|
| 14.4x | 1 hour | Page immediately |
| 6x | 6 hours | Page urgently |
| 3x | 1 day | Ticket |
| 1x | 3 days | No alert |

**Why it matters:** A 0.1% error rate sounds fine, but if your SLO allows only 0.01%, you're burning at 10x.
""",
)

# ---------------------------------------------------------------------------
# Step 6: Impact Analysis
# ---------------------------------------------------------------------------

TOTAL_CONSUMPTION_RULE = Concept(
    title="Total Consumption > 100% = Unachievable",
    icon="🚫",
    summary=(
        "If the total error budget consumption across all hard dependencies exceeds 100%, "
        "the SLO target is mathematically unachievable. "
        "You must either improve dep reliability, make deps async/soft, or lower the SLO target."
    ),
    detail="""\
**The golden rule of SLO math:**

> If total error budget consumption across all hard dependencies exceeds 100%, your SLO is **mathematically unachievable** with the current dependency graph.

**Example** — payment-service, SLO = 99.9%:

| Source | Availability | Consumption |
|---|---|---|
| Database | 99.95% | 50% |
| Auth service | 99.99% | 10% |
| Fraud detection | 99.8% | 200% |
| Self (intrinsic) | -- | 20% |
| **Total** | | **280%** |

Budget is 100%, consuming 280%. **Fraud detection is the bottleneck.**

**Remediation options:**
1. Make fraud detection a **soft dep** -> removes 200% -> total: 80%
2. Improve fraud detection to 99.95% -> drops to 50% -> total: 130% (still over)
3. Lower SLO target to 99.8% (budget = 0.2%) -> halves all percentages
""",
)

RELIABILITY_LADDER = Concept(
    title="The Reliability Ladder",
    icon="🪜",
    summary=(
        "Small differences in availability compound dramatically at high levels. "
        "Going from 99.9% to 99.5% is only 0.4% difference but means 5x error budget consumption. "
        "Going from 99.9% to 99.0% is 10x consumption."
    ),
    detail="""\
```
100.00% --- Perfection (unrealistic)
 99.99% --- Four nines (premium tier)
 99.95% --- Healthy dep (50% consumption for 99.9% SLO)
 99.90% --- Your SLO target (100% = break-even)
 99.50% --- Risky dep (500% consumption)
 99.00% --- Unstable (1000% consumption)
```

**Key insight:** Small absolute differences have enormous relative impact:

| From -> To | Absolute diff | Budget impact |
|---|---|---|
| 99.9% -> 99.5% | 0.4% | **5x** consumption |
| 99.9% -> 99.0% | 0.9% | **10x** consumption |
| 99.99% -> 99.9% | 0.09% | **10x** consumption |
""",
)

# ---------------------------------------------------------------------------
# Circular Dependency Remediation (conditional, shown after cycle detection)
# ---------------------------------------------------------------------------

CIRCULAR_DEP_REMEDIATION = Concept(
    title="Circular Dependency Remediation",
    icon="🔧",
    summary=(
        "Three strategies to break cycles: (1) introduce an async boundary (event bus) so one direction becomes non-blocking, "
        "(2) extract shared logic into a library both services depend on, "
        "(3) merge tightly-coupled services if the cycle is fundamental."
    ),
    detail="""\
**Option A: Async boundary** — Make one direction event-driven:
```
BEFORE: auth <-sync-> user (cycle!)
AFTER:  auth -sync-> user -async-> [event-bus] -async-> auth
```

**Option B: Shared library** — Extract common logic:
```
BEFORE: auth <-> user (circular)
AFTER:  auth -> [shared-auth-lib] <- user (no cycle)
```

**Option C: Merge services** — If the cycle is fundamental:
```
BEFORE: auth <-> user
AFTER:  [auth-user-service] (single service, no cycle)
```

**SLO impact of cycles:** Strongly connected components are contracted into **supernodes**. The cycle is treated as one unit with joint availability = weakest member. This is conservative but safe.
""",
)

CYCLE_CONTRACTION = Concept(
    title="Cycle Contraction into Supernodes",
    icon="🔮",
    summary=(
        "For SLO calculations, cycles are contracted into supernodes — the entire cycle is treated as one unit "
        "with joint availability equal to the weakest member. "
        "This makes the graph acyclic so composite math (serial multiplication) works correctly."
    ),
    detail="""\
When a cycle is detected during SLO calculation:

```
Original:  [checkout] -> [A] <-> [B]
Contracted: [checkout] -> [(A+B) supernode]

composite = checkout_avail x min(A_avail, B_avail)
```

**Why contraction?** Composite availability uses serial multiplication, which requires a DAG (directed acyclic graph). Cycles break this assumption, so we:

1. Detect cycles via Tarjan's algorithm
2. Replace each cycle with a single supernode
3. Supernode availability = `min(member availabilities)`
4. Run composite math on the now-acyclic graph

This is a conservative estimate — the actual joint availability could be slightly better if failures are correlated, but `min()` is the safe bound.
""",
)

# ---------------------------------------------------------------------------
# Step -> Concept mapping
# ---------------------------------------------------------------------------

STEP_CONCEPTS: dict[int, list[Concept]] = {
    1: [HARD_VS_SOFT_DEPS, MULTI_SOURCE_DISCOVERY],
    2: [COMPOSITE_AVAILABILITY, NODE_CRITICALITY_COLORS, CIRCULAR_DEPS_TARJAN],
    3: [ERROR_RATE_VS_BUDGET, RECOMMENDATION_TIERS, ERROR_BUDGET_CONSUMPTION, COLD_START_TIMELINE],
    5: [RISK_CLASSIFICATION, BURN_RATE],
    6: [TOTAL_CONSUMPTION_RULE, RELIABILITY_LADDER],
}

CIRCULAR_DEP_CONCEPTS: list[Concept] = [CIRCULAR_DEP_REMEDIATION, CYCLE_CONTRACTION]

ALL_CONCEPTS: list[Concept] = [
    HARD_VS_SOFT_DEPS,
    MULTI_SOURCE_DISCOVERY,
    COMPOSITE_AVAILABILITY,
    NODE_CRITICALITY_COLORS,
    CIRCULAR_DEPS_TARJAN,
    ERROR_RATE_VS_BUDGET,
    RECOMMENDATION_TIERS,
    ERROR_BUDGET_CONSUMPTION,
    COLD_START_TIMELINE,
    RISK_CLASSIFICATION,
    BURN_RATE,
    TOTAL_CONSUMPTION_RULE,
    RELIABILITY_LADDER,
    CIRCULAR_DEP_REMEDIATION,
    CYCLE_CONTRACTION,
]

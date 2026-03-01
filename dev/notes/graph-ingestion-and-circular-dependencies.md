# Graph Ingestion and Circular Dependencies Deep Dive

> **Date:** 2026-03-01
> **Topics:** Production graph ingestion workflow, SLO timing, Tarjan's algorithm, circular dependency handling

---

## Table of Contents

- [Graph Ingestion in Production](#graph-ingestion-in-production)
- [SLO Setting Timeline](#slo-setting-timeline)
- [Circular Dependencies Explained](#circular-dependencies-explained)
- [Real-World Scenarios](#real-world-scenarios)

---

## Graph Ingestion in Production

### Multi-Source Auto-Discovery Architecture

The system is designed for **automated discovery**, NOT manual input. Graph ingestion happens through multiple parallel sources:

| Source | Method | Confidence | Priority | Frequency |
|--------|--------|------------|----------|-----------|
| **Manual API** | Explicit declarations via API | 1.0 | Highest | On-demand |
| **Service Mesh** | Istio/Linkerd sidecar telemetry | 0.9 | High | Real-time |
| **OTel Service Graph** | Trace-based discovery from Prometheus | 0.7 | Medium | Every 15 min |
| **Kubernetes** | Manifest parsing | 0.5 | Lowest | On manifest change |

### Primary Auto-Discovery: OTel Service Graph

**File:** `src/infrastructure/integrations/otel_service_graph.py`

```python
# Background task runs every 15 minutes
async def fetch_service_graph() -> DependencyGraphIngestRequest:
    # Query Prometheus for traces_service_graph_request_total metric
    query = "traces_service_graph_request_total"

    # Parse client/server labels to extract dependencies
    for metric in result:
        client = metric_labels.get("client")  # Source service
        server = metric_labels.get("server")  # Target service

        # Auto-create edge: client → server
        edges.append(EdgeDTO(source=client, target=server))
```

**Key behaviors:**
- **Auto-discovery:** Services appear automatically when they start making/receiving calls
- **No deployment required:** First OTel trace creates the dependency edge
- **15-minute latency:** New services discovered within next sync window

### New Service Auto-Discovery

**File:** `src/application/use_cases/ingest_dependency_graph.py:106-129`

When an edge references an unknown service:

```python
# Step 2: Identify unknown services referenced in edges
unknown_service_ids = set()

for edge_dto in request.edges:
    if edge_dto.source not in service_id_map:
        unknown_service_ids.add(edge_dto.source)
    if edge_dto.target not in service_id_map:
        unknown_service_ids.add(edge_dto.target)

# Step 3: Auto-create placeholder services
for unknown_id in unknown_service_ids:
    service = Service(
        service_id=unknown_id,
        metadata={"source": "auto_discovered"},
        criticality=Criticality.MEDIUM,
        team=None,
        discovered=True  # Flag as auto-discovered
    )
    services_to_upsert.append(service)
```

**Result:** No manual intervention needed. Unknown services are created automatically with:
- `discovered=True` flag
- Default `criticality=MEDIUM`
- Metadata tag `"auto_discovered"`
- Later enrichable via manual API calls

### Multi-Source Conflict Resolution

**File:** `src/domain/services/edge_merge_service.py`

When the same edge (A → B) is reported by multiple sources:

```python
PRIORITY_MAP = {
    DiscoverySource.MANUAL: 1.0,
    DiscoverySource.SERVICE_MESH: 0.9,
    DiscoverySource.OTEL_SERVICE_GRAPH: 0.7,
    DiscoverySource.KUBERNETES: 0.5,
}

# Highest-priority source's attributes win
# All source observations are tracked for audit
```

**Example:**
- OTel discovers: `checkout → payment` (protocol unknown, confidence 0.7)
- Manual override: `checkout → payment` (protocol=gRPC, timeout=5000ms, confidence 1.0)
- **Result:** Manual attributes stored, OTel observation count tracked

### Edge Staleness Detection

**Background task:** Daily at 2:00 AM UTC

```python
# Mark edges as stale if not refreshed in 7 days
stale_edges = edges.filter(last_observed_at < now() - 7 days)
stale_edges.update(is_stale=True)
```

**Query behavior:**
- `GET /services/{id}/dependencies` excludes stale edges by default
- Pass `include_stale=true` to see historical dependencies
- Staleness indicates dependency may no longer exist

### Why Auto-Discovery Beats Manual Selection

| Concern | Manual-Only Risk | Auto-Discovery Solution |
|---------|------------------|------------------------|
| **Scale** | Unsustainable at 500-5000 services | Background sync handles any scale |
| **Accuracy** | Static declarations go stale | Runtime observation always current |
| **Coverage** | Humans forget services | OTel sees all instrumented calls |
| **Shadow dependencies** | Undocumented integrations missed | Traces reveal actual call patterns |
| **Velocity** | Can't keep up with daily deployments | Auto-adapts to topology changes |

**Verdict:** Auto-discovery is the production standard (Netflix, Google SRE pattern). Manual is for enrichment/override only.

---

## SLO Setting Timeline

### The Full Lifecycle

```
Day 0: Service Deployment
├─ Code deployed to production
├─ OTel instrumentation active
├─ Starts emitting metrics/traces
└─ Auto-discovered in dependency graph (within 15 min)

Day 0-7: Cold Start Period
├─ Insufficient data for high-confidence recommendations
├─ System CAN generate SLO, but with LOW confidence
├─ Flags: "cold_start": true, "data_quality": "insufficient"
└─ Mitigation options:
    ├─ 1. Archetype-based SLO (similar services)
    ├─ 2. Manual temporary SLO
    └─ 3. Dependency-only theoretical maximum

Day 7-30: Warming Period
├─ Sufficient data for basic recommendations
├─ Confidence increases daily as data accumulates
└─ System provides "Balanced" tier recommendations

Day 30+: Mature Baseline
├─ Full 30-day window available (PRD requirement)
├─ High-confidence recommendations (>0.85)
└─ All three tiers valid (Conservative/Balanced/Aggressive)
```

### Cold-Start Mitigation Strategies

#### Strategy 1: Archetype-Based SLO (Recommended)

**When:** New version of existing service deployed

```bash
GET /api/v1/services/checkout-service-v2/slo-recommendations

Response:
{
  "service_id": "checkout-service-v2",
  "cold_start": true,
  "archetype_match": "checkout-service-v1",
  "data_days": 2,
  "confidence_score": 0.45,

  "balanced_tier": {
    "availability": 0.999,
    "latency_p99_ms": 450,
    "note": "Based on archetype: checkout-service-v1 (30-day baseline)"
  },

  "recommendation": "Accept archetype-based SLO temporarily. " +
                    "Re-evaluate after 14 days when sufficient data available."
}
```

**How it works:**
- System finds similar services by:
  - Name similarity (e.g., `-v1` vs `-v2`)
  - Team ownership
  - Dependency pattern similarity
  - Technology stack (language, framework)
- Uses similar service's 30-day performance as baseline
- Flags clearly as archetype-based
- Auto-triggers re-evaluation when sufficient data exists

#### Strategy 2: Manual Temporary SLO

**When:** Completely new service with no similar archetype

```bash
POST /api/v1/services/new-fraud-detection/slos
{
  "source": "manual",
  "availability": 0.995,  # Conservative starting point
  "latency_p99_ms": 500,
  "temporary": true,
  "expires_at": "2026-03-30",
  "reason": "New service - using conservative SLO until 30-day baseline"
}
```

**System behavior:**
- Stores manual SLO as active target
- Sets expiration date (typically Day 30)
- Monitors actual performance against manual target
- Auto-triggers re-evaluation on expiration
- Sends notification if actual performance diverges significantly

#### Strategy 3: Dependency-Only SLO (Pre-Deployment!)

**When:** Service not yet deployed, but dependencies known

```bash
# BEFORE deployment: Declare dependencies manually
POST /api/v1/services/dependencies
{
  "source": "manual",
  "nodes": [
    {"service_id": "new-payment-service", "team": "payments"}
  ],
  "edges": [
    {
      "source": "new-payment-service",
      "target": "stripe-api",
      "attributes": {"communication_mode": "sync", "criticality": "critical"}
    },
    {
      "source": "new-payment-service",
      "target": "postgres-db",
      "attributes": {"communication_mode": "sync", "criticality": "critical"}
    }
  ]
}

# Request theoretical SLO BEFORE deployment
GET /api/v1/services/new-payment-service/slo-recommendations

Response:
{
  "service_id": "new-payment-service",
  "pre_deployment": true,
  "data_days": 0,

  "balanced_tier": {
    "availability": 0.994,  # Computed from dependencies ONLY!
    "composite_bound": {
      "max_achievable": 0.994,
      "bottleneck": "stripe-api",
      "calculation": "postgres(0.9999) × stripe-api(0.995) = 0.9949"
    },
    "note": "Theoretical maximum based on dependency graph. " +
            "No historical data. Assumes perfect implementation (no bugs)."
  }
}
```

**Key insight:** You get a **theoretical SLO ceiling** before deployment!

**Use case:**
- Architecture review: "Can we achieve 99.99% availability?"
- Answer: "No, stripe-api limits you to 99.5%"
- Decision: Add fallback payment provider or accept lower target

### Timeline Comparison Table

| Approach | Data Required | Confidence | Best Use Case |
|----------|---------------|------------|---------------|
| **Dependency-only** | 0 days (pre-deploy) | Low (theory only) | Architecture planning |
| **Archetype-based** | 0-7 days (similar service) | Medium (0.4-0.6) | New version of existing service |
| **Manual temporary** | 0 days (SRE judgment) | Low (subjective) | Completely new service type |
| **Historical baseline** | 30+ days | High (0.85+) | Production-ready recommendation |

### Cold-Start in Production: Real Example

```
Scenario: Deploying new-checkout-service-v3

Day 0 (Deploy):
├─ Deploy to production
├─ OTel auto-discovers within 15 min
└─ GET /slo-recommendations returns:
    {
      "archetype_match": "checkout-service-v2",
      "cold_start": true,
      "balanced_tier": {"availability": 0.999},
      "confidence": 0.45
    }

Day 1-7:
├─ Accumulating data
├─ Confidence increasing: 0.45 → 0.50 → 0.55 → 0.60
└─ SRE can monitor actual vs. archetype performance

Day 14:
├─ Sufficient data for medium-confidence recommendation
├─ confidence: 0.70
└─ System suggests re-evaluation

Day 30:
├─ Full baseline established
├─ confidence: 0.88
├─ System auto-triggers re-evaluation
└─ New recommendation based on actual 30-day performance
```

---

## Circular Dependencies Explained

### Tarjan's Algorithm: Intuitive Walkthrough

**Goal:** Find **Strongly Connected Components (SCCs)** - groups of nodes where you can reach any node from any other node.

**Think:** "If I start at node A, can I eventually loop back to A by following directed edges?"

#### Visual Example 1: Simple Cycle

```
   ┌─────────────────┐
   │                 ▼
[api-gateway] ─→ [auth-service]
                      │
                      ▼
               [user-service] ─┐
                   ▲           │
                   └───────────┘
```

**Step-by-step execution:**

```
1. Start DFS from api-gateway:
   api-gateway: index=0, lowlink=0, on_stack=True

2. Follow edge to auth-service:
   auth-service: index=1, lowlink=1, on_stack=True

3. Follow edge to user-service:
   user-service: index=2, lowlink=2, on_stack=True

4. user-service has self-loop:
   - See user-service already on stack
   - lowlink[user-service] = min(2, index[user-service]) = 2
   - Still 2, no change

5. user-service points back to auth-service:
   - auth-service is on stack
   - lowlink[user-service] = min(2, index[auth-service]) = min(2, 1) = 1

6. Backtrack to auth-service:
   - lowlink[auth-service] = min(1, lowlink[user-service]) = min(1, 1) = 1
   - lowlink == index → auth-service is SCC root!

7. Pop stack until auth-service:
   - Pop: user-service
   - Pop: auth-service
   - SCC = [user-service, auth-service]

8. api-gateway has no back-edges:
   - lowlink=0, index=0 → Single-node SCC
   - Filtered out (only multi-node SCCs are cycles)

Result: Cycle detected: [auth-service, user-service]
```

#### Visual Example 2: Complex Multi-Cycle

```
     ┌──────────────┐
     │              ▼
[A] ─→ [B] ─→ [C] ─→ [D]
 ▲      │      ▲      │
 │      └──────┘      │
 │                    │
 └────────────────────┘

Edge list:
A→B, B→C, C→D, D→A  (outer cycle)
B→C, C→B            (inner cycle)
```

**Tarjan's discovers:**

```python
SCC found: [A, B, C, D]  # One big SCC!
```

**Why one SCC?** Because you can reach any node from any other:
- A → B → C → D → A ✅
- B → C → B ✅ (inner cycle)
- C → D → A → B → C ✅
- D → A → B → C → D ✅

All nodes mutually reachable = one strongly connected component.

#### Visual Example 3: No Cycle (DAG)

```
[api-gateway] ─→ [auth-service]
      │               │
      ▼               ▼
[checkout] ─→ [payment-service]
```

**Tarjan's discovers:**

```python
SCCs found:
[
  [api-gateway],      # Single-node SCC
  [auth-service],     # Single-node SCC
  [checkout],         # Single-node SCC
  [payment-service]   # Single-node SCC
]

# Filter: len(scc) > 1
cycles = []  # Empty! No cycles.
```

### Implementation Details

**File:** `src/domain/services/circular_dependency_detector.py`

**Key features:**
- **Iterative implementation** (not recursive) - avoids Python recursion limit
- **Time complexity:** O(V + E) - linear in graph size
- **Space complexity:** O(V) - tracks index/lowlink per node
- **Reusable:** Each call to `detect_cycles()` resets state

```python
def detect_cycles(self, adjacency_list: dict[UUID, list[UUID]]) -> list[list[UUID]]:
    # Returns only SCCs with size > 1 (actual cycles)
    cycles = [scc for scc in sccs if len(scc) > 1]
    return cycles
```

### When Tarjan's Runs

**File:** `src/application/use_cases/detect_circular_dependencies.py`

**Trigger:** After every graph ingestion

```python
async def execute(self) -> list[CircularDependencyAlert]:
    # 1. Load full graph as adjacency list
    adjacency_list = await self.dependency_repository.get_adjacency_list()

    # 2. Run Tarjan's algorithm (synchronous, CPU-bound)
    cycles = self.detector.detect_cycles(adjacency_list)

    # 3. Create alerts for NEW cycles only
    for cycle in cycles:
        service_ids = await self._convert_uuids_to_service_ids(cycle)

        # Check if alert already exists (deduplication)
        exists = await self.alert_repository.exists_for_cycle(service_ids)

        if not exists:
            alert = CircularDependencyAlert(
                cycle_path=service_ids,
                status=AlertStatus.OPEN
            )
            await self.alert_repository.create(alert)

    return created_alerts
```

**Performance:** O(V+E) on 500 services with 1000 edges takes ~100ms (fast enough to run synchronously)

---

## Real-World Scenarios

### Scenario 1: Architectural Anti-Pattern (Most Common)

**Example:** Auth service and user service have bidirectional dependency

```
[auth-service] ─→ [user-service]
     ▲                  │
     └──────────────────┘
```

**System response:**

```json
POST /api/v1/services/dependencies

Response:
{
  "nodes_upserted": 2,
  "edges_upserted": 2,
  "circular_dependencies": [
    {
      "cycle_path": ["auth-service", "user-service", "auth-service"],
      "severity": "high",
      "detected_at": "2026-03-01T10:30:00Z",
      "recommendation": "Break cycle by introducing async boundary or shared library"
    }
  ],
  "warnings": [
    "Circular dependencies detected. Graph stored, but SLO calculations " +
    "will contract cycle into supernode for composite availability math."
  ]
}
```

**Alert stored in database:**

```sql
SELECT * FROM circular_dependency_alerts;

id       | cycle_path                                 | status | detected_at
---------|-------------------------------------------|--------|------------
uuid-123 | ["auth-service","user-service","auth..."] | open   | 2026-03-01 10:30:00
```

**SRE remediation options:**

```bash
# Option A: Break with async boundary
# Make one direction async (event-driven)

BEFORE:
auth-service ─sync─→ user-service
     ▲                     │
     └─────sync────────────┘

AFTER:
auth-service ─sync─→ user-service
     ▲                     │
[event-bus] ←─async────────┘
     │
     └─async─→ auth-service

# No cycle! user→auth is now async through event bus
```

```bash
# Option B: Extract shared logic

BEFORE:
auth-service ↔ user-service
(circular dependency)

AFTER:
auth-service ─→ [shared-auth-lib] ←─ user-service
(both depend on library, not each other - no cycle!)
```

```bash
# Option C: Merge services (if cycle is fundamental)

BEFORE:
auth-service ↔ user-service

AFTER:
[auth-user-service]  # Combined service
(no cycle - single service)
```

**Acknowledging the fix:**

```bash
PATCH /api/v1/alerts/{alert_id}
{
  "status": "resolved",
  "resolution_notes": "Introduced async event boundary via Kafka. " +
                      "User updates now published to auth-events topic.",
  "acknowledged_by": "sre-team@company.com"
}
```

### Scenario 2: Legitimate Cycle (Rare but Valid)

**Example:** Health check endpoints create cycles

```
[api-gateway] ─→ [health-service]
     ▲                  │
     └──────────────────┘
      (health check)
```

**System response:**

```json
{
  "circular_dependencies": [
    {
      "cycle_path": ["api-gateway", "health-service", "api-gateway"],
      "severity": "low",
      "notes": "Health check endpoints may create cycles but are non-critical paths"
    }
  ]
}
```

**SRE action: Acknowledge as acceptable risk**

```bash
PATCH /api/v1/alerts/{alert_id}
{
  "status": "acknowledged",
  "resolution_notes": "Health check cycle is acceptable architectural pattern. " +
                      "Health endpoints excluded from SLO calculations. " +
                      "Non-critical path with circuit breaker protection.",
  "acknowledged_by": "platform-sre@company.com"
}
```

**Configuration to exclude from SLO:**

```bash
# Mark edge as non-critical
POST /api/v1/services/dependencies
{
  "source": "manual",
  "edges": [
    {
      "source": "health-service",
      "target": "api-gateway",
      "attributes": {
        "criticality": "soft",  # Not critical path
        "exclude_from_slo": true
      }
    }
  ]
}
```

### Scenario 3: SLO Calculation with Cycles

**From PRD:** "Contract strongly connected components into supernodes for SLO computation"

**Example:**

```
Original graph:
[checkout] ─→ [A] ─→ [B]
              ▲      │
              └──────┘
              (cycle: A↔B)

After cycle contraction:
[checkout] ─→ [(A+B) supernode]

SLO Calculation:
- Treat A+B as ONE unit
- Measure JOINT availability of A+B together
- Composite: checkout_avail × (A+B)_joint_avail
```

**Implementation concept:**

```python
# Simplified from availability calculator
def compute_composite_availability(service_id: str):
    # 1. Get dependency subgraph
    subgraph = get_dependencies(service_id, depth=3)

    # 2. Detect cycles
    cycles = tarjan_detect_cycles(subgraph)

    if cycles:
        # 3. Contract each cycle into supernode
        for cycle in cycles:
            # Measure availability of ENTIRE cycle as one unit
            # (cannot achieve better than weakest link)
            cycle_services = ["A", "B"]
            cycle_availability = min(
                measure_availability("A"),
                measure_availability("B")
            )

            # Replace cycle with single node in graph
            replace_cycle_with_supernode(cycle, cycle_availability)

    # 4. Compute composite on now-acyclic graph
    return serial_multiplication(subgraph)
```

**Real output example:**

```json
GET /api/v1/services/checkout/slo-recommendations

Response:
{
  "composite_bound": {
    "max_achievable": 0.9945,
    "calculation": "checkout_self(0.999) × service_AB_cycle(0.9955)",
    "bottleneck": "service_AB_cycle",
    "notes": "Services A and B form circular dependency. " +
             "Treated as single unit with joint availability 0.9955."
  },
  "dependency_warnings": [
    "Circular dependency detected: A ↔ B. " +
    "Contracted into supernode for SLO calculation. " +
    "Consider breaking cycle for more granular reliability targets."
  ]
}
```

### Scenario 4: False Positive from Bad Config

**Example:** Manual config declares non-existent cycle

```yaml
# Incorrect manual config
payment-service:
  dependencies:
    - checkout-service  # ← WRONG! Payment shouldn't depend on checkout
```

**Actual runtime (from OTel traces):**

```
checkout ─→ payment
(No reverse edge observed!)
```

**System response:**

```json
POST /api/v1/services/dependencies
{
  "source": "manual",
  "edges": [
    {"source": "payment", "target": "checkout"}  # Bad config
  ]
}

Response:
{
  "circular_dependencies": [
    {
      "cycle_path": ["checkout", "payment", "checkout"],
      "source": "manual",
      "confidence": 1.0
    }
  ],
  "warnings": [
    "GRAPH DIVERGENCE DETECTED!",
    "Manual config declares: payment→checkout",
    "OTel traces show: checkout→payment ONLY",
    "No traces observed for payment→checkout",
    "Recommendation: Verify manual config or check if code path is unreachable"
  ]
}
```

**Auto-remediation workflow:**

```python
# Background task: Graph divergence detector
manual_edges = get_edges(source="manual")
otel_edges = get_edges(source="otel_service_graph")

divergence = find_edges_in_manual_not_in_otel(manual_edges, otel_edges)

if divergence:
    for edge in divergence:
        create_alert(
            type="graph_divergence",
            edge=edge,
            message=f"{edge.source}→{edge.target} declared manually " +
                    f"but not observed in {7} days of traces",
            recommendation="Verify config or check if code path is dead code"
        )
```

**SRE investigation:**

```bash
# 1. Check if edge ever existed
SELECT * FROM service_dependencies
WHERE source_service_id='payment' AND target_service_id='checkout';

# Result: Last observed 45 days ago (stale!)

# 2. Remove stale manual declaration
DELETE FROM service_dependencies
WHERE source='manual'
  AND source_service_id='payment'
  AND target_service_id='checkout';

# 3. Cycle alert auto-resolves (no longer forms cycle)
```

### Scenario 5: Multi-Cycle Complex Graph

**Example:** Service mesh with multiple intertwined cycles

```
     ┌─────────┐
     │         ▼
[A] ─→ [B] ─→ [C]
 ▲      │      │
 │      ▼      ▼
 │     [D] ←─ [E]
 │      │      ▲
 └──────┴──────┘
```

**Tarjan's output:**

```python
Cycles detected:
[
  [A, B, D],     # Cycle 1: A→B→D→A
  [C, E, D, B]   # Cycle 2: C→E→D→B→C
]
```

**Wait, overlapping cycles?** Tarjan's actually finds **maximal SCCs**, so:

```python
Actual output (maximal SCCs):
[
  [A, B, C, D, E]  # ONE big SCC containing all nodes
]
```

**System response:**

```json
{
  "circular_dependencies": [
    {
      "cycle_path": ["A", "B", "C", "D", "E", "A"],
      "severity": "critical",
      "size": 5,
      "notes": "Large strongly connected component detected. " +
               "Multiple intertwined cycles. Requires architectural review.",
      "recommendation": "Identify core services and break cycles with " +
                        "async boundaries, event-driven patterns, or service merging."
    }
  ]
}
```

**Architectural fix:**

```bash
# Identify core vs. auxiliary services
Core: A, B (critical path)
Auxiliary: C, D, E (supporting)

# Introduce async boundaries
BEFORE:
A ↔ B ↔ C ↔ D ↔ E (all sync, all cycles)

AFTER:
A ─sync→ B  (core path, no cycle)
B ─async→ [Event Bus]
      │
      ├─async→ C
      ├─async→ D
      └─async→ E

C, D, E ─async→ [Event Bus] ─async→ A

# Result: No sync cycles! All async boundaries break dependency loops.
```

---

## Summary: Production Best Practices

### Graph Ingestion
1. ✅ **Auto-discovery primary:** OTel Service Graph, Service Mesh
2. ✅ **Manual override only:** For enrichment (timeout, retry, protocol)
3. ✅ **Multi-source confidence:** Track all sources, highest priority wins
4. ✅ **Staleness detection:** Auto-flag edges not refreshed in 7 days
5. ✅ **New services:** Auto-created on first observed call (15-min latency)

### SLO Timing
1. ✅ **Pre-deployment:** Theoretical max from dependencies only
2. ✅ **Day 0-7:** Cold-start (archetype or manual temporary SLO)
3. ✅ **Day 7-30:** Warming period (increasing confidence)
4. ✅ **Day 30+:** Mature baseline (high confidence >0.85)

### Circular Dependencies
1. ✅ **Detection:** Automatic via Tarjan's O(V+E) after every ingestion
2. ✅ **Storage:** Alerts with open/acknowledged/resolved status
3. ✅ **SLO impact:** Cycles contracted into supernodes
4. ✅ **No blocking:** Graph ingestion succeeds, cycles flagged for review
5. ✅ **Remediation:** Async boundaries, shared libs, or service merging

**Key Insight:** The system is designed for resilience and automation. Cycles are detected, handled gracefully, and don't block normal operations. Manual intervention is for architectural fixes, not day-to-day operations.

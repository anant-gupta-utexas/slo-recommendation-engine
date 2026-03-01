# SLO Engine — Personal Reference Notes

---

## Core Concepts

### Error Rate vs Error Budget

**Error Rate** is a measurement — the percentage of requests failing right now.

```
1% error rate   = 1 in 100 requests fails
0.1% error rate = 1 in 1,000 requests fails
```

At 1,000 req/min: 1% = 10 failures/min, 5% = 50 failures/min (likely an incident).

**Error Budget** is an allowance — how many errors you can afford and still meet your SLO.

```
SLO target 99.9%  →  error budget = 0.1%
```

Two views of the same budget:

| View | 99.9% SLO over 30 days |
|---|---|
| Time-based | 43,200 min × 0.1% = **43.2 min of downtime allowed** |
| Request-based | 1M requests × 0.1% = **1,000 failed requests allowed** |

If you're down 50 min → you burned 50/43.2 = **115% of budget (breach)**.

---

## Dependency Criticality

### Edge (dependency) criticality: `hard` / `soft` / `degraded`

Describes **failure propagation semantics** — what happens to the caller if this dep goes down.

| Value | Meaning |
|---|---|
| `hard` | Caller fails completely without this dep |
| `soft` | Caller degrades gracefully, still functions |
| `degraded` | Caller runs in reduced-capability mode |

**The critical rule**: edge criticality is combined with communication mode to decide if a dependency participates in SLO math:

```
is_hard = (criticality == HARD) AND (communication_mode == SYNC)
```

Everything else — soft, degraded, or async+hard — is treated as a soft dep and excluded from calculations.

**Note on `async/await` vs architectural async**: `async/await` in code is a runtime efficiency detail — the coroutine suspends instead of blocking a thread. It is not the same as architectural async (queues/events). A database query written as `await db.execute(query)` is still architecturally **sync** — the request cannot continue without the result. Mark DB reads as `criticality=hard, mode=sync` in the dependency graph. The only exception is write-behind patterns where the DB write happens after the response is already sent to the user.

### Node (service) criticality: `high` / `medium` / `low`

Describes **business importance** of a service. Used only for UI visualization (color-coding nodes in the graph). Not used in any math.

---

## How Hard vs Soft Affects the Math

### Example setup

`checkout-service` (own availability: 99.9%) with three dependencies:

| Dep | Criticality | Mode | Availability |
|---|---|---|---|
| payment-service | hard | sync | 99.5% |
| fraud-service | hard | sync | 99.8% |
| recommendation-service | soft | sync | 97.0% |

### Composite availability bound

Only hard deps multiply in. Soft deps are skipped entirely.

```
composite = 0.999 × 0.995 × 0.998 = 0.99202  →  99.202%
```

`recommendation-service` at 97.0% contributes **nothing** here. If it goes down, checkout still works.

If `recommendation-service` were reclassified as hard:
```
composite = 0.99202 × 0.970 = 0.96226  →  96.2%
```
The composite bound collapses from 99.2% → 96.2% — a dramatic drop.

### Error budget consumption formula

```
consumption = dep_unavailability / your_error_budget
            = (1 - dep_availability) / (1 - slo_target)
```

With SLO target = 99.9% (error budget = 0.1%):

| Dep | Availability | Consumption |
|---|---|---|
| payment-service | 99.5% | (0.5%) / (0.1%) = **500%** 🔴 |
| fraud-service | 99.8% | (0.2%) / (0.1%) = **200%** 🔴 |
| recommendation-service | 97.0% | **not computed** (soft, skipped) |

"Excluded" means the loop never iterates over it. No number appears in any risk table.

---

## SLO Recommendation Tiers

Three tiers answer one question with different risk tolerances: *"What availability/latency target should you commit to?"*

### Availability tiers

Calculated from **30 days of daily availability buckets**, sorted ascending, then percentiles pulled:

| Tier | Percentile | Cap by composite bound? | Who it's for |
|---|---|---|---|
| Conservative | p0.1 (bottom 0.1% of days) | Yes | Customer SLAs, legal commitments |
| Balanced | p1 (bottom 1% of days) | Yes | Internal team targets, on-call SLOs |
| Aggressive | p5 (bottom 5% of days) | **No** | Engineering stretch goals, roadmap conversations |

**Why aggressive isn't capped**: it's aspirational — it shows what the service itself achieved, independent of systemic dependency risk. Useful for "if we want to commit to this, we need to fix dep X."

**Example** — 30 days of data, composite bound = 99.85%:

```
p0.1 raw = 99.87%  →  min(99.87%, 99.85%) = 99.85%  (Conservative)
p1   raw = 99.88%  →  min(99.88%, 99.85%) = 99.85%  (Balanced)
p5   raw = 99.90%  →  uncapped = 99.90%              (Aggressive)
```

Error budgets:
```
Conservative / Balanced: (1 - 0.9985) × 43,200 = 64.8 min/month
Aggressive:              (1 - 0.9990) × 43,200 = 43.2 min/month
```

Breach probability = fraction of historical days that would have breached the target:
```
Conservative at 99.85%: 0 days breached → 0%
Aggressive at 99.90%:   2 days breached → 6.7%
```

### Latency tiers

Latency tiers answer: *"What maximum response time can you promise?"*

Based on historical percentiles (p50/p95/p99/p999) + a noise margin (5% dedicated, 10% shared infra).

| Tier | Based on | Buffer | Breach probability |
|---|---|---|---|
| Conservative | p999 | +5% | ~0% |
| Balanced | p99 | +5% | ~1% |
| Aggressive | p95 | none | ~5% |

**Example** — p95=380ms, p99=620ms, p999=950ms, dedicated infra:

```
Conservative: 950ms × 1.05 = 997ms
Balanced:     620ms × 1.05 = 651ms
Aggressive:   380ms         = 380ms  (no buffer, 5% of requests already breach this)
```

---

## Error Budget Consumption — Worked Examples

### Example 1: Healthy dependency

Database at 99.95% availability, your SLO = 99.9%:
```
consumption = (1 - 0.9995) / (1 - 0.999) = 0.0005 / 0.001 = 50%
```
✅ LOW risk. Uses half your budget. 50% remains for yourself and other deps.

### Example 2: Risky dependency

Third-party payment gateway at 99.5%:
```
consumption = (1 - 0.995) / (1 - 0.999) = 0.005 / 0.001 = 500%
```
🔴 HIGH risk. This dep alone exceeds your entire budget 5×. Meeting 99.9% SLO is mathematically impossible.

### Example 3: Multi-dependency scenario

Payment service, SLO = 99.9%:

| Source | Availability | Consumption |
|---|---|---|
| Database | 99.95% | 50% ✅ |
| Auth service | 99.99% | 10% ✅ |
| Fraud detection | 99.8% | 200% 🔴 |
| Self (intrinsic) | — | 20% ⚠️ |
| **Total** | | **280%** |

Budget is 100%, consuming 280%. **Fraud detection is the bottleneck**.

Remediation options:

1. Make fraud detection a **soft dep** → removes 200% consumption → new total: 80% ✅
2. Improve fraud detection to 99.95% → drops from 200% to 50% → new total: 130% (still over)
3. Lower SLO target to 99.8% (budget = 0.2%) → halves all consumption percentages

---

## Risk Classification

| Risk Level | Consumption threshold | Meaning |
|---|---|---|
| LOW | < 20% | Healthy, no action needed |
| MODERATE | 20–30% | Watch and monitor |
| HIGH | > 30% | Priority for reliability investment |

---

## Action Thresholds (Operational Reference)

| Metric | Threshold | Action |
|---|---|---|
| Error rate | > 1% | Likely incident |
| Error budget used in first 2 weeks | > 70% | Burning too fast |
| Total consumption | > 100% | SLO breach guaranteed |
| Any single dep consumption | > 30% | High risk, prioritize improvement |
| Total consumption | > 150% | Critical — emergency response |

---

## The Reliability Ladder

Small differences in availability compound dramatically at high reliability levels:

```
100.00% ─── Perfection (unrealistic)
 99.99% ─── Four nines (premium tier)
 99.95% ─── Healthy dep (50% consumption for 99.9% SLO)
 99.90% ─── Your SLO target (100% consumption = break-even)
 99.50% ─── Risky dep (500% consumption)
 99.00% ─── Unstable (1000% consumption)
```

- 99.9% → 99.5%: 0.4% difference = **5× error budget consumption**
- 99.9% → 99.0%: 0.9% difference = **10× error budget consumption**

---

## Burn Rate

How fast you're consuming your error budget relative to the sustainable rate.

```
Burn Rate = observed error rate / acceptable error rate (from SLO)
```

**Example**: SLO allows 1% errors, you're seeing 5% → burn rate = 5/1 = **5×**

| Burn Rate | Budget exhausted in | Meaning |
|---|---|---|
| 1× | 30 days | Exactly sustainable |
| 2× | 15 days | Double speed |
| 10× | 3 days | Critical |
| 14.4× | ~2 days | Exhausts 2% budget in 1 hour |

**Why it matters over raw error rate**: a 0.1% error rate sounds fine, but if your SLO allows only 0.01%, you're burning at 10× and headed for a breach fast. Burn rate normalizes the signal across services with different SLO thresholds.

**Google SRE multi-window alerting model**:

| Burn Rate | Window | Budget Consumed | Severity |
|---|---|---|---|
| 14.4× | 1 hour | 2% | Page immediately |
| 6× | 6 hours | 5% | Page urgently |
| 3× | 1 day | 10% | Ticket |
| 1× | 3 days | 10% | No alert |

High burn rate + short window = sudden outage, page now. Low burn rate + long window = slow leak, ticket it.

---

## Golden Rule

> If total error budget consumption across all hard dependencies exceeds 100%, your SLO target is **mathematically unachievable** with the current dependency graph.
> You must either: improve dep reliability, make deps async/soft, or lower your SLO target.

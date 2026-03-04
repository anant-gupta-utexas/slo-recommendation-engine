# Drift Detection Ensemble

> Page-Hinkley + ADWIN + KS-test with majority voting.
> Background worker every 15 minutes. Confirmed drift triggers recommendation re-evaluation.

---

## Why Drift Detection Matters

SLO recommendations are derived from historical telemetry — a 28-day window of error rates,
latency percentiles, and throughput. When the underlying performance profile changes, the
recommendation becomes stale.

Two things cause drift:

1. **Abrupt shift** — a code deployment changes payment-service p99 from 1800ms to 900ms
   overnight. The old SLO recommendation was calibrated for the slow version.
2. **Gradual drift** — traffic grows 5% week-over-week, slowly pushing CPU utilization from
   50% to 80%. No single day looks alarming, but the baseline has moved.

A single detector can't handle both patterns well. Fast detectors (Page-Hinkley) catch
abrupt shifts but false-alarm on noise. Distributional tests (KS) catch subtle shape
changes but are expensive and slow. The ensemble approach uses three complementary
detectors and requires **2-of-3 agreement** before declaring drift.

---

## The Three Detectors

### 1. Page-Hinkley Test (Fast Abrupt Change Detector)

**What it does:** Monitors the cumulative sum of deviations from the running mean. When
the cumulative deviation exceeds a configurable threshold, it signals drift.

**How it works, step by step:**

```
Maintain running values:
  n     = number of observations so far
  x̄_n   = running mean of all observations
  T_n   = cumulative sum of (x_i - x̄_n - δ)    where δ is a tolerance parameter

At each new observation x_t:
  1. Update running mean: x̄_n = (x̄_{n-1} × (n-1) + x_t) / n
  2. Update cumulative sum: T_n = T_{n-1} + (x_t - x̄_n - δ)
  3. Track minimum: m_n = min(m_{n-1}, T_n)
  4. If (T_n - m_n) > λ   →   DRIFT DETECTED

  δ (delta)  = minimum magnitude of change worth detecting (filters noise)
  λ (lambda) = detection threshold (higher = fewer false alarms, slower detection)
```

**Concrete example — detecting a deployment change:**

```
payment-service p99 latency (ms), sampled every 15 minutes:

Before deployment:  1820, 1790, 1830, 1810, 1800, 1780, 1820  (mean ≈ 1807)
After deployment:   920,  890,  940,  910,  900,  880,  920   (mean ≈ 909)

With δ=50, λ=500:

  Observation #8 (920ms): deviation from mean = 920 - 1696 - 50 = -826
    T_8 = 0 + (-826) = -826,  m_8 = -826,  T-m = 0          → no alarm
  Observation #9 (890ms): running mean drops further
    T_9 = -826 + (890 - 1607 - 50) = -1593,  m_9 = -1593    → no alarm
  Observation #10 (940ms):
    T_10 = -1593 + (940 - 1530 - 50) = -2233,  m_10 = -2233 → no alarm

  BUT: the running mean itself is dropping. After a few more observations,
  the new data points are close to the new mean while T accumulated a large
  negative sum. The statistic T_n - m_n begins to grow:

  Observation #14: T-m exceeds λ=500  →  DRIFT DETECTED

Page-Hinkley detects this in ~6 observations after the shift (about 90 minutes
at 15-minute intervals).
```

**Strengths:** Extremely lightweight (O(1) memory, 5 arithmetic operations per update).
Detection latency for abrupt shifts: ~1-2 hours at 15-minute sampling.

**Weakness:** Only tracks the mean. Blind to distributional changes where the mean stays
constant (e.g., bimodal latency from cold starts).

**Tuning guidelines:**

| Parameter | Recommended Value | Effect of Increasing |
|-----------|------------------|---------------------|
| δ (delta) | 0.005 × baseline mean | Fewer false alarms, slower detection of small shifts |
| λ (lambda) | 50-500 (depends on metric scale) | Fewer false alarms, misses brief transient shifts |

---

### 2. ADWIN (Adaptive Windowing — Gradual + Abrupt Detector)

**What it does:** Maintains a variable-length sliding window of recent observations. At
each step, it tests whether any split of the window into two sub-windows has a
statistically significant difference in means (using Hoeffding's bound). If so, it drops
the older portion and signals drift.

**How it works, step by step:**

```
Maintain a window W of recent observations: [x_1, x_2, ..., x_n]

At each new observation x_t:
  1. Add x_t to the window
  2. For each possible split point i (optimized with bucketing):
     - W_old = [x_1, ..., x_i]       (mean = μ_old)
     - W_new = [x_{i+1}, ..., x_n]   (mean = μ_new)
     - Compute Hoeffding bound ε for current window sizes
     - If |μ_old - μ_new| ≥ ε  →  DRIFT DETECTED
       Drop W_old, keep only W_new
  3. If no split triggers, grow the window

Hoeffding bound:  ε = sqrt( (1/2m) × ln(4/δ') )
  where m = harmonic mean of |W_old| and |W_new|
  δ' = confidence parameter (lower = more conservative)
```

**Concrete example — detecting gradual traffic growth:**

```
checkout-service throughput (req/s), weekly averages over 12 weeks:

Week:  1    2    3    4    5    6    7    8    9    10   11   12
RPS:  600  610  620  615  640  655  670  690  710  740  760  790

By week 8, ADWIN's window contains all 8 observations.
It tests splits:
  [600,610,620,615] vs [640,655,670,690]
  μ_old = 611,  μ_new = 664,  |diff| = 53

  Hoeffding bound for n_old=4, n_new=4, δ'=0.01:
  ε = sqrt( (1/(2×2)) × ln(4/0.01) ) = sqrt(0.25 × 5.99) ≈ 1.22

  Wait — this bound is on [0,1] normalized data. With normalization:
  RPS normalized to [0,1] range (min=600, max=800):
  53 / 200 = 0.265,  and ε ≈ 0.47 for these small window sizes

  Not enough evidence yet. Window keeps growing.

By week 10, with 10 observations:
  [600,610,620,615,640] vs [655,670,690,710,740]
  μ_old = 617,  μ_new = 693,  |diff| = 76 → normalized: 0.38

  ε for n_old=5, n_new=5: ≈ 0.37

  0.38 > 0.37  →  DRIFT DETECTED
  Old window is dropped. New baseline starts from week 6.
```

**Strengths:** Adapts window size automatically — short window for rapid changes, long
window for slow drift. Provides theoretical guarantees (bounded false positive rate).

**Weakness:** Detects mean shifts only (like Page-Hinkley), though with better handling
of gradual drift. Higher memory than Page-Hinkley (stores the window contents, though
compressed into exponential buckets in practice).

**Tuning guidelines:**

| Parameter | Recommended Value | Effect of Increasing |
|-----------|------------------|---------------------|
| δ' (confidence) | 0.01 - 0.002 | Fewer false alarms, requires larger shift to trigger |
| Min window size | 30 observations | More stable estimates, slower initial detection |

---

### 3. KSWIN (Kolmogorov-Smirnov Windowed — Distributional Detector)

**What it does:** Compares the full probability distribution of a recent window against a
reference window using the two-sample Kolmogorov-Smirnov test. Detects any kind of
distributional change — mean shifts, variance changes, shape changes, multimodality.

**How it works, step by step:**

```
Maintain two windows:
  W_ref  = reference window of N observations (the "old" behavior)
  W_test = recent window of M observations (the "current" behavior)

At each new observation:
  1. Slide W_test forward (add new, drop oldest)
  2. Compute empirical CDFs:
     F_ref(x)  = fraction of W_ref  values ≤ x
     F_test(x) = fraction of W_test values ≤ x
  3. KS statistic: D = max_x |F_ref(x) - F_test(x)|
     (The maximum vertical distance between the two CDFs)
  4. Critical value: D_crit = c(α) × sqrt( (N+M) / (N×M) )
     where c(α) depends on significance level (c(0.05) ≈ 1.36)
  5. If D > D_crit  →  DRIFT DETECTED

Periodically refresh W_ref with recent "stable" data.
```

**Concrete example — detecting bimodal latency from cold starts:**

```
auth-service latency (ms) — deployed on serverless (Lambda):

Reference window (100 observations, no cold starts):
  [45, 52, 48, 51, 47, 50, 49, 53, 46, 51, ...]
  Distribution: unimodal, centered at ~50ms, std dev ~3ms

After a config change reduces provisioned concurrency:

Recent window (100 observations, 10% cold starts):
  [48, 51, 47, 820, 49, 52, 50, 780, 46, 53, 49, 850, ...]
  Distribution: bimodal — 90% at ~50ms, 10% at ~800ms

Mean comparison:
  μ_ref  = 50ms
  μ_test = 50 × 0.9 + 800 × 0.1 = 45 + 80 = 125ms

  Page-Hinkley would detect this (mean shifted from 50 to 125).
  BUT what if cold starts are only 3%?

  μ_test = 50 × 0.97 + 800 × 0.03 = 48.5 + 24 = 72.5ms
  A small mean shift that Page-Hinkley might miss at conservative thresholds.

KS test:
  The CDF of the reference window jumps from 0 to 1 in the 45-55ms range.
  The CDF of the test window jumps from 0 to 0.97 in 45-55ms, then flat
  until 780-850ms where it jumps to 1.0.

  D = |F_ref(55) - F_test(55)| = |1.0 - 0.97| = 0.03?

  No — the maximum difference is actually at x=55ms:
  F_ref(55) ≈ 1.0  (all reference data ≤ 55ms)
  F_test(55) ≈ 0.97  (97% of test data ≤ 55ms, 3% are cold starts > 55ms)
  D ≈ 0.03

  But wait — the CDF comparison also catches the gap at higher values:
  F_ref(100) = 1.0, F_test(100) = 0.97  →  D = 0.03
  The KS stat D = 0.03.

  D_crit for N=M=100, α=0.05: 1.36 × sqrt(200/10000) = 1.36 × 0.141 = 0.192

  D = 0.03 < D_crit = 0.192  →  NOT detected at 3% cold start rate.

  At 10% cold start rate:
  D ≈ 0.10, still < 0.192  →  borderline.

  At 20% cold start rate:
  D ≈ 0.20 > 0.192  →  DRIFT DETECTED

This shows KS detects distributional changes that affect ~20%+ of observations
with 100-sample windows. For subtler changes, use larger windows (N=500+).
```

**Strengths:** Detects any distributional change — not just mean shifts. The only detector
in the ensemble that catches variance changes, shape changes, and multimodality.

**Weakness:** Computationally expensive (O(N log N) per test for sorting). Requires larger
sample sizes to detect subtle shifts. Not useful for streaming single-point updates.

**Tuning guidelines:**

| Parameter | Recommended Value | Effect of Increasing |
|-----------|------------------|---------------------|
| Window size N | 100-500 observations | More sensitive to subtle shifts, higher memory/compute |
| α (significance) | 0.05 | Lower α = fewer false alarms, requires larger shift to trigger |
| Refresh interval | After each confirmed drift | Keeps reference window current |

---

## Majority Voting: How the Ensemble Decides

Drift is confirmed **only when at least 2 of 3 detectors agree**. This is the critical
design choice that balances sensitivity against false positives.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Page-Hinkley│     │   ADWIN     │     │   KSWIN     │
│  (PH)       │     │             │     │   (KS)      │
│             │     │             │     │             │
│ Monitors    │     │ Monitors    │     │ Monitors    │
│ cumulative  │     │ adaptive    │     │ full CDF    │
│ deviation   │     │ window mean │     │ comparison  │
│ from mean   │     │ difference  │     │             │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       │   vote: 0 or 1    │   vote: 0 or 1    │   vote: 0 or 1
       └───────────┬───────┴───────────┬───────┘
                   ▼                   │
         ┌─────────────────┐           │
         │  MAJORITY VOTE  │◄──────────┘
         │                 │
         │  sum ≥ 2 → DRIFT│
         │  sum < 2 → OK   │
         └────────┬────────┘
                  │
           ┌──────┴──────┐
           │             │
      sum ≥ 2       sum < 2
           │             │
           ▼             ▼
   ┌──────────────┐  No action.
   │ DRIFT        │  Detectors
   │ CONFIRMED    │  reset on
   │              │  next cycle.
   │ → trigger    │
   │   re-eval    │
   └──────────────┘
```

### Why each combination matters

| PH | ADWIN | KS | Votes | Action | Scenario |
|----|-------|----|-------|--------|----------|
| 1  | 1     | 1  | 3     | DRIFT  | Clear regime change — all detectors agree. Example: major deployment changing both mean and distribution. |
| 1  | 1     | 0  | 2     | DRIFT  | Mean shifted significantly but distribution shape is similar. Example: latency increased uniformly by 100ms across all percentiles. |
| 1  | 0     | 1  | 2     | DRIFT  | Abrupt distributional change. Example: sudden cold start spike causing bimodal latency. |
| 0  | 1     | 1  | 2     | DRIFT  | Gradual distributional change. Example: slowly increasing cold start rate over weeks. |
| 1  | 0     | 0  | 1     | NO ACTION | Page-Hinkley fired alone — likely a transient spike (e.g., a single slow GC pause). False alarm filtered. |
| 0  | 1     | 0  | 1     | NO ACTION | ADWIN detected a minor mean shift — could be normal daily variance. Wait for more evidence. |
| 0  | 0     | 1  | 1     | NO ACTION | KS found a distributional difference — possibly sampling noise in the reference window. Investigate, but don't trigger re-evaluation. |
| 0  | 0     | 0  | 0     | NO ACTION | All quiet. Baseline is stable. |

---

## What Gets Monitored

The drift ensemble runs on **per-service metric streams**. Each service has independent
detectors for each monitored signal:

| Signal | Why Monitor It | Drift Means |
|--------|---------------|-------------|
| `error_rate` | Core SLI — availability SLO is directly derived from this | Recommendation's availability target may be too tight or too loose |
| `latency_p99` | Core SLI — latency SLO is derived from this | Latency tier targets need recalculation |
| `throughput` (req/s) | Traffic volume affects percentile calculations and resource pressure | Feature inputs to the ML model have shifted |
| `cpu_utilization` | Resource saturation changes what latency is achievable | The "headroom" assumed in the SLO may have evaporated |
| `error_budget_burn_rate` | Meta-signal — if burn rate drifts, the SLO may be miscalibrated | Composite SLO math inputs have changed |

For a deployment with 500 services monitoring 5 signals each, the ensemble manages
**2,500 detector triplets** (7,500 individual detector instances).

---

## Background Worker Architecture

The drift detection job fits into the existing APScheduler pattern already used by
the codebase (`src/infrastructure/tasks/scheduler.py`).

### Execution Flow

```
Every 15 minutes (IntervalTrigger):

┌────────────────────────────────────────────────────────────────────┐
│                   drift_detection_sweep()                          │
│                                                                    │
│  1. Query latest 15 min of metric data from Mimir/Prometheus       │
│     ┌────────────────────────────────────────────────────┐         │
│     │ PromQL: rate(http_requests_total{status=~"5.."}    │         │
│     │         [15m]) / rate(http_requests_total[15m])     │         │
│     │         → per-service error_rate                    │         │
│     │                                                    │         │
│     │ PromQL: histogram_quantile(0.99,                   │         │
│     │         rate(http_duration_seconds_bucket[15m]))    │         │
│     │         → per-service latency_p99                   │         │
│     └────────────────────────────────────────────────────┘         │
│                                                                    │
│  2. For each service × each signal:                                │
│     ┌───────────────────────────────────────────┐                  │
│     │  Feed new observation to:                 │                  │
│     │    page_hinkley.update(value) → 0 or 1    │                  │
│     │    adwin.update(value)        → 0 or 1    │                  │
│     │    kswin.update(value)        → 0 or 1    │                  │
│     │                                           │                  │
│     │  votes = ph + adwin + ks                  │                  │
│     │  if votes >= 2:                           │                  │
│     │    emit DriftDetectedEvent                │                  │
│     └───────────────────────────────────────────┘                  │
│                                                                    │
│  3. For each confirmed drift event:                                │
│     ┌───────────────────────────────────────────┐                  │
│     │  a. Log structured event:                 │                  │
│     │     service_id, signal, old_baseline,     │                  │
│     │     new_value, detectors_fired, timestamp  │                  │
│     │                                           │                  │
│     │  b. Update baseline in PostgreSQL:        │                  │
│     │     drift_events table (audit trail)      │                  │
│     │                                           │                  │
│     │  c. Enqueue recommendation re-evaluation: │                  │
│     │     mark service as "drift_detected"      │                  │
│     │     → picked up by next batch_compute     │                  │
│     │       cycle (or trigger immediate if      │                  │
│     │       revenue-critical service)            │                  │
│     └───────────────────────────────────────────┘                  │
│                                                                    │
│  4. Emit Prometheus metrics:                                       │
│     drift_detections_total{service, signal, detector}              │
│     drift_sweep_duration_seconds                                   │
│     drift_sweep_services_checked                                   │
└────────────────────────────────────────────────────────────────────┘
```

### Scheduling Configuration

```python
# In scheduler.py, alongside existing jobs:

scheduler.add_job(
    drift_detection_sweep,
    trigger=IntervalTrigger(minutes=15),
    id="drift_detection_sweep",
    name="Drift detection ensemble sweep",
    replace_existing=True,
)
```

This aligns with the existing 15-minute OTel ingestion cycle — drift detection
runs after fresh metrics are available.

### State Management

Each detector instance needs to persist state between runs:

| Detector | State to Persist | Size per Instance |
|----------|-----------------|-------------------|
| Page-Hinkley | `n`, `x̄_n`, `T_n`, `m_n` | 4 floats = 32 bytes |
| ADWIN | Bucket structure (compressed window) | ~200-500 bytes |
| KSWIN | Reference window + test window | 2 × N × 8 bytes (N=100 → 1.6 KB) |

For 2,500 detector triplets: **~5 MB total** — fits comfortably in memory for the
in-process APScheduler model. For multi-replica deployments, state would be
serialized to Redis or PostgreSQL.

---

## Drift → Re-Evaluation Pipeline

When drift is confirmed, the following chain executes:

```
Drift Detected                    What Happens Next
─────────────────────────────────────────────────────────────────────

1. DriftDetectedEvent             Structured log + drift_events table row
   {                              │
     service_id: "payment-svc",   │
     signal: "latency_p99",       │
     old_baseline: 1800,          │
     new_value: 920,              │
     detectors: ["PH", "ADWIN"],  │
     confidence: "2/3",           │
     timestamp: "..."             │
   }                              │
                                  ▼
2. Cooldown check                 Was drift already detected for this
                                  service+signal in the last 4 hours?
                                  │
                          ┌───────┴───────┐
                          │               │
                        Yes              No
                          │               │
                     Skip (avoid     Continue ──→ 3
                     re-eval spam)
                                          │
                                          ▼
3. Baseline update                Query last 2-4 hours of data.
                                  If BOCD confirms a stable new regime:
                                  │
                                  ├─→ Update service baseline in DB
                                  │   (new mean, new p99, new distribution params)
                                  │
                                  ├─→ If new baseline differs >5% from previous:
                                  │   │
                                  │   ▼
4. SLO re-evaluation              Trigger generate_slo_recommendation()
                                  for the affected service.
                                  │
                                  ├─→ For revenue-critical services:
                                  │   run immediately (async task)
                                  │
                                  ├─→ For other services:
                                  │   mark as "pending_re_eval", picked up
                                  │   by next batch_compute_recommendations cycle
                                  │
                                  ▼
5. Downstream propagation         If checkout-service depends on payment-service
                                  and payment-service drifted, checkout's
                                  composite bound changed too.
                                  │
                                  └─→ Mark upstream services for re-evaluation:
                                      query dependency graph for all services
                                      that have a hard dep on the drifted service
```

### Re-Evaluation Scope

A single drift event can cascade through the dependency graph:

```
Example: payment-service latency improves from 1800ms to 900ms

Directly affected:
  payment-service → recalculate its own latency SLO tiers

Transitively affected (hard upstream dependencies):
  checkout-service → composite bound improved
                     (payment leg of serial chain is now faster)
  api-gateway     → end-to-end latency forecast changes

NOT affected:
  auth-service    → no dependency on payment-service
  inventory-service → independent path
```

---

## Worked Example: Full Cycle

### Scenario: Payment service gets a performance optimization deployed

**Week 1, Day 1 — Before deployment:**

```
payment-service baseline (established over 28 days):
  error_rate:   mean = 0.12%, std = 0.04%
  latency_p99:  mean = 1820ms, std = 90ms
  throughput:   mean = 340 req/s

Current SLO recommendation:
  Availability: 99.85% (balanced tier)
  Latency p99:  1950ms (balanced tier = p99 × 1.05 noise margin)
```

**Week 1, Day 1, 14:00 UTC — Deployment rolls out:**

```
payment-service performance immediately changes:
  latency_p99:  drops from ~1800ms to ~900ms
  error_rate:   drops from 0.12% to 0.05%
  throughput:   unchanged (340 req/s)
```

**14:15 UTC — First drift sweep post-deployment:**

```
New observation: latency_p99 = 920ms (vs baseline mean 1820ms)

Page-Hinkley:
  Deviation from mean = 920 - 1820 = -900
  Cumulative sum drops sharply
  T_n - m_n not yet > λ (first observation)
  Vote: 0

ADWIN:
  Window: [..., 1790, 1830, 1810, 920]
  Split test: recent [920] vs old [1790, 1830, 1810, ...]
  |μ_old - μ_new| = |1810 - 920| = 890 >> ε (Hoeffding bound)
  BUT: single new observation → window too small for statistical confidence
  Vote: 0

KSWIN:
  Test window has only 1 new-regime point out of 100
  D statistic is small
  Vote: 0

Majority: 0/3 → NO DRIFT (too early, not enough evidence)
```

**14:30 UTC — Second sweep:**

```
New observation: latency_p99 = 890ms

Page-Hinkley:
  Cumulative deviation growing: two consecutive observations ~900ms below baseline
  T_n - m_n starting to grow but still < λ
  Vote: 0

ADWIN:
  Window now has 2 recent points around 900ms
  Split test gaining confidence but not yet significant
  Vote: 0

Majority: 0/3 → NO DRIFT (building evidence)
```

**15:15 UTC — Fifth sweep (1 hour 15 min post-deployment):**

```
Five consecutive observations: 920, 890, 940, 910, 900

Page-Hinkley:
  T_n - m_n has been accumulating for 5 observations
  Each contributing ~-900 to the cumulative sum
  Statistic exceeds λ
  Vote: 1 ✓

ADWIN:
  Window split: old regime [1790, 1830, ...] vs new regime [920, 890, 940, 910, 900]
  |1810 - 912| = 898, well above Hoeffding bound for these window sizes
  Vote: 1 ✓

KSWIN:
  Test window still dominated by old-regime data (95 old, 5 new out of 100)
  D statistic = ~0.05, below D_crit
  Vote: 0

Majority: 2/3 → DRIFT CONFIRMED (PH + ADWIN agree)
```

**15:15 UTC — Re-evaluation triggered:**

```
1. DriftDetectedEvent logged:
   service=payment-service, signal=latency_p99, old=1820, new=912,
   detectors=[PH, ADWIN], confidence=2/3

2. Cooldown check: no recent drift for this service+signal → proceed

3. BOCD runs on last 2 hours of data:
   Identifies changepoint at 14:00 UTC with 94% probability
   New regime: mean=912ms, std=20ms
   Old regime: mean=1820ms, std=90ms
   Difference: 49.8% → exceeds 5% threshold

4. Baseline updated in PostgreSQL

5. SLO re-evaluation for payment-service:
   New recommendation:
     Availability: 99.92% (up from 99.85%) — fewer errors in new version
     Latency p99:  980ms (down from 1950ms) — dramatically faster

6. Upstream propagation:
   checkout-service marked for re-evaluation
   Old composite: gateway(99.95%) × checkout(99.9%) × payment(99.85%) = 99.70%
   New composite: gateway(99.95%) × checkout(99.9%) × payment(99.92%) = 99.77%
   checkout-service gets a tighter (better) SLO recommendation
```

---

## Detector Comparison Summary

| Property | Page-Hinkley | ADWIN | KSWIN |
|----------|-------------|-------|-------|
| **Detects** | Abrupt mean shifts | Gradual + abrupt mean shifts | Any distributional change |
| **Blind to** | Variance/shape changes | Variance/shape changes | Nothing (full distribution test) |
| **Speed** | Fastest (1-2 hours) | Medium (2-6 hours for gradual) | Slowest (needs large samples) |
| **Memory** | O(1) — 32 bytes | O(log n) — ~500 bytes | O(N) — ~1.6 KB per window |
| **Compute** | O(1) per update | O(log n) per update | O(N log N) per test |
| **False positive rate** | Moderate (sensitive to outliers) | Low (Hoeffding guarantee) | Very low (formal statistical test) |
| **Best for** | Post-deployment monitoring | Traffic trend detection | Cold start / bimodal detection |

### Why all three are needed

- **PH alone** would fire on every GC pause or network blip → too many false alarms
- **ADWIN alone** would miss distributional changes where the mean stays constant
- **KS alone** would be too slow and expensive to run at 15-minute granularity across
  2,500 detector triplets (at N=500, each test sorts 500 values)
- **PH + ADWIN** (2/3 majority) catches mean shifts quickly with low false positives
- **PH + KS** or **ADWIN + KS** (2/3 majority) catches distributional changes that
  also affect the mean — the most operationally important category

The ensemble gives us fast detection (PH), robustness to gradual change (ADWIN),
and distributional coverage (KS), with majority voting eliminating false alarms
from any single detector.

---

## Edge Cases and Failure Modes

### Detector Disagreement Scenarios

| Scenario | PH | ADWIN | KS | What's Happening | Correct Response |
|----------|----|----|---|----|---|
| Brief traffic spike during a sale | 1 | 0 | 0 | PH is sensitive to the mean jump; ADWIN and KS see it as within normal range | Correct NO ACTION — the spike is transient |
| Slow memory leak over 6 weeks | 0 | 1 | 0 | ADWIN's adaptive window catches the gradual trend; PH needs a sharper shift; KS window too short | Monitor — 1 vote isn't enough, but watch for ADWIN + KS to converge |
| Canary deployment (5% of traffic to new version) | 0 | 0 | 1 | KS detects the bimodal distribution (95% old, 5% new); PH and ADWIN don't see a mean shift (5% is small) | Correct NO ACTION — canary is expected, will converge when fully rolled out |
| New deployment + config rollback 20 min later | 1 | 0 | 0 | PH fires on the initial shift, but the rollback restores the original baseline before ADWIN confirms | Correct NO ACTION — the rollback "healed" the drift, no stale recommendation |

### Cooldown Prevents Re-Evaluation Spam

Without cooldown, a flapping service (oscillating between two states) would trigger
re-evaluation every 15 minutes. The 4-hour cooldown ensures:

- A drift event fires once and triggers a single re-evaluation
- If the service drifts again within 4 hours (e.g., a rollback), it's logged but
  doesn't spam the recommendation pipeline
- After 4 hours, if the new regime is still present, the detectors have fully
  stabilized and any further drift represents a genuinely new change

### Cold Start Problem

When a new service is deployed, there is no historical baseline. The detectors
need a minimum number of observations before they can reliably detect drift:

| Detector | Minimum Observations | At 15-min Intervals |
|----------|---------------------|---------------------|
| Page-Hinkley | ~20-30 | ~5-8 hours |
| ADWIN | ~30-50 | ~8-12 hours |
| KSWIN | ~100 (reference window size) | ~25 hours |

**Mitigation:** For new services, use a 24-hour warmup period where drift detection is
disabled and the system collects baseline observations. During warmup, SLO
recommendations use conservative defaults based on the service's tier and type
(from the service metadata).

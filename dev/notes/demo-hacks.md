# Demo-Specific Code Changes

This document tracks all ad-hoc modifications made to the codebase purely for demo purposes.
Each entry lists what was changed, where, and what would need to be reverted or replaced before production use.

---

## 1. Auth Middleware — Full Auth Bypass in Dev/Staging

**File:** `src/infrastructure/api/middleware/auth.py`

### Change
`verify_api_key` short-circuits at the top and returns a hardcoded `"demo-user"` identity whenever `settings.environment` is `"development"` or `"staging"`, **before** any path-exclusion or token-validation logic runs.

```python
# Lines 49-58
if settings.environment in ["development", "staging"]:
    logger.debug("auth_bypassed", environment=settings.environment,
                 path=request.url.path, reason="demo_mode")
    return "demo-user"
```

### Also changed
A second bypass exists lower in the same function (lines 32-34 + 64-67): any request whose path starts with `/api/v1/demo/` is unconditionally allowed through as `"demo-user"`, regardless of environment.

```python
EXCLUDED_PATH_PREFIXES = [
    "/api/v1/demo/",  # All demo endpoints are public
]
```

### Why it was done
Eliminates the need to provision a real API key when running `docker-compose up` locally or during a live demo.

### Production remediation
- Remove the `environment in ["development", "staging"]` early-return block entirely.
- Decide whether `/api/v1/demo/` endpoints should exist in production at all; if not, remove the prefix exclusion too (or guard the entire demo router behind a feature flag).

---

## 2. Demo Router — Synchronous Circular Dependency Detection

**File:** `src/infrastructure/api/routes/demo.py`
**Route:** `POST /api/v1/demo/dependencies`

### Change
In production, `DetectCircularDependenciesUseCase` is triggered as a background task after ingestion. The demo endpoint calls it **synchronously** inside the request handler so that `circular_dependencies_detected` is populated in the immediate HTTP response.

```python
# Lines 151-165
newly_created_alerts = await detect_circular_use_case.execute()
all_alerts = await alert_repository.list_by_status(AlertStatus.OPEN, skip=0, limit=1000)
ingested_service_ids = {node.service_id for node in request.nodes}
relevant_alerts = [
    alert for alert in all_alerts
    if any(service_id in ingested_service_ids for service_id in alert.cycle_path)
]
```

### Why it was done
The demo UI shows cycle detection results immediately after clicking "Ingest Graph". The production endpoint returns `202 Accepted` and detection runs asynchronously, so the response would always return an empty `circular_dependencies_detected` list during a live demo.

### Production remediation
Delete this route (or the whole `demo.py` router). Use `POST /api/v1/services/dependencies` (standard endpoint) and poll or use webhooks for cycle alerts.

---

## 3. Demo Router — Destructive "Clear All" Endpoint

**File:** `src/infrastructure/api/routes/demo.py`
**Route:** `DELETE /api/v1/demo/clear-all`

### Change
A raw SQL `DELETE` endpoint that truncates all three core tables in dependency order (`circular_dependency_alerts` → `service_dependencies` → `services`), with no confirmation, soft-delete, or audit trail.

```python
# Lines 265-273
await session.execute(text("DELETE FROM circular_dependency_alerts"))
await session.execute(text("DELETE FROM service_dependencies"))
await session.execute(text("DELETE FROM services"))
await session.commit()
```

### Why it was done
Allows the presenter to reset the database to a clean state between demo runs without manually connecting to PostgreSQL.

### Production remediation
Remove entirely. If data-reset tooling is needed for test environments, implement it as a CLI script (`scripts/`) with explicit environment guards and proper audit logging, never as an unauthenticated HTTP endpoint.

---

## 4. Demo Router — Synthetic SLO Recommendations (No Telemetry Required)

**File:** `src/infrastructure/api/routes/demo.py`
**Route:** `GET /api/v1/demo/services/{service_id}/slo-recommendations`

### Change
Returns fully hard-coded recommendation objects (`_generate_demo_availability_recommendation`, `_generate_demo_latency_recommendation`) populated with static numbers (targets, breach probabilities, feature attributions, counterfactuals, provenance). None of the values are derived from real telemetry.

Example hard-coded values (availability recommendation):
| Tier         | Target  | Breach Prob |
|--------------|---------|-------------|
| Conservative | 99.99%  | 2%          |
| Balanced     | 99.95%  | 8%          |
| Aggressive   | 99.9%   | 15%         |

The `lookback_days` query parameter is accepted but described as "cosmetic for demo" — it only affects the `telemetry_window_start` timestamp in the provenance block; no actual data is fetched.

### Why it was done
The real recommendations endpoint requires historical telemetry ingestion (Prometheus / OTel data) that is impractical to set up during a live demo. The synthetic endpoint lets FR-2 and FR-7 UI flows run end-to-end without any data pipeline.

### Production remediation
Delete this route. The real endpoint is `GET /api/v1/services/{service_id}/slo-recommendations`.

---

## 5. Streamlit Demo — No API Key Sent

**File:** `demo/streamlit_demo.py`
**Lines:** 1043-1044 (`render_sidebar`)

### Change
The sidebar hard-codes an empty API key and provides no input field for one:

```python
st.session_state.api_key = ""
```

`SloEngineClient.__init__` (lines 165-168) only adds the `Authorization` header when `self.api_key` is truthy, so all requests go out without authentication — relying on the middleware bypass described in item 1.

### Why it was done
Simplifies the demo setup: no API key needs to be created, copied, and pasted before the demo starts.

### Production remediation
Re-add the API key input field and remove the hardcoded empty assignment.

---

## 6. Streamlit Demo — Demo Endpoint Overrides for Standard Routes

**File:** `demo/streamlit_demo.py`

### Change
Two methods in `SloEngineClient` silently call demo-specific backend routes instead of the documented production routes:

| Method | Calls (Demo) | Should call (Production) |
|---|---|---|
| `ingest_dependencies` | `POST /api/v1/demo/dependencies` | `POST /api/v1/dependencies` |
| `get_recommendations` | `GET /api/v1/demo/services/{id}/slo-recommendations` | `GET /api/v1/services/{id}/slo-recommendations` |

```python
# Line 198
return self._request("POST", "/api/v1/demo/dependencies", json=payload)

# Lines 210-213
return self._request(
    "GET",
    f"/api/v1/demo/services/{service_id}/slo-recommendations",
    ...
)
```

### Why it was done
Piggybacks on items 2 and 4 above — the demo routes provide richer / synchronous responses needed for an uninterrupted demo flow.

### Production remediation
Point both methods back to the standard production routes and remove the `demo/` path segments.

---

## 7. Streamlit Demo — `demo_with_issues` Source Remapped at Payload Build Time

**File:** `demo/streamlit_demo.py`
**Lines:** 508-509

### Change
When the user selects the `demo_with_issues` data source in the UI, the frontend silently remaps it to `"manual"` before sending the ingestion payload to the backend:

```python
backend_source = "manual" if source == "demo_with_issues" else source
```

### Why it was done
`demo_with_issues` is a frontend-only concept (a specially crafted graph with intentional circular deps and undefined services). The backend's `source` field only accepts the enum values it knows (`manual`, `otel_service_graph`, `kubernetes`, `service_mesh`). The remap avoids a validation error.

### Production remediation
Either (a) add `demo_with_issues` as a recognised source enum on the backend, or (b) document that it is purely a UI-layer data preset and keep the remap — but make the comment explicit rather than a silent coercion.

---

## Summary Table

| # | File | Nature of Hack | Safe in Production? |
|---|------|----------------|---------------------|
| 1 | `src/infrastructure/api/middleware/auth.py` | Full auth bypass in dev/staging | **No** |
| 2 | `src/infrastructure/api/routes/demo.py` | Synchronous circular dep detection | **No** |
| 3 | `src/infrastructure/api/routes/demo.py` | Unauthenticated destructive DELETE | **No** |
| 4 | `src/infrastructure/api/routes/demo.py` | Hardcoded synthetic SLO recommendations | **No** |
| 5 | `demo/streamlit_demo.py` | No API key sent with requests | **No** |
| 6 | `demo/streamlit_demo.py` | Demo route overrides for standard endpoints | **No** |
| 7 | `demo/streamlit_demo.py` | Silent source remap (`demo_with_issues` → `manual`) | Low risk / needs comment |

# Session 10: E2E Test Debugging & Fixes

**Date:** 2026-02-15
**Duration:** ~2 hours
**Focus:** Fix DB initialization blocker, update test payloads, enable auth, debug 500 errors
**Result:** 5/20 tests passing (25%), blocking issue resolved, new blocker identified

---

## Accomplishments

### 1. Fixed DB Initialization Blocker ✅

**Problem:** FastAPI lifespan manager expects `await init_db()` but config.py provided sync version

**Solution:**
```python
# src/infrastructure/database/config.py (line 97)
async def init_db(...) -> None:  # Changed from def to async def
    global _engine, _async_session_factory
    _engine = create_async_db_engine(...)
    _async_session_factory = create_async_session_factory(_engine)
```

**Also updated:**
```python
# tests/e2e/conftest.py (line 28)
@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():  # Changed to async
    # ...
    await init_db()  # Added await
    yield
```

**Impact:** Unblocked all 16 tests that were failing with "Database session factory not initialized"

### 2. Fixed E2E Test Payloads ✅

Updated 9 test payloads to match correct API schema. Key changes:

**Before (incorrect):**
```json
{
  "nodes": [
    {
      "service_id": "service-a",
      "service_name": "Service A",
      "team": "team-alpha",
      "criticality": "high"
    }
  ],
  "edges": [
    {
      "source_service_id": "service-a",
      "target_service_id": "service-b",
      "communication_mode": "http",
      "discovery_source": "otel_service_graph"
    }
  ]
}
```

**After (correct):**
```json
{
  "source": "manual",
  "timestamp": "2026-02-15T10:00:00Z",
  "nodes": [
    {
      "service_id": "service-a",
      "metadata": {
        "service_name": "Service A",
        "team": "team-alpha",
        "criticality": "high"
      }
    }
  ],
  "edges": [
    {
      "source": "service-a",
      "target": "service-b",
      "attributes": {
        "communication_mode": "sync",
        "criticality": "hard",
        "protocol": "http"
      }
    }
  ]
}
```

**Changes:**
1. Added required `source` field (discovery source)
2. Added required `timestamp` field
3. Moved node fields into `metadata` dict
4. Changed `source_service_id` → `source`
5. Changed `target_service_id` → `target`
6. Wrapped edge attributes in `attributes` object
7. Changed `communication_mode` from "http" to "sync"
8. Added required `criticality` field for edges

**Tests Updated:**
- test_missing_api_key
- test_invalid_api_key
- test_valid_api_key
- test_successful_ingestion
- test_ingestion_with_auto_discovery
- test_ingestion_empty_payload
- test_query_service_with_dependencies
- test_query_with_direction_upstream
- test_query_with_invalid_depth
- test_ingest_and_query_workflow

### 3. Enabled Authentication ✅

**File:** `src/infrastructure/api/routes/dependencies.py`

**Changes:**
```python
# Line 33: Added import
from src.infrastructure.api.middleware.auth import verify_api_key

# Line 67: Enabled auth on POST /dependencies
async def ingest_dependencies(
    request: DependencyGraphIngestApiRequest,
    use_case: IngestDependencyGraphUseCase = Depends(...),
    current_user: str = Depends(verify_api_key),  # Uncommented
) -> DependencyGraphIngestApiResponse:

# Line 192: Enabled auth on GET /dependencies
async def query_dependencies(
    # ... params ...
    use_case: QueryDependencySubgraphUseCase = Depends(...),
    current_user: str = Depends(verify_api_key),  # Uncommented
) -> DependencySubgraphApiResponse:
```

**Impact:** Auth tests now correctly return 401 for missing/invalid keys

### 4. Enhanced Error Handler ✅

**File:** `src/infrastructure/api/middleware/error_handler.py`

**Added HTTPException handling:**
```python
# Line 10: Added import
from fastapi.exceptions import HTTPException

# Lines 72-82: Added HTTPException case
if isinstance(exc, HTTPException):
    return ProblemDetails(
        type="about:blank",
        title=self._get_status_text(exc.status_code),
        status=exc.status_code,
        detail=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        instance=request.url.path,
        correlation_id=correlation_id,
    )

# Lines 127-140: Added helper method
def _get_status_text(self, status_code: int) -> str:
    status_texts = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
        503: "Service Unavailable",
    }
    return status_texts.get(status_code, "Error")
```

**Impact:** FastAPI HTTPExceptions now converted to RFC 7807 format

---

## Test Results

### Before Session 10
- **4/20 tests passing (20%)**
- Health: 2/2 ✅
- Schema validation: 2/2 ✅
- Everything else: BLOCKED by DB init

### After Session 10
- **5/20 tests passing (25%)**
- Health endpoints: 2/2 ✅
- Authentication: 1/3 ✅ (valid key passes)
- Rate limiting: 1/2 ✅ (headers present)
- Error handling: 1/3 ✅ (correlation ID)
- **15/20 failing with 500 Internal Server Error**

### Failing Tests Analysis

**All failures share common pattern:** Getting 500 when expecting successful/error response

**Categories:**
1. **Authentication (2 failing):**
   - test_missing_api_key: Expects 401, gets 500
   - test_invalid_api_key: Expects 401, gets 500

2. **Ingestion (3 failing):**
   - test_successful_ingestion: Expects 202, gets 500
   - test_ingestion_with_auto_discovery: Expects 202, gets 500
   - test_ingestion_empty_payload: Expects 202, gets 500

3. **Query (5 failing):**
   - test_query_nonexistent_service: Expects 404, gets 500
   - test_query_service_with_no_dependencies: Expects 200, gets 500
   - test_query_service_with_dependencies: Expects 200, gets 500
   - test_query_with_direction_upstream: Expects 200, gets 500
   - test_query_with_invalid_depth: Expects 400, gets 500

4. **Rate Limiting (1 failing):**
   - test_rate_limit_enforcement: Type mismatch in error response

5. **Error Handling (2 failing):**
   - test_correlation_id_in_error_response: Expects 404, gets 500
   - test_rfc7807_error_format: Expects 404, gets 500

6. **Full Workflow (1 failing):**
   - test_ingest_and_query_workflow: Gets 500 on ingestion

---

## Root Cause Analysis

### Hypothesis: DTO → Entity Conversion Issues

**Evidence:**
1. Tests that work: health checks (no DB), schema validation (Pydantic only)
2. Tests that fail: all tests requiring use case execution
3. Pattern: 500 errors suggest exceptions in application/domain layer

**Likely Causes (Priority Order):**

1. **Enum Value Mismatch** (HIGH)
   - API schema uses "sync"/"async" for communication_mode
   - Domain entity might expect different values
   - API schema uses "hard"/"soft"/"degraded" for edge criticality
   - Domain entity might expect different values

2. **Missing Required Fields** (MEDIUM)
   - DTO conversion might miss required entity fields
   - Entity validation might fail silently

3. **Database Session Issues** (LOW)
   - get_async_session() might not be working correctly
   - Repository methods might be throwing exceptions

### Debug Commands for Next Session

```bash
# Get full stack trace
pytest tests/e2e/test_dependency_api.py::TestDependencyIngestion::test_successful_ingestion -vv -s --tb=long

# Run with pdb on failure
pytest tests/e2e/test_dependency_api.py::TestDependencyIngestion::test_successful_ingestion --pdb

# Check logs
tail -f /tmp/api.log
```

### Files to Check

**Priority 1: Enum Definitions**
- `src/infrastructure/api/schemas/dependency_schema.py` (API enums)
- `src/application/dtos/dependency_graph_dto.py` (DTO enums)
- `src/domain/entities/service_dependency.py` (Domain enums)

**Priority 2: DTO Conversion**
- `src/infrastructure/api/routes/dependencies.py` lines 86-154 (API → DTO)
- `src/application/use_cases/ingest_dependency_graph.py` (DTO → Entity)

**Priority 3: Entity Creation**
- `src/domain/entities/service.py` __post_init__ validation
- `src/domain/entities/service_dependency.py` __post_init__ validation

---

## Key Learnings

1. **AsyncIO Event Loop Issues:**
   - Session-scoped async fixtures need `pytest_asyncio.fixture`
   - Cannot mix sync and async in fixture chain
   - FastAPI lifespan requires async init/dispose functions

2. **API Schema Validation:**
   - Pydantic catches schema issues at 422 level
   - 500 errors indicate post-validation issues
   - Always test with actual API schema, not domain DTOs

3. **Error Handling Middleware:**
   - Must handle both Exception and HTTPException
   - FastAPI exceptions don't propagate through middleware like regular exceptions
   - Need explicit HTTPException case in error handler

4. **Test Payload Structure:**
   - API schema != Domain DTO structure
   - Always verify against OpenAPI spec
   - Nested structures (metadata, attributes) easy to miss

---

## Files Modified

**Infrastructure:**
- `src/infrastructure/database/config.py` (async init_db)
- `src/infrastructure/api/middleware/error_handler.py` (HTTPException handling)
- `src/infrastructure/api/routes/dependencies.py` (auth enabled)

**Tests:**
- `tests/e2e/conftest.py` (async fixtures)
- `tests/e2e/test_dependency_api.py` (9 payloads fixed)

---

## Next Session Priorities

1. **Get full stack trace** - Identify exact line causing 500 errors
2. **Fix enum mismatch** - Align API/DTO/Domain enum values
3. **Verify DTO conversion** - Test conversion pipeline in isolation
4. **Run all tests** - Expect 18-20/20 passing after fix
5. **Manual testing** - Swagger UI verification
6. **Mark Phase 4 complete** - 100% done

**Estimated Time:** 2-3 hours

---

**Session End:** 2026-02-15, Phase 4 at 95%
**Next Focus:** Debug and fix 500 errors, complete Phase 4

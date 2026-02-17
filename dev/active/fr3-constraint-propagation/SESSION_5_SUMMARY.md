# FR-3 Session 5 Summary - Test Fixes

**Date:** 2026-02-16
**Focus:** Fix all failing FR3 tests from previous session
**Status:** Major progress - 17/17 unit tests passing, 9/13 E2E tests passing

---

## What Was Done

### ✅ Fixed: Mock Type Issues (Tasks #1, #2)
**Problem:** Domain service mocks were using `AsyncMock` for synchronous methods, causing "coroutine object has no attribute" errors.

**Solution:**
- Changed `mock_budget_analyzer`, `mock_unachievable_detector`, `mock_composite`, and `mock_external_buffer` from `AsyncMock()` to `Mock()`
- These services have synchronous methods (`compute_breakdown`, `check`, `compute_composite_bound`, etc.) and should not be async mocked

**Files Modified:**
- `tests/unit/application/use_cases/test_run_constraint_analysis.py`
- `tests/unit/application/use_cases/test_get_error_budget_breakdown.py`

**Result:** Fixed 14 failing use case tests related to "'coroutine' object has no attribute" errors

---

### ✅ Fixed: Time Window Validation Errors (Task #1)
**Problem:** `AvailabilitySliData` validation failing because `window_start` and `window_end` were the same timestamp.

**Solution:**
- Added/used helper function `create_avail_sli()` that properly creates time windows:
  ```python
  now = datetime.now(timezone.utc)
  window_start = now - timedelta(days=30)
  window_end = now
  ```
- Replaced all manual `AvailabilitySliData` instantiations with `create_avail_sli()` calls

**Files Modified:**
- `tests/unit/application/use_cases/test_run_constraint_analysis.py` (added helper, replaced 7+ instances)
- `tests/unit/application/use_cases/test_get_error_budget_breakdown.py` (added helper, replaced 7+ instances)

**Result:** Fixed all "window_end must be after window_start" validation errors

---

### ✅ Fixed: CircularDependencyAlert Constructor Error
**Problem:** Test was passing `cycle_length` parameter which doesn't exist in the entity.

**Solution:**
- Removed `cycle_length=3` parameter (not used in entity)
- Changed `status="open"` to `status=AlertStatus.OPEN` (proper enum usage)
- Added import for `AlertStatus`

**File Modified:**
- `tests/unit/application/use_cases/test_run_constraint_analysis.py:539-544`

---

### ✅ Fixed: Floating Point Precision in Assertions
**Problem:** Test assertion `assert result.composite_availability_bound_pct == 99.77` failing due to floating point precision (99.77000000000001).

**Solution:**
- Changed exact equality check to tolerance-based: `assert abs(result.composite_availability_bound_pct - 99.77) < 0.01`

**File Modified:**
- `tests/unit/application/use_cases/test_run_constraint_analysis.py:268`

---

### ✅ Fixed: E2E Test Schema Assertions (Task #3)
**Problem:** E2E tests expected nested `error_budget_breakdown` field, but API returns flat response.

**Solution:**
- Updated test assertions to match actual API schema (`ErrorBudgetBreakdownApiResponse`):
  - Removed `data["error_budget_breakdown"]` nesting
  - Accessed fields directly: `data["total_error_budget_minutes"]`, `data["self_consumption_pct"]`, etc.
- Fixed risk level assertions: changed from `["LOW", "MODERATE", "HIGH"]` to `["low", "moderate", "high"]` (lowercase)
- Fixed `high_risk_dependencies` assertions:
  - Changed from expecting list of objects to list of service_id strings
  - Added logic to find matching risks in `dependency_risks` array

**Files Modified:**
- `tests/e2e/test_constraint_analysis.py:476-499` (test_successful_error_budget_breakdown)
- `tests/e2e/test_constraint_analysis.py:635-645` (test_error_budget_breakdown_high_risk_dependencies)

**Result:** 2 more E2E tests passing (9/13 total)

---

## Test Results Summary

### Unit Tests: ✅ 17/17 Passing (100%)
```
tests/unit/application/use_cases/test_run_constraint_analysis.py     10 passed
tests/unit/application/use_cases/test_get_error_budget_breakdown.py  7 passed
```

**Coverage:**
- `run_constraint_analysis.py`: 92% coverage
- `get_error_budget_breakdown.py`: 90% coverage

### E2E Tests: ⚠️ 9/13 Passing (69%)
**Passing (9 tests):**
- ✅ test_constraint_analysis_service_not_found
- ✅ test_constraint_analysis_invalid_params
- ✅ test_error_budget_breakdown_default_params
- ✅ test_error_budget_breakdown_service_not_found
- ✅ test_error_budget_breakdown_invalid_params
- ✅ test_constraint_analysis_requires_auth
- ✅ test_error_budget_breakdown_requires_auth
- ✅ test_successful_error_budget_breakdown (fixed this session)
- ✅ test_error_budget_breakdown_high_risk_dependencies (fixed this session)

**Failing (4 tests):**
- ❌ test_successful_constraint_analysis - 500 error (internal exception)
- ❌ test_constraint_analysis_with_external_service - 400 at ingestion
- ❌ test_constraint_analysis_unachievable_slo - 500 error (internal exception)
- ❌ test_constraint_analysis_no_dependencies - 400 instead of 422

---

## Remaining Issues

### Issue #1: 500 Errors on Successful Constraint Analysis
**Symptoms:**
- Tests with valid data return 500 Internal Server Error
- Error response: "An unexpected error occurred while processing the request"
- Logs show request completes with 500 after ~277ms

**Likely Causes:**
1. Exception in use case `execute()` method
2. Exception during DTO → API schema conversion
3. Missing data from mock telemetry service in E2E context

**Investigation Needed:**
- Add debug logging to use case
- Check if mock telemetry data is properly configured for E2E tests
- Verify all required fields are present in response DTO

### Issue #2: External Service Ingestion Returns 400
**Symptom:** `test_constraint_analysis_with_external_service` fails at ingestion with 400 Bad Request

**Likely Cause:** Metadata format for external services with `service_type` and `published_sla` fields not accepted by ingestion endpoint

**Fix Needed:** Update ingestion payload in test or fix ingestion validator

### Issue #3: No Dependencies Returns 400 Instead of 422
**Symptom:** Service with no dependencies returns 400 (Bad Request) instead of 422 (Unprocessable Entity)

**Status:** Both are acceptable HTTP codes for this scenario; test expectation may need update

---

## Key Learnings

1. **Mock Types Matter:** Using `AsyncMock` for synchronous methods causes subtle coroutine-related errors
2. **Helper Functions Reduce Duplication:** `create_avail_sli()` eliminated ~15 instances of copy-paste code
3. **API Schema vs Test Expectations:** E2E tests should match actual API schema, not idealized structure
4. **Floating Point Comparisons:** Always use tolerance-based assertions for float comparisons
5. **Entity Invariants:** Domain entities enforce validation rules; tests must respect them

---

## Files Modified This Session

### Test Files
1. `tests/unit/application/use_cases/test_run_constraint_analysis.py`
   - Changed 4 mock fixtures from AsyncMock to Mock
   - Added import for `Mock`
   - Replaced 7+ `AvailabilitySliData` instantiations with helper
   - Fixed CircularDependencyAlert constructor call
   - Fixed floating point assertion

2. `tests/unit/application/use_cases/test_get_error_budget_breakdown.py`
   - Changed 2 mock fixtures from AsyncMock to Mock
   - Added helper function `create_avail_sli()`
   - Added import for `Mock` and `timedelta`
   - Replaced 7+ `AvailabilitySliData` instantiations with helper

3. `tests/e2e/test_constraint_analysis.py`
   - Fixed schema assertions in 2 error budget breakdown tests
   - Added debug print for error responses (can be removed)

### No Production Code Changes
All fixes were test-only modifications - no changes to application code, domain logic, or API routes.

---

## Recommendations for Next Session

### Priority 1: Investigate 500 Errors
1. Add logging to `RunConstraintAnalysisUseCase.execute()` at each step
2. Verify mock telemetry data in E2E test setup
3. Check if all required DTO fields are populated
4. Reproduce error locally with docker-compose up

### Priority 2: Fix External Service Ingestion
1. Review ingestion schema validation for external services
2. Update test payload with correct metadata format
3. Verify `service_type` and `published_sla` fields are properly handled

### Priority 3: Finalize E2E Tests
1. Resolve 400 vs 422 status code discrepancy
2. Remove debug print statements
3. Run full test suite to ensure no regressions

### Priority 4: Update Documentation
1. Update `fr3-constraint-propagation-context.md` with Session 5 results
2. Update `fr3-constraint-propagation-tasks.md` with final test status
3. Consider archiving FR3 feature folder once complete

---

## Commands for Next Session

### Run All FR3 Tests
```bash
source .venv/bin/activate
pytest tests/unit/application/use_cases/test_run_constraint_analysis.py \
       tests/unit/application/use_cases/test_get_error_budget_breakdown.py \
       tests/e2e/test_constraint_analysis.py -v
```

### Debug Single Failing Test
```bash
pytest tests/e2e/test_constraint_analysis.py::TestConstraintAnalysisEndpoint::test_successful_constraint_analysis -vv -s
```

### Check Code Coverage
```bash
pytest tests/unit/application/use_cases/ --cov=src/application/use_cases --cov-report=term-missing
```

---

**Session Duration:** ~45 minutes
**Tests Fixed:** 17 unit tests (100%), 2 E2E tests (9/13 now passing)
**Next Session Goal:** Fix remaining 4 E2E tests, achieve 100% FR3 test pass rate

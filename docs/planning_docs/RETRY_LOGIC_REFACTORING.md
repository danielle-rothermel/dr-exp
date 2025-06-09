# Retry Logic Refactoring Plan

## Problem Analysis

### Current Issue: Missing Return Statement in Retry Loops

**File**: `src/dr_exp/job_db/supabase_job_db.py:1024`
**Function**: `get_metrics()`

The current retry logic has structural problems:
1. **Nested exception handling**: FileNotFoundError raised in multiple places
2. **Complex branching**: `if response:` creates confusing control flow
3. **Missing return safety net**: Function can fall through without returning

### Recommended Solution Pattern

**Before (Problematic)**:
```python
for attempt in range(max_retries):
    try:
        response = api_call()
        if response:
            # process response
            return result
        else:
            raise SomeError("No response")
    except Exception as e:
        if attempt == max_retries - 1:
            # handle final failure
            raise FinalError()
        else:
            # retry
            continue
# MISSING RETURN - mypy error!
```

**After (Clean)**:
```python
for attempt in range(max_retries):
    try:
        response = api_call()
        
        # Fail fast - check response immediately
        if not response:
            raise SomeError("No response")
        
        # Process successful response
        result = process(response)
        return result
        
    except Exception as e:
        if attempt == max_retries - 1:
            logger.error(f"Final attempt failed: {e}")
            raise FinalError(f"Could not complete after {max_retries} attempts: {e}")
        else:
            logger.warning(f"Retry {attempt + 1}/{max_retries}: {e}")

# Safety net (should never be reached)
raise FinalError(f"Unexpected fallthrough after {max_retries} attempts")
```

### Benefits of New Pattern

1. **Linear flow**: Each attempt either succeeds (returns) or fails (raises)
2. **Single exception path**: All failures go through same handler
3. **Fail-fast**: Immediately raise on invalid response
4. **Safety net**: Final raise prevents fallthrough
5. **Clearer intent**: Obvious that each attempt returns or raises

## Identified Locations Needing This Pattern

### 1. CONFIRMED: supabase_job_db.py:1024 - get_metrics()
- **Issue**: Missing return statement after retry loop
- **Impact**: MyPy error, potential runtime bug
- **Priority**: HIGH

### 2. CONFIRMED PROBLEMATIC PATTERNS FOUND

#### HIGH PRIORITY (Can cause runtime errors)

**supabase_job_db.py:1024** - `get_metrics()`
- Missing return statement after retry loop
- Can fall through without returning if all retries fail silently

#### MEDIUM PRIORITY (Complex control flow)

**local_job_db.py:95-204** - `claim_job()`
- Multiple nested loops with complex exception handling
- Multiple continue statements in exception handlers
- Multiple return paths scattered throughout function

**local_job_db.py:754-795** - `get_stale_jobs()`
- Loop with continue in exception handler masking errors
- Multiple validation checks causing early continues

**worker.py:228-302** - `_finalize_and_upload()`
- Multiple try/except blocks with early returns
- Similar error handling paths with subtle differences

**manager.py:89-154** - `check_stale_jobs()`
- Loop with complex exception handling and early continue
- Multiple early returns in different code paths

#### LOW PRIORITY (Minor cleanup opportunities)

**main.py:94-113** - `ConnectionManager.broadcast()`
- Loop with exception handling that continues processing
- Cleanup logic after loop completion

**job_reaper.py:37-52** - `reap_stale_jobs()`
- Multiple continue statements for different conditions
- Exception handling with continue masking details

## Common Anti-Patterns Identified

1. **Loops with try/except blocks using `continue`** - Unclear behavior when all iterations fail
2. **Multiple nested exception types** raised/caught in different places
3. **Complex nested if/else within try/except blocks**
4. **Missing explicit return statements** causing potential fallthrough
5. **Exception handlers masking errors** with continue statements
6. **Multiple early return paths** mixed with exception handling

## Implementation Plan

1. **Phase 1**: Fix immediate mypy error in `get_metrics()`
2. **Phase 2**: Audit entire codebase for similar retry patterns
3. **Phase 3**: Refactor all identified locations using consistent pattern
4. **Phase 4**: Create utility function for common retry logic

## Implementation Status

- [x] **COMPLETED**: Fix `get_metrics()` function (line 1024) - mypy error resolved
- [x] **COMPLETED**: Complete codebase audit - found 7 problematic functions
- [x] **COMPLETED**: Document all findings - documented in this file
- [ ] **PENDING**: Implement refactoring plan for remaining functions

### Recent Implementation

**2025-06-08**: Fixed `supabase_job_db.py:1024` - `get_metrics()` function
- ✅ Restructured retry logic to fail fast on empty response
- ✅ Added safety net to prevent fallthrough 
- ✅ Eliminated nested exception handling
- ✅ Verified with mypy - error count reduced from 31 to 30
- ✅ Clean linear control flow now ensures each attempt returns or raises

**Changes Made:**
```python
# Before: Complex nested if/else in try/except with potential fallthrough
if response:
    # process...
    return metrics
else:
    raise FileNotFoundError(...)

# After: Fail fast with linear flow
if not response:
    raise FileNotFoundError(...)
# process...
return metrics
# + safety net at end
```
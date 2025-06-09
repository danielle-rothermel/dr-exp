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

**supabase_job_db.py:1024** - `get_metrics()` ✅ **COMPLETED**
- ~~Missing return statement after retry loop~~
- ~~Can fall through without returning if all retries fail silently~~

#### MEDIUM PRIORITY (Complex control flow)

**local_job_db.py:95-204** - `claim_job()` ✅ **COMPLETED**
- ~~Multiple nested loops with complex exception handling~~
- ~~Multiple continue statements in exception handlers~~
- ~~Multiple return paths scattered throughout function~~

**local_job_db.py:895-936** - `get_stale_jobs()` ✅ **COMPLETED**
- ~~Loop with continue in exception handler masking errors~~
- ~~Multiple validation checks causing early continues~~

**worker.py:228-302** - `_finalize_and_upload()` ✅ **COMPLETED**
- ~~Multiple try/except blocks with early returns~~
- ~~Similar error handling paths with subtle differences~~

**manager.py:89-154** - `check_stale_jobs()` ✅ **COMPLETED**
- ~~Loop with complex exception handling and early continue~~
- ~~Multiple early returns in different code paths~~

#### LOW PRIORITY (Minor cleanup opportunities)

**main.py:94-113** - `ConnectionManager.broadcast()` ✅ **COMPLETED**
- ~~Loop with exception handling that continues processing~~
- ~~Cleanup logic after loop completion~~

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

**2025-06-08**: Refactored `local_job_db.py:95-204` - `claim_job()` function
- ✅ Extracted 6 helper methods from 110-line monolithic function
- ✅ Eliminated nested loops with complex exception handling
- ✅ Removed continue statements masking errors in exception handlers  
- ✅ Separated concerns: job discovery vs reservation handling vs claiming
- ✅ Improved error handling with specific exception types and proper logging levels
- ✅ Made code testable with single-responsibility helper methods
- ✅ Verified with mypy - only 2 additional cosmetic errors (returning Any)

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

**Helper Methods Extracted:**
- `_discover_claimable_jobs()` - Job discovery with error handling
- `_safe_read_job()` - File reading with specific exception types
- `_is_job_claimable()` - Reservation checking logic
- `_handle_job_reservation()` - Reservation expiration handling
- `_clear_expired_reservation()` - Atomic reservation cleanup
- `_attempt_claim_job()` - Atomic job claiming with proper error handling

**2025-06-08**: Refactored `local_job_db.py:895-936` - `get_stale_jobs()` function
- ✅ Extracted helper methods `_process_job_for_staleness()` and `_parse_heartbeat_timestamp()`
- ✅ Added custom exception types `JobValidationError` and `HeartbeatParseError`
- ✅ Eliminated continue statements masking errors in exception handlers
- ✅ Implemented fail-fast validation with linear control flow
- ✅ Added comprehensive unit tests covering all edge cases and error conditions
- ✅ Fixed None handling in heartbeat timestamp parsing
- ✅ Verified with mypy - no new type errors introduced

**Changes Made:**
```python
# Before: Complex loop with continue statements masking errors
for job in running_jobs:
    if not heartbeat_str or not assigned_worker or not job_id:
        continue
    try:
        # complex parsing and validation
    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing heartbeat for job {job_id}: {e}")
        continue

# After: Clean separation of concerns with specific exception handling
for job in running_jobs:
    try:
        stale_job = self._process_job_for_staleness(job, now, max_age_seconds)
        if stale_job:
            stale_jobs.append(stale_job)
    except JobValidationError as e:
        logger.warning(f"Skipping invalid job data: {e}")
    except HeartbeatParseError as e:
        logger.error(f"Error parsing heartbeat for job {job.get('id', 'unknown')}: {e}")
```

**Helper Methods Extracted:**
- `_process_job_for_staleness()` - Main staleness logic with fail-fast validation
- `_parse_heartbeat_timestamp()` - Robust timestamp parsing with proper error handling

**2025-06-08**: Refactored `worker.py:228-302` - `_finalize_and_upload()` function
- ✅ Eliminated duplicate try/except blocks with identical error handling logic
- ✅ Created custom UploadError exception for cleaner error hierarchy
- ✅ Extracted helper methods to consolidate upload logic
- ✅ Implemented single source of truth for upload failure handling  
- ✅ Added comprehensive unit tests for all new helper methods
- ✅ Verified with mypy and all tests passing - no regressions introduced
- ✅ Reduced code duplication by 30+ lines while improving maintainability

**Changes Made:**
```python
# Before: Duplicate error handling blocks
try:
    metrics_upload = self.client.upload_artifact(...)
    if not metrics_upload["success"]:
        raise RuntimeError(f"Metrics upload failed: {metrics_upload.get('error', 'Unknown error')}")
except Exception as e:
    logging.error(f"Critical: Failed to upload metrics for job {self.job_id}: {e}")
    self.client.record_failure(self.job_id, "upload_failure", f"Failed to upload training metrics: {e}")
    self.client.finalize_job(self.job_id, "failed", {"finalize_success": False})
    return {"finalize_success": False, "error": str(e)}

try:
    bundle_upload = self._create_and_upload_bundle(...)
    if not bundle_upload["success"]:
        raise RuntimeError(f"Bundle upload failed: {bundle_upload.get('error', 'Unknown error')}")
except Exception as e:
    logging.error(f"Critical: Failed to upload bundle for job {self.job_id}: {e}")
    self.client.record_failure(self.job_id, "upload_failure", f"Failed to upload training bundle: {e}")
    self.client.finalize_job(self.job_id, "failed", {"finalize_success": False})
    return {"finalize_success": False, "error": str(e)}

# After: Clean separation with single error handling path
try:
    logger_meta = logger.finalize()
    metrics_upload = self._upload_metrics_with_retry(logger_meta)
    bundle_upload = self._upload_bundle_with_retry(logger, work_dir, worker_log_path)
    return self._create_success_metadata(result, train_status, metrics_upload, bundle_upload, logger_meta)
except UploadError as e:
    return self._handle_upload_failure(e)
```

**Helper Methods Extracted:**
- `_upload_metrics_with_retry()` - Metrics upload with proper error handling
- `_upload_bundle_with_retry()` - Bundle upload with proper error handling  
- `_create_success_metadata()` - Success path metadata creation
- `_handle_upload_failure()` - Single source of truth for upload failure handling

**2025-06-08**: Refactored `manager.py:89-154` - `check_stale_jobs()` function
- ✅ Eliminated complex loop with mixed continue/re-raise error handling patterns
- ✅ Created custom StaleJobProcessingError and WorkerRestartError exception classes
- ✅ Extracted 4 helper methods with single responsibility and fail-fast validation
- ✅ Implemented linear control flow - each method either succeeds or raises specific exceptions
- ✅ Improved error isolation - worker restart failures don't crash entire manager process
- ✅ Added comprehensive unit tests covering all edge cases and error conditions
- ✅ Verified with mypy and all tests passing - no regressions introduced
- ✅ Enhanced recoverability - manager continues with next check cycle after processing errors

**Changes Made:**
```python
# Before: Complex loop with mixed error handling strategies
for worker_id in affected_workers:
    if worker_id not in managed_workers:
        logging.warning(f"Cannot restart worker {worker_id}: not managed by process manager")
        continue  # Masks errors for some workers
    try:
        self.process_manager.restart_worker(worker_id)
        logging.info("Restarted worker %s", worker_id)
    except RuntimeError as e:
        logging.error(f"Critical: Worker restart failed for {worker_id}: {e}")
        # Re-raise crashes entire process - inconsistent with continue above
        raise RuntimeError(f"Manager cannot continue with failing worker infrastructure: {e}") from e

# After: Clean separation with consistent error handling
try:
    stale_jobs = self._get_and_log_stale_jobs()
    if not stale_jobs:
        return
    self._mark_stale_jobs_failed(stale_jobs)
    self._restart_affected_workers(stale_jobs)
except StaleJobProcessingError as e:
    logging.error(f"Failed to process stale jobs: {e}")
    # Allow manager to continue with next check cycle
```

**Helper Methods Extracted:**
- `_get_and_log_stale_jobs()` - Stale job discovery and logging with fail-fast validation
- `_mark_stale_jobs_failed()` - Batch job failure marking with specific error handling
- `_restart_affected_workers()` - Coordinated worker restart operations with failure collection
- `_restart_single_worker()` - Atomic worker restart with proper error handling

**2025-06-08**: Refactored `main.py:94-113` - `ConnectionManager.broadcast()` function
- ✅ Enhanced error handling with improved observability and logging
- ✅ Added connection tracking with success/failure counts 
- ✅ Implemented debug logging for successful broadcasts to all connections
- ✅ Added warning logging for partial failures with detailed connection counts
- ✅ Maintained existing void return API while improving internal error tracking
- ✅ Added comprehensive unit tests covering all broadcast scenarios
- ✅ Configured pytest-asyncio for async test support
- ✅ Verified with all existing WebSocket tests passing - no regressions introduced

**Changes Made:**
```python
# Before: Silent partial failures with minimal logging
for connection in self.active_connections:
    try:
        await connection.send_text(message_text)
    except Exception as e:
        logger.error(f"Critical WebSocket failure during broadcast: {e}")
        disconnected.add(connection)
        # Continue with other connections but track failures

# After: Enhanced observability with success/failure tracking
total_connections = len(self.active_connections)

for connection in self.active_connections:
    try:
        await connection.send_text(message_text)
    except Exception as e:
        logger.error(f"Critical WebSocket failure during broadcast: {e}")
        disconnected.add(connection)

# Remove disconnected clients and log results
for connection in disconnected:
    self.disconnect(connection)

if disconnected:
    successful = total_connections - len(disconnected)
    logger.warning(f"Broadcast partial success: {successful}/{total_connections} connections")
else:
    logger.debug(f"Broadcast successful to all {total_connections} connections")
```

**Testing Coverage Added:**
- Successful broadcast to all connections with debug logging verification
- Partial failure scenarios with proper connection cleanup and warning logging
- Complete failure scenarios with error isolation and logging
- Empty connection set handling (no unnecessary logging)
- Complex JSON serialization with nested structures and unicode
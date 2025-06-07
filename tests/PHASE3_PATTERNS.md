# Phase 3 Testing Patterns Documentation

## Overview

Phase 3 enhanced the test infrastructure with comprehensive edge case coverage, advanced concurrency testing, and recovery mechanism validation. This document outlines the new testing patterns and best practices established in Phase 3.

## Key Achievement: Fixed Integration Test Issues

### Root Cause Analysis
- **Issue**: 4 integration tests in `test_integration.py` were returning `'failed'` instead of `'completed'`
- **Root Cause**: Test mock functions were calling `logger.log_metric()` but the actual logger interface only provides `logger.log()`
- **Solution**: Updated all test mocks to use the correct `logger.log({"metric_name": value})` pattern

### Worker Status Return Logic Fix
- **Issue**: Target job claiming was failing due to incorrect claiming logic
- **Root Cause**: Worker was calling general `claim_job()` and hoping to get the target job, but higher priority jobs would be claimed instead
- **Solution**: Implemented direct job claiming by updating job status for target jobs

## New Testing Infrastructure (test_phase3_edge_cases.py)

### 1. Database Error Scenarios (TestDatabaseErrorScenarios)

```python
# Pattern: Test database connection failures during operations
def test_worker_handles_database_connection_failure(self, isolated_job_db, worker_execution_helper):
    # Mock database operations to fail selectively
    with patch.object(isolated_job_db, 'update_job', side_effect=failing_update):
        status = worker_execution_helper.run_worker_with_trainer(successful_train)
        assert status == "completed"  # Worker should handle failures gracefully
```

**Key Patterns:**
- Use selective mocking to simulate specific failure points
- Verify worker resilience to database connectivity issues
- Test artifact upload failures without breaking job completion
- Validate proper error recording in separate error tracking

### 2. Training Function Error Scenarios (TestTrainingFunctionErrors)

```python
# Pattern: Test various training exceptions
def test_training_function_memory_error(self, isolated_job_db, worker_execution_helper):
    def memory_error_train(config, logger):
        raise MemoryError("Out of memory during training")
    
    status = worker_execution_helper.run_worker_with_trainer(memory_error_train)
    assert status == "failed"
    
    # Verify error details in job metadata
    job_details = isolated_job_db.get_job_details(job["id"])
    assert job_details["train_status"] == "crash"
    assert job_details["final_val_acc"] is None
```

**Key Patterns:**
- Test different exception types (MemoryError, RuntimeError, ValueError, etc.)
- Verify `train_status == "crash"` for training exceptions
- Check that metrics show appropriate failure values (None for accuracy, 0 for epochs)
- Avoid using actual KeyboardInterrupt in tests (use RuntimeError instead)

### 3. Concurrency and Race Conditions (TestConcurrencyAndRaceConditions)

```python
# Pattern: Test race conditions in job claiming
def test_multiple_workers_claiming_same_job(self, isolated_job_db, worker_coordination):
    # Create single job for multiple workers to compete for
    job = isolated_job_db.add_test_job({"test": "race_condition"}, priority=900)
    
    # Start multiple workers simultaneously
    worker_threads = []
    for worker_id in ["worker_1", "worker_2", "worker_3"]:
        thread = threading.Thread(target=run_worker_thread, args=(worker_id,))
        worker_threads.append(thread)
        thread.start()
    
    # Verify exactly one worker succeeded
    completed_workers = [wid for wid, status in worker_results.items() if status == "completed"]
    assert len(completed_workers) == 1
```

**Key Patterns:**
- Use threading to simulate concurrent access
- Test job claiming atomicity with multiple workers
- Verify priority ordering under concurrent access
- Test high-frequency job processing scenarios
- Validate database access pattern integrity

**Advanced Concurrency Tests:**
- **High-frequency processing**: 20 jobs processed by 5 workers rapidly
- **Database access patterns**: Concurrent claiming and status updates
- **Priority ordering**: Verify priority is maintained under concurrency

### 4. Resource Constraints (TestResourceConstraints)

```python
# Pattern: Test system behavior under resource pressure
def test_disk_space_exhaustion(self, isolated_job_db, worker_execution_helper):
    def disk_space_train(config, logger):
        raise OSError("No space left on device")
    
    status = worker_execution_helper.run_worker_with_trainer(disk_space_train)
    assert status == "failed"
    assert job_details["train_status"] == "crash"
```

**Key Patterns:**
- Test disk space exhaustion scenarios
- Verify temporary directory cleanup
- Test logger resource limits with heavy logging
- Validate graceful degradation under resource pressure

### 5. Recovery Mechanisms (TestRecoveryMechanisms)

```python
# Pattern: Test automatic retry logic
def test_automatic_job_retry_after_failure(self, isolated_job_db, worker_execution_helper):
    attempt_count = 0
    def retry_train(config, logger):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count <= 2:
            raise RuntimeError(f"Simulated failure attempt {attempt_count}")
        return {"final_val_acc": 0.95, "status": "success"}
    
    # Simulate retry logic by manually requeuing jobs
    for attempt in range(3):
        status = worker_execution_helper.run_worker_with_trainer(retry_train)
        if status == "completed":
            break
        # Requeue for retry
        isolated_job_db.update_job(job["id"], {"status": "queued", "retry_index": attempt + 1})
```

**Key Patterns:**
- Test multi-attempt failure and recovery scenarios
- Verify graceful shutdown during training
- Test manager recovery after unexpected restart
- Validate stale job detection and recovery

## Enhanced Testing Utilities

### Error Verification Patterns

**Correct Pattern for Error Verification:**
```python
# ✅ Correct: Check train_status for training failures
job_details = isolated_job_db.get_job_details(job["id"])
assert job_details["status"] == "failed"
assert job_details["train_status"] == "crash"
assert job_details["final_val_acc"] is None

# ❌ Incorrect: status_reason doesn't exist in this implementation
assert "MemoryError" in job_details.get("status_reason", "")
```

### Mock Training Functions

**Correct Logger Interface:**
```python
# ✅ Correct: Use logger.log() with dictionary
def correct_mock_train(config, logger):
    logger.log({"test_metric": 0.95, "epoch": 1})
    return {"final_val_acc": 0.95, "status": "success"}

# ❌ Incorrect: log_metric() method doesn't exist
def incorrect_mock_train(config, logger):
    logger.log_metric("test_metric", 0.95)  # This will fail
```

### Concurrency Test Patterns

```python
# Pattern: Thread coordination for deterministic concurrency tests
def run_concurrent_worker(worker_id):
    status = run_worker(
        base_path=isolated_job_db.config.base_path,
        max_claim_attempts=1,  # Fail fast for race condition tests
        heartbeat_interval=0.1,  # Fast heartbeat for testing
        trainer_fn=coordinated_train,
        client=isolated_job_db,
        worker_id=worker_id
    )
    worker_results[worker_id] = status

# Start workers with slight staggering for race condition testing
for i in range(3):
    thread = threading.Thread(target=run_concurrent_worker, args=(f"worker_{i}",))
    thread.start()
    time.sleep(0.01)  # Slight stagger to test race conditions
```

## Test Categories and Markers

### Slow Tests
```python
@pytest.mark.slow
def test_long_running_scenario():
    # Tests that take >5 seconds
```

### Integration Tests
```python
@pytest.mark.integration
def test_full_system_integration():
    # Tests that exercise multiple components
```

## Best Practices Established

### 1. Test Isolation
- Use `isolated_job_db` fixture for database isolation
- Reset state between tests using `isolated_job_db.reset_state()`
- Use temporary directories that are automatically cleaned up

### 2. Deterministic Timing
- Use `enhanced_mock_time` for controlled time progression
- Set named milestones for test coordination
- Use `advance_to_make_stale()` for stale job testing

### 3. Error Handling Verification
- Always check both job status and train_status
- Verify appropriate metadata fields (final_val_acc, num_epochs, etc.)
- Test error recovery paths, not just error detection

### 4. Concurrency Testing
- Use threading for concurrent access simulation
- Test both success and failure scenarios under concurrency
- Verify atomicity of critical operations (job claiming, status updates)

### 5. Resource Management
- Test temporary directory cleanup
- Verify graceful handling of resource exhaustion
- Test system behavior under memory/disk pressure

## Summary

Phase 3 added 18 comprehensive edge case tests covering:
- ✅ **Database error scenarios** (3 tests)
- ✅ **Training function errors** (4 tests)  
- ✅ **Concurrency and race conditions** (5 tests)
- ✅ **Resource constraints** (3 tests)
- ✅ **Recovery mechanisms** (3 tests)

**Key achievements:**
1. **Fixed 4 failing integration tests** by correcting logger interface usage
2. **Enhanced worker target job claiming** logic
3. **Systematic edge case coverage** with proper error verification
4. **Advanced concurrency testing** with thread coordination
5. **Recovery mechanism validation** with deterministic timing

These patterns provide a solid foundation for maintaining system reliability and can be extended for future edge case coverage.
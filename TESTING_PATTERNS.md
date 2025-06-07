# Testing Patterns Reference

This document provides technical patterns and best practices for testing the dr_exp system.

## Mock Training Functions

### ✅ Correct Pattern
```python
def mock_train(config, logger, *args, **kwargs):
    # Do test-specific logic
    priority_level = config.get("priority_test")
    execution_order.append(priority_level)
    
    # IMPORTANT: Return "success" not "completed"
    return {"final_val_acc": 0.95, "status": "success"}

# Use direct trainer_fn parameter
from dr_exp.manage.worker import run_worker

status = run_worker(
    base_path=integration_config.job_db_config.base_path,
    max_claim_attempts=integration_config.max_claim_attempts,
    heartbeat_interval=integration_config.worker_heartbeat_interval,
    trainer_fn=mock_train,  # Direct parameter - no patching needed
    client=factory.job_db,
    worker_id="test_worker"
)
```

### ❌ Avoid These Patterns
```python
# DON'T: Patch default_train (import-time binding issues)
with patch('dr_exp.manage.worker.default_train', side_effect=mock_train):
    factory.run_worker()

# DON'T: Return "completed" status (worker expects "success")
return {"status": "completed"}  # Wrong!

# DON'T: Use time.sleep() for coordination
time.sleep(0.1)  # Flaky timing
```

## Event-Driven Synchronization

### Threading Events for Coordination
```python
def test_async_operation():
    started = threading.Event()
    can_complete = threading.Event()
    
    def mock_operation():
        started.set()  # Signal operation started
        can_complete.wait(timeout=5)  # Wait for test coordination
        return "result"
    
    # Run operation in thread
    result = []
    thread = threading.Thread(target=lambda: result.append(mock_operation()))
    thread.start()
    
    # Wait for operation to start, then allow completion
    assert started.wait(timeout=5), "Operation did not start"
    can_complete.set()
    
    thread.join(timeout=10)
    assert len(result) == 1
```

### Heartbeat Testing Pattern
```python
def test_heartbeat_mechanism(integration_config):
    heartbeat_updates = []
    training_started = threading.Event()
    training_can_complete = threading.Event()
    
    def mock_train(config, logger, *args, **kwargs):
        training_started.set()
        training_can_complete.wait(timeout=5)
        return {"final_val_acc": 0.95, "status": "success"}
    
    # Monitor heartbeat updates
    original_update = factory.job_db.update_job
    def track_heartbeat_updates(job_id, updates):
        if "heartbeat" in updates:
            heartbeat_updates.append(updates["heartbeat"])
            if len(heartbeat_updates) >= 2:
                training_can_complete.set()
        return original_update(job_id, updates)
    
    with patch.object(factory.job_db, 'update_job', side_effect=track_heartbeat_updates):
        # Run in thread to allow heartbeat monitoring
        # ... rest of test
```

## Deterministic Timing

### Mock Time Fixture Usage
```python
def test_stale_job_detection(mock_time):
    # Set initial heartbeat
    old_heartbeat = mock_time.now()
    job_db.update_job(job_id, {"heartbeat": old_heartbeat.isoformat() + "Z"})
    
    # Advance time to make job stale
    mock_time.advance(25)  # 25 seconds
    
    # Mock datetime in the module that checks staleness
    with patch('dr_exp.job_db.local_job_db.datetime') as mock_datetime:
        mock_datetime.now.return_value = mock_time.now()
        mock_datetime.UTC = UTC
        mock_datetime.fromisoformat = datetime.fromisoformat
        
        manager.check_stale_jobs()
```

### Database State Verification
```python
def verify_job_statuses(job_db, expected_statuses):
    """Helper to verify multiple job statuses."""
    for job_id, expected_status in expected_statuses.items():
        job_details = job_db.get_job_details(job_id)
        assert job_details["status"] == expected_status, f"Job {job_id} has status {job_details['status']}, expected {expected_status}"

# Usage
verify_job_statuses(factory.job_db, {
    high_priority_job["id"]: "completed",
    low_priority_job["id"]: "queued"
})
```

## Test Fixtures

### Integration Config Pattern
```python
@pytest.fixture
def integration_config(tmp_path):
    job_db_config = JobDBConfig(
        base_path=str(tmp_path),
        storage_path=str(tmp_path / "storage"),
        mode="files_local"  # Use local mode for test isolation
    )
    
    return SystemConfig(
        job_db_config=job_db_config,
        gpus=["0", "1"],
        workers_per_gpu=2,
        heartbeat_timeout=10,
        idle_timeout_mins=1,
        max_claim_attempts=3,
        worker_heartbeat_interval=0.1  # Fast heartbeat for testing
    )
```

### Mock Time Fixture
```python
@pytest.fixture
def mock_time():
    class MockTime:
        def __init__(self):
            self._current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        
        def now(self, tz=None):
            return self._current_time
        
        def advance(self, seconds):
            self._current_time += timedelta(seconds=seconds)
    
    return MockTime()
```

## Common Pitfalls

1. **Mock Scope**: Don't patch imports, use direct parameters when possible
2. **Status Values**: Training functions return "success", jobs become "completed" 
3. **Timing**: Use events and mock time, not real delays
4. **Database Isolation**: Each test needs fresh database state
5. **Worker Lifecycle**: Always use the same parameter pattern for run_worker

## Reference Implementation

See `tests/manage/test_integration.py` for working examples of all these patterns.
# Phase 3 Context for New Agent

## Current Status
- **Phase 1**: ✅ Fixed critical integration tests with event-driven patterns
- **Phase 2**: ✅ Built comprehensive test infrastructure  
- **Phase 3**: 🔄 **CURRENT WORK** - Edge case coverage and error scenario testing

## Immediate Issues to Address

### 1. Integration Test Failures (Priority: HIGH)
4 tests in `tests/manage/test_integration.py` are failing with `'failed'` status instead of `'completed'`:

```bash
FAILED tests/manage/test_integration.py::TestManagerWorkerIntegration::test_end_to_end_job_execution
FAILED tests/manage/test_integration.py::TestFactoryIntegration::test_factory_worker_execution_with_parameters  
FAILED tests/manage/test_integration.py::TestFullSystemIntegration::test_complete_experiment_lifecycle
FAILED tests/manage/test_integration.py::TestFullSystemIntegration::test_failure_recovery_and_retry
```

**Root Cause**: Likely logger interface issues or error handling problems in worker execution.

## Available Infrastructure (Phase 2)

### Enhanced Fixtures (`tests/conftest.py`):
- `enhanced_mock_time`: Named milestones, event-driven timing
- `isolated_job_db`: Database isolation with verification utilities
- `worker_coordination`: Multi-worker synchronization 
- `integration_system`: Complete pre-configured system

### Manage-Specific Fixtures (`tests/manage/conftest.py`):
- `heartbeat_monitor`: Track heartbeat updates during execution
- `stale_job_detector`: Create and test stale job scenarios
- `worker_execution_helper`: Standardized worker execution patterns
- `priority_job_factory`: Create jobs with specific priority patterns

### Reference Implementation:
- `tests/manage/test_phase2_infrastructure.py`: 11 working tests demonstrating all patterns
- All Phase 2 infrastructure tests pass successfully

## Phase 3 Goals

### 1. Fix Current Failures
- Investigate why workers return `'failed'` instead of `'completed'`
- Check logger interface compatibility 
- Ensure proper error handling in worker execution

### 2. Systematic Edge Case Coverage
- Database connection failures during operations
- Worker crash recovery scenarios  
- Memory pressure testing
- Training function exception handling

### 3. Enhanced Concurrency Testing
- Race condition tests using worker_coordination
- Resource contention with multiple workers
- Thread safety validation
- Simultaneous worker operations

## Testing Patterns to Use

```python
# Use Phase 2 infrastructure for systematic testing
def test_edge_case(worker_coordination, isolated_job_db, enhanced_mock_time):
    # Create deterministic test scenarios
    worker_coordination.create_worker_event("test_worker")
    jobs = isolated_job_db.create_test_jobs(count=3)
    
    # Use enhanced timing for controlled execution
    enhanced_mock_time.set_milestone("test_start")
    
    # Execute with coordination
    # ... test implementation
```

## Success Criteria for Phase 3
1. **All integration tests pass** (fix the 4 failing tests)
2. **Comprehensive error scenario coverage** added
3. **Enhanced concurrency testing** implemented
4. **Systematic edge case documentation** for future maintenance

## Key Files to Focus On
- `tests/manage/test_integration.py` - Fix failing tests
- `src/dr_exp/manage/worker.py` - Investigate worker status returns
- `src/dr_exp/logging/` - Check logger interface changes
- Add new edge case tests using Phase 2 infrastructure
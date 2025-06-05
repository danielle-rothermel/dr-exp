# Priority-Based Job Queue System Implementation Plan

## Overview

This document outlines the implementation plan for adding a priority-based job queue system to dr_exp. The system will enable fine-grained control over job execution order and support "run one" functionality for immediate job execution.

## Architecture Goals

1. **Priority-based scheduling**: Jobs with higher priority execute before lower priority jobs
2. **"Run One" capability**: Immediate execution of single jobs with urgent priority
3. **Reserved job support**: Guarantee specific jobs run on designated workers
4. **Future extensibility**: Foundation for advanced scheduling features
5. **Backward compatibility**: Existing functionality remains unchanged

## Phase 1: Database Layer - Priority Foundation

### 1. Update BaseJobDB Interface
- [ ] Add `priority` parameter to existing `add_job` method
- [ ] Add `update_job_priority()` abstract method
- [ ] Add `boost_job_priority()` abstract method  
- [ ] Add `list_jobs_by_priority()` abstract method
- [ ] Update docstrings with priority information

### 2. Update LocalJobDB Implementation
- [ ] Add priority field to job creation (default=100)
- [ ] Implement priority-aware `claim_job()` with sorting
- [ ] Implement `update_job_priority()` with audit trail
- [ ] Implement `boost_job_priority()` with bounds checking
- [ ] Implement `list_jobs_by_priority()` with filtering
- [ ] Add age-based priority boost logic
- [ ] Update existing tests to handle priority

### 3. Update SupabaseJobDB Implementation  
- [ ] Add priority support to `add_job_entry()`
- [ ] Implement priority-aware job claiming
- [ ] Implement priority update methods
- [ ] Add priority to database queries

## Phase 2: Priority Classes and Constants

### 4. Create Priority System Module
- [ ] Create `src/dr_exp/utils/priority.py`
- [ ] Define `PriorityClass` enum with ranges
- [ ] Define priority constants (MIN=0, MAX=1000, DEFAULT=100)
- [ ] Add helper functions for priority validation
- [ ] Add priority boost calculation strategies

## Phase 3: Reserved Job Support (Hybrid Approach)

### 5. Add Reservation Support to Databases
- [ ] Add `reserved_for_worker` and `reservation_expires_at` to job schema
- [ ] Update `claim_job()` to respect reservations
- [ ] Add reservation timeout checking logic
- [ ] Add `add_reserved_job()` method to BaseJobDB
- [ ] Implement reservation methods in both databases

## Phase 4: Worker and Manager Updates

### 6. Update Worker Logic
- [ ] Add `target_job_id` parameter to `run_worker()`
- [ ] Add `reserved_worker_id` parameter
- [ ] Add logic to target specific jobs
- [ ] Maintain backward compatibility
- [ ] Update worker tests

### 7. Update Manager Logic
- [ ] Pass priority parameters through to workers
- [ ] Add priority display to job listing
- [ ] Update manager tests

## Phase 5: CLI Integration

### 8. Update Upload Scripts
- [ ] Add `--priority` flag to `upload_configs.py`
- [ ] Add `--priority-class` flag for named priorities
- [ ] Validate priority values
- [ ] Update upload function to pass priority

### 9. Create Priority Management Commands
- [ ] Add `boost-priority` subcommand to `manager_cli.py`
- [ ] Add `list-queue` subcommand with priority sorting
- [ ] Add `reprioritize-sweep` subcommand
- [ ] Add appropriate help text and validation

## Phase 6: Run One Implementation

### 10. Create Run One Script
- [ ] Create `scripts/run_one.py` with Hydra integration
- [ ] Implement urgent priority job creation
- [ ] Add optional worker spawning
- [ ] Add `--wait` flag for synchronous execution
- [ ] Add `--priority` override option

### 11. Add Run One CLI Support
- [ ] Add `run-one` subcommand to `manager_cli.py`
- [ ] Support config file and overrides
- [ ] Add integration with existing worker infrastructure

## Phase 7: Testing

### 12. Create Priority System Tests
- [ ] Create `tests/utils/test_priority.py`
- [ ] Test priority classes and ranges
- [ ] Test priority boost strategies
- [ ] Test boundary conditions

### 13. Update Existing Tests
- [ ] Update job database tests for priority support
- [ ] Update worker tests for reservation support
- [ ] Update manager tests for priority display
- [ ] Add integration tests for priority queue behavior

### 14. Create Run One Tests
- [ ] Test run one script with various configs
- [ ] Test priority job execution order
- [ ] Test reservation timeout behavior
- [ ] Test concurrent priority jobs

## Phase 8: Documentation

### 15. Update API Documentation
- [ ] Document priority parameters in BaseJobDB
- [ ] Document reservation system
- [ ] Update docstrings throughout

### 16. Create User Documentation
- [ ] Create `docs/priority_system.md`
- [ ] Document priority classes and ranges
- [ ] Add examples for common use cases
- [ ] Document run one functionality

### 17. Update Existing Documentation
- [ ] Update README with priority system info
- [ ] Update `manager_flow.md` with priority details
- [ ] Add priority examples to `train_examples.md`

## Phase 9: Future-Proofing

### 18. Add Priority Strategy Framework
- [ ] Create pluggable priority strategy interface
- [ ] Implement age-based boost strategy
- [ ] Implement failure penalty strategy
- [ ] Add configuration for strategy selection

### 19. Add Monitoring Support
- [ ] Add priority metrics to job records
- [ ] Add queue depth by priority metrics
- [ ] Add average wait time by priority
- [ ] Prepare for future dashboard integration

## Implementation Timeline

- **Week 1:** Phases 1-2 (Database foundation)
- **Week 2:** Phases 3-4 (Core functionality)  
- **Week 3:** Phases 5-6 (User interfaces)
- **Week 4:** Phases 7-8 (Testing & documentation)
- **Future:** Phase 9 (Enhancements)

## Success Criteria

1. ✓ Can run single job with urgent priority via `run_one.py`
2. ✓ Higher priority jobs claimed before lower priority
3. ✓ Reserved jobs only claimable by designated worker
4. ✓ All existing functionality remains unchanged
5. ✓ 100% test coverage for new code
6. ✓ Clear documentation for users and developers

## Priority Classes Design

```python
class PriorityClass(Enum):
    SYSTEM = (900, 1000)    # System maintenance, critical fixes
    URGENT = (700, 899)     # "Run one", deadline-driven
    HIGH = (400, 699)       # Important experiments
    NORMAL = (100, 399)     # Default range
    LOW = (0, 99)           # Background, nice-to-have
```

## Database Schema Changes

### Job Record Extensions
```python
{
    "id": "job_123",
    "priority": 100,                    # NEW: 0-1000, default 100
    "priority_boost_count": 0,          # NEW: Track manual boosts
    "submitted_at": "2024-01-01T00:00:00Z",  # NEW: For age-based scheduling
    "priority_class": "normal",         # NEW: Named priority class
    "reserved_for_worker": "worker_id", # NEW: Worker reservation
    "reservation_expires_at": "...",    # NEW: Reservation timeout
    # ... existing fields
}
```

## Key Interface Changes

### BaseJobDB Additions
```python
@abstractmethod
def add_job(
    self,
    job_config: Dict[str, Any],
    sweep_config_id: str,
    status: str = "queued",
    priority: int = 100  # NEW
) -> Dict[str, Any]:

@abstractmethod
def update_job_priority(
    self, 
    job_id: str, 
    new_priority: int,
    reason: Optional[str] = None
) -> Dict[str, Any]:

@abstractmethod
def boost_job_priority(
    self, 
    job_id: str, 
    boost_amount: int = 100
) -> Dict[str, Any]:

@abstractmethod
def add_reserved_job(
    self, 
    job_config: Dict[str, Any], 
    sweep_config_id: str, 
    reserved_for_worker: str,
    reservation_timeout: Optional[int] = None
) -> Dict[str, Any]:
```

## Usage Examples

### Run One Script
```bash
# Run specific config with urgent priority
python scripts/run_one.py model=resnet optim.lr=0.01

# Run with custom priority
python scripts/run_one.py model=vit --priority 800

# Run and wait for completion
python scripts/run_one.py model=resnet --wait
```

### Priority Management
```bash
# Submit with priority
python scripts/upload_configs.py --sweep "model=resnet" --priority 600

# Boost existing job
python scripts/manager_cli.py boost-priority job_123 --amount 200

# List queue by priority  
python scripts/manager_cli.py list-queue --status queued
```

This implementation provides a solid foundation for priority-based job management while maintaining system simplicity and extensibility.
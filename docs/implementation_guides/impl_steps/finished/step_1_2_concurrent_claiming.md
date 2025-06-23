# Step 1.2: Concurrent Job Claiming

## Goal
Add file locking to JobDB so multiple workers can safely claim jobs without conflicts.

## Prerequisites
- Step 1.1 completed and validated
- Required files exist: `src/dr_exp/core/job_db.py`
- `test_step_1_1.py` passes

## Overview

This step adds atomic job claiming to prevent race conditions when multiple workers compete for jobs. The implementation uses:
- File-based locking with `fcntl` for inter-process coordination
- Non-blocking lock attempts to avoid deadlocks
- Priority-based job selection
- Atomic read-modify-write operations

## Key Components

### New Methods Added to JobDB
1. **`_list_job_files()`** - Lists queued jobs sorted by priority (descending) then creation time
2. **`claim_next_job(worker_id)`** - Atomically claims the highest priority available job
3. **`update_job(job_id, updates)`** - Atomically updates job fields

### Locking Strategy
- Uses `fcntl.LOCK_EX | fcntl.LOCK_NB` for non-blocking exclusive locks
- Lock is held only during read-modify-write operations
- Automatic lock release on file close
- Graceful handling of lock contention (try next job)

### Priority Queue Implementation
- Jobs sorted by priority (highest first)
- Secondary sort by creation time for tie-breaking
- Workers always attempt highest priority job first

## Validation

Test coverage includes:
- Concurrent job claiming by multiple processes
- Priority order verification
- Atomic job updates
- Lock contention handling
- No double-claiming of jobs

Run: `pt tests/implementation/test_step_1_2.py -v`

## Implementation Notes

### Divergences from Instructions
1. **Datetime usage**: Instructions use `datetime.utcnow()` but implementation uses `datetime.now(UTC)`
   - **Type**: Positive
   - **Reason**: Consistency with Step 1.1 and modern best practices
   
2. **Field naming**: Implementation adds `started_at` field when claiming
   - **Type**: Positive addition
   - **Reason**: Useful for tracking job duration and debugging

3. **Test target**: Test uses `"test.train"` as target instead of real module
   - **Type**: Neutral
   - **Impact**: Test still validates functionality, just skips import check

### Implementation Quality Notes
- Excellent use of non-blocking locks to prevent deadlocks
- Clean separation between lock acquisition and business logic
- Proper error handling for corrupted files
- Good test design using multiprocessing to simulate real concurrency

### Lessons Learned
1. `fcntl` is the right choice for file-based inter-process locking on Unix
2. Non-blocking locks (`LOCK_NB`) are essential to prevent deadlocks
3. Always double-check state after acquiring lock (status might have changed)
4. Priority testing needs careful design to be deterministic

### Dependencies for Later Steps
- `update_job()` method is foundational for all status changes
- Lock pattern will be reused for other atomic operations
- `claim_next_job()` is the core of worker job acquisition
- Priority queue behavior affects job scheduling

### Technical Decisions
1. **fcntl over threading.Lock**: Needed for inter-process coordination
2. **Non-blocking locks**: Prevents workers from hanging on contention
3. **File-level locking**: Each job file locked independently for parallelism
4. **Priority sorting in memory**: Simple and sufficient for reasonable job counts

### Testing Insights
- Multiprocessing tests are more complex but catch real concurrency issues
- Need sufficient jobs and workers to ensure contention actually occurs
- Priority verification requires tracking claim order across workers
- Process timeouts prevent hanging tests

### Performance Considerations
- O(n) job listing for each claim (acceptable for typical job counts)
- Lock contention increases with worker count
- File operations are atomic but not as fast as in-memory queues
- Could benefit from job archival to reduce directory size

### Future Enhancement Opportunities
1. Index file for O(1) next job lookup
2. Batch claiming for reduced contention
3. Lock timeout configuration
4. Metrics on lock contention rates
5. Fairness guarantees (prevent worker starvation)

### Cross-Step Patterns
- Atomic file operations with proper locking
- Graceful handling of concurrent access
- Priority-based scheduling
- Comprehensive concurrency testing

### Risk Areas
1. **Platform dependency**: `fcntl` is Unix-only (Windows needs different approach)
2. **Lock starvation**: Possible if one worker is much faster
3. **Directory scalability**: Performance degrades with many job files
4. **Corrupted files**: Could accumulate without cleanup mechanism

## Common Mistakes to Avoid
- Using threading.Lock instead of fcntl (won't work across processes)
- Holding locks longer than necessary
- Using blocking lock acquisition (causes deadlocks)
- Not handling lock acquisition failures
- Forgetting to flush after writing
- Not re-checking state after acquiring lock

## Next Step
Proceed to Step 1.3: Job Lifecycle Management
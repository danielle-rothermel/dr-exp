# Step 1.3: Job Lifecycle Management

## Goal
Add complete job lifecycle methods including completion, failure, heartbeats, and storage management.

## Prerequisites
- Step 1.2 completed and validated
- Required files exist: `src/dr_exp/core/job_db.py` with locking
- `test_step_1_2.py` passes

## Overview

This step completes the job lifecycle by adding methods for:
- Job completion and failure handling
- Heartbeat mechanism for liveness detection
- Job listing with status filtering
- Sync queue management for artifact uploads
- Experiment-level information gathering

## Key Components

### Lifecycle Methods
1. **`complete_job(job_id, metrics)`** - Mark job as successfully completed
2. **`fail_job(job_id, error)`** - Mark job as failed with error message
3. **`heartbeat(job_id)`** - Update liveness timestamp

### Query Methods
1. **`list_jobs(status)`** - List all jobs, optionally filtered by status
2. **`get_experiment_info()`** - Aggregate experiment statistics

### Sync Queue Management
1. **`add_to_sync_queue(...)`** - Queue files for background upload
2. **`get_sync_queue_path()`** - Access sync queue directory

### Key Design Decisions
- Sync queue uses timestamped filenames for natural ordering
- Job listing returns full job data (not just IDs)
- Heartbeats are optional but recommended for long jobs
- Experiment info provides summary statistics

## Validation

Test coverage includes:
- Complete job lifecycle (create → claim → heartbeat → complete)
- Job failure handling
- Status-based job filtering
- Sync queue file creation
- Experiment statistics aggregation

Run: `pt tests/implementation/test_step_1_3.py -v`

## Implementation Notes

### Divergences from Instructions
1. **Datetime usage**: Instructions use `datetime.utcnow()` but implementation uses `datetime.now(UTC)`
   - **Type**: Positive
   - **Reason**: Consistency across all steps

2. **Field naming inconsistency**: Docs show `last_heartbeat` but actual implementation uses `heartbeat`
   - **Type**: Documentation error
   - **Impact**: Implementation is internally consistent

3. **Missing import**: Test file needs `import json` but doesn't show it
   - **Type**: Documentation omission
   - **Resolution**: Test file correctly includes the import

### Implementation Quality Notes
- Clean reuse of `update_job()` for all status changes
- Good error handling with None defaults
- Sync queue design is simple but effective
- Test coverage is comprehensive

### Lessons Learned
1. Timestamped filenames provide natural ordering without indexes
2. Returning full job data (not just IDs) is more useful for callers
3. Status filtering at the file level is simple and sufficient
4. Sync queue can be completely decoupled from job management

### Dependencies for Later Steps
- Heartbeat mechanism enables stale job recovery (Step 1.4)
- Sync queue structure used by SyncQueue class (Step 2.2)
- Job listing used by CLI commands (Step 2.5)
- Status counts used for monitoring

### Technical Decisions
1. **Sync queue as files**: Each sync item is a separate file for robustness
2. **Microsecond timestamps**: Prevents filename collisions
3. **No sync queue cleanup**: Items persist until processed
4. **Simple status counts**: Count during query rather than maintaining counters

### Testing Insights
- Need time delays in tests to ensure different timestamps
- Testing all status transitions provides good coverage
- Sync queue tests don't need actual file uploads
- Experiment info test creates realistic job distribution

### Performance Considerations
- `list_jobs()` is O(n) but includes parsing all job files
- No pagination support (could be issue with many jobs)
- Sync queue could grow unbounded without cleanup
- Status filtering still reads all files

### Future Enhancement Opportunities
1. Pagination for job listing
2. Index file for faster status queries
3. Sync queue cleanup after successful upload
4. Job archival to reduce active job count
5. Heartbeat timeout configuration
6. Batch sync queue operations

### Cross-Step Patterns
- Building on atomic update operations
- Consistent use of ISO timestamp strings
- File-per-item pattern for robustness
- Comprehensive test scenarios

### Risk Areas
1. **Sync queue growth**: No automatic cleanup mechanism
2. **Job listing performance**: Degrades linearly with job count
3. **Missing heartbeats**: No automatic failure detection yet
4. **Corrupted sync items**: Would accumulate without cleanup

## Common Mistakes to Avoid
- Forgetting to handle None/missing fields in job data
- Over-engineering sync queue (keep it simple with files)
- Adding database indexes or optimizations
- Using datetime objects in JSON (use ISO strings)
- Trying to add transaction support
- Not testing all status transitions

## Next Step
Proceed to Step 1.4: Operational Features
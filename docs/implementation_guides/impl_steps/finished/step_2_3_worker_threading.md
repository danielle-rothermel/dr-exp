# Step 2.3: Worker Threading Integration

## Goal
Add background sync and heartbeat threads to the worker for automatic file uploads and liveness tracking.

## Prerequisites
- Step 2.2 completed and validated
- Required files exist: src/dr_exp/worker/base.py, src/dr_exp/sync/queue.py
- test_step_2_2.py passes

## Overview

This step enhances the Worker with background threads for:
- **Heartbeat thread**: Sends periodic heartbeats during job execution
- **Sync thread**: Processes sync queue in background
- **Artifact tracking**: Automatically queues job outputs for sync
- **Clean shutdown**: Graceful thread termination with timeouts
- **Error artifacts**: Failed jobs save error details for debugging

## Key Components

### Threading Architecture
1. **Sync Thread** (`_sync_worker`)
   - Runs every `sync_interval` seconds
   - Processes batches from sync queue
   - Reports sync statistics
   - Handles sync errors gracefully

2. **Heartbeat Thread** (`_heartbeat_worker`)
   - Runs every `heartbeat_interval` seconds
   - Only sends heartbeats when job is running
   - Tracks current job ID
   - Continues through job transitions

### Enhanced Worker Methods
1. **`add_artifact_to_sync()`** - Queue files for background upload
2. **`start_background_threads()`** - Initialize daemon threads
3. **`stop_background_threads()`** - Graceful shutdown with join timeout
4. **Enhanced `execute_job()`** - Now tracks all created artifacts

### Artifact Detection
- Automatic discovery of files in storage directory
- Type detection based on filename/extension:
  - `.jsonl` or "metrics" → `metrics` type
  - `.pt`/`.pth` or "model" → `model` type
  - Error files → `error` type
  - Others → `other` type

## Validation

Test coverage includes:
- Background thread lifecycle management
- Sync disabled mode (heartbeat still runs)
- Thread cleanup verification
- Heartbeat frequency during long jobs
- Sync queue integration
- Error artifact creation and queueing

Run: `pt tests/implementation/test_step_2_3.py -v`

## Implementation Notes

### Divergences from Instructions
1. **Datetime usage**: Still using `datetime.utcnow()` 
   - **Type**: Consistency issue
   - **Impact**: Should use `datetime.now(UTC)` like other components

2. **Thread timing in tests**: Tests wait for sync instead of relying on threads
   - **Type**: Test design difference
   - **Reason**: Tests manually call `process_queue()` for deterministic results
   - **Impact**: More reliable tests, less timing-dependent

3. **JobDB initialization**: Tests add `validate=False` parameter
   - **Type**: Test-specific addition
   - **Reason**: Skip validation for test scenarios

### Implementation Quality Notes
- Clean separation of sync and heartbeat concerns
- Daemon threads prevent process hanging
- Event-based shutdown is more reliable than flags
- Good error isolation (threads continue after errors)
- Comprehensive artifact discovery

### Lessons Learned
1. Daemon threads are essential for clean shutdown
2. Threading.Event is better than boolean flags for coordination
3. Manual sync processing in tests avoids timing issues
4. Artifact type detection should be pluggable
5. Thread names help with debugging

### Dependencies for Later Steps
- CLI will need to configure sync function (Step 2.4)
- Multi-worker scenarios need thread-safe operations
- SLURM integration will scale thread intervals
- API will expose sync queue stats

### Technical Decisions
1. **Threads over processes**: Sufficient for I/O-bound sync operations
2. **Daemon threads**: Ensures clean process exit
3. **Fixed batch size**: Simple but could be dynamic
4. **No thread pools**: Two dedicated threads are simpler
5. **Event-based shutdown**: More responsive than sleep loops

### Testing Insights
- Thread count verification catches leaks
- Heartbeat tracking validates frequency
- Manual sync calls make tests deterministic
- Error injection tests full error flow
- Thread cleanup tests are timing-sensitive

### Performance Considerations
- Two threads per worker (minimal overhead)
- Sync batch size affects upload latency
- Heartbeat interval affects staleness detection
- Thread wake intervals affect responsiveness
- No CPU-bound operations in threads

### Future Enhancement Opportunities
1. Dynamic sync batch sizing
2. Priority-based sync queue
3. Compressed artifact uploads
4. Incremental metrics sync
5. Thread pool for parallel uploads
6. Configurable artifact type detection
7. Sync progress reporting

### Cross-Step Patterns
- Event-based coordination (like JobDB locks)
- Graceful degradation (sync errors don't stop worker)
- Comprehensive test scenarios
- Clear separation of concerns

### Risk Areas
1. **Thread leaks**: Threads might not terminate properly
2. **Sync backlog**: Queue could grow faster than processing
3. **Memory usage**: Large artifacts in queue
4. **Thread safety**: Current design avoids shared state
5. **Heartbeat failures**: No retry mechanism

## Common Mistakes to Avoid
- Using multiprocessing (threads are sufficient for I/O operations)
- Sharing mutable state between threads without locks
- Blocking main thread waiting for background threads
- Forgetting daemon=True on threads (prevents hanging on exit)
- Letting threads run forever (use should_stop event for clean shutdown)
- Not handling thread exceptions properly

## Next Step
Proceed to Step 2.4: CLI Framework
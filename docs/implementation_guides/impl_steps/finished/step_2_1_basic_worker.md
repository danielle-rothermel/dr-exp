# Step 2.1: Basic Worker Class

## Goal
Create a basic worker class that can execute jobs using Hydra's dispatch mechanism without threading.

## Prerequisites
- Phase 1 (JobDB) completed and all tests passing
- Required files exist: `src/dr_exp/core/job_db.py`
- Hydra and OmegaConf installed: `uv add hydra-core omegaconf`

## Overview

This step creates a basic Worker class that:
- Claims jobs from JobDB using priority order
- Executes jobs using Hydra's `call()` mechanism
- Manages job directories and artifacts
- Updates job status on completion/failure
- No threading yet - single job at a time

## Key Components

### Worker Class (`src/dr_exp/worker/base.py`)
Core functionality:
1. **`__init__`** - Initialize with JobDB, worker ID, and working directory
2. **`execute_job`** - Run a single job using Hydra
3. **`run_one_job`** - Claim and execute one job
4. **`run`** - Main loop to process multiple jobs

### Job Execution Flow
1. Claim next job by priority
2. Create job-specific working directory
3. Inject metadata into config (job_id, worker_id, storage_path)
4. Execute using `hydra.utils.call(config)`
5. Extract metrics from result
6. Update job status in JobDB

### Test Trainer (`src/dr_exp/trainers/test_trainer.py`)
Simple trainer for testing that:
- Accepts injected metadata
- Simulates training with configurable epochs
- Can simulate failures for testing
- Creates artifacts (metrics.jsonl, model_final.pt)
- Returns metrics dictionary
## Validation

Test coverage includes:
- Basic job execution with artifacts
- Failure handling and error propagation
- No jobs available scenario
- Multiple job execution with stats
- Max jobs limit enforcement
- Priority order verification

Run: `pt tests/implementation/test_step_2_1.py -v`

## Implementation Notes

### Divergences from Instructions
1. **Datetime usage**: Instructions use `datetime.utcnow()` but implementation uses `datetime.now(UTC)`
   - **Type**: Positive
   - **Reason**: Consistency with JobDB implementation

2. **Signal handling**: Instructions mention SIGTERM but implementation doesn't include it
   - **Type**: Omission
   - **Impact**: Signal handling added in Step 2.3 with threading
   - **Reason**: Keeping this step focused on basic functionality

3. **Sync functionality**: Not implemented yet despite being mentioned in instructions
   - **Type**: Correct deferral
   - **Reason**: Sync queue is Step 2.2

### Implementation Quality Notes
- Clean separation of job execution from job management
- Proper directory isolation for each job
- Good error handling with full tracebacks
- Metrics extraction pattern is extensible
- Test trainer provides realistic simulation

### Lessons Learned
1. Hydra's `call()` is powerful for dynamic function dispatch
2. Directory isolation prevents job interference
3. Injecting metadata into config is cleaner than parameters
4. Test trainers need controllable failure for proper testing
5. Priority order testing requires execution tracking

### Dependencies for Later Steps
- Worker class will be extended with threading (Step 2.3)
- `execute_job` method stays unchanged when adding features
- Test trainer pattern used throughout testing
- Stats dictionary format used by CLI

### Technical Decisions
1. **OmegaConf conversion**: Ensures Hydra compatibility
2. **Working directory per job**: Prevents file conflicts
3. **Metadata injection**: Clean way to pass context to jobs
4. **Simple stats**: Just counts, no timing or rates yet
5. **Print-based logging**: Simple but effective for now

### Testing Insights
- Need deterministic failure simulation (fail_rate)
- Priority testing requires custom worker subclass
- Working directory verification important
- Stats testing needs statistical tolerance
- Artifact verification ensures jobs actually ran

### Performance Considerations
- No parallelism yet (single job at a time)
- Directory creation overhead per job
- No job batching or pipelining
- Synchronous execution model

### Future Enhancement Opportunities
1. Parallel job execution
2. GPU assignment and management
3. Resource limits (memory, time)
4. Progress reporting during execution
5. Partial failure recovery
6. Job output streaming

### Cross-Step Patterns
- Building on JobDB's priority queue
- Consistent error handling patterns
- Test-driven development approach
- Clear separation of concerns

### Risk Areas
1. **Directory cleanup**: Job directories accumulate
2. **Memory leaks**: Long-running workers might accumulate state
3. **Error handling**: Some Hydra errors might not be caught
4. **Config size**: Large configs might cause issues

## Common Mistakes to Avoid
- Adding threading or async code (that's Step 2.3)
- Implementing complex error recovery
- Adding job queuing in the worker (JobDB handles that)
- Forgetting to restore working directory
- Catching exceptions too broadly
- Not creating storage directory before job execution

## Next Step
Proceed to Step 2.2: Sync Queue Implementation
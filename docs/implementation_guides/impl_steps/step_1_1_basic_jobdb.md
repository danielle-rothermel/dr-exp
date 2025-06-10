# Step 1.1: Basic JobDB Structure

## Goal
Create the foundational JobDB class that can create and retrieve jobs from the filesystem.

## Prerequisites
- Clean working directory from Step 0
- Python 3.10+ environment with `uv` installed
- Basic project structure created (`src/dr_exp/core/` exists)

## Overview

This step creates the core JobDB class that manages ML experiment jobs as JSON files on the filesystem. The implementation provides:
- Job creation with priority (0-1000)
- Job retrieval by ID
- Directory structure validation
- Storage path management
- Target validation to ensure callables exist

## Key Components

### JobDB Class (`src/dr_exp/core/job_db.py`)
- Single class, no inheritance or abstract base classes
- File-based storage using JSON
- Assertion-based validation (not exceptions)
- Priority queue support (higher priority = runs first)
- Automatic directory creation when `validate=False`

### Directory Structure
Each experiment has five subdirectories:
- `jobs/` - Job JSON files
- `storage/` - Job artifacts and outputs
- `sync_queue/` - Files pending upload
- `logs/` - Worker and system logs
- `control/` - Control files for coordination

### Job Schema
Jobs are stored as JSON with fields:
- `id`: UUID string
- `experiment_name`: Name of the experiment
- `config`: User-provided configuration (must have `_target_`)
- `priority`: 0-1000 integer
- `status`: Current status (queued, running, completed, failed)
- `created_at`, `updated_at`: ISO format timestamps
- `worker_id`, `error`, `completed_at`: Runtime fields

## Validation

Test coverage includes:
- Basic job creation and retrieval
- Directory structure validation
- Priority bounds checking
- Target importability validation
- Missing `_target_` handling

Run: `pt tests/implementation/test_step_1_1.py -v`

## Implementation Notes

### Divergences from Instructions
1. **Datetime usage**: Instructions showed `datetime.utcnow()` but implementation correctly uses `datetime.now(UTC)`
   - **Type**: Positive
   - **Reason**: `utcnow()` is deprecated, `now(UTC)` is the modern approach
   
2. **Import statement**: Implementation adds `import os` which wasn't used
   - **Type**: Neutral
   - **Impact**: No harm, gets cleaned up by ruff

### Implementation Quality Notes
- Clean separation between validation and creation modes
- Good error messages that suggest the fix (e.g., "Run: dr_exp ... init")
- Proper use of Path objects throughout
- Type annotations on all public methods

### Lessons Learned
1. Using assertions for validation is cleaner than exceptions for this use case
2. The `validate` parameter elegantly handles both normal operation and initialization
3. Target validation at job creation time prevents runtime surprises

### Dependencies for Later Steps
- Job file format is foundational - all future steps read/write this schema
- Directory structure must remain consistent across all components
- Priority field enables the queue behavior in Step 1.2
- Storage path convention (`run_{job_id}`) used by workers

### Technical Decisions
1. **JSON over other formats**: Human-readable, debuggable, sufficient for metadata
2. **UUID for job IDs**: Guarantees uniqueness without coordination
3. **Flat file structure**: One file per job, no index files to corrupt
4. **Target validation**: Fail fast at job creation rather than execution time

### Testing Insights
- Using `tempfile.TemporaryDirectory()` provides clean test isolation
- Testing both success and failure paths is crucial
- Assertion error messages should be tested to ensure they're helpful

### Performance Considerations
- No indexing means O(n) job listing, but simple and corruption-resistant
- File-per-job means good parallelism (no single file lock)
- JSON parsing is fast enough for metadata-sized configs

### Future Enhancement Opportunities
1. Could add job listing with filtering (by status, priority)
2. Might benefit from a simple index file for large experiments
3. Could validate config schema if `_target_` modules define one
4. Job archival for completed/failed jobs

### Cross-Step Patterns
- Assertion-based validation (used throughout)
- File-based operations with explicit paths
- Clear separation between required and optional parameters
- Comprehensive test coverage of edge cases

### Risk Areas
1. **Race conditions**: Not handled yet (addressed in Step 1.2)
2. **Large experiments**: No pagination or limits on job count
3. **Config size**: No validation of config size (could hit filesystem limits)
4. **Orphaned files**: No cleanup of storage for deleted jobs

## Common Mistakes to Avoid
- Using abstract base classes or interfaces
- Adding configuration files instead of direct parameters
- Using exceptions instead of assertions for validation
- Adding unspecified features (caching, indexing)
- Forgetting `parents=True` when creating directories

## Next Step
Proceed to Step 1.2: Concurrent Job Claiming
# dr_exp Agent Context Guide

## System Overview
dr_exp is a **local-first deep learning experiment manager** for HPC clusters. It manages ML training jobs via filesystem operations with optional cloud sync. No distributed systems, no complex abstractions - just files and locks.

**Core Purpose**: Submit jobs → Workers claim by priority → Execute training → Sync results

## Current Implementation Status

### ✅ Complete (Phase 1-2.6)
- **JobDB**: File-based job queue with atomic operations via fcntl
- **Worker**: Executes jobs using Hydra dispatch, manages artifacts
- **CLI**: All commands operational (init, submit, worker, list, etc.)
- **Sync Queue**: Tracks files for upload (processing not implemented)
- **Integration**: Test trainer and DeconCNN wrapper working

### ⚠️ In Progress
- **Worker Logging**: Outputs to stdout only (no file logs yet)
- **Sync Processing**: Items queued but not uploaded

### 🔜 Planned (Phase 2.7-3.5)
- **Multi-Worker Launcher**: Spawn workers across GPUs
- **Config Sweeps**: Parameter sweep generation
- **SLURM Integration**: Long-running launcher for 24 GPUs (4-8 per node), graceful shutdown on SIGTERM
- **Supabase Sync**: PostgreSQL + storage bucket
- **Remote Monitoring**: Read-only API

## Architecture

```
experiment_dir/
├── jobs/         # Job JSON files (UUID.json)
├── storage/      # Job outputs (run_UUID/)
├── sync_queue/   # Upload queue (pending/)
├── logs/         # Worker logs (not implemented)
└── control/      # Control files
```

**Key Classes**:
- `JobDB` (core/job_db.py): Single implementation, no modes/variants
- `Worker` (worker/base.py): Claims jobs, executes via Hydra
- `SyncQueue` (sync/queue.py): Tracks files for upload
- `CLI` (cli/main.py): All user commands

**Job Flow**:
1. User submits config with `_target_: module.function`
2. Worker claims highest priority job atomically
3. Hydra calls the target function with config
4. Outputs saved to storage/run_{job_id}/
5. Job marked complete/failed

## CLI Commands

All commands follow pattern:
```bash
dr_exp --base-path <path> --experiment <name> <command> [options]
```

**Essential Commands**:
```bash
# Setup
init                          # Create experiment structure

# Job Management  
submit --config-path <dir> --config-name <file> [--priority N]
list [--status queued|running|completed|failed]
kill <job_id>
boost <job_id> --priority N
run-one <job_id> --working-dir <dir>

# Worker Operations
worker --worker-id <id> [--max-jobs N] [--working-dir <dir>]
launcher --workers-per-gpu N  # Not implemented

# Monitoring
status                        # Job counts
sync-status                   # Queue status
validate                      # Check structure
recover                       # Fix stale jobs
```

## Key Technical Rules

1. **File Locking**: All concurrent access via fcntl (no distributed coordination)
2. **Fail Fast**: Use assertions not exceptions
3. **Hydra Dispatch**: Jobs must have `_target_` field pointing to callable
4. **No Abstractions**: Direct implementations only
5. **Explicit Paths**: No magic, all paths specified
6. **Local First**: Filesystem is source of truth, sync is optional

## Development Standards

**Quality Gates** (MUST pass):
```bash
ckdr  # ruff + mypy checks
pt    # pytest (all tests)
```

**Dependencies**:
```bash
uv add <package>       # Production deps
uv add --dev <package> # Dev deps
# NEVER use: pip install or uv pip install
```

**Testing**:
- Tests in `tests/implementation/test_step_X_Y.py`
- Use pytest fixtures, not standalone scripts
- Test both success and failure paths

## Common Tasks

**Submit and run job**:
```bash
# Initialize
dr_exp --base-path ./exp --experiment test init

# Submit  
dr_exp --base-path ./exp --experiment test submit \
  --config-path configs --config-name test_job

# Run worker
dr_exp --base-path ./exp --experiment test worker \
  --worker-id w1 --working-dir ./work
```

**Debug failed job**:
```bash
# List failures
dr_exp --base-path ./exp --experiment test list --status failed

# Check error
cat ./exp/test/storage/run_<job_id>/error.txt
```

## Integration Pattern

ML libraries need minimal changes:
1. Create wrapper function with Hydra-compatible signature
2. Add `_target_` pointing to wrapper
3. Use StructuredLogger for metrics
4. Save outputs to provided storage_path

Example:
```python
def train(config):
    """Wrapper for dr_exp integration."""
    logger = StructuredLogger(config.storage_path)
    # ... training code ...
    logger.log_metrics({"loss": loss})
    return {"metrics": final_metrics}
```

**Config Examples**: See `configs/` directory for living documentation of available configurations and their structure.

## Known Issues

1. **Worker logs**: Not written to files (stdout only)
2. **Sync processing**: Queue fills but doesn't upload
3. **Error format**: Saved as .txt not .json
4. **Submit syntax**: Uses Hydra-style flags not direct paths

## File/Code Navigation

When referencing code, use pattern: `path/to/file.py:123`

**Key files**:
- Job management: `src/dr_exp/core/job_db.py:150`
- Worker logic: `src/dr_exp/worker/base.py:298`
- CLI commands: `src/dr_exp/cli/main.py:45`
- Config examples: `configs/test_job.yaml`

## Future Phases Summary

**Phase 2.7-2.9**: Multi-worker launcher, parameter sweeps, SLURM integration
**Phase 3**: Supabase sync with PostgreSQL + storage
**Phase 4**: WebSocket API for remote monitoring
**Phase 5**: Cloud deployment options
**Phase 6**: Cleanup and migration tools

## Agent Instructions

1. **Read implementation guides** in `docs/implementation_guides/impl_steps/` for detailed steps
2. **Follow patterns** from completed steps (finished/ directory)
3. **Test everything** - no code proceeds without passing tests
4. **Keep it simple** - no abstractions, no clever solutions
5. **Ask if unclear** - better to clarify than guess
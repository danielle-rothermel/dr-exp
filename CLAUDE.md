# dr_exp - Deep Learning Experiment Manager

## System Overview
dr_exp is a **local-first deep learning experiment manager** for HPC clusters. It manages ML training jobs via filesystem operations with optional cloud sync. No distributed systems, no complex abstractions - just files and locks.

**Core Purpose**: Submit jobs → Workers claim by priority → Execute training → Sync results → Monitor remotely

## Current Implementation Status

### ✅ Complete (Phase 1-3)
- **JobDB**: File-based job queue with atomic operations via fcntl
- **Worker**: Executes jobs using Hydra dispatch, manages artifacts, logs to files
- **CLI**: All commands operational (init, submit, worker, list, sweep, launcher, etc.)
- **Sync Queue**: Tracks files for upload with retry logic
- **Integration**: Test trainer and DeconCNN wrapper working
- **Multi-Worker Launcher**: Spawns workers across GPUs with health monitoring
- **Config Sweeps**: Parameter sweep generation and submission
- **SLURM Integration**: Scripts and commands for HPC clusters
- **Supabase Sync**: Full database and storage bucket integration
- **Remote API**: FastAPI endpoints for experiment monitoring

### ⚠️ Known Limitations
- **Error format**: Saved as .txt not .json (minor issue)
- **Submit syntax**: Uses Hydra-style flags not direct paths
- **API artifact endpoints**: Some download functionality may need testing

## 📦 DEPENDENCY MANAGEMENT

### ⚠️ CRITICAL: Always Use `uv add`, Never `uv pip install`

This project uses `uv` for dependency management with a `pyproject.toml` file. Dependencies MUST be added using `uv add` to ensure they are properly tracked in both `pyproject.toml` and `uv.lock`.

**✅ CORRECT - Use these commands:**
```bash
# Add a production dependency
uv add package-name

# Add a development dependency
uv add --dev package-name

# Add with version constraints
uv add "package-name>=1.2.0"

# Add from git
uv add "package-name @ git+https://github.com/user/repo"

# Remove a dependency
uv remove package-name
```

**❌ INCORRECT - Never use these:**
```bash
# NEVER use uv pip install
uv pip install package-name  # ❌ Wrong!

# NEVER use pip directly
pip install package-name     # ❌ Wrong!
```

### Why This Matters
- `uv add` updates both `pyproject.toml` and `uv.lock` files
- `uv pip install` only installs to the environment without updating project files
- Using `uv pip install` breaks reproducibility and dependency tracking
- Team members won't get your dependencies if you use `uv pip install`

## Architecture

```
experiment_dir/
├── jobs/         # Job JSON files (UUID.json)
├── storage/      # Job outputs (run_UUID/)
├── sync_queue/   # Upload queue (pending/)
├── logs/         # Worker and launcher logs
├── control/      # Control files for launcher
└── .jobdb_lock   # Global lock file
```

**Key Classes**:
- `JobDB` (core/job_db.py): File-based job queue with locking
- `Worker` (worker/base.py): Claims jobs, executes via Hydra, syncs results
- `SyncQueue` (sync/queue.py): Persistent file upload queue
- `SyncHandler` (sync/sync_handler.py): Supabase upload orchestrator
- `WorkerLauncher` (worker/launcher.py): Multi-GPU worker spawner
- `SupabaseClient` (sync/supabase_client.py): Cloud sync client
- `CLI` (cli/main.py): All user commands

**Job Flow**:
1. User submits config with `_target_: module.function`
2. Worker claims highest priority job atomically
3. Hydra calls the target function with config
4. Outputs saved to storage/run_{job_id}/
5. Job marked complete/failed
6. SyncHandler uploads artifacts to Supabase
7. Remote API serves results

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
sweep --config <file> --params "key=v1,v2" [--dry-run]
list [--status queued|running|completed|failed]
kill <job_id>
boost <job_id> --priority N
run-one <job_id> --working-dir <dir>

# Worker Operations
worker --worker-id <id> [--max-jobs N] [--working-dir <dir>]
launcher --workers-per-gpu N [--max-hours 47]

# SLURM Commands
slurm status [--job-id ID]    # Show launcher status
slurm errors [--job-id ID]    # View aggregated errors
slurm control <stop|finish>   # Control launchers
slurm logs [--job-id ID]      # Show worker logs

# Monitoring
status                        # Job counts
sync-status                   # Queue status
validate                      # Check structure
recover                       # Fix stale jobs
```

## Key Technical Components

### File Locking (JobDB)
- Uses fcntl for atomic operations
- Microsecond timestamp prefixes prevent collisions
- Global lock for claim operations
- Job-specific locks for updates

### Worker System
- Health monitoring with automatic restarts
- GPU assignment via CUDA_VISIBLE_DEVICES
- File logging to experiment logs directory
- Graceful shutdown on SIGTERM

### Sync System
- SyncQueue with exponential backoff (60s × 2^attempts)
- SupabaseClient handles PostgreSQL + storage bucket
- Batch upload support
- MIME type safety for .pt files

### SLURM Integration
- 47-hour runtime limit (buffer before 48h)
- Control files for graceful shutdown
- Status JSON files for monitoring
- Error aggregation from worker logs

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
- Mock external services (Supabase, subprocess)

## Common Tasks

**Submit parameter sweep**:
```bash
# Preview sweep
dr_exp --base-path ./exp --experiment test sweep \
  --config configs/train.yaml \
  --params "model=resnet18,resnet50 lr=0.01,0.001" \
  --dry-run

# Submit sweep
dr_exp --base-path ./exp --experiment test sweep \
  --config configs/train.yaml \
  --params "model=resnet18,resnet50 lr=0.01,0.001"
```

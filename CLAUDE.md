# dr_exp - Deep Learning Experiment Manager

## System Overview
dr_exp is a **local-first deep learning experiment manager** for HPC clusters. It manages ML training jobs via filesystem operations. No distributed systems, no complex abstractions — just files and locks.

**Core Purpose**: Submit jobs → Workers claim by priority → Execute training → Monitor locally

## Current Implementation Status

### Complete
- **JobDB**: File-based job queue with atomic operations via fcntl
- **Worker**: Executes jobs using Hydra dispatch
- **CLI**: init, submit, worker, list, sweep, launcher, SLURM commands
- **Multi-Worker Launcher**: Spawns workers across GPUs with health monitoring
- **Config Sweeps**: Parameter sweep generation and submission
- **SLURM Integration**: Scripts and commands for HPC clusters

### Known Limitations
- **Submit syntax**: Uses Hydra config composition with `--config-path` and `--config-name`
- **Job IDs**: Support partial matching for convenience in CLI commands
- **SLURM integration**: Requires specific directory structure and control files
- See README **Known issues** for deferred bugs in kill, heartbeat, and scheduling

## Dependency Management

Always use `uv add` / `uv remove` — never `uv pip install` or `pip install`.

```bash
uv add package-name
uv add --dev package-name
uv sync --all-groups
```

## Architecture

```
experiment_dir/
├── jobs/         # Job JSON files (UUID.json)
├── storage/      # Job outputs (run_UUID/)
├── logs/         # Worker and launcher logs
└── control/      # Control files for launcher
```

**Key Classes**:
- `JobDB` (`core/job_db.py`): File-based job queue with atomic locking
- `Worker` (`worker/base.py`): Claims jobs, executes via Hydra
- `WorkerLauncher` (`worker/launcher.py`): Multi-GPU worker spawner with health monitoring
- `CLI` (`cli/main.py`): Main CLI entry point with command groups
- `SweepUtils` (`cli/sweep_utils.py`): Parameter sweep generation utilities

**Job Flow**:
1. User submits config with `_target_: module.function`
2. Worker claims highest priority job atomically
3. Hydra calls the target function with config
4. Outputs saved to `storage/run_{job_id}/`
5. Job marked complete/failed

## CLI Commands

```bash
dr_exp --base-path <path> --experiment <name> <command> [options]
```

**Essential Commands**:
```bash
init
validate
status

job submit --config-path <dir> --config-name <file> [--priority N] [--tags <tags>] [--overrides <overrides>]
job sweep --config <file> --params "key=v1,v2" [--dry-run] [--verbose]
job list [--status queued|running|completed|failed] [--tag <tag>]
job kill <job_id...>
job boost <job_id...> --priority N
job run-one <job_id> [--working-dir <dir>]
job recover [--threshold 300] [--dry-run]

worker --worker-id <id> [--max-jobs N] [--working-dir <dir>]
system launcher --workers-per-gpu N [--max-hours 47]

slurm status
slurm control <job_id> [--finish-current|--stop-now]
slurm errors <job_id> [--tail N]
slurm logs <job_id> [--worker <id>] [--tail N]
```

## Key Technical Components

### File Locking (JobDB)
- Uses fcntl for atomic operations
- Microsecond timestamp prefixes prevent collisions
- Global lock for claim operations
- Job-specific locks for updates

### Worker System
- Health monitoring via launcher with automatic restarts
- GPU assignment via CUDA_VISIBLE_DEVICES
- Launcher redirects subprocess stdout for worker output
- Graceful shutdown via launcher control file (not Worker SIGTERM)

### SLURM Integration
- 47-hour runtime limit (buffer before 48h)
- Control files for graceful shutdown
- Status JSON files for monitoring
- Error aggregation from worker logs

## Development Standards

**Quality Gates**:
```bash
uv run ruff check .
uv run mypy src
uv run pytest -m "not slow"
```

**Dependencies**:
```bash
uv add <package>
uv add --dev <package>
```

**Testing**:
- Tests in `tests/unit/`, `tests/integration/`, `tests/validation/`
- Use pytest fixtures, not standalone scripts
- Mock external services where needed

## Common Tasks

**Submit parameter sweep**:
```bash
dr_exp --base-path ./exp --experiment test job sweep \
  --config configs/dummy_train.yaml \
  --params "lr=0.01,0.001 model=resnet18,resnet50"
```

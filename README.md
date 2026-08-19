# dr-exp - Deep Learning Experiment Manager

A **local-first deep learning experiment manager** for HPC clusters. Manages ML training jobs via filesystem operations.

## Direction

Supabase sync, the HTTP API, and the React UI have been removed. The filesystem queue, worker execution path, and Hydra-based config model remain in place until they are replaced by dr-platform, dr-exec, and a simpler config model in a later phase.

## Quick Start

### Installation

```bash
git clone <repository-url>
cd dr_exp
uv sync --all-groups
```

### Basic Usage

1. **Initialize experiment**:
   ```bash
   uv run dr_exp --base-path ./experiments --experiment my_exp init
   ```

2. **Submit job**:
   ```bash
   uv run dr_exp --base-path ./experiments --experiment my_exp \
     job submit --config-path configs --config-name dummy_train
   ```

3. **Run worker**:
   ```bash
   uv run dr_exp --base-path ./experiments --experiment my_exp \
     worker --worker-id worker1 --max-jobs 1
   ```

## Key Features

- **Local-first**: Filesystem-based job queue with atomic file locking
- **HPC Ready**: SLURM integration with multi-GPU launcher
- **Programmatic API**: Import `JobDB` and `submit_job` for Python integration
- **Parameter Sweeps**: Built-in hyperparameter sweep generation
- **Atomic Operations**: File locking ensures consistency

## Architecture

```
experiment_dir/
├── jobs/         # Job queue (JSON files)
├── storage/      # Training outputs
├── logs/         # Worker and launcher logs
└── control/      # Launcher control
```

## Commands

**Command groups**: `job`, `system`, `slurm`

```bash
# Job management
job submit --config-path configs --config-name dummy_train
job sweep --config train.yaml --params "lr=0.01,0.001"
job list --status queued
job kill <job_id>
job boost <job_id> --priority 500
job recover --threshold 300
job run-one <job_id>

# Workers
worker --worker-id w1
system launcher --workers-per-gpu 2

# SLURM
slurm status
slurm control --finish-current
```

## Programmatic API

```python
from dr_exp import JobDB, submit_job

job_id = submit_job(
    base_path="./experiments",
    experiment="my_exp",
    config={"_target_": "dr_exp.training.dummy_trainer.train", "epochs": 10},
    priority=100,
)
```

## Known issues

These are documented for Phase 1; fixes are deferred until the queue/worker/config stack is replaced.

1. **`job kill` does not signal the running trainer** — only rewrites the job JSON to `failed`; the worker may overwrite status on completion.
2. **Worker has no SIGTERM handler** — `Worker.shutdown()` is never called; graceful drain relies on the launcher control file.
3. **Worker file logging is dead at CLI call sites** — `experiment_path` is never passed to `Worker(...)`, so stdout/stderr redirection in `Worker.__init__` never runs unless set explicitly.
4. **`attempts` is uncapped** — incremented on claim but never limited; deterministically failing jobs are re-queued forever by `recover_stale_jobs`. Launcher `worker_restarts` is counted but not capped.
5. **`job boost` sets absolute priority** despite the name suggesting a relative increase.
6. **`reserve_job` / `claim_reserved_job` race** — read-then-write without the claim lock.
7. **`claim_next_job` lock contention** — gives up after 5 attempts; under contention workers sleep 10 s between polls. All scheduling ops are O(N) directory scans.
8. **Heartbeat daemon thread starvation** — a GIL-holding trainer can starve the heartbeat thread and trigger false stale recovery.
9. **`_target_` validation duplicated** — checked in `JobDB.create_job`, CLI submit, and sweep utilities.

## Development

```bash
uv run ruff check .
uv run mypy src
uv run pytest -m "not slow"
```

See [CHANGELOG.md](CHANGELOG.md) for removal history.

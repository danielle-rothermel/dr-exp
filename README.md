# dr_exp - Deep Learning Experiment Manager

A **local-first deep learning experiment manager** for HPC clusters. Manages ML training jobs via filesystem operations with optional cloud sync.

## Quick Start

### Installation
```bash
git clone <repository-url>
cd dr_exp
uv sync
```

### Basic Usage

1. **Initialize experiment**:
   ```bash
   uv run python -m dr_exp.cli.main --base-path ./experiments --experiment my_exp init
   ```

2. **Submit job**:
   ```bash
   uv run python -m dr_exp.cli.main --base-path ./experiments --experiment my_exp \
     job submit --config-path configs --config-name train
   ```

3. **Run worker**:
   ```bash
   uv run python -m dr_exp.cli.main --base-path ./experiments --experiment my_exp \
     worker --worker-id worker1
   ```

## Key Features

- **Local-first**: Filesystem-based with no external dependencies
- **HPC Ready**: SLURM integration with multi-GPU support  
- **Programmatic API**: Import `JobDB` and `submit_job` for Python integration
- **Parameter Sweeps**: Built-in hyperparameter sweep generation
- **Remote Monitoring**: Optional Supabase sync + FastAPI server
- **Atomic Operations**: File locking ensures consistency

## Architecture

```
experiment_dir/
├── jobs/         # Job queue (JSON files)
├── storage/      # Training outputs
├── sync_queue/   # Cloud sync queue  
├── logs/         # Worker logs
└── control/      # Launcher control
```

## Commands

**Command groups**: `job`, `system`, `slurm`

```bash
# Job management
job submit --config-path configs --config-name train
job sweep --config train.yaml --params "lr=0.01,0.001"
job list --status queued
job kill <job_id>
job boost <job_id> --priority 500

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

# Submit jobs programmatically
job_id = submit_job(
    base_path="./experiments",
    experiment="my_exp", 
    config={"_target_": "my_module.train", "lr": 0.01},
    priority=500
)

# Direct JobDB access
db = JobDB("./experiments", "my_exp") 
jobs = db.list_jobs(status="completed")
```

## Configuration

Jobs require `_target_` pointing to training function:

```yaml
# configs/train.yaml
_target_: src.trainer.train_model
epochs: 100
batch_size: 32
model:
  name: resnet18
```

## Documentation

- **[Quick Start Guide](docs/quick_start_guide.md)** - Detailed setup and examples
- **[API Reference](docs/api_reference.md)** - REST API for remote monitoring  
- **[CLAUDE.md](CLAUDE.md)** - Development guide and standards

## Development

```bash
# Quality checks
lint_fix  # Linting and formatting
uv run pytest -m "not supabase"  # Skip tests requiring Supabase

# Available shortcuts (see CLAUDE.md)
lint_fix  # Combined ruff + formatting
pt        # Pytest (all tests)
pt_ci     # Pytest (skip Supabase tests)
```


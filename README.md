# dr_exp - Deep Learning Experiment Manager

A **local-first deep learning experiment manager** designed for HPC clusters. It manages ML training jobs via filesystem operations with optional cloud sync.

## Quick Start

### Installation
```bash
# Clone the repository
git clone <repository-url>
cd dr_exp

# Install with uv
uv sync
```

### Basic Usage

1. **Initialize an experiment**:
   ```bash
   dr_exp --base-path ./experiments --experiment my_exp init
   ```

2. **Submit a training job**:
   ```bash
   dr_exp --base-path ./experiments --experiment my_exp job submit \
     --config-path configs --config-name train
   ```

3. **Run a worker to process jobs**:
   ```bash
   dr_exp --base-path ./experiments --experiment my_exp worker \
     --worker-id worker1
   ```

4. **Check experiment status**:
   ```bash
   dr_exp --base-path ./experiments --experiment my_exp status
   ```

## Key Features

- **Local-first**: All data stored in filesystem, no external dependencies required
- **HPC Ready**: Designed for SLURM clusters with multi-GPU support
- **Hydra Integration**: Uses Hydra for configuration management
- **Parameter Sweeps**: Built-in support for hyperparameter sweeps
- **Cloud Sync**: Optional Supabase integration for remote monitoring
- **Atomic Operations**: File-based locking ensures data consistency
- **Worker Health**: Automatic worker health monitoring and restart

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

## Command Overview

### Job Management
- `job submit` - Submit training jobs with Hydra configs
- `job sweep` - Submit parameter sweeps
- `job list` - List jobs with filtering
- `job kill` - Terminate jobs
- `job boost` - Change job priority
- `job run-one` - Run a specific job immediately

### Worker Operations
- `worker` - Run a worker to process jobs
- `system launcher` - Launch multiple workers across GPUs

### SLURM Integration
- `slurm status` - Monitor SLURM job status
- `slurm control` - Control running SLURM jobs
- `slurm logs` - View worker logs
- `slurm errors` - View error logs

### Monitoring
- `status` - Show experiment overview
- `validate` - Validate experiment structure
- `job sync-status` - Check sync queue status

## Configuration

### Job Configuration
Jobs are defined using Hydra configs with a required `_target_` field:

```yaml
# configs/train.yaml
_target_: src.my_module.train_function

epochs: 100
batch_size: 32
learning_rate: 0.001

model:
  name: resnet18
  num_classes: 10
```

### Parameter Sweeps
Create sweeps by specifying parameter variations:

```bash
dr_exp --base-path ./exp --experiment test job sweep \
  --config configs/train.yaml \
  --params "model.name=resnet18,resnet50 learning_rate=0.01,0.001,0.0001"
```

## Development

### Running Tests
```bash
# Run all tests
uv run pytest

# Run specific test categories
uv run pytest tests/unit        # Unit tests
uv run pytest tests/integration # Integration tests
uv run pytest tests/validation  # Validation tests

# Skip slow tests
uv run pytest -m "not slow"
```

### Code Quality
```bash
# Linting and formatting
uv run ruff check
uv run ruff format

# Type checking
uv run mypy src tests
```

## Documentation

- `CLAUDE.md` - Detailed implementation guide and development standards
- `tests/README.md` - Test suite documentation
- `src/dr_exp/` - Source code with inline documentation

## License

[License information]


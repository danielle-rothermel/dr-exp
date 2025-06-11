# dr_exp Quick Start Guide

This guide shows how to set up the system and run a short debug training session using DeconCNN with minimal configuration.

## Prerequisites

- Python 3.10+ with `uv` installed
- CUDA-capable GPU (or CPU-only mode)
- Clone of the dr_exp repository

## Important Note on Paths

All commands use `$(pwd)` to ensure absolute paths. This prevents path resolution issues that can occur with relative paths. Always run commands from the repository root directory.

## Setup

1. **Install dependencies**:
   ```bash
   uv sync
   ```

2. **Verify installation**:
   ```bash
   ckdr  # Should show "All checks passed!"
   pt    # Should run and pass all tests
   ```

## Running a Debug Training Session

### Step 1: Initialize Experiment

Create an experiment directory structure:

```bash
uv run python -m dr_exp.cli.main \
  --base-path ./debug_experiment \
  --experiment test_run \
  init
```

This creates:
```
./debug_experiment/test_run/
├── jobs/         # Job JSON files
├── storage/      # Training outputs
├── sync_queue/   # Background sync queue
├── logs/         # Worker logs
├── control/      # Control commands
└── .jobdb        # Metadata
```

### Step 2: Submit a Quick Debug Job

Submit a DeconCNN classification job with minimal settings:

```bash
# Using the test trainer (very fast, for debugging)
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  submit \
  --config-path configs \
  --config-name test_job \
  --priority 500
```

Or for a real DeconCNN job with tiny settings:

```bash
# Real DeconCNN with smallest model and batch sizes
# First create a minimal config by copying and modifying decon_config.yaml
cat configs/decon_config.yaml | \
  sed 's/epochs: 1/epochs: 2/' | \
  sed 's/batch_size: 10/batch_size: 16/' | \
  sed '/limit_train_batches:/c\limit_train_batches: 5' | \
  sed '/model: resnet18_cifar/c\    - model: alexnet_cifar' \
  > debug_experiment/test_run/debug_decon.yaml

# Then submit it
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  submit \
  debug_experiment/test_run/debug_decon.yaml \
  --priority 500
```

### Step 3: Check Job Status

```bash
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  list \
  --status queued
```

### Step 4: Run a Worker

Start a worker to process the job:

```bash
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  worker \
  --worker-id debug_worker \
  --working-dir $(pwd)/work \
  --max-jobs 1
```

The worker will:
1. Claim the highest priority job
2. Execute the training function
3. Save metrics and artifacts to `storage/`
4. Mark the job complete
5. Exit after processing 1 job

### Step 5: Examine Results

**Check job completion**:
```bash
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  list \
  --status completed
```

**View training metrics**:
```bash
# Metrics are in JSONL format
cat $(pwd)/debug_experiment/test_run/storage/run_*/metrics.jsonl | jq .
```

**Check final results in job record**:
```bash
# Find the job ID from list command, then:
cat $(pwd)/debug_experiment/test_run/jobs/<job_id>.json | jq .final_metrics
```

## Understanding the System

### Job Flow
1. **Submit**: Creates job JSON with config and priority
2. **Claim**: Worker atomically claims highest priority unclaimed job
3. **Execute**: Worker runs the job's `_target_` function via Hydra
4. **Log**: StructuredLogger writes metrics/events to storage
5. **Complete**: Worker updates job with results and marks complete

### Key Components
- **JobDB**: File-based job queue with atomic operations
- **Worker**: Executes jobs, manages heartbeats, discovers artifacts
- **CLI**: Unified interface for all operations
- **StructuredLogger**: Captures all training outputs

### Priority System
- Range: 0-1000 (higher = more urgent)
- Default: 100
- Urgent jobs: 700+
- System jobs: 900+

### Debugging Tips

**Run specific job immediately** (bypasses queue):
```bash
# First submit a job to get ID
JOB_ID=$(uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  submit \
  --config-path configs \
  --config-name test_job | grep "Created job:" | cut -d' ' -f3)

# Then run it immediately
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  run-one \
  $JOB_ID \
  --working-dir $(pwd)/work
```

**Monitor worker activity**:
Worker output goes to stdout/stderr. To capture it:
```bash
# Run worker with output redirection
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  worker \
  --worker-id debug_worker \
  --working-dir $(pwd)/work \
  2>&1 | tee worker.log
```

**Check for errors**:
```bash
# List failed jobs
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  list \
  --status failed

# View error details
cat $(pwd)/debug_experiment/test_run/storage/run_<job_id>/error.txt
```

## Next Steps

- Run multiple workers: Use different `--worker-id` values
- Submit parameter sweeps: Use comma-separated values in overrides
- Monitor long runs: Workers log status every 30 seconds
- SLURM integration: See `scripts/slurm_job.sbatch` for cluster usage
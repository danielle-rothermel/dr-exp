# dr_exp Quick Start Guide

Run a minimal local experiment using the built-in dummy trainer.

## Prerequisites

- Python 3.12+ with `uv` installed
- Clone of the dr_exp repository

## Setup

```bash
uv sync --all-groups
uv run python -c "import dr_exp"
```

## Initialize an Experiment

```bash
uv run dr_exp --base-path ./debug_experiment --experiment test_run init
```

Creates:

```
./debug_experiment/test_run/
├── jobs/
├── storage/
├── logs/
└── control/
```

## Submit a Job

```bash
uv run dr_exp --base-path ./debug_experiment --experiment test_run \
  job submit --config-path configs --config-name dummy_train --priority 500
```

The dummy trainer config uses `_target_: dr_exp.training.dummy_trainer.train`.

## Run a Worker

```bash
uv run dr_exp --base-path ./debug_experiment --experiment test_run \
  worker --worker-id debug_worker --max-jobs 1
```

## Inspect Results

```bash
uv run dr_exp --base-path ./debug_experiment --experiment test_run job list
uv run dr_exp --base-path ./debug_experiment --experiment test_run status
```

Job artifacts land in `./debug_experiment/test_run/storage/run_<job_id>/` (`metrics.json`, `config.json`, `model_final.pt`).

## Run One Job Directly

```bash
uv run dr_exp --base-path ./debug_experiment --experiment test_run \
  job run-one <job_id_prefix>
```

On failure, check `storage/run_<job_id>/error.txt`.

## Parameter Sweeps

```bash
uv run dr_exp --base-path ./debug_experiment --experiment test_run \
  job sweep --config configs/dummy_train.yaml --params "lr=0.01,0.001" --dry-run
```

## SLURM (cluster)

Use `scripts/dr_exp_slurm.sbatch` with `BASE_PATH` and `EXPERIMENT` set. See `docs/project_workflows.md`.

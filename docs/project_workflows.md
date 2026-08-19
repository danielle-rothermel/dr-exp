# dr_exp Project Workflows

Local and SLURM workflows for the filesystem-based experiment manager.

## Local Development

```bash
# Initialize
dr_exp --base-path ./experiments --experiment dev init

# Submit single job
dr_exp --base-path ./experiments --experiment dev \
  job submit --config-path configs --config-name dummy_train

# Submit sweep
dr_exp --base-path ./experiments --experiment dev \
  job sweep --config configs/dummy_train.yaml --params "epochs=2,5"

# Run worker locally
dr_exp --base-path ./experiments --experiment dev worker --worker-id w0 --max-jobs 5

# Operational commands
dr_exp --base-path ./experiments --experiment dev job list --status running
dr_exp --base-path ./experiments --experiment dev job recover --dry-run
dr_exp --base-path ./experiments --experiment dev validate
```

## SLURM Cluster

1. Set environment variables:
   - `BASE_PATH` — experiments root on shared storage
   - `EXPERIMENT` — experiment name
   - `WORKERS_PER_GPU` — workers per GPU (default 2)

2. Submit the canonical template:
   ```bash
   sbatch scripts/dr_exp_slurm.sbatch
   ```

3. Control a running launcher:
   ```bash
   python scripts/launcher_control.py --base-path $BASE_PATH --experiment $EXPERIMENT finish-current
   python scripts/launcher_control.py --base-path $BASE_PATH --experiment $EXPERIMENT stop-now
   ```

4. Inspect via CLI:
   ```bash
   dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT slurm status
   dr_exp --base-path $BASE_PATH --experiment $EXPERIMENT slurm logs <slurm_job_id>
   ```

## Programmatic Submission

```python
from dr_exp import submit_job, submit_jobs

job_id = submit_job(
    base_path="./experiments",
    experiment="dev",
    config={"_target_": "dr_exp.training.dummy_trainer.train", "epochs": 10},
)
```

## Hydra Config Layout

User training configs live under `configs/` and compose model, optimizer, and machine profiles. Job submit uses Hydra composition:

```bash
dr_exp ... job submit --config-path configs --config-name dummy_train \
  --overrides "epochs=5,lr=0.01"
```

The resolved config must include `_target_` pointing at an importable training function.

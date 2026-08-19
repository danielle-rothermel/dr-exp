# Utility Scripts

Surviving scripts for SLURM cluster operations:

- `dr_exp_slurm.sbatch` — canonical SLURM template for multi-GPU worker launcher
- `launcher_control.py` — send control commands to a running launcher (finish-current, stop-now)

Set `BASE_PATH`, `EXPERIMENT`, and `WORKERS_PER_GPU` when submitting the sbatch script.

See `docs/project_workflows.md` for workflow documentation.

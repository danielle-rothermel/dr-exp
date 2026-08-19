# dr_exp Package

Local-first experiment manager: filesystem job queue, Hydra worker dispatch, SLURM launcher.

Subpackages:
- `core/` — JobDB file-based queue
- `worker/` — job execution and multi-GPU launcher
- `cli/` — Click CLI and sweep utilities
- `training/` — dummy trainer for tests and smoke runs
- `submit.py` — programmatic job submission helpers

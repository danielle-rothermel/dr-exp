# Utility Scripts

Python scripts and utilities for development, testing, and cluster operations:

## Core Utilities
- `start_backend.py` – convenience wrapper to start the FastAPI backend
- `reap_stale_jobs.py` – marks running jobs with stale heartbeats as failed (also available via CLI)

## Submission Scripts
- `submission/` – directory containing job submission utilities and SLURM scripts
  - `submit_jobs.py` – unified job submission script with safety features
  - `submission_utils.py` – shared utilities for job submission
  - `submit_slurm_embedded.sh` – most reliable SLURM submission method
  - Various experiment-specific submission scripts

## SLURM Scripts
- `dr_exp_cluster.sbatch` – production-ready SLURM template
- `slurm_job_safe.sbatch` – improved SLURM script with better logging
- Various monitoring and launcher scripts

## Database/Remote Operations
- `supabase/` – scripts for remote database operations
  - `check_remote_db.py` – verify remote database connectivity
  - `deploy_to_remote.py` – deployment utilities
  - `fix_remote_db.py` – database repair utilities

For detailed workflow documentation, see `docs/project_workflows.md`.

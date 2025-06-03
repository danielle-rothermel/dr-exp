# Utility Scripts

Python scripts used as future CLI endpoints, in addition to some solely for development and testing:

- `reset_mock_db.py` – clears the local mock database.
- `run_worker.py` – thin wrapper that calls `dr_exp.worker.run_worker` for manual execution.
- `start_backend.py` – convenience wrapper to start the FastAPI backend.
- `upload_configs.py` – generates Hydra configs and uploads them to Supabase.
- `reap_stale_jobs.py` – marks running jobs with stale heartbeats as failed (also available via `manager_cli reap-stale-jobs`).
- `cleanup_run_data.py` – deletes run directories with a `finished.flag` once uploads are complete (also available via `manager_cli cleanup-run-data`).

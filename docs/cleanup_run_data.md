# Cleanup Run Data (`docs/cleanup_run_data.md`)

## Purpose

`cleanup_run_data.py` deletes local run directories that have already been uploaded. After a worker finishes uploading artifacts, a `finished.flag` file is written inside `run_<job_id>` in the local storage directory. These directories can be safely removed to reclaim disk space.

## Command Line Usage

```bash
python scripts/cleanup_run_data.py --base-path /path/to/env
```

Or via the manager CLI:

```bash
python -m dr_exp.manager_cli cleanup-run-data --base-path /path/to/env
```

The script scans the storage directory for `run_*` folders containing `finished.flag` and removes them, reporting the number deleted.

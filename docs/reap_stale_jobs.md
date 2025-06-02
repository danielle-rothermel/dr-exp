# Reap Stale Jobs (`docs/reap_stale_jobs.md`)

## Purpose

`reap_stale_jobs.py` cleans up jobs that were left in the `running` state when their manager stopped unexpectedly. It checks the heartbeat timestamp and marks stale jobs as failed.

## Command Line Usage

```bash
python scripts/reap_stale_jobs.py --max-age-mins 30 --base-path /path/to/env
```

Any running job with a heartbeat older than the provided threshold is updated to `status='failed'` with `status_reason='manager_died'`.

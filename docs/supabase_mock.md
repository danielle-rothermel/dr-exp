# LocalDB Client Specification (`docs/supabase_mock.md`)

## Purpose

This document defines the contract and structure for the filesystem-backed LocalDB client. It allows agent-based or CI-driven development and testing of the experiment management system without requiring internet access or live Supabase services.

The mock is intended to:

* Simulate database interactions (e.g., job claiming, status updates, metric logging)
* Mimic Supabase Storage behavior using the local filesystem
* Ensure interface compatibility with the real `supabase_client.py`

---

## Overview

The LocalDB client implements the same interface as the production client (`SupabaseClient`) and is selected at runtime via the `EXPMGR_MODE` environment variable (set to ``"mock"``).

* Uses local disk for storage (e.g., `./mock_storage/`)
* Optionally uses in-memory or SQLite-based metadata storage
* Supports the same high-level operations: claim job, update job, log metrics, upload artifacts

---

## Interface Requirements

The mock must implement the following methods:

```python
class SupabaseClient:
    def claim_job(self) -> dict: ...
    def update_job(self, job_id: str, data: dict): ...
    def log_metrics(self, job_id: str, metrics: list[dict]): ...
    def record_failure(self, job_id: str, error_type: str, message: str, stacktrace: Optional[str] = None): ...
    def finalize_job(self, job_id: str, final_status: str, metadata: dict): ...
    def upload_artifact(self, job_id: str, local_path: str, remote_path_suffix: str): ...
```

---

## Filesystem Layout

Artifacts and metrics should be stored using the same layout as real Supabase Storage:

```
mock_storage/
  run_<uuid>/
    metrics.jsonl
    checkpoint_epoch_10.pt.gz
    artifacts/
      plots/loss.png
      logs/training.log
```

---

## Job Simulation

Jobs will be stored as **individual JSON files** under `mock_db/jobs/`, one per job ID.

Behavior:

* Job claim should atomically assign one `status="queued"` job to a requester

  * Use file-level locking (`fcntl` or equivalent) to ensure concurrency safety
* Update functions should edit the job JSON file in place
* Retry count (`retry_index`) should increment automatically when a job is retried

---

## Metric and Error Logging

Metrics will be appended to per-job `.jsonl` files for compatibility with the production logger.

* Metrics path: `mock_db/metrics/<job_id>.jsonl`
* Format: one JSON object per line (JSONL)

Errors will be written to a **global `errors.jsonl` file**:

* Path: `mock_db/errors.jsonl`
* Each line is a JSON object with: `job_id`, `error_type`, `message`, `stacktrace`, `timestamp`

Stacktraces may be omitted (`null`) but format must match the schema.

---

## Implementation Notes

* The mock should **not require any external dependencies** beyond Python stdlib
* Supports concurrency-safe job claiming via file locking
* Artifacts should be **copied** from `local_path` to `mock_storage/run_<id>/<remote_path_suffix>` to simulate upload
* Environment variable `EXPMGR_MODE=mock` should control whether the mock is used
* Resetting the mock should **fully wipe** the mock DB and storage folders:

  * Deletes `mock_db/jobs/`, `mock_db/metrics/`, `mock_db/errors.jsonl`, and `mock_storage/`

Optional: provide CLI utility (`reset_mock_db.py`) to perform full wipe

---

## Future Extensions

* Implement Supabase row filtering (e.g., select jobs by cluster)
* Support resumable jobs and checkpoint linking
* Add validation layer to ensure returned structures match the real schema
* Support dry-run logging to preview what would be sent to Supabase


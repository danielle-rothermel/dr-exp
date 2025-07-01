# Supabase Schema Specification (`docs/supabase_schema.md`)

## Purpose

Supabase acts as the central database and object store for experiment coordination. It stores:

* Hydra-generated configs and sweep metadata
* Job state and assignment tracking with priority-based scheduling
* Metrics, artifact paths, and structured errors
* Post-run summaries for analysis and UI display

This schema provides the foundation for job lifecycle control, observability, reproducibility, and researcher interactivity.

## Database Setup

The system supports both local development and production deployment:

### Local Development (Recommended)
```bash
# Install Supabase CLI
brew install supabase/tap/supabase

# Start local instance (applies migrations automatically)
supabase start

# Set environment mode
export EXPMGR_MODE=supabase_local
```

### Production Deployment
```bash
# Set environment mode with credentials
export EXPMGR_MODE=supabase_remote
export SUPABASE_URL="your_project_url"
export SUPABASE_SERVICE_ROLE_KEY="your_service_role_key"
```

## Database Migrations

The schema is managed through SQL migrations in `supabase/migrations/`:

- `0001_initial_schema.sql`: Core tables and relationships
- `0002_add_priority_and_reservations.sql`: Priority system and job reservations
- `0003_create_storage_bucket.sql`: Storage bucket for experiment artifacts

All migrations are automatically applied when running `supabase start` or `supabase db reset`.

---

## Core Tables and Their Roles

### 1. `sweep_config_clusters`

High-level groupings of logically related sweeps. Human-friendly description + shared metadata.

| Field       | Type      | Description                      |
| ----------- | --------- | -------------------------------- |
| id          | UUID      | Primary key                      |
| name        | text      | Display name                     |
| description | text      | Optional text; may be left blank |
| created\_at | timestamp | Time of creation                 |

### 2. `sweep_configs`

Individual Hydra-resolved config instances to be used for job creation.

| Field              | Type      | Description                               |
| ------------------ | --------- | ----------------------------------------- |
| id                 | UUID      | Primary key                               |
| cluster\_id        | UUID      | Foreign key to `sweep_config_clusters.id` |
| config\_json       | jsonb     | Full resolved config                      |
| config\_hash       | text      | Hash of the config for deduplication      |
| interface\_version | text      | Used to ensure trainer compatibility      |
| created\_at        | timestamp | Time of config registration               |

### 3. `jobs`

Tracks training jobs with config references, current status, progress metrics, logs, and output artifact pointers.

| Field                    | Type      | Description                                                    |
| ------------------------ | --------- | -------------------------------------------------------------- |
| id                       | UUID      | Primary key                                                    |
| config\_id               | UUID      | Foreign key to `sweep_configs.id`                              |
| status                   | text      | `queued`, `running`, `completed`, `failed`, `killed`, `deleted`          |
| retry\_index             | int       | Retry count for this logical job                               |
| assigned\_worker         | text      | Default = `"unassigned"`; updated when a worker claims the job |
| heartbeat                | timestamp | Last update from worker                                        |
| metrics\_path            | text      | Path to `.jsonl` file in Supabase Storage; default = `""`      |
| artifacts\_path          | text      | Path to bundled `bundle.zip` archive; default = `""`            |
| num\_epochs              | int       | Reported by `train()`                                          |
| final\_val\_acc          | float     | Final reported accuracy                                        |
| final\_train\_loss       | float     | Final reported train loss                                      |
| upload\_complete\_at     | timestamp | When logger finalized upload                                   |
| finalize\_success        | bool      | Whether logger reported success                                |
| kill_requested | bool | Set when an admin issues a kill request |
| status_reason | text | Populated by the manager on failure (e.g. `worker_lost`) |
| train_status | text | Result reported by the trainer (`success` or `failed`) |
| metrics_storage_path | text | Path to the uploaded metrics file |
| bundle_storage_path | text | Path to the archived artifacts bundle |
| resumable\_from\_run\_id | UUID      | If resumed from a prior run                                    |
| checkpoint\_url          | text      | Path to resume checkpoint in blob storage; default = `""`      |
| interface\_version       | text      | Interface compatibility version tag                            |
| code\_version            | text      | Git SHA of training code                                       |
| start\_time              | timestamp | When training began                                            |
| end\_time                | timestamp | When training ended (only set for completed or failed jobs)    |
| priority                 | int       | Job priority (0-1000, higher = more urgent)                   |
| reserved\_for\_worker    | text      | Worker ID that can claim this job (NULL for unreserved)       |
| reservation\_expires\_at | timestamp | When job reservation expires (NULL for permanent)             |
| created\_at              | timestamp | When job was created                                           |

### 4. `metrics`

Optional per-epoch or per-step summary table. Can be used for UI previews, live streaming, or downsampled plotting.

| Field   | Type  | Description                                 |
| ------- | ----- | ------------------------------------------- |
| job\_id | UUID  | Foreign key to `jobs.id`                    |
| epoch   | int   | Epoch number                                |
| step    | int   | Optional — only used for step-based logging |
| metric  | text  | Metric name (e.g., `train_loss`)            |
| value   | float | Scalar value                                |

### 5. `errors`

Captures structured tracebacks and failure causes for post-mortem inspection.

| Field       | Type      | Description                             |
| ----------- | --------- | --------------------------------------- |
| job\_id     | UUID      | Foreign key to `jobs.id`                |
| error\_type | text      | `nan_failure`, `crash`, `timeout`, etc. |
| message     | text      | Short summary or exception class        |
| stacktrace  | text      | Nullable — full traceback if available  |
| timestamp   | timestamp | Time of failure                         |

### 6. `failures`

Keeps a retry log for auditability and diagnosis of repeated failures.

| Field        | Type      | Description                    |
| ------------ | --------- | ------------------------------ |
| job\_id      | UUID      | Job this failure relates to    |
| retry\_index | int       | Auto-incremented retry number  |
| error\_type  | text      | Matched to `errors.error_type` |
| timestamp    | timestamp | When the failure occurred      |

---

## Supabase Storage Buckets

All blob content is stored in Supabase Storage with structured paths.

* Bucket: `experiment-artifacts`
* Layout:

  ```
  experiment-artifacts/
    run_<uuid>/
      metrics.jsonl
      checkpoint_epoch_10.pt.gz
      artifacts/
        plots/loss.png
        logs/training.log
        summaries/config.yaml
  ```

Each run’s artifacts may use arbitrary subdirectories inside `artifacts/` for organization.

---

## Priority System

The jobs table includes a comprehensive priority-based scheduling system:

### Priority Classes
- **SYSTEM (900-1000):** Critical system maintenance and urgent fixes
- **URGENT (700-899):** Deadline-driven experiments and "run one" jobs  
- **HIGH (400-699):** Important experiments that should run soon
- **NORMAL (100-399):** Default priority range for regular experiments
- **LOW (0-99):** Background jobs that can run when resources are available

### Job Reservations
Jobs can be reserved for specific workers with automatic timeout:
- `reserved_for_worker`: Worker ID that can claim this job
- `reservation_expires_at`: When reservation expires (NULL for permanent)
- Reserved jobs bypass normal queue order when claimed by the designated worker
- Expired reservations are treated as unreserved jobs

### PostgreSQL Functions

#### `claim_next_job(worker_id_input TEXT)`
Atomically claims the next available job for a worker, respecting priority and reservations:

1. **Reserved jobs for this worker** (not expired)
2. **Unreserved jobs** by priority (highest first), then by creation time (oldest first)
3. **Expired reservations** by priority and creation time

Returns the full job record if a job was claimed, or empty result if no jobs available.

---

## Notes

* Row-Level Security (RLS) is not currently enforced but may be added in the future to restrict field mutability.
* Jobs are treated as append-only with `status`, `heartbeat`, `end_time`, and result fields updated as needed.
* Metrics, errors, and failures are append-only and can be manually purged via admin tools.
* Deleted jobs retain the row (status = `deleted`) but associated blobs (artifacts, metrics) are removed.
* Interface and code version hashes are stored per job to support compatibility and reproducibility checks.
* Priority changes are logged with timestamps and reasons for audit trails.
* Storage TTL, retention policies, and artifact metadata are deferred for future development.


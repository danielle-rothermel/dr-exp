# Supabase Schema Specification (`docs/supabase_schema.md`)

## Purpose

Supabase acts as the central database and object store for experiment coordination. It stores:

* Hydra-generated configs and sweep metadata
* Job state and assignment tracking
* Metrics, artifact paths, and structured errors
* Post-run summaries for analysis and UI display

This schema provides the foundation for job lifecycle control, observability, reproducibility, and researcher interactivity.

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
| status                   | text      | `queued`, `running`, `completed`, `failed`, `deleted`          |
| retry\_index             | int       | Retry count for this logical job                               |
| assigned\_worker         | text      | Default = `"unassigned"`; updated when a worker claims the job |
| heartbeat                | timestamp | Last update from worker                                        |
| metrics\_path            | text      | Path to `.jsonl` file in Supabase Storage; default = `""`      |
| artifacts\_path          | text      | Path to artifacts folder or archive; default = `""`            |
| num\_epochs              | int       | Reported by `train()`                                          |
| final\_val\_acc          | float     | Final reported accuracy                                        |
| final\_train\_loss       | float     | Final reported train loss                                      |
| upload\_complete\_at     | timestamp | When logger finalized upload                                   |
| finalize\_success        | bool      | Whether logger reported success                                |
| resumable\_from\_run\_id | UUID      | If resumed from a prior run                                    |
| checkpoint\_url          | text      | Path to resume checkpoint in blob storage; default = `""`      |
| interface\_version       | text      | Interface compatibility version tag                            |
| code\_version            | text      | Git SHA of training code                                       |
| start\_time              | timestamp | When training began                                            |
| end\_time                | timestamp | When training ended (only set for completed or failed jobs)    |

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

## Notes

* Row-Level Security (RLS) is not currently enforced but may be added in the future to restrict field mutability.
* Jobs are treated as append-only with `status`, `heartbeat`, `end_time`, and result fields updated as needed.
* Metrics, errors, and failures are append-only and can be manually purged via admin tools.
* Deleted jobs retain the row (status = `deleted`) but associated blobs (artifacts, metrics) are removed.
* Interface and code version hashes are stored per job to support compatibility and reproducibility checks.
* Storage TTL, retention policies, and artifact metadata are deferred for future development.


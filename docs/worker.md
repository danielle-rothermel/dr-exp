# Worker Process Specification (`docs/worker.md`)

## Purpose

The Worker is the atomic unit of execution in the experiment management system. Each worker process is responsible for:

* Atomically claiming a job from Supabase
* Loading the Hydra config and initializing logging paths
* Running the training loop via `train(cfg, logger)`
* Periodically reporting metrics, metadata, and heartbeats
* Uploading results to Supabase and Supabase Storage
* Handling failures and retries according to system policy

Workers are launched by the Manager (`run_manager.py`) as subprocesses, typically in a multi-worker-per-GPU configuration.

---

## Responsibilities

* Query Supabase to atomically claim a job (`status = queued` → `running`)
* Load and validate the `config_json` (Hydra DictConfig)
* Inject runtime paths for logging, checkpointing, artifact storage
* Initialize `StructuredLogger` with experiment manager configuration
* Execute training via `train(cfg, logger)`
* Log heartbeat at fixed intervals to Supabase
* Catch and report NaNs, timeouts, or crashes to the `failures` and `errors` tables
* Upload `.jsonl` log, checkpoint(s), and artifacts to Supabase Storage
* Mark job completion with `upload_complete_at` and `finalize_success = True`

---

## Inputs

* `cfg`: Hydra DictConfig pulled from Supabase `config_json`
* `run_id`: Job UUID used as the canonical ID throughout the system
* `logging.out_path`, `checkpoint_dir`, `artifact_dir`: injected by manager
* Optional resume metadata: `cfg.resume_from`, `checkpoint_url`, `resumable_from_run_id`

---

## Outputs

* `.jsonl` log file with metrics
* Saved checkpoint(s) (optional or periodic)
* Artifacts directory with plots, logs, summaries
* Final result dictionary from `train()`:

```python
{
  "final_val_acc": float,
  "final_train_loss": float,
  "num_epochs": int,
  "status": "success" | "nan_failure" | "crash",
  "metrics_path": str,
  "artifacts_path": str,
  "num_checkpoints": int
}
```

* Supabase job record is updated with all outputs, final status, and timestamps

---

## Failure Handling

* If `train()` raises an exception:

  * Worker logs full stacktrace to `errors` table
  * Sets `status = failed`, records timestamp, and exits
* If NaN detected or early termination:

  * Return `status = "nan_failure"`
* Manager may requeue job if under retry limit

---

## Heartbeats

* Worker updates a `heartbeat` timestamp in Supabase every `N` seconds
* Manager polls heartbeats to detect stalled or crashed workers
* Heartbeat interval is configurable (e.g., `--heartbeat-interval 10`)

---

## Retry Logic

* Job retry behavior is configured via `max_retries` in manager/CLI logic
* Worker does not automatically retry failed jobs (requeueing is external)
* Worker skips completed jobs unless explicitly requeued

---

## Optional Extensions

* Real-time metrics streaming to FastAPI via WebSocket (in parallel to `.jsonl` log)
* Resume from previous checkpoints using `resume_training(cfg, checkpoint_path)`
* Delayed start to stagger worker load on startup
* Compression of checkpoints or artifacts before upload. Directories selected
  for upload are zipped and stored as single `.zip` files in Supabase Storage.

---


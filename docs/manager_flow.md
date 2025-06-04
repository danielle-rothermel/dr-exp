# Manager & Launcher Specification (`docs/manager.md`)

### Purpose

The Manager process is launched per SLURM job and acts as the orchestrator for all training workers running on that job’s GPU resources. It manages local resource setup, worker launching, heartbeat monitoring, job reassignment, and graceful cleanup.

The Launcher initializes the execution environment (e.g., CUDA MPS) and delegates to the Manager.

### Key Parameters and Environment Variables

| Parameter              | Description                                |
| ---------------------- | ------------------------------------------ |
| `--gpus-per-node`      | Number of GPUs available on this SLURM job |
| `--workers-per-gpu`    | Number of concurrent workers per GPU       |
| `--heartbeat-interval` | Seconds between heartbeat checks           |
| `--idle-timeout-mins`  | Minutes of inactivity before shutdown      |
| `SLURM_ARRAY_TASK_ID`  | Used to identify worker group/run group ID |
| `SLURM_JOB_ID`         | Used for traceability and job metadata     |

## Manager <> Worker Interaction

`scripts/run_manager.py` is launched once per SLURM job. It discovers the GPUs available to that job and spawns one or more worker processes on each GPU. Each worker process runs the `run_worker.py` wrapper (which calls `dr_exp.manage.worker_logic.run_worker`) in its own subprocess. Workers claim jobs from Supabase (or the mock client), execute training and periodically update a heartbeat. The manager monitors these heartbeats to detect stalled or crashed workers and restarts them when needed.

### Launch Sequence

1. **Manager start**: `scripts/run_manager.py` is executed with parameters such as `--gpus-per-node`, `--workers-per-gpu` and `--heartbeat-interval`.
2. **GPU discovery**: The manager uses `discover_gpus()` to build a list of GPU IDs. If `CUDA_VISIBLE_DEVICES` is set, only those IDs are used.
3. **Worker spawning**: For each GPU and configured worker count, the manager calls `launch_worker()` which in turn starts a new `multiprocessing.Process` with `_worker_target`.
4. **Environment setup for worker**: `_worker_target` sets `CUDA_VISIBLE_DEVICES` to the assigned GPU ID and exports `DR_EXP_BASE_PATH` (used by the mock Supabase client). It then ensures the worker's directory exists and calls `run_worker_main()`.
5. **Worker entrypoint**: `run_worker_main()` (defined in `dr_exp.manage.manager_logic`) simply loads `dr_exp.manage.worker_logic.run_worker()` and passes the base path and working directory. The script `scripts/run_worker.py` merely exposes a CLI for this function.

### Worker Responsibilities

Inside `run_worker.run_worker()` the following actions occur:

1. **Job claim**: The worker obtains a client instance via `get_supabase_client()` and attempts to atomically claim a job (`status='queued' → 'running'`). It uses exponential backoff if no job is immediately available.
2. **Configuration setup**: Once a job is claimed, the worker fetches its configuration and creates a local working directory. Paths for metrics, checkpoints and artifacts are injected into the config.
3. **Heartbeat loop**: A background thread updates the job's `heartbeat` field every `heartbeat_interval` seconds using `client.update_job()`.
4. **Training**: The provided `trainer_fn` is called. Any exception is captured and recorded via `client.record_failure()`.
5. **Uploading results**: After training the worker uploads metrics, checkpoints, artifacts and its log file to Supabase Storage, then finalizes the job record with success or failure status.
6. **Cleanup**: Temporary files are removed and the function returns the final status string.

### Manager Monitoring

While workers run, the manager periodically executes two checks:

1. **Heartbeat check** (`check_heartbeats`): The manager lists all running jobs via the Supabase client. If a job's heartbeat is older than twice the heartbeat interval, the manager assumes the worker was lost. It marks the job as failed (`status_reason='worker_lost'`) and restarts that worker process.
2. **Idle timeout** (`check_idle_timeout`): If no running jobs remain for the configured idle timeout window, the manager initiates shutdown of all workers.

Workers write heartbeats and logs directly to Supabase, so the manager relies solely on the job records to monitor health. Workers do not communicate back to the manager process except through those updates.

### Shutdown Behaviour

On receiving SIGTERM or SIGINT, the manager sets a shutdown flag, waits for the current heartbeat check loop to finish, and then terminates all worker processes. Each worker will finish its current iteration and exit. When idle timeout is reached, the same shutdown procedure occurs.

### Environment Variables

- `CUDA_VISIBLE_DEVICES`: Set by the manager for each worker so it only sees its assigned GPU.
- `DR_EXP_BASE_PATH`: Base directory used by `LocalDBClient` when workers interact with the local DB/Storage.

## Manager <> FastAPI Interaction

The manager and FastAPI backend do not talk to each other directly; instead they share state via the JobDBClient. The manager, launches workers & updates job records in Supabase based on their work.  The FastAPI backend exposes REST endpoints which read or modify these same Supabase records. Actions triggered by the UI or CLI through the FastAPI API (e.g. job kill or requeue) result in Supabase updates that the manager or workers react to.

**Details:**
1. The manager and its workers communicate only with Supabase. They never call the FastAPI server directly.
2. When the manager spawns a worker, the worker claims a job from the Supabase `jobs` table and updates `status` and `heartbeat` fields as training progresses.
3. The FastAPI backend reads these job records to answer `GET /job/{job_id}` and `GET /metrics/{run_id}` requests. Metrics are loaded from the same paths the worker uploaded to Supabase Storage.
4. When an administrator issues `POST /job/kill` or `POST /job/requeue`, the FastAPI backend updates the corresponding fields in Supabase. Workers or the manager observe these changes (e.g. the `kill_requested` flag) and act accordingly.
5. Secrets such as Supabase credentials for the manager and the FastAPI admin API key are provided via environment variables as described in the environment documentation.

## 

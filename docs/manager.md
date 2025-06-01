# Manager & Launcher Specification (`docs/manager.md`)

## Purpose

The Manager process is launched per SLURM job and acts as the orchestrator for all training workers running on that job’s GPU resources. It manages local resource setup, worker launching, heartbeat monitoring, job reassignment, and graceful cleanup.

The Launcher initializes the execution environment (e.g., CUDA MPS) and delegates to the Manager.

---

## Responsibilities

### Launcher (`slurm_job.sbatch` + `run_manager.py`):

* Setup MPS directories and control daemon
* Source cluster-specific environment scripts
* Trap termination signals for clean shutdown
* Launch `run_manager.py` with appropriate arguments

### Manager (`run_manager.py`):

* Discover available GPUs and spawn N worker processes per GPU
* Monitor worker health via periodic heartbeats
* Detect unresponsive or crashed workers and restart them
* Query Supabase for stale or failed jobs to reclaim
* Enforce idle timeout (e.g., shutdown after 30 min inactivity)

---

## Key Parameters and Environment Variables

| Parameter              | Description                                |
| ---------------------- | ------------------------------------------ |
| `--gpus-per-node`      | Number of GPUs available on this SLURM job |
| `--workers-per-gpu`    | Number of concurrent workers per GPU       |
| `--heartbeat-interval` | Seconds between heartbeat checks           |
| `--idle-timeout-mins`  | Minutes of inactivity before shutdown      |
| `SLURM_ARRAY_TASK_ID`  | Used to identify worker group/run group ID |
| `SLURM_JOB_ID`         | Used for traceability and job metadata     |

---

## Worker Lifecycle Management

Each worker is launched via `multiprocessing.Process` and executes:

1. Claims a job from Supabase
2. Runs `train(cfg, logger)`
3. Logs structured outputs and artifacts
4. Reports heartbeats back to manager
5. Cleans up or retries on failure

If a worker crashes or stalls:

* The manager detects the missing heartbeat
* Logs the issue and restarts the worker process

---

## Cleanup Behavior

On SLURM termination or after timeout:

* Manager kills all child workers
* MPS control daemon is terminated
* Temp directories are deleted
* Supabase is optionally updated to mark job(s) as aborted

---

## Logging and Monitoring

* Logs are written per worker to `training.log`
* Optional: Aggregate manager-level logs for orchestration events
* Heartbeats are timestamped and stored in Supabase
* CLI tools or UI monitor job health via `last_heartbeat`

---

## Optional Extensions

* Priority-based job scheduling
* Dynamic scaling of worker count based on GPU memory or load
* Auto-throttling misbehaving workers
* Periodic status push to external dashboards (e.g., Grafana)

---


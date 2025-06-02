# Manager & Worker Interaction

This document clarifies how `run_manager.py` and `run_worker.py` cooperate during a training run. It focuses on the runtime sequence and how data flows between the two scripts.

## Overview

`run_manager.py` is launched once per SLURM job. It discovers the GPUs available to that job and spawns one or more worker processes on each GPU. Each worker process runs `run_worker.py` in its own subprocess. Workers claim jobs from Supabase (or the mock client), execute training and periodically update a heartbeat. The manager monitors these heartbeats to detect stalled or crashed workers and restarts them when needed.

## Launch Sequence

1. **Manager start**: `run_manager.py` is executed with parameters such as `--gpus-per-node`, `--workers-per-gpu` and `--heartbeat-interval`.
2. **GPU discovery**: The manager uses `discover_gpus()` to build a list of GPU IDs. If `CUDA_VISIBLE_DEVICES` is set, only those IDs are used.
3. **Worker spawning**: For each GPU and configured worker count, the manager calls `launch_worker()` which in turn starts a new `multiprocessing.Process` with `_worker_target`.
4. **Environment setup for worker**: `_worker_target` sets `CUDA_VISIBLE_DEVICES` to the assigned GPU ID and exports `DR_EXP_BASE_PATH` (used by the mock Supabase client). It then ensures the worker's directory exists and calls `run_worker_main()`.
5. **Worker entrypoint**: `run_worker_main()` (defined in `run_manager.py`) simply loads `run_worker.run_worker()` from `scripts/run_worker.py` and passes the base path and working directory. If the real worker implementation is missing an error is raised.

## Worker Responsibilities

Inside `run_worker.run_worker()` the following actions occur:

1. **Job claim**: The worker obtains a client instance via `get_supabase_client()` and attempts to atomically claim a job (`status='queued' → 'running'`). It uses exponential backoff if no job is immediately available.
2. **Configuration setup**: Once a job is claimed, the worker fetches its configuration and creates a local working directory. Paths for metrics, checkpoints and artifacts are injected into the config.
3. **Heartbeat loop**: A background thread updates the job's `heartbeat` field every `heartbeat_interval` seconds using `client.update_job()`.
4. **Training**: The provided `trainer_fn` is called. Any exception is captured and recorded via `client.record_failure()`.
5. **Uploading results**: After training the worker uploads metrics, checkpoints, artifacts and its log file to Supabase Storage, then finalizes the job record with success or failure status.
6. **Cleanup**: Temporary files are removed and the function returns the final status string.

## Manager Monitoring

While workers run, the manager periodically executes two checks:

1. **Heartbeat check** (`check_heartbeats`): The manager lists all running jobs via the Supabase client. If a job's heartbeat is older than twice the heartbeat interval, the manager assumes the worker was lost. It marks the job as failed (`status_reason='worker_lost'`) and restarts that worker process.
2. **Idle timeout** (`check_idle_timeout`): If no running jobs remain for the configured idle timeout window, the manager initiates shutdown of all workers.

Workers write heartbeats and logs directly to Supabase, so the manager relies solely on the job records to monitor health. Workers do not communicate back to the manager process except through those updates.

## Shutdown Behaviour

On receiving SIGTERM or SIGINT, the manager sets a shutdown flag, waits for the current heartbeat check loop to finish, and then terminates all worker processes. Each worker will finish its current iteration and exit. When idle timeout is reached, the same shutdown procedure occurs.

## Environment Variables

- `CUDA_VISIBLE_DEVICES`: Set by the manager for each worker so it only sees its assigned GPU.
- `DR_EXP_BASE_PATH`: Base directory used by `SupabaseMockClient` when workers interact with the mock DB/Storage.

## Summary

`run_manager.py` orchestrates worker lifecycles and watches for failures via heartbeat timestamps. `run_worker.py` focuses on job execution: claiming work, running training, uploading results and sending heartbeats. Their interaction is indirect—workers communicate status exclusively through Supabase (or the mock client) while the manager supervises and restarts workers when heartbeats stop.


# Manager CLI Overview (`docs/manager_cli.md`)

The `manager_cli.py` script provides a command line interface that wraps many of
the Experiment Manager utilities. It is primarily used when interacting with
real or mock environments outside of SLURM job scripts.

## Commands

- `run`
  - Starts the manager process which launches worker processes on the available
    GPUs.  Options include:
    - `--gpus-per-node`: number of GPUs visible on the node (defaults to `1`).
    - `--workers-per-gpu`: workers to spawn per GPU.
    - `--heartbeat-interval`: seconds between heartbeat checks.
    - `--idle-timeout-mins`: minutes of inactivity before shutdown.
- `discover-gpus`
  - Prints the GPU identifiers the manager would use.  Useful for debugging when
    `CUDA_VISIBLE_DEVICES` is set.
- `run-worker`
  - Runs a single worker directly.  Takes a `worker_id` and `work_dir` as
    arguments.
- `reap-stale-jobs`
  - Marks running jobs with heartbeats older than `--max-age-mins` as failed.
  - Accepts `--base-path` to point at a LocalDB instance when in mock mode.
- `cleanup-run-data`
  - Removes `run_<job_id>` directories from storage once a `finished.flag` file
    is present.  Accepts `--base-path` for the mock environment.
- `upload-configs`
  - Generates and uploads Hydra sweep configurations using the logic from
    `scripts/upload_configs.py`.
  - Now supports `--priority` flag to set job priority (0-1000, default: 100).

## Priority Management Commands

- `list-jobs`
  - Lists jobs ordered by priority (highest first) with status filtering.
  - Options:
    - `--status`: Filter by job status (default: `queued`). Can specify multiple statuses.
    - `--limit`: Maximum number of jobs to display (default: `20`).
    - `--base-path`: Base path for database client.
  - Example: `list-jobs --status queued running --limit 50`

- `boost-priority`
  - Increases a job's priority by a specified amount.
  - Arguments:
    - `job_id`: The job ID to boost.
    - `--amount`: Priority boost amount (default: `100`).
    - `--base-path`: Base path for database client.
  - Example: `boost-priority abc123 --amount 200`

- `set-priority`
  - Sets a job's priority to an exact value.
  - Arguments:
    - `job_id`: The job ID to update.
    - `priority`: New priority value (0-1000).
    - `--reason`: Optional reason for the priority change.
    - `--base-path`: Base path for database client.
  - Example: `set-priority abc123 900 --reason "Conference deadline"`

- `run-one`
  - Reserves and immediately executes a single high-priority job, bypassing the queue.
  - Options:
    - `--base-config-path`: Directory containing Hydra config files.
    - `--config-name`: Name of the main config file (default: `config.yaml`).
    - `--overrides`: Hydra override string (e.g., `model=resnet lr=0.001`).
    - `--priority`: Job priority (default: `700` for URGENT class).
    - `--reservation-timeout`: Reservation timeout in seconds (default: `300`).
    - `--work-dir`: Working directory for temporary files.
    - `--base-path`: Base path for database client.
    - `--worker-id`: Worker ID for job reservation.
  - Example: `run-one --overrides "model=resnet lr=0.001" --priority 850`

All commands internally call `get_supabase_client()`, so the environment variable
`EXPMGR_MODE` controls whether the real Supabase client or the local mock is
used.

## Priority System Integration

The CLI now includes comprehensive priority management capabilities:

1. **Job Submission**: Upload configs with custom priorities using `--priority` flag
2. **Queue Monitoring**: View jobs ordered by priority with `list-jobs`
3. **Priority Adjustment**: Boost or set exact priorities for existing jobs
4. **Urgent Execution**: Use `run-one` for immediate execution of critical jobs

See `docs/priority_system.md` for detailed documentation of the priority system.

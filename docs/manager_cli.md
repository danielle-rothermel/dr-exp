# Manager CLI Overview (`docs/manager_cli.md`)

The `dr_exp.manager_cli` module exposes a command line interface that wraps many
of the Experiment Manager utilities.  It is primarily used when interacting with
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

All commands internally call `get_supabase_client()`, so the environment variable
`EXPMGR_MODE` controls whether the real Supabase client or the local mock is
used.

# Manager CLI Overview (`docs/manager_cli.md`)

The `manager_cli.py` script provides a command line interface with grouped commands for 
comprehensive experiment management. It uses a modern command pattern architecture with 
organized subcommands for different aspects of the system.

## Command Structure

The CLI is organized into three main command groups:

- **`system`**: System management and infrastructure commands
- **`job`**: Job management and workflow commands  
- **`admin`**: Administrative and maintenance commands

All commands follow the pattern: `manager_cli.py <group> <command> [arguments]`

## System Commands (`system`)

### `run`
Starts the manager process which launches worker processes on available GPUs.

**Usage:** `manager_cli.py system run [options]`

**Options:**
- `--gpus-per-node`: Number of GPUs available on this node (default: 1)
- `--workers-per-gpu`: Number of worker processes per GPU (default: 1)  
- `--heartbeat-timeout`: Worker heartbeat timeout in seconds (default: 60)
- `--idle-timeout-mins`: Minutes of inactivity before manager shutdown (default: 30)

**Example:**
```bash
uv run python scripts/manager_cli.py system run --gpus-per-node 4 --workers-per-gpu 2
```

### `discover-gpus`
Lists visible GPU IDs that the manager would use.

**Usage:** `manager_cli.py system discover-gpus [options]`

**Options:**
- `--gpus-per-node`: Total GPUs if CUDA_VISIBLE_DEVICES not set (default: 1)

**Example:**
```bash
uv run python scripts/manager_cli.py system discover-gpus
```

### `run-worker`
Runs a single worker process directly.

**Usage:** `manager_cli.py system run-worker <worker_id> <work_dir>`

**Arguments:**
- `worker_id`: Unique worker identifier
- `work_dir`: Working directory for temporary files

**Example:**
```bash
uv run python scripts/manager_cli.py system run-worker dev_worker ./work
```

### `status`
Shows comprehensive system status including configuration, environment, and job information.

**Usage:** `manager_cli.py system status`

**Example:**
```bash
uv run python scripts/manager_cli.py system status
```

## Job Commands (`job`)

### `list-jobs`
Lists jobs ordered by priority with status filtering.

**Usage:** `manager_cli.py job list-jobs [options]`

**Options:**
- `--status`: Filter by job status (default: queued). Multiple values allowed.
- `--limit`: Maximum number of jobs to display (default: 20)

**Example:**
```bash
uv run python scripts/manager_cli.py job list-jobs --status queued running --limit 50
```

### `boost-priority`
Increases a job's priority by a specified amount.

**Usage:** `manager_cli.py job boost-priority <job_id> [options]`

**Arguments:**
- `job_id`: The job ID to boost

**Options:**
- `--amount`: Priority boost amount (default: 100)

**Example:**
```bash
uv run python scripts/manager_cli.py job boost-priority abc123 --amount 200
```

### `set-priority`
Sets a job's priority to an exact value.

**Usage:** `manager_cli.py job set-priority <job_id> <priority> [options]`

**Arguments:**
- `job_id`: The job ID to update
- `priority`: New priority value (0-1000)

**Options:**
- `--reason`: Optional reason for the priority change

**Example:**
```bash
uv run python scripts/manager_cli.py job set-priority abc123 900 --reason "Conference deadline"
```

### `run-one`
Creates and immediately executes a single high-priority job.

**Usage:** `manager_cli.py job run-one [options]`

**Options:**
- `--overrides`: Hydra-style config overrides (e.g., "model=resnet,lr=0.001")
- `--priority`: Job priority (default: 850)
- `--config-path`: Path to config directory (default: auto-detected)
- `--config-name`: Config file name (default: config.yaml)

**Example:**
```bash
uv run python scripts/manager_cli.py job run-one --overrides "model=resnet,lr=0.001" --priority 850
```

### `upload-configs`
Generates and uploads experiment configurations using Hydra sweeps.

**Usage:** `manager_cli.py job upload-configs [options]`

**Options:**
- `--sweep`: Parameter sweep definition (e.g., "model=resnet,vit lr=0.01,0.001")
- `--priority`: Set initial priority for all jobs (0-1000, default: 100)
- `--base-config-path`: Directory containing Hydra config files
- `--config-name`: Name of main config file (default: config.yaml)

**Example:**
```bash
uv run python scripts/manager_cli.py job upload-configs --sweep "model=resnet,vit optim=adam,sgd" --priority 500
```

## Admin Commands (`admin`)

### `reap-stale-jobs`
Marks running jobs with stale heartbeats as failed.

**Usage:** `manager_cli.py admin reap-stale-jobs [options]`

**Options:**
- `--max-age-mins`: Heartbeat age threshold in minutes (default: 60)

**Example:**
```bash
uv run python scripts/manager_cli.py admin reap-stale-jobs --max-age-mins 120
```

### `cleanup-run-data`
Removes old job run directories that have finished uploading.

**Usage:** `manager_cli.py admin cleanup-run-data`

**Example:**
```bash
uv run python scripts/manager_cli.py admin cleanup-run-data
```

## Architecture Features

### Command Pattern Design
- Extensible command architecture with grouped subcommands
- Consistent error handling and validation across all commands
- Clean separation of concerns between CLI presentation and business logic

### Environment Awareness
- SLURM-aware configuration with automatic directory management
- Environment-specific optimizations (job ID detection, node information)
- Comprehensive system status reporting including scheduler details

### Input Validation
- Centralized validation for all command arguments
- Priority range validation (0-1000)
- Job ID format validation and config override parsing
- Clear error messages for invalid inputs

### Error Handling
- Proper exit codes for all commands (0 for success, non-zero for failures)
- Structured error reporting with user-friendly messages
- Graceful handling of validation errors and system exceptions

## Priority System Integration

The CLI provides comprehensive priority management capabilities:

1. **Job Submission**: Upload configs with custom priorities using `--priority` flag
2. **Queue Monitoring**: View jobs ordered by priority with `list-jobs`
3. **Priority Adjustment**: Boost or set exact priorities for existing jobs
4. **Urgent Execution**: Use `run-one` for immediate execution of critical jobs
5. **System Status**: Monitor queue state and priority distribution

All commands automatically use the configured database mode (`EXPMGR_MODE` environment variable)
to work with files_local, supabase_local, or supabase_remote setups.

See `docs/priority_system.md` for detailed documentation of the priority system.
# Manager & Worker Flow Specification

## Overview

The Manager/Worker system achieves clean separation of concerns and eliminates mixed responsibilities. The system uses abstract interface methods to ensure the manager focuses purely on coordination logic while delegating all database-specific operations to appropriate abstractions.

## Key Architectural Principles

### Streamlined Interface Methods
The manager uses only abstract methods from `BaseJobDB`, eliminating database-specific code paths:
- `list_running_jobs()`: Get currently running jobs for monitoring
- `get_stale_jobs(max_age_seconds)`: Find jobs with stale heartbeats
- `mark_jobs_failed(job_ids, reason)`: Batch failure marking for lost workers
- `has_queued_jobs()`: Quick queue status check for idle timeout
- `get_queue_summary(limit)`: Preview of highest priority queued jobs

### Clean Separation of Concerns
- **Manager**: Focuses purely on high-level coordination logic
- **Worker**: Handles job execution with improved error handling
- **ProcessManager**: Abstracts multiprocessing lifecycle management
- **Factory**: Creates properly integrated system components

## System Components

### Manager (`src/dr_exp/manage/manager.py`)

The `Manager` class coordinates worker processes using only abstract interface methods:

**Core Responsibilities:**
- Launch and monitor worker processes via `ProcessManager`
- Detect stale jobs and mark them as failed
- Handle idle timeout and graceful shutdown
- Log system status and queue information

**Key Methods:**
- `start_workers()`: Launch configured worker processes
- `run()`: Main event loop with heartbeat monitoring
- `check_stale_jobs()`: Find and recover from lost workers
- `check_idle_timeout()`: Monitor for system inactivity

### Worker (`src/dr_exp/manage/worker.py`)

The worker has been redesigned with better separation of concerns:

**Components:**
- **HeartbeatManager**: Manages background heartbeat thread
- **JobExecutor**: Handles job execution with structured error handling
- **managed_work_directory**: Context manager for temporary directories

**Improved Error Handling:**
- Comprehensive exception capture and logging
- Structured failure recording with stack traces
- Automatic cleanup on both success and failure
- Proper artifact uploading even on training failures

### ProcessManager (`src/dr_exp/manage/process_manager.py`)

Abstracts multiprocessing details from the manager:

**Interface:**
- `launch_worker(worker_id, gpu_id, work_dir)`: Start worker process
- `stop_all_workers()`: Terminate all worker processes
- `restart_worker(worker_id)`: Restart failed worker
- `get_worker_count()`: Current active worker count
- `get_worker_status()`: Detailed worker status information

**Implementations:**
- `ProcessManager`: Real multiprocessing implementation
- `MockProcessManager`: Test-friendly mock for unit tests

### Factory System (`src/dr_exp/utils/factory.py`)

Ensures consistent system configuration and shared instances:

**Components:**
- `SystemConfig`: Unified configuration for all components
- `Factory`: Creates properly integrated managers and workers
- `create_system()`: Main entry point with environment awareness

## Execution Flow

### 1. System Initialization

```python
# Create system with environment-aware configuration
system = create_system()

# Or with explicit configuration
config = SystemConfig(
    gpus=["0", "1"],
    workers_per_gpu=2,
    heartbeat_timeout=60,
    idle_timeout_mins=30
)
system = create_system(config)
```

### 2. Manager Launch Sequence

1. **Initialization**: Manager created with shared job database and process manager
2. **Worker Spawning**: `start_workers()` launches configured workers via ProcessManager
3. **Environment Setup**: Each worker gets assigned GPU and isolated work directory
4. **Monitoring Loop**: Manager enters main loop monitoring job status and worker health

### 3. Worker Execution Flow

1. **Job Claiming**: Worker claims next available job using priority-based selection
2. **Heartbeat Start**: Background thread begins sending regular heartbeats
3. **Training Execution**: JobExecutor handles training with comprehensive error management
4. **Artifact Upload**: Results uploaded to storage regardless of training outcome
5. **Job Finalization**: Job marked as completed/failed with detailed metadata
6. **Cleanup**: Temporary files removed and worker ready for next job

### 4. Health Monitoring

**Stale Job Detection:**
```python
# Manager checks for workers that haven't sent heartbeats
stale_jobs = self.job_db.get_stale_jobs(self.heartbeat_timeout * 2)
if stale_jobs:
    job_ids = [job.job_id for job in stale_jobs]
    self.job_db.mark_jobs_failed(job_ids, "worker_lost")
    # Restart affected workers
```

**Idle Timeout:**
```python
# Manager monitors for system inactivity
if not self.job_db.has_queued_jobs() and not running_jobs:
    # Log queue status and prepare for shutdown
    queue_summary = self.job_db.get_queue_summary(limit=5)
```

## Command Line Interface

### Running the Manager

```bash
# Direct manager execution
uv run python scripts/run_manager.py --gpus-per-node 2 --workers-per-gpu 2

# Via manager CLI
uv run python scripts/manager_cli.py run --gpus-per-node 2 --workers-per-gpu 2

# With custom configuration
uv run python scripts/run_manager.py \
  --gpus-per-node 4 \
  --workers-per-gpu 1 \
  --heartbeat-timeout 30 \
  --idle-timeout 60
```

### Running Individual Workers

```bash
# Single worker for development/testing
uv run python scripts/run_worker.py --worker-id dev_worker

# Continuous mode
uv run python scripts/run_worker.py --worker-id test_worker --continuous

# Target specific job
uv run python scripts/run_worker.py --target-job-id <job_id>
```

## Environment Configuration

### Required Environment Variables

- `EXPMGR_MODE`: Database mode (`files_local`, `supabase_local`, `supabase_remote`)
- `DR_EXP_BASE_PATH`: Base directory for job data storage (default: `./job_data`)

### Worker Environment Setup

Each worker process gets:
- `CUDA_VISIBLE_DEVICES`: Set to assigned GPU ID
- `DR_EXP_BASE_PATH`: Inherited from manager environment
- Isolated working directory for temporary files

## Integration with Other Components

### FastAPI Backend

- Manager and workers communicate only through the job database
- FastAPI reads job status for UI display
- Admin operations (kill, requeue) update job records that manager/workers react to
- Real-time updates via WebSocket based on database changes

### Priority System

- Workers claim jobs in priority order (highest first)
- Manager logs queue status during idle periods
- Priority changes immediately affect job claiming order

### Storage System

- Workers upload artifacts to configured storage backend
- Manager doesn't directly handle storage operations
- Storage abstraction allows local files or cloud storage

## Error Handling and Recovery

### Worker Failures

1. **Training Exceptions**: Captured and recorded with full stack traces
2. **Worker Process Crashes**: Detected by stale heartbeat monitoring
3. **Resource Issues**: Structured error logging for debugging
4. **Automatic Recovery**: Manager restarts failed workers automatically

### Manager Resilience

1. **Database Connectivity**: Graceful handling of temporary connection issues
2. **Resource Cleanup**: Proper worker termination on shutdown signals
3. **State Recovery**: Manager can resume monitoring existing jobs after restart

## Testing Strategy

### Unit Tests
- Manager components tested in isolation using mock dependencies
- Worker components tested with temporary directories and mock training
- ProcessManager has both real and mock implementations

### Integration Tests
- End-to-end job execution workflows
- Manager-worker coordination scenarios
- System status and health monitoring
- Error recovery and cleanup behavior

### Performance Considerations

1. **Batch Operations**: Stale job detection processes multiple jobs efficiently
2. **Lightweight Monitoring**: Manager uses efficient database queries
3. **Minimal Overhead**: Worker heartbeats are lightweight database updates
4. **Resource Isolation**: Each worker operates in isolated environment

This streamlined architecture provides better maintainability, clearer responsibilities, and improved error handling while maintaining all existing functionality.
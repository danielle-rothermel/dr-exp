# Step 2.7: Multi-Worker Launcher

## Goal
Create a launcher that spawns and monitors multiple workers across available GPUs for long-running SLURM jobs.

## Prerequisites
- Step 2.6 completed and validated
- Worker class exists and can execute jobs
- CLI framework in place
- GPU environment with CUDA support

## Overview

This step implements a robust multi-worker launcher for HPC clusters:
- **GPU discovery**: Automatic detection via CUDA_VISIBLE_DEVICES or nvidia-smi
- **Worker spawning**: Multiple workers per GPU with unique IDs
- **Health monitoring**: Automatic restart of failed workers
- **Control files**: Graceful stop/finish-current commands
- **SLURM integration**: 47-hour runtime limit, signal handling
- **Status tracking**: JSON status files and error aggregation

## Key Components

### WorkerLauncher Class
Main launcher with capabilities:
1. **`discover_gpus()`** - Find available GPUs via env vars or nvidia-smi
2. **`spawn_worker()`** - Launch worker process with GPU assignment
3. **`check_worker_health()`** - Monitor and restart failed workers
4. **`check_control_files()`** - Handle stop/finish-current commands
5. **`write_status()`** - Output JSON status for monitoring
6. **`aggregate_errors()`** - Collect errors from worker logs
7. **`run()`** - Main loop with signal handling
8. **`maintenance()`** - Periodic job recovery and cleanup

### Design Decisions
- **Process groups**: Use `os.setsid()` for clean shutdown
- **Worker IDs**: Include SLURM job ID, node name, GPU index
- **Restart logic**: Only restart if pending jobs exist
- **Runtime limits**: Graceful shutdown before SLURM timeout
- **Control files**: Touch-based signaling for simplicity

## Validation

Test coverage includes:
- Launcher initialization and configuration
- GPU discovery methods (env vars and nvidia-smi)
- Worker spawning with correct environment
- Health monitoring and automatic restarts
- Control file handling (stop/finish-current)
- Status file generation with job counts
- Graceful shutdown with SIGTERM handling
- Runtime limit enforcement

Run: `pt tests/implementation/test_step_2_7.py -v`

## Implementation Notes

### Perfect Match with Instructions
The implementation follows the instructions exactly with no divergences. All planned features were implemented as specified.

### Implementation Quality Notes
- Excellent signal handling for SLURM compatibility
- Robust process management with groups
- Clean separation of control logic
- Comprehensive status reporting
- Good error aggregation for debugging

### Lessons Learned
1. Process groups essential for clean subprocess management
2. SLURM signal handling must be registered early
3. Worker IDs should encode location information
4. Control files provide simple, reliable IPC
5. Status files enable external monitoring

### Dependencies for Later Steps
- SLURM integration scripts will use this launcher (Step 2.9)
- Status files enable monitoring dashboards
- Control file pattern reused in other components
- Error aggregation helps debugging at scale

### Technical Decisions
1. **Process groups**: Enable killing all descendants with one signal
2. **File-based control**: More reliable than signals across nodes
3. **JSON status**: Machine-readable for monitoring tools
4. **Worker restart limit**: Via pending job check, not hard limit
5. **Error aggregation**: Centralized debugging for multi-worker runs

### Testing Insights
- Mock subprocess.Popen to avoid real process spawning
- Patch environment variables for GPU discovery tests
- Use time manipulation to test runtime limits
- Mock process poll() for health check testing
- Verify signal handling with mock killpg

### Performance Considerations
- Worker spawn time negligible compared to job runtime
- Status writes every 60s balance freshness vs I/O
- Maintenance every 10min for stale job recovery
- Process polling every 5s catches failures quickly
- Log aggregation scales linearly with worker count

### Future Enhancement Opportunities
1. Add worker CPU/memory limits via cgroups
2. Implement worker affinity to specific GPUs
3. Add Prometheus metrics export
4. Support heterogeneous GPU types
5. Implement worker pooling for small jobs
6. Add email notifications for failures

### Cross-Step Patterns
- Control file signaling (similar to JobDB locks)
- Status JSON files for monitoring
- Process group management for cleanup
- Comprehensive test mocking strategies
- SLURM-aware design patterns

### Risk Areas
1. **Zombie processes**: Mitigated by process groups
2. **GPU allocation conflicts**: CUDA_VISIBLE_DEVICES isolation
3. **Log disk usage**: Need rotation in production
4. **Worker deadlocks**: Timeout and restart logic
5. **SLURM timeout**: 47-hour limit with buffer

## Common Mistakes to Avoid
- Using complex IPC instead of simple control files
- Forgetting SIGTERM handling for SLURM
- Not using process groups for subprocess management
- Implementing complex worker coordination
- Ignoring CUDA_VISIBLE_DEVICES for GPU isolation

## Next Step
Proceed to Step 2.8: Config Sweeps
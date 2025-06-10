# Debugging Aids and Potential Issues

This document consolidates all debugging aids needed and potential issues identified during the dr_exp workflow analysis.

## Implementation Status Summary

### ✅ Completed (8 items)
1. **Verbose Submission Output** - Added `--verbose` flag to submit command with detailed validation
2. **Worker Debug Logging** - Added `--log-level` parameter to worker command with configurable logging levels
3. **Config Validation Command** - Added `validate config` subcommand with detailed parameter analysis
4. **Detailed Job Listing** - Added `--verbose` flag to list command with comprehensive job information
5. **Debug Mode for Single Job** - Added `--debug` and `--output-dir` flags to run_one command
6. **Sync Status Command** - Added `sync status` command to show queue state
7. **Force Sync Command** - Added `sync force` command for manual sync trigger
8. **Sync History Command** - Added `sync history` command to track sync operations

### 🔲 Open (10+ debugging aids remaining)
- Job recovery dry-run
- SLURM health checks
- Experiment management tools
- And more...

## Debugging Aids Still Needed

### 6. Job Recovery

#### Dry Run Recovery 🔲 OPEN
**Status**: Not yet implemented
**Need**: Preview what will be recovered
```bash
dr_exp recover --dry-run
```
**Expected output**:
```
Checking for stale jobs (timeout: 5 minutes)...
Found 2 stale jobs:
  - job_abc123: last heartbeat 15 min ago (worker: slurm123456_gpu_node1_worker0)
  - job_def456: last heartbeat 8 min ago (worker: slurm123456_gpu_node2_worker1)
  
These jobs would be reset to 'queued' status.
Run without --dry-run to recover these jobs.
```

### 7. SLURM-Specific Debugging

#### Worker Health Check 🔲 OPEN
**Status**: Not yet implemented
**Need**: Verify worker process health
```bash
dr_exp slurm health 123456
```
**Expected output**:
```
SLURM Job 123456 Health Check:
Node: node042
Workers:
  slurm123456_node042_gpu0_w0: ✓ Alive (PID: 12345, Memory: 8.2 GB / 10 GB)
  slurm123456_node042_gpu0_w1: ✓ Alive (PID: 12346, Memory: 7.8 GB / 10 GB)
  slurm123456_node042_gpu1_w0: ✗ Dead (Exit code: 137 - OOM Kill)
  
GPU Utilization:
  GPU 0: 85% (2 workers)
  GPU 1: 42% (1 worker)
  
Recent errors: 3 (check logs/slurm_123456/errors.log)
```

#### Live Log Tail
**Need**: Real-time log monitoring
```bash
dr_exp slurm tail 123456 --follow
```

### 8. Experiment Management

#### Experiment Health Check 🔲 OPEN
**Status**: Not yet implemented
**Need**: Overall experiment status
```bash
dr_exp health
```
**Expected output**:
```
Experiment: resnet_sweep
Base path: /scratch/users/jane/experiments

Jobs:
  Total: 1,234
  Queued: 45
  Running: 12
  Completed: 1,150
  Failed: 27 (2.2% failure rate)

Workers:
  Active SLURM jobs: 2
  Total workers: 12 (6 per SLURM job)
  Alive: 11
  Dead: 1

Storage:
  Total size: 125.3 GB
  Sync queue: 15 items (2.1 GB)
  
Recent activity:
  Jobs/hour: 45.2 (last hour)
  Avg completion time: 12.3 min
  
Warnings:
  ⚠ 1 worker dead (slurm123456_node042_gpu1_w0)
  ⚠ High failure rate on job pattern "lr=0.1" (15/20 failed)
```

#### Experiment Summary
**Need**: Quick overview of experiment
```bash
dr_exp summary
```

## Potential Issues Identified

### 1. Configuration and Setup Issues

#### Missing Initialization ✅ SOLVED
**Issue**: No initialization command to create directory structure
**Impact**: Users might miss creating required directories
**Solution**: Implemented `dr_exp init` command with:
- Automatic directory creation
- Permission validation
- Example config generation
- Disk space warnings
- Clear next steps guidance

#### Config Validation Gap
**Issue**: No validation that `_target_` function actually exists until execution
**Impact**: Jobs fail at runtime rather than submission time
**Solution**: Validate importability during submission

#### Schema Validation Missing
**Issue**: No validation beyond `_target_` field existence
**Impact**: Runtime failures due to missing required parameters
**Solution**: Optional schema validation against function signature

### 2. Job Management Issues

#### No Job ID Feedback
**Issue**: Job submission doesn't show created job ID by default
**Impact**: Users can't track specific jobs easily
**Solution**: Always display job ID on creation

#### Large Job List Pagination
**Issue**: No pagination for job listings
**Impact**: Performance issues with thousands of jobs
**Solution**: Add pagination support with `--page` and `--limit`

#### Job Filtering Limitations
**Issue**: Can only filter by status, not by config values
**Impact**: Hard to find specific job types
**Solution**: Add filter options like `--filter "config.model=resnet18"`

### 3. Worker Execution Issues

#### Silent Import Failures
**Issue**: Import errors for `_target_` only visible in logs
**Impact**: Confusing "job failed" without clear reason
**Solution**: Pre-validate imports before claiming job

#### Resource Limits Not Enforced
**Issue**: No memory/CPU limit enforcement mentioned
**Impact**: One job could consume all resources
**Solution**: Resource limits via cgroups or ulimit

#### No Progress Indication
**Issue**: No visibility into training progress
**Impact**: Can't tell if job is progressing or hung
**Solution**: Progress callbacks that update job metadata

### 4. Sync Issues

#### Invisible Sync Status
**Issue**: Sync happens silently in background
**Impact**: No visibility into sync failures or backlog
**Solution**: Sync status commands and metrics

#### No Manual Sync Trigger
**Issue**: Can't force sync of specific items
**Impact**: Important results might be delayed
**Solution**: Manual sync commands

#### Partial Upload Handling
**Issue**: No handling of partial uploads mentioned
**Impact**: Large files might fail repeatedly
**Solution**: Resumable uploads with chunking

### 5. SLURM Integration Issues

#### Multiple Job Conflicts
**Issue**: Original design didn't account for multiple SLURM jobs
**Impact**: Worker ID conflicts
**Solution**: Include SLURM job ID in worker names

#### No Resource Visibility
**Issue**: Can't see GPU/memory allocation per worker
**Impact**: Hard to debug resource issues
**Solution**: Resource tracking in status files

#### Log Scatter
**Issue**: Logs scattered across different locations
**Impact**: Hard to debug issues
**Solution**: Centralized logs under `logs/slurm_{job_id}/`

#### No Graceful Shutdown
**Issue**: Only hard kill available
**Impact**: Jobs interrupted mid-training
**Solution**: Control files for graceful shutdown

### 6. Error Handling Issues

#### Scattered Error Messages
**Issue**: Errors only in individual worker logs
**Impact**: Need to check many files to understand failures
**Solution**: Aggregated error log per SLURM job

#### No Error Patterns
**Issue**: No analysis of error patterns
**Impact**: Systematic issues hard to identify
**Solution**: Error pattern analysis in health check

#### Limited Error Context
**Issue**: Error messages might lack context
**Impact**: Hard to reproduce issues
**Solution**: Include config, environment, and system state in errors

### 7. Monitoring Gaps

#### No Active Worker List
**Issue**: Can't see which workers are active
**Impact**: Don't know if workers are running
**Solution**: Worker registry with heartbeats

#### No Job Duration Tracking
**Issue**: No visibility into how long jobs take
**Impact**: Can't estimate completion times
**Solution**: Track and display job durations

#### No Failure Analysis
**Issue**: No aggregated view of failures
**Impact**: Can't identify problematic configurations
**Solution**: Failure analysis commands

### 8. Operational Issues

#### No Experiment Listing
**Issue**: Can't list all experiments under base path
**Impact**: Forget what experiments exist
**Solution**: `dr_exp list-experiments` command

#### No Cleanup Integration
**Issue**: Cleanup tools separate from main CLI
**Impact**: Inconsistent interface
**Solution**: Integrate cleanup into main CLI

#### No Config Templates
**Issue**: Users must write configs from scratch
**Impact**: Error-prone and slow to start
**Solution**: Config template generation

### 9. Recovery Issues

#### Fixed Heartbeat Timeout
**Issue**: 5-minute timeout might not suit all jobs
**Impact**: Long-running jobs might be incorrectly recovered
**Solution**: Configurable timeout per job or global setting

#### No Recovery History
**Issue**: No record of which jobs were recovered
**Impact**: Can't debug recovery issues
**Solution**: Recovery log with timestamps

#### Recovery During Active Training
**Issue**: Job might be recovered while still running
**Impact**: Duplicate work
**Solution**: Better heartbeat mechanism with worker state

### 10. Security/Safety Issues

#### No Job Validation
**Issue**: Any `_target_` can be executed
**Impact**: Security risk
**Solution**: Whitelist of allowed targets

#### No Resource Quotas
**Issue**: One experiment could consume all resources
**Impact**: Unfair resource usage
**Solution**: Per-experiment quotas

#### No Access Control
**Issue**: Anyone can modify any experiment
**Impact**: Accidental interference
**Solution**: File permissions and ownership checks

## Recommended Implementation Priority

### High Priority (Needed for Basic Usage)
1. Init command for setup
2. Verbose submission output
3. Config validation
4. Sync status command
5. Worker debug logging
6. Aggregated error logs
7. SLURM health checks

### Medium Priority (Improves Usability)
1. Job filtering and pagination
2. Force sync command
3. Dry-run recovery
4. Experiment health check
5. Progress indication
6. Worker resource visibility

### Low Priority (Nice to Have)
1. Error pattern analysis
2. Config templates
3. Failure analytics
4. Advanced filtering
5. Historical metrics
6. Access control

## Testing Recommendations

### Manual Testing Checklist
- [ ] Test with malformed configs
- [ ] Test with non-existent `_target_`
- [ ] Test with 1000+ jobs
- [ ] Test worker death and recovery
- [ ] Test sync failures
- [ ] Test multiple SLURM jobs
- [ ] Test resource limits
- [ ] Test graceful shutdown
- [ ] Test error aggregation
- [ ] Test all debug commands

### Automated Testing Needs
- Config validation tests
- Worker lifecycle tests
- Sync queue tests
- Recovery mechanism tests
- SLURM integration tests
- Error handling tests
- CLI command tests

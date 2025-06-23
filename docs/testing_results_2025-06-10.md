# Testing Results - 2025-06-10

This document records the systematic testing of dr_exp commands following the Quick Start Guide.

## Test 1: `run-one` Command

### Expectation
- Command accepts config file path as shown in guide: `run-one configs/test_job.yaml`
- Executes job immediately bypassing queue
- No worker process required

### Action
```bash
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run run-one test_experiment/test_run/example_config.yaml
```

### Result vs Expectation
- **FAILED**: Command expects job ID, not config file path
- **Documentation Error**: Quick Start guide shows incorrect syntax
- **Actual Usage**: `run-one <job_id> [--working-dir <path>]`
- **Workaround**: Must first submit job to get ID, then use run-one
- When used correctly with job ID, it works as expected

## Test 2: Worker Log Monitoring

### Expectation
- Worker creates log file at `logs/worker_<worker_id>.log`
- Logs contain detailed execution information
- Can monitor with `tail -f` as shown in guide

### Action
```bash
# Started worker
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run worker --worker-id test_worker --working-dir $(pwd)/work --max-jobs 1
# Checked for log file
ls -la $(pwd)/test_experiment/test_run/logs/
```

### Result vs Expectation
- **FAILED**: No log files created
- **Impact**: Cannot monitor worker activity as documented
- **Worker Output**: Goes to stdout/stderr only
- **Missing Feature**: File-based logging not implemented

## Test 3: Failed Job Inspection

### Expectation
- Submit command accepts configs with invalid targets
- Failed jobs appear in `list --status failed`
- Error details saved to `storage/run_<job_id>/error.json`

### Action
```bash
# Submitted job with fail_rate=1.0
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit test_experiment/test_run/runtime_fail_config.yaml
# Ran worker to process it
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run worker --worker-id fail_worker2 --working-dir $(pwd)/work --max-jobs 1
```

### Result vs Expectation
- **Partial Success**: Submit validates target module at submission time (good but unexpected)
- **Success**: Runtime failures are captured correctly
- **Success**: Failed jobs appear in `list --status failed`
- **Documentation Error**: Error saved to `error.txt` not `error.json`

## Test 4: Multiple Concurrent Workers

### Expectation
- Multiple workers can run concurrently
- Jobs distributed by priority (highest first)
- No race conditions or conflicts

### Action
```bash
# Submitted 5 jobs with priorities 100-500
for i in {1..5}; do
  uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit configs/test_job.yaml --priority $((100 * i))
done
# Started 3 workers with max-jobs=2 each
for i in {1..3}; do
  uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run worker --worker-id worker_$i --working-dir $(pwd)/work_$i --max-jobs 2 &
done
```

### Result vs Expectation
- **Success**: Workers claimed jobs in correct priority order (500→400→300→200→100)
- **Success**: No race conditions or conflicts observed
- **Success**: Each worker respected max-jobs limit
- **Minor Issue**: Only 5 jobs total (not 6) because we only submitted 5

## New Issues Discovered

### 1. Documentation Errors
- **run-one syntax**: Guide shows config file path, but command expects job ID
- **error file format**: Guide mentions `error.json` but system creates `error.txt`
- **log monitoring**: Guide shows `tail -f logs/worker_*.log` but no log files are created

### 2. Missing Features
- **Worker file logging**: Workers only output to stdout/stderr, no persistent log files
- **run-one with config**: No way to run a config file directly without submitting first

### 3. Positive Findings
- **Target validation**: Submit command validates module existence (prevents some errors)
- **Concurrent execution**: Multiple workers handle concurrent job claiming correctly
- **Priority system**: Works exactly as documented

## Test 5: `validate` Command

### Expectation
- Validates experiment structure and configuration
- Checks for issues beyond just directory existence

### Action
```bash
# Test on valid experiment
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run validate
# Test on non-existent experiment
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment non_existent validate
# Test on corrupted experiment (removed sync_queue)
rm -rf $(pwd)/test_experiment/test_run/sync_queue
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run validate
```

### Result vs Expectation
- **Success**: Validates directory structure correctly
- **Success**: Clear error messages for missing directories
- **Limited Scope**: Only checks directories, not config validity or data integrity
- **Good UX**: Shows total job count when valid

## Test 6: `boost` Command

### Expectation
- Boosts job priority by a relative amount
- Can boost multiple jobs at once
- Works on queued jobs only

### Action
```bash
# Submit job with low priority
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit configs/test_job.yaml --priority 100
# Boost single job
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run boost 097b5a87-d65f-49d0-a0aa-049e3219ea7d --priority 800
# Boost multiple jobs
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run boost job1 job2 --priority 900
```

### Result vs Expectation
- **Different Behavior**: Sets absolute priority, not relative boost
- **Success**: Shows old → new priority values
- **Success**: Can boost multiple jobs at once
- **Success**: Rejects boosting non-queued jobs with clear error

## Test 7: `recover` Command

### Expectation
- Finds jobs stuck in "running" with stale heartbeats
- Resets them to "queued" status
- Handles worker failures gracefully

### Action
```bash
# Manually created stale job with 10+ minute old heartbeat
# Then ran recover
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run recover
```

### Result vs Expectation
- **Success**: Correctly identifies stale jobs (heartbeat > 5 minutes)
- **Success**: Resets status to "queued"
- **Success**: Clears worker_id and adds error message
- **Success**: Lists recovered job IDs for visibility
- **Confirms**: Issue #3 about stuck jobs can be resolved with recover command

## Test 8: `sync-status` Command

### Expectation
- Shows sync queue statistics
- Helps diagnose sync issues
- Reports pending/failed/completed items

### Action
```bash
# Check empty queue
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run sync-status
# Run worker to generate sync items
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run worker --worker-id sync_test --working-dir $(pwd)/work --max-jobs 1
# Check again
uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run sync-status
```

### Result vs Expectation
- **Success**: Shows sync queue counts
- **Success**: Items created when worker processes jobs
- **Limited Info**: Only shows counts, no details
- **Issue**: Sync items accumulate but aren't being processed

## Additional Findings

### 1. Boost Command Behavior
- **Expected**: Relative priority boost (e.g., +200)
- **Actual**: Sets absolute priority value
- **Impact**: Must know current priority to boost effectively

### 2. Sync Queue Processing
- **Issue**: Sync items created but not processed
- **Count**: 5 pending items after single job completion
- **Impact**: Could lead to unbounded growth

### 3. Validate Command Scope
- **Limited to**: Directory structure validation only
- **Missing**: Config validation, job integrity checks
- **Opportunity**: Could validate more aspects of experiment health

## Recommendations

1. **Update Quick Start Guide** to show correct `run-one` syntax with job ID
2. **Implement worker file logging** to match documentation
3. **Consider adding** `run-one-config` command for direct config execution
4. **Update error file** references from `.json` to `.txt` in documentation
5. **Add example** of getting job ID from submit output for use with run-one
6. **Document boost behavior** as setting absolute priority, not relative
7. **Investigate sync queue** processing - items accumulate without being processed
8. **Enhance validate command** to check more than just directory structure
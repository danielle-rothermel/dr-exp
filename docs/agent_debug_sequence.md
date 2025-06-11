# Agent Debug Sequence for dr_exp

## Instructions for Agent

Execute each step sequentially and record results in a new file: `/docs/debug_results_YYYY-MM-DD_HHMMSS.md`
Example filename: `debug_results_2025-06-10_143022.md` (use 24-hour time format)

For each step:
1. Run the command exactly as shown
2. Record the result using the format below
3. If a command fails, try up to 3 alternative approaches before moving on
4. Continue through all steps regardless of failures

### Alternative Approach Examples
When a command fails, try these types of alternatives:
- **File not found**: Use `find . -name "filename"` to locate it, check different directories
- **Command syntax error**: Run with `--help` flag, check similar commands, review error message
- **Permission denied**: Check file ownership with `ls -la`, try different paths
- **Config issues**: Create minimal test config, check for required fields
- **No output**: Add verbose flags (-v, --debug), check exit codes with `echo $?`

### Result Recording Format
```
## Step X: [Step Name]
Command: `[exact command]`
Expected: [what should happen]
Actual: [what actually happened]
Status: ✅ PASS | ⚠️ UNEXPECTED | ❌ FAIL
Notes: [any observations, error messages, or alternative approaches tried]
```

### Preconditions
- Working directory: Repository root (`/Users/daniellerothermel/drotherm/repos/dr_exp`)
- Clean state: Remove any existing `test_experiment` directory
- Python environment: Activated with `uv`

## Debug Sequence

### Setup Phase

#### Step 1: Clean Environment
Command: `rm -rf test_experiment 2>/dev/null; rm -rf work work_* 2>/dev/null; rm -rf job_* 2>/dev/null; echo "Clean environment ready"`
Expected: Removes all test artifacts and prints "Clean environment ready"
Status: Should always succeed

#### Step 2: Verify Installation
Command: `ckdr`
Expected: Output "All checks passed!"
Status: Must pass before continuing

#### Step 3: Initialize Experiment
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run init`
Expected: Creates directory structure and prints success message
Verify: Check that these directories exist:
- `test_experiment/test_run/jobs/`
- `test_experiment/test_run/storage/`
- `test_experiment/test_run/sync_queue/`
- `test_experiment/test_run/logs/`
- `test_experiment/test_run/control/`

### Quick Start Guide Commands

#### Step 4: Submit Test Job
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit --config-path configs --config-name test_job --priority 500`
Expected: Creates job and shows job ID, priority, and target
Capture: Job ID for later use

#### Step 5: List Queued Jobs
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run list --status queued`
Expected: Shows 1 queued job with priority 500
Verify: Job ID matches Step 4

#### Step 6: Run Worker
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run worker --worker-id debug_worker --working-dir $(pwd)/work --max-jobs 1`
Expected: Worker claims job, executes it, marks complete, exits
Verify: Output shows "completed": 1

#### Step 7: Check Worker Logs
Command: `ls -la $(pwd)/test_experiment/test_run/logs/`
Expected: Contains file `worker_debug_worker.log`
Alternative if not found:
1. Check if logs written elsewhere: `find test_experiment -name "*.log" -type f`
2. Check worker output for log location mentions
3. Verify logs directory exists and has write permissions
Status Criteria:
- ✅ PASS if log file exists
- ❌ FAIL if no log file (document as known issue)

#### Step 8: Check Completed Jobs
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run list --status completed`
Expected: Shows 1 completed job
Verify: Job status changed from queued to completed

#### Step 9: View Metrics
Command: `cat $(pwd)/test_experiment/test_run/storage/run_*/metrics.jsonl | head -n 5`
Expected: JSONL format metrics with epoch, loss, accuracy
Verify: File exists and contains valid JSON lines

#### Step 10: Test run-one with Job ID
Command: First get a job ID from a previous submission or create new job
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run run-one <JOB_ID> --working-dir $(pwd)/work`
Expected: Executes specific job immediately, bypassing queue
Status Criteria:
- ✅ PASS if job executes and shows "COMPLETED"
- ❌ FAIL if job not found or execution fails
Note: run-one requires job ID, not config file

#### Step 11: Test run-one (Correct Version)
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit --config-path configs --config-name test_job`
Capture: Job ID from output
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run run-one [JOB_ID] --working-dir $(pwd)/work`
Expected: Executes job immediately, shows "COMPLETED"

### Failed Job Testing

#### Step 12: Submit Failing Job
Command: `echo '_target_: "src.dr_exp.trainers.test_trainer.train"\nepochs: 1\nfail_rate: 1.0' > test_experiment/test_run/fail_job.yaml`
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit --config-path test_experiment/test_run --config-name fail_job`
Expected: Creates job successfully

#### Step 13: Process Failing Job
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run worker --worker-id fail_worker --working-dir $(pwd)/work --max-jobs 1`
Expected: Job fails with "Simulated training failure"
Verify: Worker shows "failed": 1

#### Step 14: Check Failed Jobs
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run list --status failed`
Expected: Shows 1 failed job

#### Step 15: View Error Details
Command: `cat $(pwd)/test_experiment/test_run/storage/run_*/error.txt`
Expected: Text formatted error details
Note: Error files are stored as .txt not .json

### Multiple Worker Testing

#### Step 16: Submit Multiple Jobs
Command: `for i in {1..5}; do uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit --config-path configs --config-name test_job --priority $((100 * i)); done`
Expected: Creates 5 jobs with priorities 100, 200, 300, 400, 500
Capture: All job IDs

#### Step 17: Run Concurrent Workers
Command: `for i in {1..3}; do uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run worker --worker-id worker_$i --working-dir $(pwd)/work_$i --max-jobs 2 & done; wait`
Expected: 3 workers process jobs concurrently, highest priority first
Verify During Execution: Run `ps aux | grep "worker_"` in another terminal to confirm 3 concurrent processes
Verify After: Check job claim order matches priority (500, 400, 300, 200, 100)
Status Criteria: 
- ✅ PASS if all jobs processed and priority order maintained
- ⚠️ UNEXPECTED if jobs processed but priority order wrong
- ❌ FAIL if workers don't run concurrently or jobs fail

### Additional CLI Commands

#### Step 18: Validate Experiment
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run validate`
Expected: Shows "✓ Validation PASSED" with job count

#### Step 19: Validate Missing Experiment
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment non_existent validate`
Expected: Shows "✗ Validation FAILED" with missing directories

#### Step 20: Test Boost Command
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit --config-path configs --config-name test_job --priority 100`
Capture: Job ID
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run boost [JOB_ID] --priority 800`
Expected: Shows "Boosted job: [ID] (100 → 800)"

#### Step 21: Test Recovery
##### Step 21a: Create Stale Job (Optional)
Command: `uv run python -c "import json, datetime; job_file = 'test_experiment/test_run/jobs/9136a8ec-3dc7-4803-a142-c54bb462d690.json'; data = json.load(open(job_file)); data['status'] = 'running'; data['heartbeat'] = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)).isoformat(); json.dump(data, open(job_file, 'w'), indent=2)"`
Expected: Modifies job to appear stale (if job exists)
Note: Skip if no queued job available

##### Step 21b: Run Recovery
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run recover`
Expected: Either "No stale jobs found" or "Recovered X stale job(s)"
Status Criteria:
- ✅ PASS if command runs without error
- Verify recovered jobs listed if any found

#### Step 22: Check Sync Status
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run sync-status`
Expected: Shows pending/failed/completed counts
Status Criteria:
- ✅ PASS if shows counts (even if non-zero)
- ⚠️ UNEXPECTED if pending count > 10 (indicates sync backlog)
- ❌ FAIL if command errors
Note: High pending count suggests sync processing issue

#### Step 23: Check Experiment Status
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run status`
Expected: Shows job counts and sync queue status

### Config Composition Testing

#### Step 24: Test Hydra Config
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit --config-path configs --config-name decon_config`
Expected: Creates job with DeconCNN trainer using Hydra composition
Status Criteria:
- ✅ PASS if creates job (tests Hydra composition with defaults)
- ❌ FAIL if missing fields or composition errors

#### Step 25: Verify Storage Locations
Command: `find . -name "lightning_logs" -type d 2>/dev/null`
Expected: No results (logs should be in experiment storage)
Command: `ls -la test_experiment/test_run/storage/`
Expected: All job outputs contained here

### Config Sweep Testing (New in 2.8)

#### Step 26: Test Basic Parameter Sweep (Dry Run)
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run sweep --config configs/test_job.yaml --params "epochs=1,2,3" --priority 600 --dry-run`
Expected: Shows 3 configurations with different epoch values
Verify: Each config should have different epochs value (1, 2, 3)
Status Criteria:
- ✅ PASS if shows 3 configs with correct values
- ❌ FAIL if config generation fails

#### Step 27: Submit Multi-Parameter Sweep
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run sweep --config configs/test_job.yaml --params "epochs=2,3 fail_rate=0.0,0.5" --priority 700`
Expected: Creates 4 jobs (2×2 grid: 2 epochs × 2 fail_rates)
Capture: Job IDs from output
Status Criteria:
- ✅ PASS if creates exactly 4 jobs
- ❌ FAIL if wrong number of jobs or submission errors

#### Step 28: Verify Sweep Jobs Created
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run list | grep "priority=700"`
Expected: Shows 4 jobs with priority 700
Verify: Each job has unique parameter combination

### Multi-Worker Launcher Testing (New in 2.7)

#### Step 29: Test Launcher in CPU Mode
Command: `timeout 30 uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run launcher --workers-per-gpu 2 --max-hours 0.001 2>&1 | tee launcher.log`
Expected: Launches 2 CPU workers (no GPUs on Mac), exits after ~3.6 seconds
Verify: Log shows "No GPUs detected, running in CPU mode"
Note: Uses timeout to ensure launcher stops
Status Criteria:
- ✅ PASS if spawns 2 workers in CPU mode
- ⚠️ UNEXPECTED if finds GPUs on Mac
- ❌ FAIL if crashes or hangs

#### Step 30: Check Launcher Status File
Command: `cat test_experiment/test_run/launcher_status_local.json | jq .`
Expected: JSON with workers info, start time, GPUs (empty), status
Verify: Shows 2 CPU workers were spawned

#### Step 31: Test Launcher Control File
Command: `echo "finish-current" > test_experiment/test_run/control/launcher_control_local.txt`
Command: `timeout 30 uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run launcher --workers-per-gpu 1`
Expected: Launcher detects control file and stops gracefully
Verify: Log shows "Control file detected: finish-current"

### SLURM Command Testing (New in 2.9)

#### Step 32: Test SLURM Status (No Jobs)
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run slurm status`
Expected: Shows "No active SLURM launcher jobs found"
Status Criteria:
- ✅ PASS if command runs without error
- ❌ FAIL if command crashes

#### Step 33: Test SLURM Control Commands
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run slurm control --stop-now --job-id 12345`
Expected: Creates control file for job 12345
Verify: Check control file exists: `ls test_experiment/test_run/control/launcher_control_12345.txt`

#### Step 34: Test SLURM Error Viewing
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run slurm errors`
Expected: Shows "No SLURM error logs found" (since no SLURM jobs ran)

## Synthesis Instructions

After completing all steps, create a synthesis section with:

### 1. Failures Table
Create a table with all ❌ FAIL results:
| Step | Command Summary | Expected | Actual | Root Cause |
|------|-----------------|----------|--------|------------|
| 7 | Check worker logs | Log file exists | No log file | Feature not implemented |
| (add all failures) |

### 2. Unexpected Behaviors
Create a table with all ⚠️ UNEXPECTED results:
| Step | Description | Impact | Recommendation |
|------|-------------|--------|----------------|
| 15 | Error format .txt not .json | Minor - docs wrong | Update documentation |
| (add all unexpected) |

### 3. Prioritized Issues List
Group issues by severity:

**Critical** (Blocks core functionality):
- Issue name: Description and impact

**Major** (Affects user experience):
- Issue name: Description and impact

**Minor** (Documentation/cosmetic):
- Issue name: Description and impact

### 4. Summary Statistics
- Total Steps: [count]
- Passed: [count] ([percentage]%)
- Failed: [count] ([percentage]%)
- Unexpected: [count] ([percentage]%)
- New Features Tested: Config sweeps (3 steps), Launcher (3 steps), SLURM (3 steps)

### 5. Overall System Assessment
Brief paragraph on system health, what works well, and what needs attention.

Present the completed debug results file for review.

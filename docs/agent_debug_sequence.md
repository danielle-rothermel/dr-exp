# Agent Debug Sequence for dr_exp

## Instructions for Agent

Execute each step sequentially and record results in a new file: `/docs/debug_results_YYYY-MM-DD_HHMMSS.md`

For each step:
1. Run the command exactly as shown
2. Record the result using the format below
3. If a command fails, try up to 3 alternative approaches before moving on
4. Continue through all steps regardless of failures

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
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit configs/test_job.yaml --priority 500`
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
Note: Documentation says this should exist

#### Step 8: Check Completed Jobs
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run list --status completed`
Expected: Shows 1 completed job
Verify: Job status changed from queued to completed

#### Step 9: View Metrics
Command: `cat $(pwd)/test_experiment/test_run/storage/run_*/metrics.jsonl | head -n 5`
Expected: JSONL format metrics with epoch, loss, accuracy
Verify: File exists and contains valid JSON lines

#### Step 10: Test run-one (Documentation Version)
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run run-one configs/test_job.yaml`
Expected: Runs job immediately bypassing queue
Note: Documentation shows this syntax

#### Step 11: Test run-one (Correct Version)
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit configs/test_job.yaml`
Capture: Job ID from output
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run run-one [JOB_ID] --working-dir $(pwd)/work`
Expected: Executes job immediately, shows "COMPLETED"

### Failed Job Testing

#### Step 12: Submit Failing Job
Command: `echo '_target_: "src.dr_exp.trainers.test_trainer.train"\nepochs: 1\nfail_rate: 1.0' > test_experiment/test_run/fail_job.yaml`
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit test_experiment/test_run/fail_job.yaml`
Expected: Creates job successfully

#### Step 13: Process Failing Job
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run worker --worker-id fail_worker --working-dir $(pwd)/work --max-jobs 1`
Expected: Job fails with "Simulated training failure"
Verify: Worker shows "failed": 1

#### Step 14: Check Failed Jobs
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run list --status failed`
Expected: Shows 1 failed job

#### Step 15: View Error Details
Command: `cat $(pwd)/test_experiment/test_run/storage/run_*/error.json | jq .`
Expected: JSON formatted error details
Alternative: Try `error.txt` if `error.json` not found

### Multiple Worker Testing

#### Step 16: Submit Multiple Jobs
Command: `for i in {1..5}; do uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit configs/test_job.yaml --priority $((100 * i)); done`
Expected: Creates 5 jobs with priorities 100, 200, 300, 400, 500
Capture: All job IDs

#### Step 17: Run Concurrent Workers
Command: `for i in {1..3}; do uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run worker --worker-id worker_$i --working-dir $(pwd)/work_$i --max-jobs 2 & done; wait`
Expected: 3 workers process jobs concurrently, highest priority first
Verify: Jobs claimed in priority order (500, 400, 300, 200, 100)

### Additional CLI Commands

#### Step 18: Validate Experiment
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run validate`
Expected: Shows "✓ Validation PASSED" with job count

#### Step 19: Validate Missing Experiment
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment non_existent validate`
Expected: Shows "✗ Validation FAILED" with missing directories

#### Step 20: Test Boost Command
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit configs/test_job.yaml --priority 100`
Capture: Job ID
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run boost [JOB_ID] --priority 800`
Expected: Shows "Boosted job: [ID] (100 → 800)"

#### Step 21: Test Recovery
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run recover`
Expected: No stale jobs found (or recovers any found)
Note: Hard to test without manually creating stale job

#### Step 22: Check Sync Status
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run sync-status`
Expected: Shows pending/failed/completed counts
Note: Check if pending items accumulate

#### Step 23: Check Experiment Status
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run status`
Expected: Shows job counts and sync queue status

### Config Composition Testing

#### Step 24: Test Hydra Config
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run submit configs/decon_config.yaml`
Expected: Creates job with DeconCNN trainer
Note: This uses Hydra config composition

#### Step 25: Verify Storage Locations
Command: `find . -name "lightning_logs" -type d 2>/dev/null`
Expected: No results (logs should be in experiment storage)
Command: `ls -la test_experiment/test_run/storage/`
Expected: All job outputs contained here

## Synthesis Instructions

After completing all steps, create a synthesis section with:

### 1. Failures Table
| Step | Command | Expected | Actual | Root Cause |
|------|---------|----------|--------|------------|
| List all ❌ FAIL results |

### 2. Unexpected Behaviors
| Step | Description | Impact |
|------|-------------|--------|
| List all ⚠️ UNEXPECTED results |

### 3. Prioritized Issues List
1. **Critical**: [Issues blocking core functionality]
2. **Major**: [Issues affecting user experience]
3. **Minor**: [Documentation or cosmetic issues]

### 4. Summary Statistics
- Total Steps: X
- Passed: X (X%)
- Failed: X (X%)
- Unexpected: X (X%)

Present the completed debug results file for review.
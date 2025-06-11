# Fix Documentation Gaps

## Objective
Update documentation to match actual system behavior.

## Files to Modify
- `/docs/agent_debug_sequence.md` - Fix run-one syntax
- `/docs/quick_start_guide.md` - Fix commands and remove incorrect features
- `/src/dr_exp/cli/main.py` - Update CLI help strings
- `/docs/implementation_guides/impl_steps/STEP_EXECUTION_CONTEXT.md` - Note functionality mismatches

## Implementation

### Step 1: Update agent_debug_sequence.md

Find Step 10 and replace:

```markdown
#### Step 10: Test run-one (Documentation Version)
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run run-one configs/test_job.yaml`
Expected: Runs job immediately bypassing queue
Alternative approaches when this fails:
1. Try with job ID instead: `run-one <job-id>`
2. Check help: `run-one --help`
3. Try different config file paths
Status Criteria:
- ✅ PASS if job runs (unlikely based on known issue)
- ❌ FAIL if "No job found" error (expected - document as doc bug)
```

With:

```markdown
#### Step 10: Test run-one with Job ID
Command: First get a job ID from a previous submission or create new job
Command: `uv run python -m dr_exp.cli.main --base-path $(pwd)/test_experiment --experiment test_run run-one <JOB_ID> --working-dir $(pwd)/work`
Expected: Executes specific job immediately, bypassing queue
Status Criteria:
- ✅ PASS if job executes and shows "COMPLETED"
- ❌ FAIL if job not found or execution fails
Note: run-one requires job ID, not config file
```

### Step 2: Update quick_start_guide.md

Find and replace these sections:

1. Remove worker log monitoring section (around line 175):
```markdown
**Monitor worker activity**:
```bash
# Worker logs show detailed execution
tail -f $(pwd)/debug_experiment/test_run/logs/worker_debug_worker.log
```
```

Replace with:
```markdown
**Monitor worker activity**:
Worker output goes to stdout/stderr. To capture it:
```bash
# Run worker with output redirection
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  worker \
  --worker-id debug_worker \
  --working-dir $(pwd)/work \
  2>&1 | tee worker.log
```
```

2. Fix run-one syntax (around line 166):
```markdown
**Run specific job immediately** (bypasses queue):
```bash
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  run-one \
  configs/test_job.yaml
```
```

Replace with:
```markdown
**Run specific job immediately** (bypasses queue):
```bash
# First submit a job to get ID
JOB_ID=$(uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  submit \
  --config-path configs \
  --config-name test_job | grep "Created job:" | cut -d' ' -f3)

# Then run it immediately
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  run-one \
  $JOB_ID \
  --working-dir $(pwd)/work
```
```

3. Fix submit command syntax (around line 80):
```markdown
# Using the test trainer (very fast, for debugging)
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  submit \
  configs/test_job.yaml \
  --priority 500
```

Replace with:
```markdown
# Using the test trainer (very fast, for debugging)
uv run python -m dr_exp.cli.main \
  --base-path $(pwd)/debug_experiment \
  --experiment test_run \
  submit \
  --config-path configs \
  --config-name test_job \
  --priority 500
```

4. Fix error file reference (around line 189):
```markdown
# View error details
cat $(pwd)/debug_experiment/test_run/storage/run_<job_id>/error.json | jq .
```

Replace with:
```markdown
# View error details
cat $(pwd)/debug_experiment/test_run/storage/run_<job_id>/error.txt
```

### Step 3: Update CLI help in cli/main.py

Find these commands and update their help/docstrings:

1. run-one command (around line 380):
```python
@click.command()
@click.argument("job_id")
@click.option("--no-sync", is_flag=True, help="Disable sync for debugging")
@click.option("--working-dir", help="Working directory for execution")
@click.pass_context
def run_one(ctx: click.Context, job_id: str, no_sync: bool, working_dir: Optional[str]) -> None:
    """Run a specific job immediately by job ID.
    
    Example:
        dr_exp --base-path ./exp --experiment test run-one 7c9a0e51-5a7a-4d46-a7f2
    """
```

2. init command help (around line 420):
Update the success message to not mention .jobdb file:
```python
click.echo(f"\nExperiment initialized successfully!")
click.echo(f"\nTo submit a job: dr_exp --base-path {base_path} --experiment {experiment} submit --config-path configs --config-name your_config")
```

### Step 4: Update STEP_EXECUTION_CONTEXT.md

Add a new section after line 119:

```markdown
## Known Implementation Gaps

These features are documented but not yet implemented:
1. **Worker file logging**: Workers output to stdout only, no log files created in `logs/`
2. **Sync queue processing**: Items accumulate but are not processed
3. **.jobdb metadata file**: Referenced in docs but not created or used

These behaviors differ from documentation:
1. **run-one command**: Requires job ID, not config file path
2. **Error files**: Saved as `error.txt` not `error.json`
3. **Submit command**: Uses Hydra-style `--config-path` and `--config-name`, not file paths
```

## Test

Create test file `/tests/implementation/test_doc_fixes.py`:

```python
import pytest
from pathlib import Path

def test_documentation_files_exist():
    docs_dir = Path("docs")
    assert (docs_dir / "quick_start_guide.md").exists()
    assert (docs_dir / "agent_debug_sequence.md").exists()
    
def test_no_worker_log_references():
    # Ensure we removed worker log references
    quick_start = Path("docs/quick_start_guide.md").read_text()
    assert "worker_debug_worker.log" not in quick_start
    assert "tail -f" not in quick_start or "worker.log" in quick_start
    
def test_correct_run_one_syntax():
    # Ensure run-one uses job ID
    quick_start = Path("docs/quick_start_guide.md").read_text()
    assert "run-one" in quick_start
    assert "configs/test_job.yaml" not in quick_start.split("run-one")[1].split("\n")[0]
    
def test_error_file_format():
    # Ensure error.txt not error.json
    quick_start = Path("docs/quick_start_guide.md").read_text()
    assert "error.json" not in quick_start
    assert "error.txt" in quick_start
```

## Verification Steps

1. Run tests: `pt tests/implementation/test_doc_fixes.py -v`
2. Manually review updated documentation for clarity
3. Run through quick start guide to ensure all commands work

## Common Mistakes to Avoid
- DO NOT add new features while updating docs
- DO NOT leave old syntax examples
- DO NOT create comprehensive documentation - just fix critical errors
- DO NOT update docs for unimplemented features
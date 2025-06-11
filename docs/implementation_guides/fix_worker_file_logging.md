# Fix Worker File Logging

## Objective
Implement file logging for workers to capture all stdout/stderr output.

## Files to Modify
- `/src/dr_exp/worker/base.py` - Add file logging to Worker class

## Implementation

### Step 1: Add logging setup to Worker.__init__

In worker/base.py, find the __init__ method (around line 50) and add after self.stats initialization:

```python
# Set up file logging
self.log_file = None
if experiment_path:
    log_dir = Path(experiment_path) / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"worker_{worker_id}.log"
    self.log_file = open(log_path, "a", buffering=1)  # Line buffered
    
    # Redirect stdout and stderr
    self._original_stdout = sys.stdout
    self._original_stderr = sys.stderr
    sys.stdout = self.log_file
    sys.stderr = self.log_file
    
    # Write header
    print(f"=== Worker {worker_id} started at {datetime.now(UTC).isoformat()} ===")
    print(f"Experiment: {Path(experiment_path).name}")
    print(f"Sync: {'enabled' if enable_sync else 'disabled'}")
    print(f"=" * 60)
```

### Step 2: Add cleanup to shutdown method

Find the shutdown method (around line 390) and add at the beginning:

```python
def shutdown(self, reason: str = "signal") -> None:
    """Shutdown worker gracefully."""
    print(f"\n=== Worker {self.worker_id} shutting down: {reason} ===")
    
    if self.log_file:
        # Restore original stdout/stderr
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        self.log_file.close()
        self.log_file = None
```

### Step 3: Add sys import at top

Add to imports:
```python
import sys
```

### Step 4: Handle exceptions in run method

In the run method, wrap the main loop in try/finally to ensure cleanup:

Find the run method and modify:

```python
def run(self) -> Dict[str, int]:
    """Run worker until shutdown or max_jobs reached."""
    try:
        # ... existing run code ...
        return self.stats
    finally:
        # Ensure log cleanup even on unexpected exit
        if self.log_file and not self.log_file.closed:
            sys.stdout = getattr(self, '_original_stdout', sys.__stdout__)
            sys.stderr = getattr(self, '_original_stderr', sys.__stderr__)
            self.log_file.close()
```

## Test

Create test file `/tests/implementation/test_worker_logging_fix.py`:

```python
import pytest
from pathlib import Path
import time
from dr_exp.worker.base import Worker
from dr_exp.core.job_db import JobDB

def test_worker_creates_log_file(tmp_path):
    # Create experiment
    job_db = JobDB(
        base_path=str(tmp_path),
        experiment_name="test_exp",
        validate=False
    )
    
    # Create a job
    job_id = job_db.create_job(
        config={"_target_": "dr_exp.trainers.test_trainer.train", "epochs": 1},
        priority=100
    )
    
    # Run worker
    worker = Worker(
        worker_id="test_worker",
        job_db=job_db,
        working_dir=str(tmp_path / "work"),
        experiment_path=str(tmp_path / "test_exp"),
        max_jobs=1,
        enable_sync=False
    )
    
    stats = worker.run()
    
    # Check log file exists
    log_file = tmp_path / "test_exp" / "logs" / "worker_test_worker.log"
    assert log_file.exists()
    
    # Check log content
    log_content = log_file.read_text()
    assert "Worker test_worker started at" in log_content
    assert "Experiment: test_exp" in log_content
    assert "Test trainer started" in log_content  # From test trainer output
    assert "completed successfully" in log_content
    assert stats["completed"] == 1

def test_worker_log_append_mode(tmp_path):
    # Create experiment
    job_db = JobDB(
        base_path=str(tmp_path),
        experiment_name="test_exp",
        validate=False
    )
    
    log_dir = tmp_path / "test_exp" / "logs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "worker_test_worker.log"
    
    # Write initial content
    log_file.write_text("Previous run content\n")
    
    # Create and run worker (no jobs, just initialization)
    worker = Worker(
        worker_id="test_worker",
        job_db=job_db,
        working_dir=str(tmp_path / "work"),
        experiment_path=str(tmp_path / "test_exp"),
        max_jobs=1,
        enable_sync=False
    )
    
    # Just initialize to test logging setup
    worker.shutdown("test")
    
    # Check previous content preserved
    log_content = log_file.read_text()
    assert "Previous run content" in log_content
    assert "Worker test_worker started at" in log_content

def test_worker_log_on_error(tmp_path):
    # Create experiment  
    job_db = JobDB(
        base_path=str(tmp_path),
        experiment_name="test_exp",
        validate=False
    )
    
    # Create failing job
    job_id = job_db.create_job(
        config={"_target_": "dr_exp.trainers.test_trainer.train", "epochs": 1, "fail_rate": 1.0},
        priority=100
    )
    
    # Run worker
    worker = Worker(
        worker_id="error_worker",
        job_db=job_db,
        working_dir=str(tmp_path / "work"),
        experiment_path=str(tmp_path / "test_exp"),
        max_jobs=1,
        enable_sync=False
    )
    
    stats = worker.run()
    
    # Check error logged
    log_file = tmp_path / "test_exp" / "logs" / "worker_error_worker.log"
    log_content = log_file.read_text()
    assert "failed" in log_content
    assert "RuntimeError" in log_content
    assert stats["failed"] == 1
```

## Verification Steps

1. Run tests: `pt tests/implementation/test_worker_logging_fix.py -v`
2. Run actual worker and check logs:
   ```bash
   dr_exp --base-path ./test --experiment log_test init
   dr_exp --base-path ./test --experiment log_test submit --config-name test --priority 100
   dr_exp --base-path ./test --experiment log_test worker --worker-id w1
   cat ./test/log_test/logs/worker_w1.log
   ```
3. Verify log contains all output including prints from training function

## Common Mistakes to Avoid
- DO NOT use Python logging module - redirect stdout/stderr
- DO NOT rotate logs or limit size
- DO NOT buffer writes - use line buffering
- DO NOT create separate error/info logs - one file for everything
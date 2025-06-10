# Step 2.1: Basic Worker Class

## Goal (1 sentence)
Create a basic worker class that can execute jobs using Hydra's dispatch mechanism without threading.

## Prerequisites
- [ ] Phase 1 (JobDB) completed and all tests passing
- [ ] Required files exist: src/dr_exp/core/job_db.py
- [ ] Hydra and OmegaConf installed: `uv add hydra-core omegaconf`

## Implementation

### 1. Create src/dr_exp/worker/__init__.py
```python
# Empty file to make this a package
```

### 2. Create src/dr_exp/worker/base.py
```python
"""Base worker implementation for job execution."""
import os
import sys
import traceback
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

import hydra
from omegaconf import OmegaConf, DictConfig

from ..core.job_db import JobDB


class Worker:
    """Base worker that executes jobs from JobDB."""
    
    def __init__(
        self, 
        job_db: JobDB,
        worker_id: str,
        working_dir: Optional[str] = None
    ):
        """Initialize worker.
        
        Args:
            job_db: JobDB instance to get jobs from
            worker_id: Unique identifier for this worker
            working_dir: Directory to run jobs in (defaults to current dir)
        """
        self.job_db = job_db
        self.worker_id = worker_id
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.current_job_id: Optional[str] = None
        
        # Ensure working directory exists
        self.working_dir.mkdir(parents=True, exist_ok=True)
    
    def execute_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single job using Hydra.
        
        Args:
            job: Job data from JobDB
            
        Returns:
            Result dict with status and optional error
        """
        job_id = job["id"]
        config = job["config"]
        
        # Create job-specific working directory
        job_dir = self.working_dir / f"job_{job_id}"
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # Change to job directory
        original_cwd = Path.cwd()
        os.chdir(job_dir)
        
        try:
            # Convert config to OmegaConf
            if isinstance(config, dict):
                config = OmegaConf.create(config)
            
            # Inject job metadata into config
            config.job_id = job_id
            config.worker_id = self.worker_id
            config.storage_path = str(self.job_db.get_storage_path(job_id))
            
            # Ensure storage directory exists
            Path(config.storage_path).mkdir(parents=True, exist_ok=True)
            
            # Execute using Hydra's call mechanism
            print(f"[{self.worker_id}] Executing job {job_id} with _target_={config._target_}")
            result = hydra.utils.call(config)
            
            # Job succeeded
            return {
                "status": "success",
                "result": result,
                "completed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            # Job failed
            error_msg = f"{type(e).__name__}: {str(e)}"
            tb = traceback.format_exc()
            
            print(f"[{self.worker_id}] Job {job_id} failed: {error_msg}")
            print(f"Traceback:\n{tb}")
            
            return {
                "status": "failed",
                "error": error_msg,
                "traceback": tb,
                "completed_at": datetime.utcnow().isoformat()
            }
            
        finally:
            # Always return to original directory
            os.chdir(original_cwd)
    
    def run_one_job(self) -> str:
        """Claim and execute one job.
        
        Returns:
            Status: 'completed', 'failed', or 'no_job'
        """
        # Try to claim a job
        job = self.job_db.claim_next_job(self.worker_id)
        
        if not job:
            print(f"[{self.worker_id}] No jobs available")
            return "no_job"
        
        self.current_job_id = job["id"]
        print(f"[{self.worker_id}] Claimed job {job['id']} (priority={job['priority']})")
        
        # Execute the job
        result = self.execute_job(job)
        
        # Update job status based on result
        if result["status"] == "success":
            # Extract metrics if provided
            metrics = None
            if isinstance(result.get("result"), dict):
                metrics = result["result"].get("metrics")
            
            self.job_db.complete_job(job["id"], metrics)
            print(f"[{self.worker_id}] Job {job['id']} completed successfully")
            status = "completed"
        else:
            self.job_db.fail_job(job["id"], result["error"])
            print(f"[{self.worker_id}] Job {job['id']} failed")
            status = "failed"
        
        self.current_job_id = None
        return status
    
    def run(self, max_jobs: Optional[int] = None) -> Dict[str, int]:
        """Run worker until no more jobs or max_jobs reached.
        
        Args:
            max_jobs: Maximum number of jobs to execute (None = unlimited)
            
        Returns:
            Dict with counts of completed, failed, and total jobs
        """
        stats = {
            "completed": 0,
            "failed": 0,
            "total": 0
        }
        
        print(f"[{self.worker_id}] Worker started")
        
        while max_jobs is None or stats["total"] < max_jobs:
            status = self.run_one_job()
            
            if status == "no_job":
                break
            elif status == "completed":
                stats["completed"] += 1
            elif status == "failed":
                stats["failed"] += 1
            
            stats["total"] += 1
        
        print(f"[{self.worker_id}] Worker finished: {stats}")
        return stats
```

### 3. Create src/dr_exp/trainers/__init__.py
```python
# Empty file to make this a package
```

### 4. Create src/dr_exp/trainers/test_trainer.py
```python
"""Simple test trainer for worker testing."""
import time
import random
from pathlib import Path
from typing import Dict, Any


def train(
    job_id: str,
    worker_id: str, 
    storage_path: str,
    epochs: int = 10,
    fail_rate: float = 0.0,
    **kwargs
) -> Dict[str, Any]:
    """Simple test training function.
    
    Args:
        job_id: Job ID (injected by worker)
        worker_id: Worker ID (injected by worker)
        storage_path: Path to store artifacts (injected by worker)
        epochs: Number of epochs to simulate
        fail_rate: Probability of failure (for testing)
        **kwargs: Additional config parameters
        
    Returns:
        Dict with training results
    """
    print(f"Test trainer started: job_id={job_id}, epochs={epochs}")
    
    # Simulate failure if requested
    if fail_rate > 0 and random.random() < fail_rate:
        raise RuntimeError("Simulated training failure")
    
    # Create storage directory
    storage = Path(storage_path)
    storage.mkdir(parents=True, exist_ok=True)
    
    # Simulate training with metrics
    metrics = []
    for epoch in range(epochs):
        loss = 1.0 / (epoch + 1) + random.random() * 0.1
        accuracy = min(0.99, epoch / epochs + random.random() * 0.1)
        
        metrics.append({
            "epoch": epoch,
            "loss": loss,
            "accuracy": accuracy
        })
        
        # Simulate computation time
        time.sleep(0.01)
        
        # Save metrics to file
        metrics_file = storage / "metrics.jsonl"
        with open(metrics_file, "a") as f:
            import json
            f.write(json.dumps(metrics[-1]) + "\n")
    
    # Save final model (dummy file)
    model_file = storage / "model_final.pt"
    model_file.write_text(f"Dummy model for job {job_id}")
    
    # Return final metrics
    final_metrics = {
        "final_loss": metrics[-1]["loss"],
        "final_accuracy": metrics[-1]["accuracy"],
        "total_epochs": epochs
    }
    
    print(f"Test trainer completed: final_accuracy={final_metrics['final_accuracy']:.3f}")
    
    return {
        "metrics": final_metrics,
        "artifacts": {
            "metrics_file": str(metrics_file),
            "model_file": str(model_file)
        }
    }
```

### 5. Create tests/implementation/test_step_2_1.py
```python
"""Test basic worker functionality."""
import tempfile
import json
import pytest
from pathlib import Path

from src.dr_exp.core.job_db import JobDB
from src.dr_exp.worker.base import Worker


def test_basic_worker():
    """Test worker can execute a single job."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize JobDB
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create a test job
        config = {
            "_target_": "src.dr_exp.trainers.test_trainer.train",
            "epochs": 5
        }
        job_id = job_db.create_job(config, priority=100)
        
        # Create worker with specific working directory
        work_dir = Path(tmpdir) / "worker_dir"
        worker = Worker(
            job_db=job_db,
            worker_id="test_worker",
            working_dir=str(work_dir)
        )
        
        # Run one job
        status = worker.run_one_job()
        assert status == "completed"
        
        # Verify job completed
        job = job_db.get_job(job_id)
        assert job["status"] == "completed"
        assert job["error"] is None
        assert "final_metrics" in job
        assert job["final_metrics"]["total_epochs"] == 5
        
        # Verify artifacts created
        storage_path = job_db.get_storage_path(job_id)
        assert (storage_path / "metrics.jsonl").exists()
        assert (storage_path / "model_final.pt").exists()
        
        # Verify working directory structure
        assert work_dir.exists()
        assert (work_dir / f"job_{job_id}").exists()
        


def test_worker_failure_handling():
    """Test worker handles job failures correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create a job that will fail
        config = {
            "_target_": "src.dr_exp.trainers.test_trainer.train",
            "epochs": 5,
            "fail_rate": 1.0  # Always fail
        }
        job_id = job_db.create_job(config)
        
        # Create and run worker
        worker = Worker(job_db=job_db, worker_id="test_worker")
        status = worker.run_one_job()
        
        assert status == "failed"
        
        # Verify job marked as failed
        job = job_db.get_job(job_id)
        assert job["status"] == "failed"
        assert "RuntimeError: Simulated training failure" in job["error"]
        


def test_worker_no_jobs():
    """Test worker behavior when no jobs available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # No jobs created
        worker = Worker(job_db=job_db, worker_id="test_worker")
        status = worker.run_one_job()
        
        assert status == "no_job"
        


def test_worker_run_multiple():
    """Test worker running multiple jobs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create multiple jobs
        job_ids = []
        for i in range(5):
            config = {
                "_target_": "src.dr_exp.trainers.test_trainer.train",
                "epochs": 2,
                "index": i,
                "fail_rate": 0.2 if i == 2 else 0.0  # One job will fail
            }
            job_id = job_db.create_job(config, priority=i * 100)
            job_ids.append(job_id)
        
        # Run worker
        worker = Worker(job_db=job_db, worker_id="batch_worker")
        stats = worker.run()
        
        # Verify stats
        assert stats["total"] == 5
        assert stats["completed"] >= 4  # At least 4 should complete
        assert stats["failed"] <= 1     # At most 1 should fail
        
        # Verify all jobs processed
        for job_id in job_ids:
            job = job_db.get_job(job_id)
            assert job["status"] in ["completed", "failed"]
        


def test_worker_max_jobs():
    """Test worker respects max_jobs limit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create 10 jobs
        for i in range(10):
            config = {
                "_target_": "src.dr_exp.trainers.test_trainer.train",
                "epochs": 1
            }
            job_db.create_job(config)
        
        # Run worker with limit
        worker = Worker(job_db=job_db, worker_id="limited_worker")
        stats = worker.run(max_jobs=3)
        
        assert stats["total"] == 3
        assert stats["completed"] == 3
        
        # Verify only 3 jobs processed
        queued_count = len(job_db.list_jobs(status="queued"))
        assert queued_count == 7
        


def test_worker_priority_order():
    """Test worker processes jobs in priority order."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create jobs with different priorities
        config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 1}
        
        low_id = job_db.create_job(config, priority=100)
        high_id = job_db.create_job(config, priority=900)
        med_id = job_db.create_job(config, priority=500)
        
        # Track execution order
        execution_order = []
        
        # Custom worker that tracks order
        class TrackingWorker(Worker):
            def execute_job(self, job):
                execution_order.append(job["id"])
                return super().execute_job(job)
        
        worker = TrackingWorker(job_db=job_db, worker_id="tracking_worker")
        worker.run()
        
        # Verify priority order (high, med, low)
        assert execution_order == [high_id, med_id, low_id]
        


```

## Validation
```bash
# Install required dependencies
uv add hydra-core omegaconf

# Run the test with pytest
pt tests/implementation/test_step_2_1.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_2_1.py::test_basic_worker PASSED
# tests/implementation/test_step_2_1.py::test_worker_failure_handling PASSED
# tests/implementation/test_step_2_1.py::test_worker_no_jobs PASSED
# tests/implementation/test_step_2_1.py::test_worker_run_multiple PASSED
# tests/implementation/test_step_2_1.py::test_worker_max_jobs PASSED
# tests/implementation/test_step_2_1.py::test_worker_priority_order PASSED
# ============================== 6 passed in X.XXs ===============================

# Verify code quality (runs ruff linting/formatting + mypy type checks)
ckdr

# Expected: All checks passed!
```

## Common Mistakes
- DO NOT: Add threading or async code yet - keep it simple
- DO NOT: Implement complex error recovery - just mark as failed
- DO NOT: Add job queuing in the worker - JobDB handles that
- DO NOT: Forget to change back to original directory after job execution
- DO NOT: Catch exceptions too broadly - let Hydra errors propagate properly

## Next Step
Proceed to Step 2.2: Sync Queue Implementation
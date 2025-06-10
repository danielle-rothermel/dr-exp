# Step 1.3: Job Lifecycle Management

## Goal (1 sentence)
Add complete job lifecycle methods including completion, failure, heartbeats, and storage management.

## Prerequisites
- [ ] Step 1.2 completed and validated
- [ ] Required files exist: src/dr_exp/core/job_db.py with locking
- [ ] test_step_1_2.py passes

## Implementation

### 1. Update src/dr_exp/core/job_db.py
Add these methods to the JobDB class:
```python
    def complete_job(self, job_id: str, metrics: Optional[Dict[str, Any]] = None) -> bool:
        """Mark a job as completed successfully.
        
        Args:
            job_id: Job to complete
            metrics: Optional final metrics to store
            
        Returns:
            True if updated, False if job not found
        """
        updates = {
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
            "error": None
        }
        if metrics:
            updates["final_metrics"] = metrics
        
        return self.update_job(job_id, updates)
    
    def fail_job(self, job_id: str, error: str) -> bool:
        """Mark a job as failed.
        
        Args:
            job_id: Job to fail
            error: Error message
            
        Returns:
            True if updated, False if job not found
        """
        updates = {
            "status": "failed",
            "completed_at": datetime.utcnow().isoformat(),
            "error": error
        }
        
        return self.update_job(job_id, updates)
    
    def heartbeat(self, job_id: str) -> bool:
        """Update job heartbeat timestamp.
        
        Workers should call this periodically to indicate they're alive.
        
        Args:
            job_id: Job to heartbeat
            
        Returns:
            True if updated, False if job not found
        """
        updates = {
            "last_heartbeat": datetime.utcnow().isoformat()
        }
        
        return self.update_job(job_id, updates)
    
    def list_jobs(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all jobs, optionally filtered by status.
        
        Args:
            status: Optional status filter (queued, running, completed, failed)
            
        Returns:
            List of job data dicts
        """
        jobs = []
        
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file, "r") as f:
                    job_data = json.load(f)
                    
                    if status is None or job_data.get("status") == status:
                        jobs.append(job_data)
                        
            except (json.JSONDecodeError, IOError):
                # Skip corrupted files
                continue
        
        # Sort by creation time
        jobs.sort(key=lambda x: x.get("created_at", ""))
        return jobs
    
    def get_sync_queue_path(self) -> Path:
        """Get path to sync queue directory.
        
        Returns:
            Path to sync queue directory
        """
        return self.sync_queue_dir
    
    def add_to_sync_queue(self, job_id: str, file_path: str, 
                         file_type: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Add a file to the sync queue.
        
        Args:
            job_id: Job that created this file
            file_path: Path to file to sync
            file_type: Type of file (metrics, logs, model, etc.)
            metadata: Optional metadata about the file
            
        Returns:
            Sync item ID
        """
        sync_id = str(uuid.uuid4())
        sync_item = {
            "id": sync_id,
            "job_id": job_id,
            "file_path": file_path,
            "file_type": file_type,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "status": "pending",
            "attempts": 0,
            "error": None
        }
        
        # Write to sync queue with timestamp prefix for ordering
        timestamp = int(time.time() * 1000000)  # Microseconds
        sync_file = self.sync_queue_dir / f"{timestamp}_{sync_id}.json"
        
        with open(sync_file, "w") as f:
            json.dump(sync_item, f, indent=2)
        
        return sync_id
    
    def get_experiment_info(self) -> Dict[str, Any]:
        """Get information about this experiment.
        
        Returns:
            Dict with experiment metadata
        """
        jobs = self.list_jobs()
        
        # Count by status
        status_counts = {}
        for job in jobs:
            status = job.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "experiment_name": self.experiment_name,
            "base_path": str(self.base_path),
            "experiment_path": str(self.experiment_path),
            "total_jobs": len(jobs),
            "status_counts": status_counts,
            "created_at": min(
                (j.get("created_at") for j in jobs if j.get("created_at")), 
                default=None
            )
        }
```

### 2. Create tests/implementation/test_step_1_3.py
```python
"""Test job lifecycle management."""
import tempfile
import time
import pytest
from pathlib import Path

from src.dr_exp.core.job_db import JobDB


def test_job_lifecycle():
    """Test complete job lifecycle from creation to completion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create a job
        config = {"_target_": "test.train", "epochs": 10}
        job_id = job_db.create_job(config, priority=200)
        
        # Verify initial state
        job = job_db.get_job(job_id)
        assert job["status"] == "queued"
        assert job["attempts"] == 0
        
        # Claim the job
        claimed_job = job_db.claim_next_job("worker_1")
        assert claimed_job is not None
        assert claimed_job["id"] == job_id
        assert claimed_job["status"] == "running"
        assert claimed_job["worker_id"] == "worker_1"
        assert claimed_job["attempts"] == 1
        assert "started_at" in claimed_job
        
        # Send heartbeats
        for i in range(3):
            time.sleep(0.1)
            success = job_db.heartbeat(job_id)
            assert success
            
            # Verify heartbeat updated
            job = job_db.get_job(job_id)
            assert "last_heartbeat" in job
        
        # Complete the job with metrics
        metrics = {
            "final_loss": 0.23,
            "final_accuracy": 0.95,
            "total_epochs": 10
        }
        success = job_db.complete_job(job_id, metrics)
        assert success
        
        # Verify completion
        job = job_db.get_job(job_id)
        assert job["status"] == "completed"
        assert job["error"] is None
        assert "completed_at" in job
        assert job["final_metrics"] == metrics
        


def test_job_failure():
    """Test job failure handling."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create and claim a job
        config = {"_target_": "test.train"}
        job_id = job_db.create_job(config)
        job_db.claim_next_job("worker_1")
        
        # Fail the job
        error_msg = "CUDA out of memory"
        success = job_db.fail_job(job_id, error_msg)
        assert success
        
        # Verify failure
        job = job_db.get_job(job_id)
        assert job["status"] == "failed"
        assert job["error"] == error_msg
        assert "completed_at" in job
        


def test_job_listing():
    """Test listing jobs with filters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create jobs in different states
        config = {"_target_": "test.train"}
        
        # Create 3 queued jobs
        queued_ids = []
        for i in range(3):
            job_id = job_db.create_job(config, priority=i*100)
            queued_ids.append(job_id)
        
        # Create 2 running jobs
        running_ids = []
        for i in range(2):
            job_id = job_db.create_job(config)
            job_db.claim_next_job(f"worker_{i}")
            running_ids.append(job_id)
        
        # Create 1 completed job
        job_id = job_db.create_job(config)
        job_db.claim_next_job("worker_complete")
        job_db.complete_job(job_id)
        completed_id = job_id
        
        # Create 1 failed job
        job_id = job_db.create_job(config)
        job_db.claim_next_job("worker_fail")
        job_db.fail_job(job_id, "Test error")
        failed_id = job_id
        
        # Test listing all jobs
        all_jobs = job_db.list_jobs()
        assert len(all_jobs) == 7
        
        # Test filtering by status
        queued_jobs = job_db.list_jobs(status="queued")
        assert len(queued_jobs) == 3
        assert all(j["id"] in queued_ids for j in queued_jobs)
        
        running_jobs = job_db.list_jobs(status="running")
        assert len(running_jobs) == 2
        assert all(j["id"] in running_ids for j in running_jobs)
        
        completed_jobs = job_db.list_jobs(status="completed")
        assert len(completed_jobs) == 1
        assert completed_jobs[0]["id"] == completed_id
        
        failed_jobs = job_db.list_jobs(status="failed")
        assert len(failed_jobs) == 1
        assert failed_jobs[0]["id"] == failed_id
        


def test_sync_queue():
    """Test sync queue functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create a job
        config = {"_target_": "test.train"}
        job_id = job_db.create_job(config)
        
        # Add items to sync queue
        sync_ids = []
        
        # Add metrics file
        sync_id1 = job_db.add_to_sync_queue(
            job_id=job_id,
            file_path="/tmp/metrics.json",
            file_type="metrics",
            metadata={"lines": 100}
        )
        sync_ids.append(sync_id1)
        
        # Small delay to ensure different timestamps
        time.sleep(0.001)
        
        # Add model file
        sync_id2 = job_db.add_to_sync_queue(
            job_id=job_id,
            file_path="/tmp/model.pt",
            file_type="model",
            metadata={"epoch": 10, "size_mb": 250}
        )
        sync_ids.append(sync_id2)
        
        # Verify sync files created
        sync_files = list(job_db.sync_queue_dir.glob("*.json"))
        assert len(sync_files) == 2
        
        # Verify files are ordered by timestamp
        sync_files.sort()
        for sync_file in sync_files:
            with open(sync_file, "r") as f:
                sync_data = json.load(f)
                assert sync_data["id"] in sync_ids
                assert sync_data["job_id"] == job_id
                assert sync_data["status"] == "pending"
                assert sync_data["attempts"] == 0
        


def test_experiment_info():
    """Test experiment info gathering."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create jobs in various states
        config = {"_target_": "test.train"}
        
        # 5 queued
        for _ in range(5):
            job_db.create_job(config)
        
        # 2 running
        for i in range(2):
            job_id = job_db.create_job(config)
            job_db.claim_next_job(f"worker_{i}")
        
        # 3 completed
        for _ in range(3):
            job_id = job_db.create_job(config)
            job_db.claim_next_job("worker_temp")
            job_db.complete_job(job_id)
        
        # 1 failed
        job_id = job_db.create_job(config)
        job_db.claim_next_job("worker_temp")
        job_db.fail_job(job_id, "Error")
        
        # Get experiment info
        info = job_db.get_experiment_info()
        
        assert info["experiment_name"] == "test_exp"
        assert info["total_jobs"] == 11
        assert info["status_counts"]["queued"] == 5
        assert info["status_counts"]["running"] == 2
        assert info["status_counts"]["completed"] == 3
        assert info["status_counts"]["failed"] == 1
        assert "created_at" in info
        


```

## Validation
```bash
# Run the test with pytest
pt tests/implementation/test_step_1_3.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_1_3.py::test_job_lifecycle PASSED
# tests/implementation/test_step_1_3.py::test_job_failure PASSED
# tests/implementation/test_step_1_3.py::test_job_listing PASSED
# tests/implementation/test_step_1_3.py::test_sync_queue PASSED
# tests/implementation/test_step_1_3.py::test_experiment_info PASSED
# ============================== 5 passed in X.XXs ===============================

# Verify previous tests still work
pt tests/implementation/test_step_1_1.py -v
pt tests/implementation/test_step_1_2.py -v

# Verify code quality (runs ruff linting/formatting + mypy type checks)
ckdr

# Expected: All checks passed!
```

## Common Mistakes
- DO NOT: Forget to handle None/missing fields in job data
- DO NOT: Use complex sync queue management - keep it simple with files
- DO NOT: Add database indexes or optimization - file system handles it
- DO NOT: Forget that JSON doesn't handle datetime objects - use ISO strings
- DO NOT: Add transaction support - single file updates are atomic enough

## Next Step
Proceed to Step 1.4: Operational Features
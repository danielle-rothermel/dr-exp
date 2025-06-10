# Step 1.4: Operational Features

## Goal (1 sentence)
Add operational methods for marking jobs as failed, recovering stale jobs, and boosting priority to complete the JobDB implementation.

## Prerequisites
- [ ] Step 1.3 completed and validated
- [ ] Required files exist: src/dr_exp/core/job_db.py with lifecycle methods
- [ ] test_step_1_3.py passes

## Implementation

### 1. Update src/dr_exp/core/job_db.py
Add these final methods to the JobDB class:
```python
    def mark_job_failed(self, job_id: str, reason: str) -> bool:
        """Mark a running job as failed (kill it).
        
        Args:
            job_id: Job identifier
            reason: Reason for marking as failed
            
        Returns:
            True if job was marked failed, False if not found or not running
        """
        job = self.get_job(job_id)
        if job and job["status"] == "running":
            return self.update_job(job_id, {
                "status": "failed",
                "error": f"Killed: {reason}",
                "completed_at": datetime.now(UTC).isoformat()
            })
        return False

    def recover_stale_jobs(self, heartbeat_timeout: int = 300) -> List[str]:
        """Reset jobs with stale heartbeats back to queued.
        
        Args:
            heartbeat_timeout: Seconds before considering heartbeat stale
            
        Returns:
            List of recovered job IDs
        """
        from datetime import timedelta
        
        cutoff = datetime.now(UTC) - timedelta(seconds=heartbeat_timeout)
        recovered = []
        
        for job_file in self.jobs_dir.glob("*.json"):
            with open(job_file, 'r') as f:
                job = json.load(f)
            
            if job["status"] == "running":
                heartbeat = job.get("heartbeat")
                if not heartbeat or datetime.fromisoformat(heartbeat) < cutoff:
                    # Reset to queued
                    self.update_job(job["id"], {
                        "status": "queued",
                        "assigned_worker": None,
                        "started_at": None,
                        "heartbeat": None,
                        "error": "Worker died - job reset to queue"
                    })
                    recovered.append(job["id"])
        
        return recovered
    
    def boost_priority(self, job_ids: List[str], new_priority: int) -> int:
        """Boost priority of multiple jobs.
        
        Args:
            job_ids: List of job IDs to boost
            new_priority: New priority value (0-1000)
            
        Returns:
            Number of jobs updated
        """
        assert 0 <= new_priority <= 1000, f"Priority must be 0-1000, got {new_priority}"
        
        updated = 0
        for job_id in job_ids:
            job = self.get_job(job_id)
            if job and job["status"] == "queued":
                self.update_job(job_id, {"priority": new_priority})
                updated += 1
                logger.info(f"Boosted job {job_id} to priority {new_priority}")
        
        return updated
```

### 2. Create tests/implementation/test_step_1_4.py
```python
"""Test operational features."""
import tempfile
import time
import pytest
from datetime import datetime, timedelta, UTC

from src.dr_exp.core.job_db import JobDB


def test_mark_job_failed():
    """Test marking jobs as failed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        # Create jobs in different states
        config = {"_target_": "dr_exp.training.dummy_trainer.train_dummy"}
        
        # Queued job
        queued_id = job_db.create_job(config)
        
        # Running job
        running_id = job_db.create_job(config)
        job_db.claim_next_job("worker_1")
        
        # Completed job
        completed_id = job_db.create_job(config)
        job_db.claim_next_job("worker_2")
        job_db.complete_job(completed_id)
        
        # Cannot mark queued job as failed
        success = job_db.mark_job_failed(queued_id, "Test kill")
        assert not success
        job = job_db.get_job(queued_id)
        assert job["status"] == "queued"  # Unchanged
        
        # Mark running job as failed
        success = job_db.mark_job_failed(running_id, "Test kill")
        assert success
        job = job_db.get_job(running_id)
        assert job["status"] == "failed"
        assert "Killed: Test kill" in job["error"]
        
        # Cannot mark completed job as failed
        success = job_db.mark_job_failed(completed_id, "Test kill")
        assert not success
        job = job_db.get_job(completed_id)
        assert job["status"] == "completed"  # Unchanged
        
        # Cannot mark non-existent job as failed
        success = job_db.mark_job_failed("fake_id", "Test kill")
        assert not success
        


def test_boost_priority():
    """Test priority boosting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        config = {"_target_": "dr_exp.training.dummy_trainer.train_dummy"}
        
        # Create low priority jobs
        job1_id = job_db.create_job(config, priority=100)
        job2_id = job_db.create_job(config, priority=150)
        
        # Boost priority of multiple jobs
        updated = job_db.boost_priority([job1_id, job2_id], 900)
        assert updated == 2
        
        # Verify boost
        job1 = job_db.get_job(job1_id)
        assert job1["priority"] == 900
        job2 = job_db.get_job(job2_id)
        assert job2["priority"] == 900
        
        # Create more jobs to test ordering
        job3_id = job_db.create_job(config, priority=200)
        
        # Boosted jobs should be claimed first (job1 first due to earlier creation)
        claimed = job_db.claim_next_job("worker_1")
        assert claimed["id"] == job1_id
        
        # Cannot boost running job
        running_id = job_db.create_job(config)
        job_db.claim_next_job("worker_2")
        updated = job_db.boost_priority([running_id], 950)
        assert updated == 0  # No jobs updated
        
        # Cannot boost with invalid priority
        try:
            job_db.boost_priority([job3_id], 1500)
            assert False, "Should have failed"
        except AssertionError as e:
            assert "Priority must be 0-1000" in str(e)
        


def test_recover_stale_jobs():
    """Test stale job recovery."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        
        config = {"_target_": "dr_exp.training.dummy_trainer.train_dummy"}
        
        # Create and claim jobs
        fresh_id = job_db.create_job(config)
        job_db.claim_next_job("worker_fresh")
        job_db.heartbeat(fresh_id)  # Recent heartbeat
        
        stale_id = job_db.create_job(config)
        job_db.claim_next_job("worker_stale")
        # No heartbeat - will be stale
        
        # Make the stale job actually stale by backdating its heartbeat
        old_time = (datetime.now(UTC) - timedelta(seconds=400)).isoformat()
        job_db.update_job(stale_id, {"heartbeat": old_time})
        
        # Recover with 5 minute threshold
        recovered = job_db.recover_stale_jobs(heartbeat_timeout=300)
        
        assert len(recovered) == 1
        assert stale_id in recovered
        
        # Verify stale job is queued again
        stale_job = job_db.get_job(stale_id)
        assert stale_job["status"] == "queued"
        assert stale_job["assigned_worker"] is None
        assert "Worker died" in stale_job["error"]
        
        # Fresh job should still be running
        fresh_job = job_db.get_job(fresh_id)
        assert fresh_job["status"] == "running"
        




def test_complete_jobdb():
    """Integration test of complete JobDB functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="final_test", validate=False)
        
        # Simulate a complete workflow
        config = {
            "_target_": "dr_exp.training.dummy_trainer.train_dummy",
            "model": "resnet50",
            "epochs": 100
        }
        
        # 1. Create urgent job
        urgent_id = job_db.create_job(config, priority=950)
        
        # 2. Create normal jobs
        normal_ids = []
        for i in range(3):
            job_id = job_db.create_job(config, priority=200 + i*50)
            normal_ids.append(job_id)
        
        # 3. Worker claims urgent job first
        claimed = job_db.claim_next_job("gpu_worker_1")
        assert claimed["id"] == urgent_id
        
        # 4. Send heartbeats while working
        for _ in range(5):
            job_db.heartbeat(urgent_id)
            time.sleep(0.01)
        
        # 5. Add files to sync queue during training
        job_db.add_to_sync_queue(
            urgent_id, 
            f"{job_db.get_storage_path(urgent_id)}/metrics.jsonl",
            "metrics"
        )
        
        # 6. Complete the job
        job_db.complete_job(urgent_id, {"accuracy": 0.98})
        
        # 7. Get experiment summary
        info = job_db.get_experiment_info()
        assert info["total_jobs"] == 4
        assert info["status_counts"]["completed"] == 1
        assert info["status_counts"]["queued"] == 3
        


```

## Validation
```bash
# Run the test with pytest
pt tests/implementation/test_step_1_4.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_1_4.py::test_mark_job_failed PASSED
# tests/implementation/test_step_1_4.py::test_boost_priority PASSED
# tests/implementation/test_step_1_4.py::test_recover_stale_jobs PASSED
# tests/implementation/test_step_1_4.py::test_complete_jobdb PASSED
# ============================== 4 passed in X.XXs ===============================

# Run ALL Phase 1 tests to ensure nothing broke
pt tests/implementation/test_step_1_1.py -v
pt tests/implementation/test_step_1_2.py -v
pt tests/implementation/test_step_1_3.py -v

# Verify code quality (runs ruff linting/formatting + mypy type checks)
ckdr

# Expected: All checks passed!
```

## Common Mistakes
- DO NOT: Add complex recovery logic - simple status reset is enough
- DO NOT: Implement job dependencies or workflows - not needed
- DO NOT: Add authentication or access control - single user system
- DO NOT: Optimize file operations - OS handles caching
- DO NOT: Add callbacks or hooks - keep it simple

## Phase 1 Complete! 🎉

You have successfully implemented a complete, thread-safe, file-based job database with:
- Priority-based queueing
- Concurrent job claiming with file locks
- Full job lifecycle (create, claim, update, complete, fail)
- Operational features (mark failed, boost priority, recover stale jobs)
- Sync queue for artifact tracking

## Next Step
Proceed to Phase 2, Step 2.1: Basic Worker Class
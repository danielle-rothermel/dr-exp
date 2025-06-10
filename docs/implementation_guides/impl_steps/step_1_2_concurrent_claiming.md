# Step 1.2: Concurrent Job Claiming

## Goal (1 sentence)
Add file locking to JobDB so multiple workers can safely claim jobs without conflicts.

## Prerequisites
- [ ] Step 1.1 completed and validated
- [ ] Required files exist: src/dr_exp/core/job_db.py
- [ ] test_step_1_1.py passes

## Implementation

### 1. Update src/dr_exp/core/job_db.py
Add these imports at the top:
```python
import fcntl
import time
from typing import List
```

Add these methods to the JobDB class:
```python
    def _list_job_files(self) -> List[Path]:
        """List all job files sorted by priority (highest first) then creation time.
        
        Returns:
            List of job file paths
        """
        job_files = []
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file, "r") as f:
                    job_data = json.load(f)
                    # Only include queued jobs
                    if job_data.get("status") == "queued":
                        job_files.append((
                            job_file,
                            job_data.get("priority", 0),
                            job_data.get("created_at", "")
                        ))
            except (json.JSONDecodeError, IOError):
                # Skip corrupted files
                continue
        
        # Sort by priority (descending) then created_at (ascending)
        job_files.sort(key=lambda x: (-x[1], x[2]))
        return [f[0] for f in job_files]
    
    def claim_next_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Claim the next available job atomically.
        
        Uses file locking to ensure only one worker can claim a job.
        
        Args:
            worker_id: ID of the worker claiming the job
            
        Returns:
            Job data dict if claimed, None if no jobs available
        """
        # Get sorted list of queued jobs
        job_files = self._list_job_files()
        
        for job_file in job_files:
            try:
                # Open file with exclusive lock
                with open(job_file, "r+") as f:
                    # Try to acquire exclusive lock (non-blocking)
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    
                    try:
                        # Read current data
                        f.seek(0)
                        job_data = json.load(f)
                        
                        # Double-check status (could have changed)
                        if job_data.get("status") != "queued":
                            continue
                        
                        # Claim the job
                        job_data["status"] = "running"
                        job_data["worker_id"] = worker_id
                        job_data["started_at"] = datetime.utcnow().isoformat()
                        job_data["updated_at"] = datetime.utcnow().isoformat()
                        job_data["attempts"] = job_data.get("attempts", 0) + 1
                        
                        # Write back atomically
                        f.seek(0)
                        f.truncate()
                        json.dump(job_data, f, indent=2)
                        f.flush()
                        
                        # Release lock happens automatically when file closes
                        return job_data
                        
                    finally:
                        # Ensure lock is released even if error occurs
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        
            except (IOError, BlockingIOError):
                # Lock is held by another process, try next job
                continue
            except Exception:
                # Skip corrupted files
                continue
        
        # No jobs available
        return None
    
    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update a job atomically.
        
        Args:
            job_id: Job to update
            updates: Fields to update
            
        Returns:
            True if updated, False if job not found
        """
        job_path = self.jobs_dir / f"{job_id}.json"
        if not job_path.exists():
            return False
        
        try:
            with open(job_path, "r+") as f:
                # Acquire exclusive lock
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                
                try:
                    # Read current data
                    f.seek(0)
                    job_data = json.load(f)
                    
                    # Apply updates
                    job_data.update(updates)
                    job_data["updated_at"] = datetime.utcnow().isoformat()
                    
                    # Write back atomically
                    f.seek(0)
                    f.truncate()
                    json.dump(job_data, f, indent=2)
                    f.flush()
                    
                    return True
                    
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    
        except Exception:
            return False
```

### 2. Create tests/implementation/test_step_1_2.py
```python
"""Test concurrent job claiming."""
import tempfile
import multiprocessing
import time
import pytest
from pathlib import Path

from src.dr_exp.core.job_db import JobDB


def worker_process(base_path: str, worker_id: str, results_queue):
    """Worker process that tries to claim jobs."""
    job_db = JobDB(base_path=base_path, experiment_name="test_exp")
    
    claimed_jobs = []
    for _ in range(10):  # Try up to 10 times
        job = job_db.claim_next_job(worker_id)
        if job:
            claimed_jobs.append(job["id"])
            # Simulate some work
            time.sleep(0.01)
        else:
            # No more jobs
            break
        time.sleep(0.001)  # Small delay between attempts
    
    results_queue.put((worker_id, claimed_jobs))


def test_concurrent_claiming():
    """Test that multiple workers can claim jobs without conflicts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize JobDB
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create 20 jobs with different priorities
        job_ids = []
        for i in range(20):
            config = {
                "_target_": "test.train",
                "index": i
            }
            # Higher index = higher priority
            priority = i * 50
            job_id = job_db.create_job(config, priority=priority)
            job_ids.append((job_id, priority))
        
        # Start 4 worker processes
        num_workers = 4
        results_queue = multiprocessing.Queue()
        processes = []
        
        for i in range(num_workers):
            p = multiprocessing.Process(
                target=worker_process,
                args=(tmpdir, f"worker_{i}", results_queue)
            )
            p.start()
            processes.append(p)
        
        # Wait for all workers to finish
        for p in processes:
            p.join(timeout=10)
            assert not p.is_alive(), "Worker process hung"
        
        # Collect results
        all_claimed = []
        worker_claims = {}
        
        for _ in range(num_workers):
            worker_id, claimed = results_queue.get()
            worker_claims[worker_id] = claimed
            all_claimed.extend(claimed)
        
        # Verify all jobs were claimed exactly once
        assert len(all_claimed) == 20, f"Expected 20 claims, got {len(all_claimed)}"
        assert len(set(all_claimed)) == 20, "Some jobs claimed multiple times!"
        
        # Verify each worker got some jobs
        for worker_id, claims in worker_claims.items():
            assert len(claims) > 0, f"{worker_id} didn't claim any jobs"
        
        # Verify high priority jobs were claimed first
        # Get the first 5 jobs claimed across all workers
        claim_times = {}
        for worker_id, claims in worker_claims.items():
            for idx, job_id in enumerate(claims):
                if job_id not in claim_times:
                    claim_times[job_id] = idx
        
        # Check that highest priority jobs (last 5 created) were claimed early
        high_priority_ids = [jid for jid, _ in job_ids[-5:]]
        high_priority_claim_order = [claim_times.get(jid, 999) for jid in high_priority_ids]
        avg_claim_order = sum(high_priority_claim_order) / len(high_priority_claim_order)
        
        assert avg_claim_order < 10, "High priority jobs not claimed first"
        


def test_job_updates():
    """Test atomic job updates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp")
        
        # Create a job
        config = {"_target_": "test.train"}
        job_id = job_db.create_job(config, priority=100)
        
        # Update the job
        updates = {
            "status": "completed",
            "metrics": {"loss": 0.5, "accuracy": 0.95}
        }
        success = job_db.update_job(job_id, updates)
        assert success
        
        # Verify updates
        job = job_db.get_job(job_id)
        assert job["status"] == "completed"
        assert job["metrics"]["accuracy"] == 0.95
        assert "updated_at" in job
        
        # Test updating non-existent job
        success = job_db.update_job("fake_id", {"status": "failed"})
        assert not success
        


```

## Validation
```bash
# Run the test with pytest
pt tests/implementation/test_step_1_2.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_1_2.py::test_concurrent_claiming PASSED
# tests/implementation/test_step_1_2.py::test_job_updates PASSED
# ============================== 2 passed in X.XXs ===============================

# Verify previous test still works
pt tests/implementation/test_step_1_1.py -v

# Verify code quality (runs ruff linting/formatting + mypy type checks)
ckdr

# Expected: All checks passed!
```

## Common Mistakes
- DO NOT: Use threading.Lock - we need inter-process locking (fcntl)
- DO NOT: Hold locks longer than necessary - release immediately after update
- DO NOT: Forget to handle lock acquisition failures - other workers may have the lock
- DO NOT: Use blocking lock acquisition - use LOCK_NB to avoid deadlocks
- DO NOT: Forget to flush after writing - ensure data is on disk

## Next Step
Proceed to Step 1.3: Job Lifecycle Management
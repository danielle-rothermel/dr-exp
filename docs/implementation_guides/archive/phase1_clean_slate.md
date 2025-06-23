# Phase 1: Clean Slate Implementation Guide

## Overview
This phase creates a completely new foundation by removing ALL legacy code and implementing a single, simple JobDB class. 

**Duration**: 3-4 days
**Outcome**: Clean codebase with single storage pattern

## Pre-flight Checklist

### Step 1: Create New Branch
```bash
git checkout -b architecture-redesign
git push -u origin architecture-redesign
```

### Step 2: Verify You're on Correct Branch
```bash
git branch --show-current  # Should show: architecture-redesign
```

## Files to Delete (NO EXCEPTIONS)

### Delete Entire Directories
```bash
# Remove all complex JobDB implementations
rm -rf src/dr_exp/job_db/

# Remove factory patterns and complex configuration
rm -rf src/dr_exp/utils/factory.py
rm -rf src/dr_exp/utils/jobdb_factory.py
rm -rf src/dr_exp/utils/cli_config.py

# Remove old manager/worker implementations (will rewrite)
rm -rf src/dr_exp/manage/

# Remove complex CLI system (will simplify)
rm -rf src/dr_exp/cli/
```

### Delete Specific Files
```bash
# Remove mode-specific scripts
rm scripts/run_worker.py
rm scripts/run_manager.py
rm scripts/upload_configs.py
rm scripts/reset_local_jobdb.py

# Remove old configuration files
rm src/dr_exp/job_db/config.py
rm src/dr_exp/job_db/jobdb_config.py
```

## New Directory Structure to Create

```bash
mkdir -p src/dr_exp/core/
mkdir -p src/dr_exp/sync/
mkdir -p src/dr_exp/worker/
```

## Step 3: Implement Single JobDB Class

**IMPORTANT**: JobDB is created once per experiment and shared by all workers. It uses file locking to ensure atomic operations when multiple workers access it simultaneously.

Create `src/dr_exp/core/job_db.py`:

```python
"""Single, simple JobDB implementation - no modes, no complexity."""

import json
import os
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging
import sys

logger = logging.getLogger(__name__)

# Note: fcntl is Unix-only. For Windows development, you'll need a different locking mechanism.
# The cluster (Linux) will use fcntl for production.


class JobDB:
    """Simple file-based job database with optional Supabase sync.
    
    Always writes to /scratch filesystem first.
    Supabase is only for remote read access.
    """
    
    def __init__(self, base_path: str, experiment_name: str):
        """Initialize JobDB for a specific experiment.
        
        Args:
            base_path: Base directory for all experiments (e.g., "/scratch/users/jane/ml_experiments")
            experiment_name: Name of this experiment (e.g., "resnet_hparam_search")
        """
        # Validate inputs immediately - fail fast
        assert base_path, "base_path cannot be empty"
        assert experiment_name, "experiment_name cannot be empty"
        assert "/" not in experiment_name, "experiment_name cannot contain '/'"
        
        # Ensure base_path exists
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        self.experiment_name = experiment_name
        self.experiment_path = self.base_path / experiment_name
        
        # Clear, predictable paths under experiment directory
        self.jobs_dir = self.experiment_path / "jobs"
        self.storage_dir = self.experiment_path / "storage"
        self.sync_queue_dir = self.experiment_path / "sync_queue"
        
        # Create directories
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.sync_queue_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"JobDB initialized for experiment '{experiment_name}' at {self.experiment_path}")
    
    def create_job(self, config: Dict[str, Any], priority: int = 100) -> str:
        """Create a new job with given configuration.
        
        Args:
            config: Job configuration dictionary
            priority: Job priority (0-1000, higher = more urgent)
            
        Returns:
            job_id: Unique identifier for the created job
        """
        # Validate priority
        assert 0 <= priority <= 1000, f"Priority must be 0-1000, got {priority}"
        
        # Validate _target_ exists
        assert "_target_" in config, "Config must include _target_ field"
        
        # Optionally validate target is importable
        target = config["_target_"]
        module_path, func_name = target.rsplit('.', 1)
        try:
            import importlib
            importlib.import_module(module_path)
        except ImportError as e:
            assert False, f"Cannot import target module {module_path}: {e}"
        
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "experiment_name": self.experiment_name,
            "config": config,
            "priority": priority,
            "status": "queued",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        
        # Write to filesystem
        job_path = self.jobs_dir / f"{job_id}.json"
        with open(job_path, 'w') as f:
            json.dump(job_data, f, indent=2)
        
        logger.info(f"Created job {job_id} with priority {priority}")
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job data by ID.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Job data dictionary or None if not found
        """
        job_path = self.jobs_dir / f"{job_id}.json"
        if not job_path.exists():
            return None
            
        with open(job_path, 'r') as f:
            return json.load(f)
    
    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update job fields.
        
        Args:
            job_id: Job identifier
            updates: Fields to update
            
        Returns:
            True if successful, False if job not found
        """
        job = self.get_job(job_id)
        if job is None:
            return False
        
        # Apply updates
        job.update(updates)
        job["updated_at"] = datetime.now(UTC).isoformat()
        
        # Write back
        job_path = self.jobs_dir / f"{job_id}.json"
        with open(job_path, 'w') as f:
            json.dump(job, f, indent=2)
            
        return True
    
    def claim_next_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Atomically claim the highest priority queued job.
        
        Uses file locking to ensure only one worker can claim a job.
        
        Args:
            worker_id: Identifier of the worker claiming the job
            
        Returns:
            Claimed job data or None if no jobs available
        """
        import fcntl
        import time
        import random
        
        # Get all queued jobs
        queued_jobs = []
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file, 'r') as f:
                    job = json.load(f)
                    if job["status"] == "queued":
                        queued_jobs.append((job_file, job))
            except:
                continue  # Skip files being written
        
        if not queued_jobs:
            return None
        
        # Sort by priority (descending) then by created_at (ascending)
        queued_jobs.sort(key=lambda x: (-x[1]["priority"], x[1]["created_at"]))
        
        # Try to claim jobs in order
        for job_file, job in queued_jobs:
            # Open file with exclusive lock
            try:
                with open(job_file, 'r+') as f:
                    # Multiple workers can call this simultaneously - fcntl ensures only one wins
                    # Try to get exclusive lock (non-blocking)
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    
                    # Re-read under lock to ensure status hasn't changed
                    current_data = json.load(f)
                    
                    if current_data["status"] != "queued":
                        # Another worker claimed it
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        continue
                    
                    # Claim the job
                    current_data["status"] = "running"
                    current_data["assigned_worker"] = worker_id
                    current_data["started_at"] = datetime.now(UTC).isoformat()
                    
                    # Write updated data
                    f.seek(0)
                    json.dump(current_data, f, indent=2)
                    f.truncate()
                    
                    # Lock is released when file is closed, even if worker crashes
                    # Release lock
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    
                    logger.info(f"Worker {worker_id} claimed job {job['id']}")
                    return current_data
                    
            except BlockingIOError:
                # Failed lock attempts automatically try the next job in priority order
                # Another worker has the lock, try next job
                continue
            except Exception as e:
                logger.debug(f"Failed to claim job {job['id']}: {e}")
                continue
        
        # No jobs could be claimed
        return None
    
    def list_jobs(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all jobs, optionally filtered by status.
        
        Args:
            status: Optional status filter
            
        Returns:
            List of job dictionaries
        """
        jobs = []
        for job_file in self.jobs_dir.glob("*.json"):
            with open(job_file, 'r') as f:
                job = json.load(f)
                if status is None or job["status"] == status:
                    jobs.append(job)
        
        # Sort by created_at for consistent ordering
        jobs.sort(key=lambda j: j["created_at"])
        return jobs
    
    def get_storage_path(self, job_id: str) -> Path:
        """Get storage directory path for a job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            Path to job's storage directory
        """
        path = self.storage_dir / f"run_{job_id}"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    def queue_for_sync(self, local_path: Path, remote_path: str) -> None:
        """Queue a file for background sync to Supabase.
        
        Args:
            local_path: Path to local file
            remote_path: Destination path in Supabase storage
        """
        sync_item = {
            "local_path": str(local_path),
            "remote_path": remote_path,
            "queued_at": datetime.now(UTC).isoformat(),
            "status": "pending"
        }
        
        # Use timestamp + uuid to ensure uniqueness
        sync_id = f"{datetime.now(UTC).timestamp()}_{uuid.uuid4().hex[:8]}"
        sync_path = self.sync_queue_dir / f"{sync_id}.json"
        
        with open(sync_path, 'w') as f:
            json.dump(sync_item, f, indent=2)
```

This implementation handles multiple workers correctly. The fcntl.LOCK_EX ensures atomic job claiming. No additional concurrency code is needed.

## Step 3b: Add Operational Methods to JobDB

Add these methods to the JobDB class for operational management:

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

## Step 4: Install Dependencies

Before testing, install required dependencies using uv:

```bash
# Add core dependencies
uv add pydantic

# Add development dependencies
uv add --dev pytest pytest-cov pytest-xdist
```

## Step 4.5: Create Init Command Support

Update JobDB to support validation and add init command to create proper structure.

### Update JobDB Constructor

Add validation parameter to `src/dr_exp/core/job_db.py`:

```python
def __init__(self, base_path: str, experiment_name: str, validate: bool = True):
    """Initialize JobDB.
    
    Args:
        base_path: Base directory for experiments
        experiment_name: Name of this experiment
        validate: Whether to validate directory structure exists
    """
    self.base_path = Path(base_path)
    self.experiment_name = experiment_name
    self.experiment_path = self.base_path / experiment_name
    
    # Define expected directories
    self.jobs_dir = self.experiment_path / "jobs"
    self.storage_dir = self.experiment_path / "storage"  
    self.sync_queue_dir = self.experiment_path / "sync_queue"
    self.logs_dir = self.experiment_path / "logs"
    self.control_dir = self.experiment_path / "control"
    
    if validate:
        # Check that experiment is initialized
        required_dirs = [
            self.jobs_dir,
            self.storage_dir,
            self.sync_queue_dir,
            self.logs_dir,
            self.control_dir
        ]
        
        missing = [d for d in required_dirs if not d.exists()]
        if missing:
            missing_names = [d.name for d in missing]
            raise RuntimeError(
                f"Experiment not initialized. Missing directories: {missing_names}\n"
                f"Run: dr_exp --base-path {base_path} --experiment {experiment_name} init"
            )
    else:
        # Create directories if they don't exist (for init command)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.sync_queue_dir.mkdir(parents=True, exist_ok=True)
```

This ensures experiments are properly initialized before use. The init command (implemented in Phase 2) will create these directories with proper structure.

## Step 5: Create Pytest Tests

Create proper test file at `tests/test_job_db.py`:

```python
#!/usr/bin/env python3
"""Test the new simple JobDB implementation."""

import os
import tempfile
import shutil
from pathlib import Path
from dr_exp.core.job_db import JobDB


def test_job_db():
    """Test basic JobDB operations."""
    print("Testing JobDB implementation...")
    
    # Create temporary scratch directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize JobDB
        base_path = os.path.join(tmpdir, "users", "testuser", "experiments")
        db = JobDB(base_path=base_path, experiment_name="test_experiment")
        print(f"✓ Created JobDB at {db.experiment_path}")
        
        # Create a job with _target_
        job_id = db.create_job({
            "_target_": "dr_exp.trainers.test_trainer.train_test",
            "model": "resnet18", 
            "lr": 0.01
        }, priority=500)
        print(f"✓ Created job {job_id}")
        
        # Get the job
        job = db.get_job(job_id)
        assert job is not None
        assert job["config"]["model"] == "resnet18"
        assert job["priority"] == 500
        assert job["status"] == "queued"
        print("✓ Retrieved job successfully")
        
        # Claim the job
        claimed_job = db.claim_next_job("test_worker")
        assert claimed_job is not None
        assert claimed_job["id"] == job_id
        assert claimed_job["status"] == "running"
        assert claimed_job["assigned_worker"] == "test_worker"
        print("✓ Claimed job successfully")
        
        # Update job
        success = db.update_job(job_id, {"status": "completed"})
        assert success
        updated_job = db.get_job(job_id)
        assert updated_job["status"] == "completed"
        print("✓ Updated job successfully")
        
        # Test storage paths
        storage_path = db.get_storage_path(job_id)
        assert storage_path.exists()
        print(f"✓ Created storage path {storage_path}")
        
        # Test sync queue
        test_file = storage_path / "test.txt"
        test_file.write_text("test content")
        db.queue_for_sync(test_file, f"experiments/{db.experiment_name}/runs/{job_id}/test.txt")
        
        sync_files = list(db.sync_queue_dir.glob("*.json"))
        assert len(sync_files) == 1
        print("✓ Queued file for sync")
        
    print("\n✅ All tests passed!")


def test_operational_features():
    """Test operational JobDB methods."""
    print("\nTesting operational features...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "operational_test")
        db = JobDB(base_path=base_path, experiment_name="test_ops")
        
        # Create test jobs
        job1 = db.create_job({
            "_target_": "dr_exp.trainers.test_trainer.train_test",
            "name": "job1"
        }, priority=100)
        
        job2 = db.create_job({
            "_target_": "dr_exp.trainers.test_trainer.train_test",
            "name": "job2"
        }, priority=200)
        
        # Test priority boost
        updated = db.boost_priority([job1, job2], 900)
        assert updated == 2
        assert db.get_job(job1)["priority"] == 900
        print("✓ Priority boost working")
        
        # Simulate running job with stale heartbeat
        import time
        from datetime import datetime, UTC, timedelta
        
        # Claim job1
        claimed = db.claim_next_job("worker1")
        assert claimed["id"] == job1  # Should be job1 (both have same priority, job1 created first)
        
        # Set old heartbeat
        old_heartbeat = (datetime.now(UTC) - timedelta(seconds=400)).isoformat()
        db.update_job(job1, {"heartbeat": old_heartbeat})
        
        # Recover stale jobs
        recovered = db.recover_stale_jobs(heartbeat_timeout=300)
        assert len(recovered) == 1
        assert recovered[0] == job1
        assert db.get_job(job1)["status"] == "queued"
        print("✓ Stale job recovery working")
        
        # Test kill job
        # First claim it again
        claimed = db.claim_next_job("worker2")
        assert claimed["id"] == job1
        
        # Kill it
        killed = db.mark_job_failed(job1, "Test kill")
        assert killed == True
        assert db.get_job(job1)["status"] == "failed"
        assert "Killed: Test kill" in db.get_job(job1)["error"]
        print("✓ Job kill working")
        
    print("✅ All operational tests passed!")


def test_concurrent_claims():
    """Test that multiple workers can't claim the same job."""
    import concurrent.futures
    import threading
    
    print("\nTesting concurrent job claims...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "concurrent_test")
        db = JobDB(base_path=base_path, experiment_name="test_concurrent")
        
        # Create multiple jobs
        job_ids = []
        for i in range(10):
            job_id = db.create_job({
                "_target_": "dr_exp.trainers.test_trainer.train_test",
                "task": i
            }, priority=100)
            job_ids.append(job_id)
        
        print(f"Created {len(job_ids)} jobs")
        
        # Track which worker claimed which job
        claimed_jobs = {}
        claim_lock = threading.Lock()
        
        def worker_claim_jobs(worker_id):
            """Worker function that claims jobs."""
            local_claims = []
            while True:
                job = db.claim_next_job(f"worker_{worker_id}")
                if job is None:
                    break
                local_claims.append(job["id"])
                # Simulate some work
                time.sleep(0.01)
            
            with claim_lock:
                claimed_jobs[worker_id] = local_claims
            return len(local_claims)
        
        # Run 6 workers concurrently (simulating 3 GPUs × 2 workers each)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(worker_claim_jobs, i) for i in range(6)]
            results = [f.result() for f in futures]
        
        # Verify results
        all_claimed = []
        for worker_id, jobs in claimed_jobs.items():
            print(f"Worker {worker_id} claimed {len(jobs)} jobs")
            all_claimed.extend(jobs)
        
        # Check that each job was claimed exactly once
        assert len(all_claimed) == len(job_ids), "Not all jobs were claimed"
        assert len(set(all_claimed)) == len(job_ids), "Some jobs were claimed multiple times!"
        
        print("✓ Each job was claimed exactly once")
        print("✓ Concurrent access is working correctly")


if __name__ == "__main__":
    test_job_db()
    test_operational_features()
    test_concurrent_claims()
```

## Step 6: Run Tests with Quality Gates

### Validation Gate
Run these commands and fix ALL issues before proceeding:

```bash
# 1. Code quality check
ckdr
# Expected: "All checks passed!"
# If fails: Fix the code, not the rules

# 2. Run all tests
pt
# Expected: All tests pass, no skips
# If fails: Fix implementation, not tests

# 3. Verify JobDB tests specifically
pt tests/test_job_db.py -v
# Expected: Detailed passing output
```

⚠️ **CRITICAL**: If any check fails:
1. Read the FULL error message
2. Understand what the test/check expects
3. Fix YOUR CODE to meet expectations
4. Do NOT modify tests/rules to pass

Common fixes:
- Type errors → Add proper type hints
- Lint errors → Refactor code structure
- Test failures → Implementation doesn't match spec

## Validation Checklist

Before proceeding to Phase 2, ensure:

- [ ] All specified files and directories have been deleted
- [ ] New `JobDB` class is implemented in `src/dr_exp/core/job_db.py`
- [ ] **ALL quality checks pass**: `ckdr` shows "All checks passed!"
- [ ] **ALL tests pass**: `pt` shows all tests passing with no skips
- [ ] Test coverage is adequate: `pt --cov=dr_exp.core.job_db`
- [ ] No references to old classes remain:
  ```bash
  # This should return no results:
  grep -r "LocalJobDB\|SupabaseJobDB\|BaseJobDB" src/
  grep -r "JobDBConfig\|get_job_db_client" src/
  ```

## Common Mistakes to Avoid

1. **DO NOT** try to maintain backwards compatibility
2. **DO NOT** add configuration options for different modes
3. **DO NOT** create abstract base classes or interfaces
4. **DO NOT** add complex error handling - use assertions for fail-fast
5. **DO NOT** implement Supabase syncing yet - that comes in Phase 3

### ⚠️ Test Anti-Patterns to AVOID

❌ **DO NOT modify tests to pass:**
```python
# WRONG - Don't change expected values
assert job["priority"] == 500  # Changed from 900 to match bug
```

❌ **DO NOT skip failing tests:**
```python
# WRONG - Fix the implementation instead
@pytest.mark.skip("This test is failing")
def test_priority_ordering():
```

❌ **DO NOT catch exceptions to hide failures:**
```python
# WRONG - Let tests fail clearly
try:
    result = db.claim_next_job("worker")
except Exception:
    result = None  # Hiding the real issue
```

✅ **DO fix the implementation to match test expectations**

## DO NOT IMPLEMENT

DO NOT add:
- Database locks or transactions
- Redis/distributed locks  
- Worker registration systems
- Job reservation mechanisms
The fcntl locking is sufficient for all use cases.

## Next Phase

Once all tests pass and the checklist is complete, proceed to Phase 2: Worker Integration.
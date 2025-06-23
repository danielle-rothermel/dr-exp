# Fix Priority Ordering Under Concurrency

## Objective
Enhance file locking in claim_next_job to improve priority ordering when multiple workers compete.

## Files to Modify
- `/src/dr_exp/core/job_db.py` - Enhance claim_next_job locking mechanism

## Implementation

### Step 1: Update claim_next_job in job_db.py

Find the claim_next_job method (around line 200) and replace it:

```python
def claim_next_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
    """Claim the highest priority unclaimed job with enhanced locking."""
    import fcntl
    import time
    import random
    
    # Use a lock file to ensure atomic priority scanning
    lock_file = self.jobs_dir / ".claim_lock"
    lock_file.touch(exist_ok=True)
    
    with open(lock_file, "w") as lock_fd:
        # Exclusive lock with small random backoff to reduce contention
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if attempt < max_attempts - 1:
                    time.sleep(0.001 * random.uniform(0.5, 1.5))  # 0.5-1.5ms
                else:
                    return None
        
        try:
            # Find highest priority unclaimed job
            best_job = None
            best_priority = -1
            
            for job_file in self.jobs_dir.glob("*.json"):
                if job_file.name == ".claim_lock":
                    continue
                    
                try:
                    with open(job_file, "r") as f:
                        job = json.load(f)
                    
                    if (job["status"] == "queued" and 
                        job["priority"] > best_priority):
                        best_job = job
                        best_priority = job["priority"]
                        
                except (json.JSONDecodeError, KeyError):
                    continue
            
            if not best_job:
                return None
            
            # Claim the best job
            job_file = self.jobs_dir / f"{best_job['id']}.json"
            
            # Re-read and update atomically
            with open(job_file, "r") as f:
                job = json.load(f)
            
            # Double-check status
            if job["status"] != "queued":
                return None
            
            # Update job
            job["status"] = "claimed"
            job["worker_id"] = worker_id
            job["claimed_at"] = datetime.now(UTC).isoformat()
            job["updated_at"] = datetime.now(UTC).isoformat()
            
            # Write atomically
            temp_file = job_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(job, f, indent=2)
            temp_file.replace(job_file)
            
            return job
            
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
```

### Step 2: Add imports at top if missing

Ensure these imports are present:
```python
import fcntl
import time
import random
```

## Test

Create test file `/tests/implementation/test_priority_concurrency_fix.py`:

```python
import pytest
import threading
import time
from pathlib import Path
from dr_exp.core.job_db import JobDB

def test_concurrent_priority_order(tmp_path):
    # Create JobDB
    job_db = JobDB(
        base_path=str(tmp_path),
        experiment_name="test_exp",
        validate=False
    )
    
    # Create jobs with different priorities
    job_ids = []
    priorities = [100, 500, 300, 700, 200, 600, 400, 800]
    for priority in priorities:
        job_id = job_db.create_job(
            config={"_target_": "test.func", "priority": priority},
            priority=priority
        )
        job_ids.append((job_id, priority))
    
    # Track claim order
    claimed_priorities = []
    lock = threading.Lock()
    
    def worker_claim(worker_id):
        for _ in range(2):  # Each worker claims 2 jobs
            job = job_db.claim_next_job(worker_id)
            if job:
                with lock:
                    claimed_priorities.append(job["priority"])
            time.sleep(0.001)  # Small delay between claims
    
    # Start 4 concurrent workers
    threads = []
    for i in range(4):
        t = threading.Thread(target=worker_claim, args=(f"worker_{i}",))
        threads.append(t)
        t.start()
    
    # Wait for completion
    for t in threads:
        t.join()
    
    # Verify all jobs claimed
    assert len(claimed_priorities) == 8
    
    # Check priority ordering (should be mostly descending)
    # Allow some out-of-order due to concurrency, but general trend should hold
    inversions = 0
    for i in range(1, len(claimed_priorities)):
        if claimed_priorities[i] > claimed_priorities[i-1]:
            inversions += 1
    
    # Should have few inversions (< 25% of claims)
    assert inversions < len(claimed_priorities) * 0.25

def test_lock_contention_handling(tmp_path):
    job_db = JobDB(
        base_path=str(tmp_path),
        experiment_name="test_exp",
        validate=False
    )
    
    # Create single job
    job_db.create_job(
        config={"_target_": "test.func"},
        priority=100
    )
    
    # Try to claim from multiple threads simultaneously
    results = []
    lock = threading.Lock()
    
    def try_claim(worker_id):
        job = job_db.claim_next_job(worker_id)
        with lock:
            results.append(job)
    
    threads = []
    for i in range(10):
        t = threading.Thread(target=try_claim, args=(f"worker_{i}",))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    # Only one should succeed
    successful_claims = [r for r in results if r is not None]
    assert len(successful_claims) == 1
    
    # Others should get None
    assert results.count(None) == 9
```

## Verification Steps

1. Run tests: `pt tests/implementation/test_priority_concurrency_fix.py -v`
2. Test with real concurrent workers:
   ```bash
   # Submit jobs with various priorities
   for p in 100 200 300 400 500; do
     dr_exp --base-path ./test --experiment concurrent submit --config-name test --priority $p
   done
   
   # Run multiple workers simultaneously
   for i in 1 2 3; do
     dr_exp --base-path ./test --experiment concurrent worker --worker-id w$i &
   done
   ```
3. Check that higher priority jobs are generally claimed first

## Common Mistakes to Avoid
- DO NOT use complex distributed locking
- DO NOT guarantee perfect ordering - best effort is acceptable
- DO NOT add long delays that slow down job claiming
- DO NOT modify job structure or add new fields
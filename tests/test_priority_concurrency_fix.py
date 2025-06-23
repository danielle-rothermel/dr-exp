import threading
import time
from dr_exp.core.job_db import JobDB


def test_concurrent_priority_order(tmp_path):
    # Create JobDB
    job_db = JobDB(base_path=str(tmp_path), experiment_name="test_exp", validate=False)

    # Create jobs with different priorities
    job_ids = []
    priorities = [100, 500, 300, 700, 200, 600, 400, 800]
    for priority in priorities:
        job_id = job_db.create_job(
            config={"_target_": "test.func", "priority": priority}, priority=priority
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
        if claimed_priorities[i] > claimed_priorities[i - 1]:
            inversions += 1

    # Should have few inversions (< 25% of claims)
    assert inversions < len(claimed_priorities) * 0.25


def test_lock_contention_handling(tmp_path):
    job_db = JobDB(base_path=str(tmp_path), experiment_name="test_exp", validate=False)

    # Create single job
    job_db.create_job(config={"_target_": "test.func"}, priority=100)

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

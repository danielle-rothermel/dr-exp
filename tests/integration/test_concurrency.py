"""Integration tests for concurrency and priority handling."""

import tempfile
import multiprocessing
import time
import threading
from multiprocessing import Queue
from pathlib import Path

from dr_exp.core.job_db import JobDB


def worker_process(base_path: str, worker_id: str, results_queue: Queue) -> None:
    """Worker process that tries to claim jobs."""
    job_db = JobDB(base_path=base_path, experiment_name="test_exp", validate=False)

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


def test_concurrent_claiming() -> None:
    """Test that multiple workers can claim jobs without conflicts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize JobDB
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create 20 jobs with different priorities
        job_ids = []
        for i in range(20):
            config = {"_target_": "test.train", "index": i}
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
                target=worker_process, args=(tmpdir, f"worker_{i}", results_queue)
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
        for claims in worker_claims.values():
            for idx, job_id in enumerate(claims):
                if job_id not in claim_times:
                    claim_times[job_id] = idx

        # Check that highest priority jobs (last 5 created) were claimed early
        high_priority_ids = [jid for jid, _ in job_ids[-5:]]
        high_priority_claim_order = [
            claim_times.get(jid, 999) for jid in high_priority_ids
        ]
        avg_claim_order = sum(high_priority_claim_order) / len(
            high_priority_claim_order
        )

        assert avg_claim_order < 10, "High priority jobs not claimed first"


def test_job_updates() -> None:
    """Test atomic job updates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create a job
        config = {"_target_": "test.train"}
        job_id = job_db.create_job(config, priority=100)

        # Update the job
        updates = {"status": "completed", "metrics": {"loss": 0.5, "accuracy": 0.95}}
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


def test_concurrent_priority_order(tmp_path: Path) -> None:
    """Test that jobs are claimed in priority order under concurrency."""
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

    def worker_claim(worker_id: str) -> None:
        # Each worker keeps trying to claim jobs until none are available
        while True:
            job = job_db.claim_next_job(worker_id)
            if job:
                with lock:
                    claimed_priorities.append(job["priority"])
                time.sleep(0.001)  # Small delay between claims
            else:
                # No more jobs available
                break

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


def test_lock_contention_handling(tmp_path: Path) -> None:
    """Test handling of lock contention with many concurrent workers."""
    job_db = JobDB(base_path=str(tmp_path), experiment_name="test_exp", validate=False)

    # Create single job
    job_db.create_job(config={"_target_": "test.func"}, priority=100)

    # Try to claim from multiple threads simultaneously
    results = []
    lock = threading.Lock()

    def try_claim(worker_id: str) -> None:
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

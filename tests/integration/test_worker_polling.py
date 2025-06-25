"""Integration tests for worker polling behavior."""

import tempfile
import threading
import time

from dr_exp.core.job_db import JobDB
from dr_exp.worker.base import Worker
from tests.utils.polling_helpers import (
    run_infinite_polling_test,
    run_max_jobs_termination_test,
)


def test_worker_infinite_polling_no_jobs() -> None:
    """Test that worker polls indefinitely when no jobs and no max_jobs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="polling_test", validate=False)

        # Create worker with no jobs available
        worker = Worker(
            job_db=job_db,
            worker_id="polling_worker",
            sync_enabled=False,  # Disable sync for simpler testing
        )

        # Test infinite polling behavior (worker polls every 10 seconds)
        result = run_infinite_polling_test(
            worker, timeout_seconds=1.0, no_job_threshold=1
        )

        # Verify polling behavior
        assert result.worker_started, "Worker should have started"
        assert not result.worker_finished, (
            "Worker should not finish with infinite polling"
        )
        assert result.no_job_count >= 1, (
            f"Expected at least 1 no_job poll, got {result.no_job_count}"
        )
        assert result.exception is None, (
            f"Worker should not raise exception: {result.exception}"
        )


def test_worker_max_jobs_termination() -> None:
    """Test that worker terminates after processing max_jobs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(
            base_path=tmpdir, experiment_name="max_jobs_test", validate=False
        )

        # Create 3 jobs
        for i in range(3):
            config = {
                "_target_": "dr_exp.trainers.test_trainer.train",
                "epochs": 1,
                "index": i,
            }
            job_db.create_job(config, priority=100 + i)

        # Create worker
        worker = Worker(
            job_db=job_db,
            worker_id="terminating_worker",
            sync_enabled=False,
        )

        # Test max_jobs termination
        result = run_max_jobs_termination_test(worker, max_jobs=2)

        # Verify termination behavior
        assert result.worker_started, "Worker should have started"
        assert result.worker_finished, "Worker should finish when max_jobs reached"
        assert result.stats is not None, "Worker should return stats"
        assert result.stats["total"] == 2, (
            f"Expected 2 jobs processed, got {result.stats['total']}"
        )
        assert result.stats["completed"] == 2, (
            f"Expected 2 completed, got {result.stats['completed']}"
        )
        assert result.exception is None, (
            f"Worker should not raise exception: {result.exception}"
        )


def test_worker_mixed_polling_and_jobs() -> None:
    """Test worker that polls, then processes jobs when they arrive."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="mixed_test", validate=False)

        # Create worker with no initial jobs
        worker = Worker(
            job_db=job_db,
            worker_id="mixed_worker",
            sync_enabled=False,
        )

        # Add jobs after worker starts polling
        def add_jobs_later() -> None:
            time.sleep(0.2)  # Short delay
            for i in range(2):
                config = {
                    "_target_": "dr_exp.trainers.test_trainer.train",
                    "epochs": 1,
                    "index": i,
                }
                job_db.create_job(config, priority=100 + i)

        # Start job adder in background
        job_thread = threading.Thread(target=add_jobs_later, daemon=True)
        job_thread.start()

        # Run worker with max_jobs to terminate after processing the 2 jobs
        stats = worker.run(max_jobs=2)

        # Verify behavior
        assert stats["total"] == 2, f"Expected 2 jobs processed, got {stats['total']}"
        assert stats["completed"] == 2, (
            f"Expected 2 completed, got {stats['completed']}"
        )


def test_worker_polling_with_sync_enabled() -> None:
    """Test infinite polling behavior with sync threads enabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(
            base_path=tmpdir, experiment_name="sync_polling_test", validate=False
        )

        # Create worker with sync enabled but no Supabase
        worker = Worker(
            job_db=job_db,
            worker_id="sync_polling_worker",
            sync_enabled=True,  # This should disable itself due to no Supabase
            sync_interval=0.2,
            heartbeat_interval=0.2,
        )

        # Test infinite polling behavior (shorter test since sync is disabled)
        result = run_infinite_polling_test(
            worker, timeout_seconds=0.5, no_job_threshold=1
        )

        # Verify polling behavior with threads
        assert result.worker_started, "Worker should have started"
        assert not result.worker_finished, (
            "Worker should not finish with infinite polling"
        )
        assert result.no_job_count >= 1, (
            f"Expected at least 1 no_job poll, got {result.no_job_count}"
        )
        assert result.exception is None, (
            f"Worker should not raise exception: {result.exception}"
        )


def test_worker_thread_lifecycle_during_polling() -> None:
    """Test that background threads start and stop properly during polling."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="thread_test", validate=False)

        # Create one job to process
        config = {"_target_": "dr_exp.trainers.test_trainer.train", "epochs": 1}
        job_db.create_job(config)

        # Create worker with threads
        worker = Worker(
            job_db=job_db,
            worker_id="thread_lifecycle_worker",
            sync_enabled=False,
            heartbeat_interval=0.1,
        )

        # Get initial thread count
        initial_threads = threading.active_count()

        # Run worker for one job, then it should poll
        def run_worker() -> dict[str, int]:
            return worker.run(max_jobs=1)

        thread = threading.Thread(target=run_worker, daemon=True)
        thread.start()
        thread.join(timeout=2.0)

        # Give threads time to stop
        time.sleep(0.2)

        # Verify thread cleanup
        final_threads = threading.active_count()
        assert final_threads <= initial_threads + 1, (
            f"Thread leak detected: {final_threads} vs {initial_threads}"
        )

        # Verify threads were created and stopped
        assert worker.heartbeat_thread is not None, (
            "Heartbeat thread should have been created"
        )
        assert not worker.heartbeat_thread.is_alive(), (
            "Heartbeat thread should be stopped"
        )


def test_worker_shutdown_signal() -> None:
    """Test that worker responds to shutdown signals in background threads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(
            base_path=tmpdir, experiment_name="shutdown_test", validate=False
        )

        # Create worker with no jobs
        worker = Worker(
            job_db=job_db,
            worker_id="shutdown_worker",
            sync_enabled=False,
        )

        # Test that should_stop event works
        assert not worker.should_stop.is_set(), "should_stop should start as False"

        # Start background threads manually
        worker.start_background_threads()

        # Verify threads started
        assert worker.heartbeat_thread is not None, "Heartbeat thread should start"
        assert worker.heartbeat_thread.is_alive(), "Heartbeat thread should be alive"

        # Signal shutdown
        worker.should_stop.set()
        assert worker.should_stop.is_set(), "should_stop should be set"

        # Stop background threads
        worker.stop_background_threads()

        # Verify threads stopped
        assert not worker.heartbeat_thread.is_alive(), "Heartbeat thread should stop"

"""Test worker with threading integration."""

import tempfile
import time
import threading
from pathlib import Path

from src.dr_exp.core.job_db import JobDB
from src.dr_exp.worker.base import Worker
from src.dr_exp.sync.queue import SyncItem


def test_worker_with_threads():
    """Test worker with background threads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize JobDB
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create a test job
        config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 3}
        job_id = job_db.create_job(config, priority=100)

        # Track sync calls
        synced_items = []

        def mock_sync(item: SyncItem):
            synced_items.append(item)
            print(f"Mock sync: {item.file_type} - {Path(item.file_path).name}")

        # Create worker
        worker = Worker(
            job_db=job_db,
            worker_id="threaded_worker",
            sync_interval=1,  # Fast for testing
            heartbeat_interval=1,
        )
        worker.sync_fn = mock_sync

        # Run the job
        stats = worker.run(max_jobs=1)

        assert stats["completed"] == 1

        # Verify heartbeat was sent
        job = job_db.get_job(job_id)
        assert "last_heartbeat" in job

        # Verify artifacts were queued
        sync_stats = worker.sync_queue.get_stats()
        assert sync_stats["total"] >= 2  # At least metrics and model

        # Manually process sync queue to verify integration
        if worker.sync_fn:
            results = worker.sync_queue.process_queue(worker.sync_fn, batch_size=10)
            assert results["success"] > 0 or results["skipped"] > 0

        # Verify some items were synced
        assert len(synced_items) > 0

        # Check artifact types
        file_types = {item.file_type for item in synced_items}
        assert "metrics" in file_types or "model" in file_types


def test_worker_no_sync():
    """Test worker with sync disabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create a job
        config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 2}
        job_db.create_job(config)

        # Create worker with sync disabled
        worker = Worker(job_db=job_db, worker_id="no_sync_worker", sync_enabled=False)

        # Run the job
        stats = worker.run()

        assert stats["completed"] == 1

        # Verify no sync thread started
        assert worker.sync_thread is None

        # But heartbeat thread should still run
        assert worker.heartbeat_thread is not None


def test_worker_thread_cleanup():
    """Test that threads are properly cleaned up."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create multiple jobs
        for i in range(3):
            config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 1}
            job_db.create_job(config)

        # Create worker
        worker = Worker(
            job_db=job_db,
            worker_id="cleanup_worker",
            sync_interval=0.5,
            heartbeat_interval=0.5,
        )

        # Get initial thread count
        initial_threads = threading.active_count()

        # Run worker
        stats = worker.run()

        assert stats["completed"] == 3

        # Give threads time to stop
        time.sleep(1)

        # Verify threads stopped
        assert not worker.sync_thread.is_alive()
        assert not worker.heartbeat_thread.is_alive()

        # Thread count should be back to initial (or close)
        final_threads = threading.active_count()
        assert final_threads <= initial_threads + 1  # Allow small variance


def test_worker_heartbeat_during_execution():
    """Test that heartbeats are sent during job execution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create a slow job
        config = {
            "_target_": "src.dr_exp.trainers.test_trainer.train",
            "epochs": 50,  # More epochs = longer execution
        }
        job_db.create_job(config)

        # Track heartbeats
        heartbeat_times = []
        original_heartbeat = job_db.heartbeat

        def tracking_heartbeat(job_id_arg):
            heartbeat_times.append(time.time())
            return original_heartbeat(job_id_arg)

        job_db.heartbeat = tracking_heartbeat

        # Create worker with fast heartbeat
        worker = Worker(
            job_db=job_db,
            worker_id="heartbeat_worker",
            heartbeat_interval=0.1,  # 100ms
        )

        # Run the job
        stats = worker.run()

        assert stats["completed"] == 1

        # Should have sent multiple heartbeats
        assert len(heartbeat_times) >= 2

        # Verify heartbeat spacing
        if len(heartbeat_times) > 1:
            intervals = []
            for i in range(1, len(heartbeat_times)):
                interval = heartbeat_times[i] - heartbeat_times[i - 1]
                intervals.append(interval)

            avg_interval = sum(intervals) / len(intervals)
            assert 0.05 < avg_interval < 0.2  # Close to 0.1s


def test_worker_sync_queue_integration():
    """Test that sync queue is properly integrated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create a job
        config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 5}
        job_db.create_job(config)

        # Track sync processing
        processed_files = []

        def tracking_sync(item: SyncItem):
            processed_files.append(Path(item.file_path).name)
            # Simulate successful upload
            time.sleep(0.01)

        # Create worker
        worker = Worker(job_db=job_db, worker_id="sync_test_worker", sync_interval=0.5)
        worker.sync_fn = tracking_sync

        # Run the job
        stats = worker.run()

        assert stats["completed"] == 1

        # Manually process sync queue to verify integration
        if worker.sync_fn:
            results = worker.sync_queue.process_queue(worker.sync_fn, batch_size=10)
            assert results["success"] > 0 or results["skipped"] > 0

        # Verify files were processed
        assert len(processed_files) > 0

        # Check expected files
        assert any("metrics" in f for f in processed_files)
        assert any("model" in f for f in processed_files)

        # Verify sync queue stats
        sync_stats = worker.sync_queue.get_stats()
        assert sync_stats["completed"] > 0


def test_worker_error_artifacts():
    """Test that errors are saved and queued for sync."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create a job that will fail
        config = {
            "_target_": "src.dr_exp.trainers.test_trainer.train",
            "epochs": 5,
            "fail_rate": 1.0,  # Always fail
        }
        job_id = job_db.create_job(config)

        # Create worker
        worker = Worker(job_db=job_db, worker_id="error_worker")

        # Run the job
        stats = worker.run()

        assert stats["failed"] == 1

        # Verify error file was created
        storage_path = job_db.get_storage_path(job_id)
        error_file = storage_path / "error.txt"
        assert error_file.exists()

        # Verify error content
        error_content = error_file.read_text()
        assert "RuntimeError: Simulated training failure" in error_content
        assert "Traceback" in error_content

        # Verify error file is in sync queue
        sync_stats = worker.sync_queue.get_stats()
        assert sync_stats["pending"] >= 1

        # Check for error file in queue
        items = worker.sync_queue.get_pending_items()
        error_items = [i for i in items if i.file_type == "error"]
        assert len(error_items) >= 1

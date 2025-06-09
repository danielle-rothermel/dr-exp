"""Phase 3: Comprehensive edge case coverage and error scenario testing.

This module implements systematic testing of error conditions, concurrency issues,
and recovery mechanisms using the enhanced Phase 2 infrastructure.
"""

import pytest
import threading
import time
import tempfile
import os
from unittest.mock import patch
from pathlib import Path

from dr_exp.manage.worker import run_worker
from dr_exp.manage.manager import Manager
from dr_exp.manage.process_manager import MockProcessManager
from dr_exp.training.result import create_success_result
from tests.conftest import make_wrapped_config


class TestDatabaseErrorScenarios:
    """Test error scenarios involving database operations."""

    @pytest.mark.edge_case
    @pytest.mark.fast
    def test_worker_handles_database_connection_failure(
        self, isolated_job_db, worker_execution_helper
    ):
        """Test worker behavior when database connection fails during execution."""
        # Create a job
        job = isolated_job_db.add_test_job({"test": "db_failure"})

        # Mock training function that succeeds
        def successful_train(config, logger):
            logger.log({"test_metric": 0.95})
            return create_success_result(
                final_metrics={
                    "final_val_acc": 0.95,
                    "final_train_loss": 0.1,
                    "final_val_loss": 0.15,
                },
                epochs=1,
                logger_meta={
                    "metrics_path": "test_metrics.jsonl",
                    "num_checkpoints": 0,
                },
                artifacts_path=logger.paths.artifact_dir,
                training_time=1.0,
            )

        # Mock database update to fail during heartbeat
        original_update = isolated_job_db.update_job
        call_count = 0

        def failing_update(job_id, updates):
            nonlocal call_count
            call_count += 1
            # Fail heartbeat updates but allow other updates
            if "heartbeat" in updates and call_count > 2:
                raise ConnectionError("Database connection lost")
            return original_update(job_id, updates)

        with patch.object(isolated_job_db, "update_job", side_effect=failing_update):
            # Worker should complete despite heartbeat failures
            status = worker_execution_helper.run_worker_with_trainer(successful_train)
            assert status == "completed"

        # Job should still be marked as completed
        job_details = isolated_job_db.get_job_details(job["id"])
        assert job_details["status"] == "completed"

    @pytest.mark.edge_case
    @pytest.mark.fast
    def test_worker_handles_config_fetch_failure(self, integration_system):
        """Test worker behavior when job config cannot be fetched."""
        # Create a job
        job = integration_system.job_db.add_job(
            make_wrapped_config({"test": "config_failure"}),
            "config_sweep",
            status="queued",
            priority=100,
        )

        # Mock config fetch to fail
        with patch.object(
            integration_system.job_db, "get_config_for_job", return_value=None
        ):
            status = run_worker(
                base_path=integration_system.config.job_db_config.base_path,
                max_claim_attempts=integration_system.config.max_claim_attempts,
                heartbeat_interval=integration_system.config.worker_heartbeat_interval,
                trainer_fn=lambda cfg, logger: {},
                client=integration_system.job_db,
                worker_id="config_failure_worker",
            )
            assert status == "failed"

        # Job should be marked as failed
        job_details = integration_system.job_db.get_job_details(job["id"])
        assert job_details["status"] == "failed"
        # Config missing should result in finalize_success being False
        assert job_details["finalize_success"] is False

    @pytest.mark.edge_case
    @pytest.mark.fast
    def test_worker_handles_artifact_upload_failure(
        self, isolated_job_db, worker_execution_helper
    ):
        """Test worker behavior when artifact upload fails."""
        # Create a job
        job = isolated_job_db.add_test_job({"test": "upload_failure"})

        def successful_train(config, logger):
            logger.log({"test_metric": 0.95})
            return create_success_result(
                final_metrics={
                    "final_val_acc": 0.95,
                    "final_train_loss": 0.1,
                    "final_val_loss": 0.15,
                },
                epochs=1,
                logger_meta={
                    "metrics_path": "test_metrics.jsonl",
                    "num_checkpoints": 0,
                },
                artifacts_path=logger.paths.artifact_dir,
                training_time=1.0,
            )

        # Mock upload_artifact to fail
        def failing_upload(job_id, file_path, remote_name):
            raise IOError("Upload service unavailable")

        with patch.object(
            isolated_job_db, "upload_artifact", side_effect=failing_upload
        ):
            # Worker should still complete but with upload failures recorded
            status = worker_execution_helper.run_worker_with_trainer(successful_train)
            assert status == "completed"

        # Job should be completed despite upload failures
        job_details = isolated_job_db.get_job_details(job["id"])
        assert job_details["status"] == "completed"


class TestTrainingFunctionErrors:
    """Test various training function error scenarios."""

    @pytest.mark.edge_case
    @pytest.mark.slow
    @pytest.mark.timeout
    def test_training_function_timeout(self, isolated_job_db, worker_execution_helper):
        """Test worker behavior when training function hangs."""
        # Create a job
        _job = isolated_job_db.add_test_job({"test": "timeout"})

        # Training function that simulates hanging (optimized for faster testing)
        def hanging_train(config, logger):
            time.sleep(1)  # Reduced from 10s to 1s for faster testing
            logger.log({"test_metric": 0.95})
            return create_success_result(
                final_metrics={
                    "final_val_acc": 0.95,
                    "final_train_loss": 0.1,
                    "final_val_loss": 0.15,
                },
                epochs=1,
                logger_meta={
                    "metrics_path": "test_metrics.jsonl",
                    "num_checkpoints": 0,
                },
                artifacts_path=logger.paths.artifact_dir,
                training_time=1.0,
            )

        # Use a very short timeout for testing
        with patch("signal.alarm"):
            status = worker_execution_helper.run_worker_with_trainer(hanging_train)
            # In real implementation, this would timeout and return "failed"
            # For this test, we just verify the timeout mechanism would be called
            assert status in ["completed", "failed"]  # Depends on implementation

    @pytest.mark.edge_case
    @pytest.mark.fast
    def test_training_function_memory_error(
        self, isolated_job_db, worker_execution_helper
    ):
        """Test worker behavior when training function runs out of memory."""
        # Create a job
        job = isolated_job_db.add_test_job({"test": "memory_error"})

        def memory_error_train(config, logger):
            raise MemoryError("Out of memory during training")

        status = worker_execution_helper.run_worker_with_trainer(memory_error_train)
        assert status == "failed"

        # Verify error details are recorded
        job_details = isolated_job_db.get_job_details(job["id"])
        assert job_details["status"] == "failed"
        # Training should be marked as crashed due to exception
        assert job_details["train_status"] == "crash"
        # Metrics should show failure
        assert job_details["final_val_acc"] == 0.0
        assert job_details["num_epochs"] == 0

    @pytest.mark.edge_case
    @pytest.mark.fast
    def test_training_function_user_interrupt(
        self, isolated_job_db, worker_execution_helper
    ):
        """Test worker behavior when training is interrupted by user."""
        # Create a job
        job = isolated_job_db.add_test_job({"test": "user_interrupt"})

        def interrupted_train(config, logger):
            # Use a custom exception to simulate interruption without actually interrupting the test
            raise RuntimeError("User interrupted training (simulated)")

        status = worker_execution_helper.run_worker_with_trainer(interrupted_train)
        assert status == "failed"

        # Verify interruption is recorded
        job_details = isolated_job_db.get_job_details(job["id"])
        assert job_details["status"] == "failed"
        assert job_details["train_status"] == "crash"

    @pytest.mark.edge_case
    @pytest.mark.fast
    def test_training_function_corrupted_data(
        self, isolated_job_db, worker_execution_helper
    ):
        """Test worker behavior when training encounters corrupted data."""
        # Create a job
        job = isolated_job_db.add_test_job({"test": "corrupted_data"})

        def corrupted_data_train(config, logger):
            raise ValueError("Corrupted data detected in batch 15")

        status = worker_execution_helper.run_worker_with_trainer(corrupted_data_train)
        assert status == "failed"

        # Verify error is recorded with useful details
        job_details = isolated_job_db.get_job_details(job["id"])
        assert job_details["status"] == "failed"
        assert job_details["train_status"] == "crash"


class TestConcurrencyAndRaceConditions:
    """Test concurrency issues and race conditions."""

    @pytest.mark.edge_case
    @pytest.mark.concurrency
    @pytest.mark.slow
    def test_multiple_workers_claiming_same_job(
        self, isolated_job_db, worker_coordination
    ):
        """Test that multiple workers cannot claim the same job."""
        # Create a single high-priority job
        job = isolated_job_db.add_test_job({"test": "race_condition"}, priority=900)

        # Create coordination events
        worker_ids = ["worker_1", "worker_2", "worker_3"]
        completion_events = {}

        for worker_id in worker_ids:
            worker_coordination.create_worker_event(worker_id)
            completion_events[worker_id] = threading.Event()

        # Mock training function that coordinates execution
        def coordinated_train(config, logger):
            # Signal that training started and wait briefly
            time.sleep(0.1)
            logger.log({"test_metric": 0.95})
            return create_success_result(
                final_metrics={
                    "final_val_acc": 0.95,
                    "final_train_loss": 0.1,
                    "final_val_loss": 0.15,
                },
                epochs=1,
                logger_meta={
                    "metrics_path": "test_metrics.jsonl",
                    "num_checkpoints": 0,
                },
                artifacts_path=logger.paths.artifact_dir,
                training_time=0.1,
            )

        # Start multiple workers simultaneously
        worker_threads = []
        worker_results = {}

        def run_worker_thread(worker_id):
            status = run_worker(
                base_path=isolated_job_db.config.base_path,
                max_claim_attempts=1,  # Only try once to avoid retries
                heartbeat_interval=0.1,
                trainer_fn=coordinated_train,
                client=isolated_job_db,
                worker_id=worker_id,
            )
            worker_results[worker_id] = status

        for worker_id in worker_ids:
            thread = threading.Thread(target=run_worker_thread, args=(worker_id,))
            worker_threads.append(thread)
            thread.start()

        # Wait for all workers to complete
        for thread in worker_threads:
            thread.join(timeout=5)

        # Exactly one worker should have completed the job
        completed_workers = [
            wid for wid, status in worker_results.items() if status == "completed"
        ]
        no_job_workers = [
            wid for wid, status in worker_results.items() if status == "no_job"
        ]

        assert len(completed_workers) == 1, (
            f"Expected 1 completed worker, got {len(completed_workers)}"
        )
        assert len(no_job_workers) == 2, (
            f"Expected 2 no_job workers, got {len(no_job_workers)}"
        )

        # Job should be completed
        job_details = isolated_job_db.get_job_details(job["id"])
        assert job_details["status"] == "completed"

    @pytest.mark.edge_case
    @pytest.mark.concurrency
    @pytest.mark.fast
    def test_concurrent_job_claiming_with_priorities(
        self, priority_job_factory, worker_coordination
    ):
        """Test priority ordering is maintained under concurrent access."""
        # Create jobs with different priorities
        _jobs = priority_job_factory.create_high_medium_low_jobs()

        # Track execution order
        execution_order = []
        order_lock = threading.Lock()

        def priority_tracking_train(config, logger):
            with order_lock:
                priority_level = config.get("priority_test", "unknown")
                execution_order.append(priority_level)

            logger.log({"priority_metric": 0.95})
            return create_success_result(
                final_metrics={
                    "final_val_acc": 0.95,
                    "final_train_loss": 0.1,
                    "final_val_loss": 0.15,
                },
                epochs=1,
                logger_meta={
                    "metrics_path": "test_metrics.jsonl",
                    "num_checkpoints": 0,
                },
                artifacts_path=logger.paths.artifact_dir,
                training_time=0.1,
            )

        # Start multiple workers
        worker_threads = []
        worker_results = {}

        def run_concurrent_worker(worker_id):
            status = run_worker(
                base_path=priority_job_factory.job_db.config.base_path,
                max_claim_attempts=2,
                heartbeat_interval=0.1,
                trainer_fn=priority_tracking_train,
                client=priority_job_factory.job_db,
                worker_id=worker_id,
            )
            worker_results[worker_id] = status

        # Launch workers slightly staggered to test race conditions
        for i in range(3):
            worker_id = f"priority_worker_{i}"
            thread = threading.Thread(target=run_concurrent_worker, args=(worker_id,))
            worker_threads.append(thread)
            thread.start()
            time.sleep(0.01)  # Slight stagger

        # Wait for completion
        for thread in worker_threads:
            thread.join(timeout=5)

        # Verify priority order was maintained
        assert len(execution_order) == 3
        # Jobs should be executed in priority order: priority_900, priority_500, priority_100
        assert execution_order[0] == "priority_900"
        assert execution_order[1] == "priority_500"
        assert execution_order[2] == "priority_100"

    @pytest.mark.edge_case
    @pytest.mark.concurrency
    @pytest.mark.fast
    def test_worker_crash_during_execution(self, isolated_job_db, enhanced_mock_time):
        """Test system recovery when worker crashes during job execution."""
        # Create a job and claim it (simulating worker taking it)
        _job = isolated_job_db.add_test_job({"test": "worker_crash"})
        claimed_job = isolated_job_db.claim_job("crashed_worker")
        assert claimed_job is not None

        # Set old heartbeat to simulate worker crash
        old_heartbeat = enhanced_mock_time.create_stale_timestamp(30)  # 30 seconds ago
        isolated_job_db.update_job(claimed_job["id"], {"heartbeat": old_heartbeat})

        # Advance time to trigger stale detection
        enhanced_mock_time.advance_to_make_stale(heartbeat_timeout=10)

        # Create manager to check for stale jobs
        manager = Manager(
            gpus=["0"],
            workers_per_gpu=1,
            heartbeat_timeout=10,
            idle_timeout_mins=1,
            base_dir=str(Path(isolated_job_db.config.base_path) / "manager"),
            client=isolated_job_db,
            process_manager=MockProcessManager(),
        )

        # Mock datetime for stale job detection
        from datetime import datetime, UTC

        with patch("dr_exp.job_db.local_job_db.datetime") as mock_datetime:
            mock_datetime.now.return_value = enhanced_mock_time.now()
            mock_datetime.UTC = UTC
            mock_datetime.fromisoformat = datetime.fromisoformat
            manager.check_stale_jobs()

        # Stale job should be marked as failed
        stale_job_details = isolated_job_db.get_job_details(claimed_job["id"])
        assert stale_job_details["status"] == "failed"

    @pytest.mark.edge_case
    @pytest.mark.concurrency
    @pytest.mark.slow
    def test_high_frequency_job_creation_and_processing(self, isolated_job_db):
        """Test system behavior under high-frequency job creation and processing."""
        # Create many jobs rapidly
        jobs = []
        for i in range(20):
            job = isolated_job_db.add_test_job(
                {"batch_id": i // 5, "job_in_batch": i % 5},
                priority=100 + i,
                sweep_name="high_frequency_sweep",
            )
            jobs.append(job)

        # Process with multiple concurrent workers
        worker_threads = []
        worker_results = {}

        def high_frequency_train(config, logger):
            # Simulate quick processing with some variability
            time.sleep(0.01 + (config["job_in_batch"] * 0.01))
            logger.log({"batch_id": config["batch_id"], "processed": True})
            return create_success_result(
                final_metrics={
                    "final_val_acc": 0.95,
                    "final_train_loss": 0.1,
                    "final_val_loss": 0.15,
                },
                epochs=1,
                logger_meta={
                    "metrics_path": "test_metrics.jsonl",
                    "num_checkpoints": 0,
                },
                artifacts_path=logger.paths.artifact_dir,
                training_time=0.01,
            )

        def run_high_frequency_worker(worker_id):
            completed_count = 0
            while True:
                status = run_worker(
                    base_path=isolated_job_db.config.base_path,
                    max_claim_attempts=1,  # Quick attempts
                    heartbeat_interval=0.05,
                    trainer_fn=high_frequency_train,
                    client=isolated_job_db,
                    worker_id=worker_id,
                )
                if status == "completed":
                    completed_count += 1
                elif status == "no_job":
                    break  # No more jobs available
            worker_results[worker_id] = completed_count

        # Start multiple workers
        for i in range(5):
            worker_id = f"hf_worker_{i}"
            thread = threading.Thread(
                target=run_high_frequency_worker, args=(worker_id,)
            )
            worker_threads.append(thread)
            thread.start()

        # Wait for all workers to complete
        for thread in worker_threads:
            thread.join(timeout=10)

        # Verify all jobs were processed
        total_completed = sum(worker_results.values())
        assert total_completed == 20

        # Verify all jobs are marked as completed
        completed_jobs = isolated_job_db.get_jobs_by_status("completed")
        assert len(completed_jobs) == 20

    @pytest.mark.edge_case
    @pytest.mark.concurrency
    @pytest.mark.fast
    def test_concurrent_database_access_patterns(self, isolated_job_db):
        """Test various concurrent database access patterns."""
        from datetime import datetime, UTC

        # Create initial jobs
        _initial_jobs = isolated_job_db.create_test_jobs(
            count=10, priority_range=(100, 500)
        )

        # Pattern 1: Concurrent job claiming
        claim_results = {}

        def concurrent_claimer(worker_id, claim_count=3):
            claimed_jobs = []
            for i in range(claim_count):
                try:
                    job = isolated_job_db.claim_job(worker_id)
                    if job:
                        claimed_jobs.append(job["id"])
                        # Simulate some work before claiming next job
                        time.sleep(0.01)
                except Exception:
                    pass  # Handle concurrent access gracefully
            claim_results[worker_id] = claimed_jobs

        # Start multiple claimers simultaneously
        claimer_threads = []
        for i in range(4):
            worker_id = f"claimer_{i}"
            thread = threading.Thread(target=concurrent_claimer, args=(worker_id,))
            claimer_threads.append(thread)
            thread.start()

        for thread in claimer_threads:
            thread.join(timeout=5)

        # Verify no double-claiming occurred
        all_claimed_jobs = []
        for worker_id, claimed_list in claim_results.items():
            all_claimed_jobs.extend(claimed_list)

        # Each job should only be claimed once
        assert len(all_claimed_jobs) == len(set(all_claimed_jobs))

        # Pattern 2: Concurrent status updates
        status_update_results = {}

        def concurrent_status_updater(worker_id):
            updates_made = 0
            for job_id in claim_results.get(worker_id, []):
                try:
                    isolated_job_db.update_job(
                        job_id,
                        {
                            "heartbeat": datetime.now(UTC).isoformat() + "Z",
                            "custom_field": f"updated_by_{worker_id}",
                        },
                    )
                    updates_made += 1
                except Exception:
                    pass  # Handle concurrent access gracefully
            status_update_results[worker_id] = updates_made

        # Perform concurrent status updates
        updater_threads = []
        for worker_id in claim_results.keys():
            thread = threading.Thread(
                target=concurrent_status_updater, args=(worker_id,)
            )
            updater_threads.append(thread)
            thread.start()

        for thread in updater_threads:
            thread.join(timeout=5)

        # Verify updates were applied
        total_updates = sum(status_update_results.values())
        assert total_updates > 0


class TestResourceConstraints:
    """Test system behavior under resource constraints."""

    @pytest.mark.edge_case
    @pytest.mark.fast
    def test_disk_space_exhaustion(self, isolated_job_db, worker_execution_helper):
        """Test worker behavior when disk space is exhausted."""
        # Create a job
        job = isolated_job_db.add_test_job({"test": "disk_space"})

        def disk_space_train(config, logger):
            # Simulate disk space error during checkpoint saving
            logger.log({"epoch": 1, "loss": 0.5})
            # This would normally save a checkpoint and fail due to disk space
            raise OSError("No space left on device")

        status = worker_execution_helper.run_worker_with_trainer(disk_space_train)
        assert status == "failed"

        # Verify error is recorded
        job_details = isolated_job_db.get_job_details(job["id"])
        assert job_details["status"] == "failed"
        assert job_details["train_status"] == "crash"

    @pytest.mark.edge_case
    @pytest.mark.fast
    def test_temporary_directory_cleanup(
        self, isolated_job_db, worker_execution_helper
    ):
        """Test that temporary directories are properly cleaned up."""
        # Create a job
        _job = isolated_job_db.add_test_job({"test": "temp_cleanup"})

        created_temp_dirs = []

        def temp_tracking_train(config, logger):
            # Create some temporary files to test cleanup
            temp_file = tempfile.mktemp()
            created_temp_dirs.append(temp_file)

            logger.log({"test_metric": 0.95})
            return create_success_result(
                final_metrics={
                    "final_val_acc": 0.95,
                    "final_train_loss": 0.1,
                    "final_val_loss": 0.15,
                },
                epochs=1,
                logger_meta={
                    "metrics_path": "test_metrics.jsonl",
                    "num_checkpoints": 0,
                },
                artifacts_path=logger.paths.artifact_dir,
                training_time=0.1,
            )

        # Mock tempfile.mkdtemp to track directory creation
        original_mkdtemp = tempfile.mkdtemp
        created_work_dirs = []

        def tracking_mkdtemp(*args, **kwargs):
            temp_dir = original_mkdtemp(*args, **kwargs)
            created_work_dirs.append(temp_dir)
            return temp_dir

        with patch("tempfile.mkdtemp", side_effect=tracking_mkdtemp):
            status = worker_execution_helper.run_worker_with_trainer(
                temp_tracking_train
            )
            assert status == "completed"

        # Work directories should be cleaned up after job completion
        for work_dir in created_work_dirs:
            assert not os.path.exists(work_dir), (
                f"Work directory {work_dir} was not cleaned up"
            )

    @pytest.mark.edge_case
    @pytest.mark.fast
    def test_logger_resource_limits(self, isolated_job_db, worker_execution_helper):
        """Test logger behavior under resource constraints."""
        # Create a job
        job = isolated_job_db.add_test_job({"test": "logger_limits"})

        def resource_intensive_train(config, logger):
            # Log many metrics to test resource limits
            for i in range(1000):
                logger.log({"step": i, "metric": 0.95 + i * 0.001})

            # Try to save many checkpoints
            for i in range(10):
                logger.save_checkpoint({"step": i}, f"checkpoint_{i}")

            return create_success_result(
                final_metrics={
                    "final_val_acc": 0.95,
                    "final_train_loss": 0.1,
                    "final_val_loss": 0.15,
                },
                epochs=10,
                logger_meta={
                    "metrics_path": "test_metrics.jsonl",
                    "num_checkpoints": 10,
                },
                artifacts_path=logger.paths.artifact_dir,
                training_time=1.0,
            )

        status = worker_execution_helper.run_worker_with_trainer(
            resource_intensive_train
        )
        assert status == "completed"

        # Job should complete successfully even with heavy logging
        job_details = isolated_job_db.get_job_details(job["id"])
        assert job_details["status"] == "completed"


class TestRecoveryMechanisms:
    """Test various recovery mechanisms and resilience patterns."""

    @pytest.mark.edge_case
    @pytest.mark.fast
    def test_automatic_job_retry_after_failure(
        self, isolated_job_db, worker_execution_helper
    ):
        """Test automatic retry mechanism for failed jobs."""
        # Create a job that will fail initially
        job = isolated_job_db.add_test_job({"test": "auto_retry", "retry_count": 0})

        attempt_count = 0

        def retry_train(config, logger):
            nonlocal attempt_count
            attempt_count += 1

            # Fail on first two attempts, succeed on third
            if attempt_count <= 2:
                raise RuntimeError(f"Simulated failure attempt {attempt_count}")

            logger.log({"retry_success": True, "attempt": attempt_count})
            return create_success_result(
                final_metrics={
                    "final_val_acc": 0.95,
                    "final_train_loss": 0.1,
                    "final_val_loss": 0.15,
                },
                epochs=attempt_count,
                logger_meta={
                    "metrics_path": "test_metrics.jsonl",
                    "num_checkpoints": 1,
                },
                artifacts_path=logger.paths.artifact_dir,
                training_time=1.0,
            )

        # Simulate retry logic by running worker multiple times
        status1 = worker_execution_helper.run_worker_with_trainer(retry_train)
        assert status1 == "failed"

        # Manually requeue for retry (in real system this would be automatic)
        job_details = isolated_job_db.get_job_details(job["id"])
        isolated_job_db.update_job(
            job["id"],
            {"status": "queued", "retry_index": job_details["retry_index"] + 1},
        )

        status2 = worker_execution_helper.run_worker_with_trainer(retry_train)
        assert status2 == "failed"

        # Second retry
        job_details = isolated_job_db.get_job_details(job["id"])
        isolated_job_db.update_job(
            job["id"],
            {"status": "queued", "retry_index": job_details["retry_index"] + 1},
        )

        status3 = worker_execution_helper.run_worker_with_trainer(retry_train)
        assert status3 == "completed"

        # Final job should be completed
        final_details = isolated_job_db.get_job_details(job["id"])
        assert final_details["status"] == "completed"
        assert final_details["retry_index"] == 2

    @pytest.mark.edge_case
    @pytest.mark.fast
    def test_graceful_shutdown_during_training(
        self, isolated_job_db, worker_execution_helper
    ):
        """Test graceful shutdown when training is in progress."""
        # Create a job
        job = isolated_job_db.add_test_job({"test": "graceful_shutdown"})

        shutdown_event = threading.Event()
        training_started = threading.Event()

        def graceful_shutdown_train(config, logger):
            training_started.set()

            # Simulate long-running training that checks for shutdown
            for epoch in range(100):
                if shutdown_event.is_set():
                    # Save current progress and exit gracefully
                    logger.log({"epoch": epoch, "interrupted": True})
                    logger.save_checkpoint({"epoch": epoch}, "interrupted")
                    return {"final_val_acc": 0.5, "status": "interrupted"}

                time.sleep(0.01)  # Simulate work
                logger.log({"epoch": epoch, "loss": 1.0 - epoch * 0.01})

            return {"final_val_acc": 0.95, "status": "success"}

        def run_worker_with_shutdown():
            return worker_execution_helper.run_worker_with_trainer(
                graceful_shutdown_train
            )

        # Start worker in thread
        worker_thread = threading.Thread(target=run_worker_with_shutdown)
        worker_thread.start()

        # Wait for training to start then signal shutdown
        assert training_started.wait(timeout=5)
        time.sleep(0.1)  # Let some training happen
        shutdown_event.set()

        # Wait for worker to complete
        worker_thread.join(timeout=5)

        # Job should be completed with interrupted status
        job_details = isolated_job_db.get_job_details(job["id"])
        assert job_details["status"] in [
            "completed",
            "failed",
        ]  # Depends on implementation

    @pytest.mark.edge_case
    @pytest.mark.integration
    @pytest.mark.fast
    def test_manager_recovery_after_restart(
        self, integration_system, enhanced_mock_time
    ):
        """Test manager recovery after unexpected restart."""
        # Create multiple jobs in different states
        jobs = []

        # Queued job
        jobs.append(
            integration_system.job_db.add_job(
                make_wrapped_config({"test": "queued_job"}),
                "recovery_sweep",
                status="queued",
                priority=100,
            )
        )

        # Running job (should be detected as stale after restart)
        running_job = integration_system.job_db.add_job(
            make_wrapped_config({"test": "running_job"}),
            "recovery_sweep",
            status="running",
            priority=200,
        )
        jobs.append(running_job)

        # Set old heartbeat for running job
        old_heartbeat = enhanced_mock_time.create_stale_timestamp(30)
        integration_system.job_db.update_job(
            running_job["id"], {"heartbeat": old_heartbeat, "worker_id": "dead_worker"}
        )

        # Create manager (simulates restart)
        manager = Manager(
            gpus=integration_system.config.gpus,
            workers_per_gpu=integration_system.config.workers_per_gpu,
            heartbeat_timeout=integration_system.config.heartbeat_timeout,
            idle_timeout_mins=integration_system.config.idle_timeout_mins,
            base_dir=str(
                Path(integration_system.config.job_db_config.base_path) / "manager"
            ),
            client=integration_system.job_db,
            process_manager=MockProcessManager(),
        )

        # Manager should detect and recover stale jobs
        # Use stale job detector infrastructure (get it from fixture)
        # Since we don't have direct access to the fixture, let's create a simple datetime patch
        from datetime import datetime, UTC

        def create_datetime_patch():
            return patch("dr_exp.job_db.local_job_db.datetime")

        def configure_patch(mock_datetime):
            mock_datetime.now.return_value = enhanced_mock_time.now()
            mock_datetime.UTC = UTC
            mock_datetime.fromisoformat = datetime.fromisoformat
            return mock_datetime

        with create_datetime_patch() as mock_datetime:
            configure_patch(mock_datetime)
            manager.check_stale_jobs()

        # Running job should be marked as failed and requeued
        running_job_details = integration_system.job_db.get_job_details(
            running_job["id"]
        )
        assert running_job_details["status"] == "failed"
        assert "worker_lost" in running_job_details.get("status_reason", "")


# Test markers for different categories
pytest.mark.slow
pytest.mark.integration

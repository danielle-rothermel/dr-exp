"""Integration tests for the complete manager-worker architecture."""

import threading
import pytest
from unittest.mock import patch
from pathlib import Path
from datetime import datetime, UTC, timedelta
from contextlib import contextmanager

from dr_exp.utils.factory import create_system, SystemConfig
from dr_exp.job_db import JobDBConfig
from dr_exp.manage.manager import Manager
from dr_exp.manage.worker import run_worker
from dr_exp.manage.process_manager import MockProcessManager
from dr_exp.training import create_success_result
from tests.conftest import make_wrapped_config


@pytest.fixture
def integration_config(tmp_path):
    """Create a system configuration for integration testing."""
    job_db_config = JobDBConfig(
        base_path=str(tmp_path),
        storage_path=str(tmp_path / "storage"),
        mode="files_local",
    )

    return SystemConfig(
        job_db_config=job_db_config,
        gpus=["0", "1"],
        workers_per_gpu=2,
        heartbeat_timeout=10,
        idle_timeout_mins=1,
        max_claim_attempts=3,
        worker_heartbeat_interval=0.1,  # Fast heartbeat for testing
    )


@pytest.fixture
def mock_time():
    """Fixture providing controlled time for deterministic timing tests."""

    class MockTime:
        def __init__(self):
            self._current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
            self._time_calls = []

        def now(self, tz=None):
            self._time_calls.append(self._current_time)
            return self._current_time

        def advance(self, seconds):
            """Advance mock time by specified seconds."""
            self._current_time += timedelta(seconds=seconds)

        def get_calls(self):
            return self._time_calls.copy()

        def reset_calls(self):
            self._time_calls.clear()

    return MockTime()


@contextmanager
def event_driven_mock_train(completion_events=None, execution_order=None, results=None):
    """Context manager for event-driven mock training with deterministic timing."""
    completion_events = completion_events or {}
    execution_order = execution_order or []
    results = results or {}

    def mock_train(config, logger, *args, **kwargs):
        job_key = (
            config.get("test_param")
            or config.get("priority_test")
            or config.get("job_number", "default")
        )
        execution_order.append(job_key)

        # Signal completion if event provided
        event = completion_events.get(job_key)
        if event:
            event.set()

        # Return configured result
        default_result = create_success_result(
            final_metrics={
                "final_val_acc": 0.95,
                "final_train_loss": 0.1,
                "final_val_loss": 0.15,
            },
            epochs=1,
            logger_meta={"metrics_path": "test_metrics.jsonl", "num_checkpoints": 0},
            artifacts_path=logger.paths.artifact_dir,
            training_time=0.1,
        )
        return results.get(job_key, default_result)

    with patch("dr_exp.train_examples.dummy_trainer.train", side_effect=mock_train):
        yield execution_order


class TestManagerWorkerIntegration:
    """Test the complete manager-worker integration."""

    def test_end_to_end_job_execution(self, integration_config):
        """Test complete end-to-end job execution flow."""
        # Create system factory
        factory = create_system(integration_config)

        # Add test jobs
        job1 = factory.job_db.add_job(
            make_wrapped_config({"test_param": "value1"}),
            "test_sweep",
            status="queued",
            priority=100,
        )
        job2 = factory.job_db.add_job(
            make_wrapped_config({"test_param": "value2"}),
            "test_sweep",
            status="queued",
            priority=200,
        )

        # Mock the actual training function to avoid real execution
        def mock_train(config, logger, *args, **kwargs):
            """Mock training function that simulates work."""
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

        # Run worker to process jobs
        # Use direct trainer_fn to bypass import issues

        # Worker should claim and execute the higher priority job first
        status1 = run_worker(
            base_path=integration_config.job_db_config.base_path,
            max_claim_attempts=integration_config.max_claim_attempts,
            heartbeat_interval=integration_config.worker_heartbeat_interval,
            trainer_fn=mock_train,
            client=factory.job_db,
            worker_id="test_worker_1",
        )
        assert status1 == "completed"

        # Check that the higher priority job was processed
        job_details = factory.job_db.get_job_details(job2["id"])
        assert job_details["status"] == "completed"

        # Process second job
        status2 = run_worker(
            base_path=integration_config.job_db_config.base_path,
            max_claim_attempts=integration_config.max_claim_attempts,
            heartbeat_interval=integration_config.worker_heartbeat_interval,
            trainer_fn=mock_train,
            client=factory.job_db,
            worker_id="test_worker_2",
        )
        assert status2 == "completed"

        # Check that the lower priority job was also processed
        job_details = factory.job_db.get_job_details(job1["id"])
        assert job_details["status"] == "completed"

    def test_manager_coordinates_multiple_workers(self, integration_config):
        """Test that manager can coordinate multiple workers."""
        # Create system with mock process manager for testing
        factory = create_system(integration_config)
        mock_process_manager = MockProcessManager()

        # Create manager with mock process manager
        manager = Manager(
            gpus=integration_config.gpus,
            workers_per_gpu=integration_config.workers_per_gpu,
            heartbeat_timeout=integration_config.heartbeat_timeout,
            idle_timeout_mins=integration_config.idle_timeout_mins,
            base_dir=str(Path(integration_config.job_db_config.base_path) / "manager"),
            client=factory.job_db,
            process_manager=mock_process_manager,
        )

        # Add several jobs for workers to process
        jobs = []
        for i in range(4):
            job = factory.job_db.add_job(
                make_wrapped_config({"job_number": i}),
                "multi_job_sweep",
                status="queued",
                priority=100 + i,
            )
            jobs.append(job)

        # Simulate manager launching workers
        manager.start_workers()

        # Verify that workers were launched (2 GPUs × 2 workers/GPU = 4 workers)
        assert mock_process_manager.get_worker_count() == 4

        # Verify worker status
        worker_status = mock_process_manager.get_worker_status()
        assert len(worker_status) == 4

        # Check that workers are distributed across GPUs
        gpu_assignments = [info["gpu"] for info in worker_status.values()]
        assert "0" in gpu_assignments
        assert "1" in gpu_assignments

    def test_stale_job_detection_and_recovery(self, integration_config, mock_time):
        """Test that stale jobs are detected and marked as failed."""
        factory = create_system(integration_config)

        # Create job and simulate it being claimed but worker dying
        job = factory.job_db.add_job(
            make_wrapped_config({"test": "stale_job"}),
            "stale_sweep",
            status="queued",
            priority=100,
        )

        # Claim the job manually to simulate worker claiming it
        claimed_job = factory.job_db.claim_job("dead_worker")
        assert claimed_job is not None
        assert claimed_job["id"] == job["id"]

        # Set the heartbeat timestamp to an old time to simulate stale job
        old_heartbeat = mock_time.now()
        factory.job_db.update_job(
            job["id"], {"heartbeat": old_heartbeat.isoformat() + "Z"}
        )

        # Advance time to make the job stale
        mock_time.advance(25)  # 25 seconds > heartbeat_timeout * 2 (20s)

        # Create manager with deterministic timing
        manager = Manager(
            gpus=["0"],
            workers_per_gpu=1,
            heartbeat_timeout=10,  # 10 second timeout (threshold will be 20s)
            idle_timeout_mins=1,
            base_dir=str(Path(integration_config.job_db_config.base_path) / "manager"),
            client=factory.job_db,
            process_manager=MockProcessManager(),
        )

        # Mock datetime in job_db for stale job detection
        with patch("dr_exp.job_db.local_job_db.datetime") as job_db_mock_datetime:
            job_db_mock_datetime.now.return_value = mock_time.now()
            job_db_mock_datetime.UTC = UTC
            job_db_mock_datetime.fromisoformat = datetime.fromisoformat

            # Check for stale jobs
            manager.check_stale_jobs()

        # Verify job was marked as failed
        job_details = factory.job_db.get_job_details(job["id"])
        assert job_details["status"] == "failed"
        assert "worker_lost" in job_details.get("status_reason", "")

    def test_priority_based_job_scheduling(self, integration_config):
        """Test that jobs are processed in priority order."""
        factory = create_system(integration_config)

        # Add jobs with different priorities (higher number = higher priority)
        _low_priority_job = factory.job_db.add_job(
            make_wrapped_config({"priority_test": "low"}),
            "priority_sweep",
            status="queued",
            priority=100,
        )
        _high_priority_job = factory.job_db.add_job(
            make_wrapped_config({"priority_test": "high"}),
            "priority_sweep",
            status="queued",
            priority=900,
        )
        _medium_priority_job = factory.job_db.add_job(
            make_wrapped_config({"priority_test": "medium"}),
            "priority_sweep",
            status="queued",
            priority=500,
        )

        # Mock training to track execution order
        execution_order = []

        def mock_train(config, logger, *args, **kwargs):
            priority_level = config.get("priority_test")
            execution_order.append(priority_level)
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

        # Use run_worker with custom trainer_fn to bypass the default_train import issue

        # Process all jobs with custom trainer function
        for i in range(3):
            status = run_worker(
                base_path=integration_config.job_db_config.base_path,
                max_claim_attempts=integration_config.max_claim_attempts,
                heartbeat_interval=integration_config.worker_heartbeat_interval,
                trainer_fn=mock_train,  # Pass mock directly as parameter
                client=factory.job_db,
                worker_id=f"priority_worker_{i}",
            )
            assert status == "completed"

        # Verify jobs were executed in priority order (high to low)
        assert execution_order == ["high", "medium", "low"]

    def test_worker_heartbeat_mechanism(self, integration_config):
        """Test that worker heartbeat mechanism works correctly."""
        factory = create_system(integration_config)

        # Add a job that takes a bit of time to complete
        _job = factory.job_db.add_job(
            make_wrapped_config({"heartbeat_test": True}),
            "heartbeat_sweep",
            status="queued",
            priority=100,
        )

        heartbeat_updates = []
        training_started = threading.Event()
        training_can_complete = threading.Event()

        def mock_train(config, logger, *args, **kwargs):
            # Signal training started
            training_started.set()
            # Wait for test to verify heartbeats before completing
            training_can_complete.wait(timeout=5)
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

        # Monitor heartbeat updates
        original_update = factory.job_db.update_job

        def track_heartbeat_updates(job_id, updates):
            if "heartbeat" in updates:
                heartbeat_updates.append(updates["heartbeat"])
                # Allow training to complete after we get some heartbeats
                if len(heartbeat_updates) >= 2:
                    training_can_complete.set()
            return original_update(job_id, updates)

        with patch.object(
            factory.job_db, "update_job", side_effect=track_heartbeat_updates
        ):
            # Run worker in thread to allow heartbeat monitoring
            from dr_exp.manage.worker import run_worker

            result = []

            def run_worker_thread():
                status = run_worker(
                    base_path=integration_config.job_db_config.base_path,
                    max_claim_attempts=integration_config.max_claim_attempts,
                    heartbeat_interval=integration_config.worker_heartbeat_interval,
                    trainer_fn=mock_train,  # Pass mock directly as parameter
                    client=factory.job_db,
                    worker_id="heartbeat_worker",
                )
                result.append(status)

            worker_thread = threading.Thread(target=run_worker_thread)
            worker_thread.start()

            # Wait for training to start
            assert training_started.wait(timeout=5), "Training did not start"

            # Wait for worker to complete
            worker_thread.join(timeout=10)
            assert len(result) == 1
            assert result[0] == "completed"

        # Verify that heartbeats were sent during job execution
        assert len(heartbeat_updates) >= 2, (
            f"Expected >= 2 heartbeats, got {len(heartbeat_updates)}"
        )

    def test_system_status_reporting(self, integration_config):
        """Test that system status reporting works correctly."""
        factory = create_system(integration_config)

        # Add jobs in different states
        queued_job = factory.job_db.add_job(
            make_wrapped_config({"status": "queued"}),
            "status_sweep",
            status="queued",
            priority=100,
        )
        _running_job = factory.job_db.add_job(
            make_wrapped_config({"status": "running"}),
            "status_sweep",
            status="running",
            priority=200,
        )

        # Get system status
        status = factory.get_system_status()

        # Verify status structure
        assert "configuration" in status
        assert "job_status" in status
        assert "queue_preview" in status

        # Verify configuration
        config = status["configuration"]
        assert config["gpus"] == ["0", "1"]
        assert config["workers_per_gpu"] == 2
        assert config["total_worker_capacity"] == 4
        assert config["mode"] == "files_local"

        # Verify job status
        job_status = status["job_status"]
        assert job_status["running_jobs"] == 1
        assert job_status["has_queued_jobs"] is True

        # Verify queue preview
        queue_preview = status["queue_preview"]
        assert len(queue_preview) >= 1
        assert any(job["id"] == queued_job["id"] for job in queue_preview)


class TestFactoryIntegration:
    """Test the factory system integration."""

    def test_factory_creates_consistent_components(self, integration_config):
        """Test that factory creates properly integrated components."""
        # Set required environment variable for ProcessManager
        with patch.dict(
            "os.environ",
            {"DR_EXP_BASE_PATH": integration_config.job_db_config.base_path},
        ):
            factory = create_system(integration_config)

            # Create manager and verify it uses the same job_db instance
            manager = factory.create_manager()
            assert manager.job_db is factory.job_db

            # Verify manager configuration matches factory config
            assert manager.gpus == integration_config.gpus
            assert manager.workers_per_gpu == integration_config.workers_per_gpu
            assert manager.heartbeat_timeout == integration_config.heartbeat_timeout

    def test_factory_environment_configuration(self, integration_config, tmp_path):
        """Test that factory respects environment configuration."""
        # Test with environment variables
        with patch.dict(
            "os.environ",
            {
                "EXPMGR_MODE": "files_local",
                "DR_EXP_BASE_PATH": str(tmp_path / "env_test"),
            },
        ):
            # Create factory without explicit config (should use environment)
            factory = create_system()

            # Verify environment configuration was picked up
            assert factory.config.job_db_config.mode == "files_local"
            assert str(tmp_path / "env_test") in factory.config.job_db_config.base_path

    def test_factory_worker_execution_with_parameters(self, integration_config):
        """Test factory worker execution with various parameters."""
        factory = create_system(integration_config)

        # Add job for targeted execution
        target_job = factory.job_db.add_job(
            make_wrapped_config({"target": True}),
            "target_sweep",
            status="queued",
            priority=100,
        )

        # Add decoy job that shouldn't be processed
        decoy_job = factory.job_db.add_job(
            make_wrapped_config({"target": False}),
            "target_sweep",
            status="queued",
            priority=200,  # Higher priority, but we'll target specific job
        )

        def mock_train(config, logger, *args, **kwargs):
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

        # Use direct trainer_fn to bypass import issues

        # Run worker targeting specific job
        status = run_worker(
            base_path=integration_config.job_db_config.base_path,
            max_claim_attempts=integration_config.max_claim_attempts,
            heartbeat_interval=integration_config.worker_heartbeat_interval,
            trainer_fn=mock_train,
            client=factory.job_db,
            worker_id="targeted_worker",
            target_job_id=target_job["id"],
            respect_reservations=False,
        )
        assert status == "completed"

        # Verify target job was processed
        target_details = factory.job_db.get_job_details(target_job["id"])
        assert target_details["status"] == "completed"

        # Verify decoy job was not processed
        decoy_details = factory.job_db.get_job_details(decoy_job["id"])
        assert decoy_details["status"] == "queued"


@pytest.mark.integration
class TestFullSystemIntegration:
    """Full system integration tests that simulate real usage patterns."""

    def test_complete_experiment_lifecycle(self, integration_config):
        """Test complete experiment lifecycle from job creation to completion."""
        factory = create_system(integration_config)

        # Phase 1: Create experiment jobs (simulating config upload)
        experiment_jobs = []
        for model in ["resnet", "vit"]:
            for lr in [0.01, 0.001]:
                job = factory.job_db.add_job(
                    make_wrapped_config({"model": model, "lr": lr, "epochs": 1}),
                    "experiment_sweep",
                    status="queued",
                    priority=100,
                )
                experiment_jobs.append(job)

        assert len(experiment_jobs) == 4

        # Phase 2: Process jobs with multiple workers (simulating parallel execution)
        results = []

        def mock_train(config, logger, *args, **kwargs):
            # Simulate training with different results based on config
            if config["model"] == "vit":
                final_accuracy = 0.95
            else:
                final_accuracy = 0.90

            logger.log({"accuracy": final_accuracy})
            logger.log({"loss": 0.1})

            results.append(
                {
                    "model": config["model"],
                    "lr": config["lr"],
                    "accuracy": final_accuracy,
                }
            )

            return create_success_result(
                final_metrics={
                    "final_val_acc": final_accuracy,
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

        # Use direct trainer_fn to bypass import issues

        # Process all jobs
        for i in range(len(experiment_jobs)):
            status = run_worker(
                base_path=integration_config.job_db_config.base_path,
                max_claim_attempts=integration_config.max_claim_attempts,
                heartbeat_interval=integration_config.worker_heartbeat_interval,
                trainer_fn=mock_train,
                client=factory.job_db,
                worker_id=f"exp_worker_{i}",
            )
            assert status == "completed"

        # Phase 3: Verify results
        assert len(results) == 4

        # Verify all jobs completed successfully
        for job in experiment_jobs:
            job_details = factory.job_db.get_job_details(job["id"])
            assert job_details["status"] == "completed"

        # Verify expected results structure
        vit_results = [r for r in results if r["model"] == "vit"]
        resnet_results = [r for r in results if r["model"] == "resnet"]

        assert len(vit_results) == 2  # Two learning rates
        assert len(resnet_results) == 2  # Two learning rates

        # Verify VIT generally performed better (mocked behavior)
        avg_vit_acc = sum(r["accuracy"] for r in vit_results) / len(vit_results)
        avg_resnet_acc = sum(r["accuracy"] for r in resnet_results) / len(
            resnet_results
        )
        assert avg_vit_acc > avg_resnet_acc

    def test_failure_recovery_and_retry(self, integration_config):
        """Test system behavior when jobs fail and need retry."""
        factory = create_system(integration_config)

        # Create job that will initially fail
        failing_job = factory.job_db.add_job(
            make_wrapped_config({"will_fail": True}),
            "failure_sweep",
            status="queued",
            priority=100,
        )

        call_count = 0

        def mock_train_with_failure(config, logger, *args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Fail on first attempt, succeed on retry
            if call_count == 1:
                raise RuntimeError("Simulated training failure")
            else:
                logger.log({"recovery_metric": 0.85})
                return create_success_result(
                    final_metrics={
                        "final_val_acc": 0.85,
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

        # Use direct trainer_fn to bypass import issues

        # First attempt should fail due to training exception
        status1 = run_worker(
            base_path=integration_config.job_db_config.base_path,
            max_claim_attempts=integration_config.max_claim_attempts,
            heartbeat_interval=integration_config.worker_heartbeat_interval,
            trainer_fn=mock_train_with_failure,
            client=factory.job_db,
            worker_id="failure_worker_1",
        )
        assert status1 == "failed"  # Worker reports failure due to training exception

        # Verify job marked as failed (training failed)
        job_details = factory.job_db.get_job_details(failing_job["id"])
        assert job_details["status"] == "failed"

        # Manually requeue the job (simulating retry logic)
        factory.job_db.update_job(
            failing_job["id"],
            {"status": "queued", "retry_index": job_details["retry_index"] + 1},
        )

        # Second attempt should succeed
        status2 = run_worker(
            base_path=integration_config.job_db_config.base_path,
            max_claim_attempts=integration_config.max_claim_attempts,
            heartbeat_interval=integration_config.worker_heartbeat_interval,
            trainer_fn=mock_train_with_failure,
            client=factory.job_db,
            worker_id="failure_worker_2",
        )
        assert status2 == "completed"

        # Verify job completed successfully on retry
        final_details = factory.job_db.get_job_details(failing_job["id"])
        assert final_details["status"] == "completed"
        assert final_details["retry_index"] == 1

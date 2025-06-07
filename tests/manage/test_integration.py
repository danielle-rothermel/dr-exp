"""Integration tests for the complete manager-worker architecture."""

import os
import tempfile
import threading
import time
import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from dr_exp.utils.factory import create_system, SystemConfig
from dr_exp.job_db import JobDBConfig, LocalJobDB
from dr_exp.manage.manager import Manager
from dr_exp.manage.worker import run_worker
from dr_exp.manage.process_manager import MockProcessManager


@pytest.fixture
def integration_config(tmp_path):
    """Create a system configuration for integration testing."""
    job_db_config = JobDBConfig(
        base_path=str(tmp_path),
        storage_path=str(tmp_path / "storage"),
        mode="files_local"
    )
    
    return SystemConfig(
        job_db_config=job_db_config,
        gpus=["0", "1"],
        workers_per_gpu=2,
        heartbeat_timeout=10,
        idle_timeout_mins=1,
        max_claim_attempts=3,
        worker_heartbeat_interval=1.0
    )


class TestManagerWorkerIntegration:
    """Test the complete manager-worker integration."""
    
    def test_end_to_end_job_execution(self, integration_config):
        """Test complete end-to-end job execution flow."""
        # Create system factory
        factory = create_system(integration_config)
        
        # Add test jobs
        job1 = factory.job_db.add_job(
            {"test_param": "value1"}, "test_sweep", 
            status="queued", priority=100
        )
        job2 = factory.job_db.add_job(
            {"test_param": "value2"}, "test_sweep", 
            status="queued", priority=200
        )
        
        # Mock the actual training function to avoid real execution
        def mock_train(config, logger, *args, **kwargs):
            """Mock training function that simulates work."""
            time.sleep(0.1)  # Simulate some work
            logger.log_metric("test_metric", 0.95)
            return {"final_val_acc": 0.95, "status": "completed"}
        
        # Run worker to process jobs
        with patch('dr_exp.manage.worker.default_train', side_effect=mock_train):
            # Worker should claim and execute the higher priority job first
            status1 = factory.run_worker(worker_id="test_worker_1")
            assert status1 == "completed"
            
            # Check that the higher priority job was processed
            job_details = factory.job_db.get_job_details(job2["id"])
            assert job_details["status"] == "completed"
            
            # Process second job
            status2 = factory.run_worker(worker_id="test_worker_2")
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
            process_manager=mock_process_manager
        )
        
        # Add several jobs for workers to process
        jobs = []
        for i in range(4):
            job = factory.job_db.add_job(
                {"job_number": i}, "multi_job_sweep",
                status="queued", priority=100 + i
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
    
    @pytest.mark.skip("TODO: Fix stale job detection timing in test")
    def test_stale_job_detection_and_recovery(self, integration_config):
        """Test that stale jobs are detected and marked as failed."""
        factory = create_system(integration_config)
        
        # Create job and simulate it being claimed but worker dying
        job = factory.job_db.add_job(
            {"test": "stale_job"}, "stale_sweep",
            status="queued", priority=100
        )
        
        # Claim the job manually to simulate worker claiming it
        claimed_job = factory.job_db.claim_next_job("dead_worker")
        assert claimed_job is not None
        assert claimed_job["id"] == job["id"]
        
        # Wait longer than heartbeat timeout to make job stale
        time.sleep(0.1)  # Short sleep for test speed
        
        # Use manager's stale job detection with very short timeout for testing
        manager = Manager(
            gpus=["0"],
            workers_per_gpu=1,
            heartbeat_timeout=0.01,  # Very short timeout for testing
            idle_timeout_mins=1,
            base_dir=str(Path(integration_config.job_db_config.base_path) / "manager"),
            client=factory.job_db,
            process_manager=MockProcessManager()
        )
        
        # Check for stale jobs
        manager.check_stale_jobs()
        
        # Verify job was marked as failed
        job_details = factory.job_db.get_job_details(job["id"])
        assert job_details["status"] == "failed"
        assert "worker_lost" in job_details.get("status_reason", "")
    
    @pytest.mark.skip("TODO: Fix mock patching in worker execution context")
    def test_priority_based_job_scheduling(self, integration_config):
        """Test that jobs are processed in priority order."""
        factory = create_system(integration_config)
        
        # Add jobs with different priorities (higher number = higher priority)
        low_priority_job = factory.job_db.add_job(
            {"priority_test": "low"}, "priority_sweep",
            status="queued", priority=100
        )
        high_priority_job = factory.job_db.add_job(
            {"priority_test": "high"}, "priority_sweep", 
            status="queued", priority=900
        )
        medium_priority_job = factory.job_db.add_job(
            {"priority_test": "medium"}, "priority_sweep",
            status="queued", priority=500
        )
        
        # Mock training to track execution order
        execution_order = []
        
        def mock_train(config, logger, *args, **kwargs):
            execution_order.append(config["priority_test"])
            time.sleep(0.05)  # Simulate work
            return {"status": "completed"}
        
        with patch('dr_exp.manage.worker.default_train', side_effect=mock_train):
            # Process all jobs
            for i in range(3):
                status = factory.run_worker(worker_id=f"priority_worker_{i}")
                assert status == "completed"
        
        # Verify jobs were executed in priority order (high to low)
        assert execution_order == ["high", "medium", "low"]
    
    @pytest.mark.skip("TODO: Fix heartbeat timing in test") 
    def test_worker_heartbeat_mechanism(self, integration_config):
        """Test that worker heartbeat mechanism works correctly."""
        factory = create_system(integration_config)
        
        # Add a job that takes a bit of time to complete
        job = factory.job_db.add_job(
            {"heartbeat_test": True}, "heartbeat_sweep",
            status="queued", priority=100
        )
        
        heartbeat_updates = []
        
        def mock_train(config, logger, *args, **kwargs):
            # Simulate longer running job
            time.sleep(0.3)  # Should allow multiple heartbeats
            return {"status": "completed"}
        
        # Monitor heartbeat updates
        original_update = factory.job_db.update_job
        
        def track_heartbeat_updates(job_id, updates):
            if "heartbeat" in updates:
                heartbeat_updates.append(updates["heartbeat"])
            return original_update(job_id, updates)
        
        with patch('dr_exp.manage.worker.default_train', side_effect=mock_train):
            with patch.object(factory.job_db, 'update_job', side_effect=track_heartbeat_updates):
                status = factory.run_worker(
                    worker_id="heartbeat_worker",
                    heartbeat_interval=0.1  # Fast heartbeat for testing
                )
                assert status == "completed"
        
        # Verify that heartbeats were sent during job execution
        assert len(heartbeat_updates) >= 2  # Should have multiple heartbeat updates
    
    def test_system_status_reporting(self, integration_config):
        """Test that system status reporting works correctly."""
        factory = create_system(integration_config)
        
        # Add jobs in different states
        queued_job = factory.job_db.add_job(
            {"status": "queued"}, "status_sweep",
            status="queued", priority=100
        )
        running_job = factory.job_db.add_job(
            {"status": "running"}, "status_sweep", 
            status="running", priority=200
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
        with patch.dict('os.environ', {
            'EXPMGR_MODE': 'files_local',
            'DR_EXP_BASE_PATH': str(tmp_path / "env_test")
        }):
            # Create factory without explicit config (should use environment)
            factory = create_system()
            
            # Verify environment configuration was picked up
            assert factory.config.job_db_config.mode == "files_local"
            assert str(tmp_path / "env_test") in factory.config.job_db_config.base_path
    
    @pytest.mark.skip("TODO: Fix mock patching in worker execution context")
    def test_factory_worker_execution_with_parameters(self, integration_config):
        """Test factory worker execution with various parameters."""
        factory = create_system(integration_config)
        
        # Add job for targeted execution
        target_job = factory.job_db.add_job(
            {"target": True}, "target_sweep",
            status="queued", priority=100
        )
        
        # Add decoy job that shouldn't be processed
        decoy_job = factory.job_db.add_job(
            {"target": False}, "target_sweep",
            status="queued", priority=200  # Higher priority, but we'll target specific job
        )
        
        def mock_train(config, logger, *args, **kwargs):
            return {"status": "completed", "config": config}
        
        with patch('dr_exp.manage.worker.default_train', side_effect=mock_train):
            # Run worker targeting specific job
            status = factory.run_worker(
                worker_id="targeted_worker",
                target_job_id=target_job["id"],
                respect_reservations=False
            )
            assert status == "completed"
        
        # Verify target job was processed
        target_details = factory.job_db.get_job_details(target_job["id"])
        assert target_details["status"] == "completed"
        
        # Verify decoy job was not processed
        decoy_details = factory.job_db.get_job_details(decoy_job["id"])
        assert decoy_details["status"] == "queued"


@pytest.mark.integration
@pytest.mark.skip("TODO: Fix mock patching for full system tests")
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
                    {"model": model, "lr": lr, "epochs": 1},
                    "experiment_sweep",
                    status="queued",
                    priority=100
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
            
            logger.log_metric("accuracy", final_accuracy)
            logger.log_metric("loss", 0.1)
            
            results.append({
                "model": config["model"],
                "lr": config["lr"],
                "accuracy": final_accuracy
            })
            
            return {"final_val_acc": final_accuracy, "status": "completed"}
        
        with patch('dr_exp.manage.worker.default_train', side_effect=mock_train):
            # Process all jobs
            for i in range(len(experiment_jobs)):
                status = factory.run_worker(worker_id=f"exp_worker_{i}")
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
        avg_resnet_acc = sum(r["accuracy"] for r in resnet_results) / len(resnet_results)
        assert avg_vit_acc > avg_resnet_acc
    
    def test_failure_recovery_and_retry(self, integration_config):
        """Test system behavior when jobs fail and need retry."""
        factory = create_system(integration_config)
        
        # Create job that will initially fail
        failing_job = factory.job_db.add_job(
            {"will_fail": True}, "failure_sweep",
            status="queued", priority=100
        )
        
        call_count = 0
        
        def mock_train_with_failure(config, logger, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            # Fail on first attempt, succeed on retry
            if call_count == 1:
                raise RuntimeError("Simulated training failure")
            else:
                logger.log_metric("recovery_metric", 0.85)
                return {"final_val_acc": 0.85, "status": "completed"}
        
        with patch('dr_exp.manage.worker.default_train', side_effect=mock_train_with_failure):
            # First attempt should complete (worker completes), but job should fail
            status1 = factory.run_worker(worker_id="failure_worker_1")
            assert status1 == "completed"  # Worker completed successfully
            
            # Verify job marked as failed (training failed)
            job_details = factory.job_db.get_job_details(failing_job["id"])
            assert job_details["status"] == "failed"
            
            # Manually requeue the job (simulating retry logic)
            factory.job_db.update_job(failing_job["id"], {
                "status": "queued",
                "retry_index": job_details["retry_index"] + 1
            })
            
            # Second attempt should succeed
            status2 = factory.run_worker(worker_id="failure_worker_2")
            assert status2 == "completed"
            
            # Verify job completed successfully on retry
            final_details = factory.job_db.get_job_details(failing_job["id"])
            assert final_details["status"] == "completed"
            assert final_details["retry_index"] == 1
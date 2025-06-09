"""Tests for the worker implementation."""

import os
import zipfile
import pytest
from unittest.mock import Mock, patch
from typing import Any, Dict

from dr_exp.job_db import LocalJobDB, JobDBConfig
from dr_exp.manage.worker import (
    run_worker,
    HeartbeatManager,
    JobExecutor,
    managed_work_directory,
    _claim_job,
    UploadError,
)
from dr_exp.training.training_result import TrainingResult, create_failure_result
from dr_exp.logging.base_logger import BaseLogger


def make_config() -> Dict[str, Any]:
    """Create a test configuration in the wrapped format expected by the system."""
    return {
        "config": {
            "train": {"num_epochs": 2},
            "logging": {},
            "max_epochs": 2,  # Add top-level epochs for dummy_trainer compatibility
        },
        "metadata": {
            "cluster_name": "test_cluster",
            "description": "test config",
            "interface_version": None,
            "code_version": None,
        },
    }


@pytest.fixture
def temp_client(tmp_path: Any) -> LocalJobDB:
    """Create a temporary LocalJobDB client."""
    return LocalJobDB(
        JobDBConfig(
            base_path=str(tmp_path),
            storage_path=str(tmp_path / "storage"),
            mode="files_local",
        )
    )


class TestHeartbeatManager:
    """Test the HeartbeatManager class."""

    def test_initialization(self) -> None:
        """Test heartbeat manager initialization."""
        mock_client = Mock()
        manager = HeartbeatManager(mock_client, "job123", 5.0)

        assert manager.client is mock_client
        assert manager.job_id == "job123"
        assert manager.interval == 5.0
        assert manager.thread is None
        assert not manager.stop_event.is_set()

    def test_start_and_stop(self) -> None:
        """Test starting and stopping heartbeat."""
        mock_client = Mock()
        manager = HeartbeatManager(
            mock_client, "job123", 0.1
        )  # Short interval for testing

        # Start heartbeat
        manager.start()
        assert manager.thread is not None
        assert manager.thread.is_alive()

        # Stop heartbeat
        manager.stop()
        assert not manager.thread.is_alive()


class TestManagedWorkDirectory:
    """Test the managed work directory context manager."""

    def test_with_provided_directory(self, tmp_path: Any) -> None:
        """Test with an explicitly provided work directory."""
        work_dir = str(tmp_path / "work")

        with managed_work_directory(work_dir, "job123") as managed_dir:
            assert managed_dir == work_dir
            assert os.path.exists(work_dir)

        # Directory should still exist after context (not cleaned up)
        assert os.path.exists(work_dir)

    def test_with_temporary_directory(self) -> None:
        """Test with automatically created temporary directory."""
        with managed_work_directory(None, "job123") as managed_dir:
            assert managed_dir is not None
            assert os.path.exists(managed_dir)
            assert "job123" in managed_dir

        # Temporary directory should be cleaned up
        assert not os.path.exists(managed_dir)


class TestJobExecutor:
    """Test the JobExecutor class."""

    def test_initialization(self, temp_client: LocalJobDB) -> None:
        """Test job executor initialization."""
        job = {"id": "job123", "status": "running"}
        mock_trainer = Mock()

        executor = JobExecutor(
            job=job,
            client=temp_client,
            trainer_fn=mock_trainer,
            logger_cls=Mock,
            heartbeat_interval=5.0,
        )

        assert executor.job is job
        assert executor.job_id == "job123"
        assert executor.client is temp_client
        assert executor.trainer_fn is mock_trainer
        assert executor.heartbeat_interval == 5.0

    def test_upload_metrics_with_retry_success(self, temp_client: LocalJobDB) -> None:
        """Test successful metrics upload."""
        job = {"id": "job123", "status": "running"}
        mock_trainer = Mock()

        executor = JobExecutor(
            job=job,
            client=temp_client,
            trainer_fn=mock_trainer,
            logger_cls=Mock,
            heartbeat_interval=5.0,
        )

        # Mock successful upload
        temp_client.upload_artifact = Mock(
            return_value={"success": True, "storage_path": "/path/to/metrics"}
        )

        logger_meta = {"metrics_path": "/tmp/metrics.jsonl"}
        result = executor._upload_metrics_with_retry(logger_meta)

        assert result["success"] is True
        assert result["storage_path"] == "/path/to/metrics"
        temp_client.upload_artifact.assert_called_once_with(
            "job123", "/tmp/metrics.jsonl", "metrics.jsonl"
        )

    def test_upload_metrics_with_retry_failure(self, temp_client: LocalJobDB) -> None:
        """Test metrics upload failure."""
        job = {"id": "job123", "status": "running"}
        mock_trainer = Mock()

        executor = JobExecutor(
            job=job,
            client=temp_client,
            trainer_fn=mock_trainer,
            logger_cls=Mock,
            heartbeat_interval=5.0,
        )

        # Mock failed upload
        temp_client.upload_artifact = Mock(
            return_value={"success": False, "error": "Upload failed"}
        )

        logger_meta = {"metrics_path": "/tmp/metrics.jsonl"}

        with pytest.raises(UploadError) as exc_info:
            executor._upload_metrics_with_retry(logger_meta)

        assert "Metrics upload failed: Upload failed" in str(exc_info.value)

    def test_upload_bundle_with_retry_success(self, temp_client: LocalJobDB) -> None:
        """Test successful bundle upload."""
        job = {"id": "job123", "status": "running"}
        mock_trainer = Mock()
        mock_logger = Mock()

        executor = JobExecutor(
            job=job,
            client=temp_client,
            trainer_fn=mock_trainer,
            logger_cls=Mock,
            heartbeat_interval=5.0,
        )

        # Mock successful bundle creation and upload
        executor._create_and_upload_bundle = Mock(
            return_value={"success": True, "storage_path": "/path/to/bundle"}
        )

        result = executor._upload_bundle_with_retry(
            mock_logger, "/tmp/work", "/tmp/worker.log"
        )

        assert result["success"] is True
        assert result["storage_path"] == "/path/to/bundle"

    def test_upload_bundle_with_retry_failure(self, temp_client: LocalJobDB) -> None:
        """Test bundle upload failure."""
        job = {"id": "job123", "status": "running"}
        mock_trainer = Mock()
        mock_logger = Mock()

        executor = JobExecutor(
            job=job,
            client=temp_client,
            trainer_fn=mock_trainer,
            logger_cls=Mock,
            heartbeat_interval=5.0,
        )

        # Mock failed bundle upload
        executor._create_and_upload_bundle = Mock(
            return_value={"success": False, "error": "Bundle failed"}
        )

        with pytest.raises(UploadError) as exc_info:
            executor._upload_bundle_with_retry(
                mock_logger, "/tmp/work", "/tmp/worker.log"
            )

        assert "Bundle upload failed: Bundle failed" in str(exc_info.value)

    def test_handle_upload_failure(self, temp_client: LocalJobDB) -> None:
        """Test upload failure handling."""
        job = {"id": "job123", "status": "running"}
        mock_trainer = Mock()

        executor = JobExecutor(
            job=job,
            client=temp_client,
            trainer_fn=mock_trainer,
            logger_cls=Mock,
            heartbeat_interval=5.0,
        )

        # Mock client methods
        temp_client.record_failure = Mock()
        temp_client.finalize_job = Mock()

        error = UploadError("Test upload error")
        result = executor._handle_upload_failure(error)

        assert result["finalize_success"] is False
        assert result["error"] == "Test upload error"

        temp_client.record_failure.assert_called_once_with(
            "job123", "upload_failure", "Test upload error"
        )
        temp_client.finalize_job.assert_called_once_with(
            "job123", "failed", {"finalize_success": False}
        )

    def test_create_success_metadata(self, temp_client: LocalJobDB) -> None:
        """Test successful metadata creation."""
        job = {"id": "job123", "status": "running"}
        mock_trainer = Mock()

        executor = JobExecutor(
            job=job,
            client=temp_client,
            trainer_fn=mock_trainer,
            logger_cls=Mock,
            heartbeat_interval=5.0,
        )

        # Mock client method
        temp_client.finalize_job = Mock()

        # Create mock result and uploads
        result = TrainingResult(
            status="success",
            final_val_acc=0.95,
            final_train_loss=0.1,
            final_val_loss=0.2,
            num_epochs=10,
            metrics_path="/path/to/metrics",
            artifacts_path="/path/to/artifacts",
            num_checkpoints=3,
            training_time=123.45,
            error=None,
        )

        metrics_upload = {"storage_path": "/path/to/metrics"}
        bundle_upload = {"storage_path": "/path/to/bundle"}
        logger_meta = {"finalize_success": True}

        response = executor._create_success_metadata(
            result, "success", metrics_upload, bundle_upload, logger_meta
        )

        assert response["finalize_success"] is True
        assert "metadata" in response

        metadata = response["metadata"]
        assert metadata["final_val_acc"] == 0.95
        assert metadata["final_train_loss"] == 0.1
        assert metadata["num_epochs"] == 10
        assert metadata["train_status"] == "success"
        assert metadata["metrics_storage_path"] == "/path/to/metrics"
        assert metadata["bundle_storage_path"] == "/path/to/bundle"
        assert "upload_complete_at" in metadata

        temp_client.finalize_job.assert_called_once_with(
            "job123", "completed", metadata
        )


class TestClaimJob:
    """Test the job claiming logic."""

    def test_claim_normal_job_success(self, temp_client: LocalJobDB) -> None:
        """Test successful normal job claiming."""
        # Add a job to claim
        job = temp_client.add_job(make_config(), "sweep1", status="queued")

        result = _claim_job(temp_client, "worker1", None, 3, True)

        assert isinstance(result, dict)
        assert result["id"] == job["id"]
        assert result["assigned_worker"] == "worker1"

    def test_claim_normal_job_no_jobs(self, temp_client: LocalJobDB) -> None:
        """Test normal job claiming when no jobs available."""
        result = _claim_job(temp_client, "worker1", None, 2, True)

        assert result == "no_job"

    def test_claim_target_job_success(self, temp_client: LocalJobDB) -> None:
        """Test successful target job claiming."""
        # Add a job to claim
        job = temp_client.add_job(make_config(), "sweep1", status="queued")

        result = _claim_job(temp_client, "worker1", job["id"], 3, True)

        assert isinstance(result, dict)
        assert result["id"] == job["id"]

    def test_claim_target_job_not_found(self, temp_client: LocalJobDB) -> None:
        """Test target job claiming when job doesn't exist."""
        result = _claim_job(temp_client, "worker1", "nonexistent", 3, True)

        assert result == "job_not_found"

    def test_claim_target_job_not_queued(self, temp_client: LocalJobDB) -> None:
        """Test target job claiming when job is not queued."""
        # Add a job but mark it as running
        job = temp_client.add_job(make_config(), "sweep1", status="running")

        result = _claim_job(temp_client, "worker1", job["id"], 3, True)

        assert result == "job_not_available"


class TestStreamlinedWorker:
    """Test the main streamlined worker function."""

    def test_worker_success(self, tmp_path: Any, temp_client: LocalJobDB) -> None:
        """Test successful job execution."""
        job = temp_client.add_job(make_config(), "sweep1", status="queued")

        work_dir = tmp_path / "work"
        status = run_worker(
            base_path=str(tmp_path),
            work_dir=str(work_dir),
            heartbeat_interval=0.01,  # Fast heartbeat for testing
            client=temp_client,
            worker_id="w0",
        )

        assert status == "completed"

        # Check job was updated properly
        job_data = temp_client.get_job_details(job["id"])
        assert job_data["status"] == "completed"
        assert job_data["assigned_worker"] == "w0"
        assert "upload_complete_at" in job_data

        # Check artifacts were created
        storage_run = os.path.join(temp_client.storage_dir, f"run_{job['id']}")
        assert os.path.exists(os.path.join(storage_run, "metrics.jsonl"))

        bundle_zip = os.path.join(storage_run, "bundle.zip")
        assert os.path.exists(bundle_zip)

        # Check bundle contents
        with zipfile.ZipFile(bundle_zip) as zf:
            names = zf.namelist()
            assert "worker.log" in names
            assert "artifacts/loss_plot.txt" in names
            assert any(n.startswith("checkpoints/") for n in names)

    def test_worker_no_job(self, tmp_path: Any, temp_client: LocalJobDB) -> None:
        """Test worker when no jobs are available."""
        work_dir = tmp_path / "work"
        result = run_worker(
            base_path=str(tmp_path),
            work_dir=str(work_dir),
            max_claim_attempts=2,
            heartbeat_interval=0.01,
            client=temp_client,
            worker_id="wid",
        )

        assert result == "no_job"

    def test_worker_training_failure(
        self, tmp_path: Any, temp_client: LocalJobDB
    ) -> None:
        """Test worker when training function fails."""
        job = temp_client.add_job(make_config(), "sweep1", status="queued")

        def failing_train(cfg: Any, logger: BaseLogger) -> TrainingResult:
            return create_failure_result("Training failed")

        work_dir = tmp_path / "work"
        status = run_worker(
            base_path=str(tmp_path),
            work_dir=str(work_dir),
            heartbeat_interval=0.01,
            trainer_fn=failing_train,
            client=temp_client,
            worker_id="wfail",
        )

        assert status == "failed"

        # Check job was marked as failed
        job_data = temp_client.get_job_details(job["id"])
        assert job_data["status"] == "failed"

        # Check error was recorded in job metadata (single source of truth)
        assert "error_message" in job_data
        assert "RuntimeError" in job_data["error_message"]
        assert "Training failed" in job_data["error_message"]

    def test_worker_with_target_job(
        self, tmp_path: Any, temp_client: LocalJobDB
    ) -> None:
        """Test worker with specific target job ID."""
        job = temp_client.add_job(make_config(), "sweep1", status="queued")

        status = run_worker(
            base_path=str(tmp_path),
            heartbeat_interval=0.01,
            client=temp_client,
            worker_id="w0",
            target_job_id=job["id"],
        )

        assert status == "completed"

        # Check the specific job was executed
        job_data = temp_client.get_job_details(job["id"])
        assert job_data["status"] == "completed"
        assert job_data["assigned_worker"] == "w0"

    def test_worker_with_nonexistent_target_job(
        self, tmp_path: Any, temp_client: LocalJobDB
    ) -> None:
        """Test worker with nonexistent target job ID."""
        status = run_worker(
            base_path=str(tmp_path),
            heartbeat_interval=0.01,
            client=temp_client,
            worker_id="w0",
            target_job_id="nonexistent",
        )

        assert status == "job_not_found"

    def test_worker_config_missing(
        self, tmp_path: Any, temp_client: LocalJobDB
    ) -> None:
        """Test worker when job config is missing."""
        # Create a job but don't set up config properly
        job = temp_client.add_job(make_config(), "sweep1", status="queued")

        # Mock get_config_for_job to return None
        with patch.object(temp_client, "get_config_for_job", return_value=None):
            status = run_worker(
                base_path=str(tmp_path),
                heartbeat_interval=0.01,
                client=temp_client,
                worker_id="w0",
            )

        assert status == "failed"

        # Check job was marked as failed
        job_data = temp_client.get_job_details(job["id"])
        assert job_data["status"] == "failed"

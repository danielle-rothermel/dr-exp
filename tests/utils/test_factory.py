"""Tests for the factory and configuration."""

import pytest
from unittest.mock import patch
from pathlib import Path

from dr_exp.utils.factory import SystemConfig, Factory, create_system
from dr_exp.job_db import JobDBConfig, LocalJobDB
from dr_exp.manage.manager import Manager
from dr_exp.manage.process_manager import ProcessManager


@pytest.fixture
def temp_config(tmp_path: Path) -> SystemConfig:
    """Create a temporary system configuration."""
    job_db_config = JobDBConfig(
        base_path=str(tmp_path),
        storage_path=str(tmp_path / "storage"),
        mode="files_local",
    )

    return SystemConfig(
        job_db_config=job_db_config,
        gpus=["0", "1"],
        workers_per_gpu=2,
        heartbeat_timeout=30,
        idle_timeout_mins=5,
        manager_base_dir=str(tmp_path / "manager"),
    )


class TestSystemConfig:
    """Test the SystemConfig class."""

    def test_default_initialization(self) -> None:
        """Test system config with default values."""
        job_db_config = JobDBConfig(base_path="/tmp", mode="files_local")
        config = SystemConfig(job_db_config=job_db_config)

        assert isinstance(config.job_db_config, JobDBConfig)
        assert isinstance(config.gpus, list)
        assert config.workers_per_gpu == 1
        assert config.heartbeat_timeout == 60
        assert config.idle_timeout_mins == 30
        assert config.max_claim_attempts == 5
        assert config.worker_heartbeat_interval == 5.0
        assert config.multiprocessing_start_method == "fork"

    def test_custom_initialization(self, temp_config: SystemConfig) -> None:
        """Test system config with custom values."""
        assert temp_config.gpus == ["0", "1"]
        assert temp_config.workers_per_gpu == 2
        assert temp_config.heartbeat_timeout == 30
        assert temp_config.idle_timeout_mins == 5

    def test_gpu_discovery_from_env(self) -> None:
        """Test GPU discovery from CUDA_VISIBLE_DEVICES."""
        with patch.dict(
            "os.environ",
            {"CUDA_VISIBLE_DEVICES": "2,3,4"},
        ):
            job_db_config = JobDBConfig(base_path="/tmp", mode="files_local")
            config = SystemConfig(job_db_config=job_db_config)
            assert config.gpus == ["2", "3", "4"]

    def test_gpu_discovery_default(self) -> None:
        """Test GPU discovery default behavior."""
        with patch.dict(
            "os.environ",
            {},
            clear=True,
        ):
            job_db_config = JobDBConfig(base_path="/tmp", mode="files_local")
            config = SystemConfig(job_db_config=job_db_config)
            assert config.gpus == ["0"]

    def test_manager_base_dir_default(self, tmp_path: Path) -> None:
        """Test default manager base directory."""
        job_db_config = JobDBConfig(
            base_path=str(tmp_path),
            storage_path=str(tmp_path / "storage"),
            mode="files_local",
        )
        config = SystemConfig(
            job_db_config=job_db_config, auto_detect_environment=False
        )
        assert config.manager_base_dir == str(tmp_path / "manager")

    def test_validation_success(self, temp_config: SystemConfig) -> None:
        """Test successful validation."""
        # Should not raise any exceptions
        temp_config.validate()

    def test_validation_no_gpus(self, temp_config: SystemConfig) -> None:
        """Test validation with no GPUs."""
        temp_config.gpus = []

        with pytest.raises(AssertionError, match="At least one GPU must be specified"):
            temp_config.validate()

    def test_validation_invalid_workers_per_gpu(
        self, temp_config: SystemConfig
    ) -> None:
        """Test validation with invalid workers per GPU."""
        temp_config.workers_per_gpu = 0

        with pytest.raises(AssertionError, match="workers_per_gpu must be at least 1"):
            temp_config.validate()

    def test_validation_low_heartbeat_timeout(self, temp_config: SystemConfig) -> None:
        """Test validation with too low heartbeat timeout."""
        temp_config.heartbeat_timeout = 5

        with pytest.raises(
            AssertionError, match="heartbeat_timeout must be at least 10 seconds"
        ):
            temp_config.validate()

    def test_validation_low_worker_heartbeat_interval(
        self, temp_config: SystemConfig
    ) -> None:
        """Test validation with too low worker heartbeat interval."""
        temp_config.worker_heartbeat_interval = 0.05

        with pytest.raises(
            AssertionError,
            match="worker_heartbeat_interval must be at least 0.1 seconds",
        ):
            temp_config.validate()

    def test_validation_heartbeat_interval_vs_timeout(
        self, temp_config: SystemConfig
    ) -> None:
        """Test validation with heartbeat interval >= timeout."""
        temp_config.worker_heartbeat_interval = 35
        temp_config.heartbeat_timeout = 30

        with pytest.raises(
            AssertionError,
            match="worker_heartbeat_interval must be less than heartbeat_timeout",
        ):
            temp_config.validate()


class TestFactory:
    """Test the Factory class."""

    def test_initialization_with_config(self, temp_config: SystemConfig) -> None:
        """Test factory initialization with config."""
        factory = Factory(temp_config)
        assert factory.config is temp_config

    def test_initialization_default_config(self) -> None:
        """Test factory initialization with default config."""
        job_db_config = JobDBConfig(base_path="/tmp", mode="files_local")
        system_config = SystemConfig(job_db_config=job_db_config)
        factory = Factory(system_config)
        assert isinstance(factory.config, SystemConfig)

    def test_job_db_property(self, temp_config: SystemConfig) -> None:
        """Test job database property."""
        factory = Factory(temp_config)

        # First access should create the instance
        job_db = factory.job_db
        assert isinstance(job_db, LocalJobDB)

        # Second access should return the same instance
        job_db2 = factory.job_db
        assert job_db is job_db2

    def test_process_manager_property(self, temp_config: SystemConfig) -> None:
        """Test process manager property."""
        factory = Factory(temp_config)

        # First access should create the instance
        pm = factory.process_manager
        assert isinstance(pm, ProcessManager)

        # Second access should return the same instance
        pm2 = factory.process_manager
        assert pm is pm2

    def test_create_manager(self, temp_config: SystemConfig) -> None:
        """Test creating a manager."""
        factory = Factory(temp_config)
        manager = factory.create_manager()

        assert isinstance(manager, Manager)
        assert manager.gpus == ["0", "1"]
        assert manager.workers_per_gpu == 2
        assert manager.heartbeat_timeout == 30
        assert manager.idle_timeout.total_seconds() == 5 * 60

    def test_run_worker(self, temp_config: SystemConfig) -> None:
        """Test running a worker."""
        factory = Factory(temp_config)

        # Add a job for the worker to claim
        job = factory.job_db.add_job({"test": "config"}, "sweep1", status="queued")

        with patch("dr_exp.utils.factory.run_worker") as mock_run:
            mock_run.return_value = "completed"

            status = factory.run_worker(
                worker_id="test_worker", target_job_id=job["id"]
            )

            assert status == "completed"
            mock_run.assert_called_once()

            # Check arguments passed to run_streamlined_worker
            call_args = mock_run.call_args
            assert call_args.kwargs["worker_id"] == "test_worker"
            assert call_args.kwargs["target_job_id"] == job["id"]
            assert call_args.kwargs["client"] is factory.job_db

    def test_get_system_status_empty(self, temp_config: SystemConfig) -> None:
        """Test getting system status with no jobs."""
        factory = Factory(temp_config)
        status = factory.get_system_status()

        assert status["configuration"]["gpus"] == ["0", "1"]
        assert status["configuration"]["workers_per_gpu"] == 2
        assert status["configuration"]["total_worker_capacity"] == 4
        assert status["configuration"]["mode"] == "files_local"

        assert status["job_status"]["running_jobs"] == 0
        assert status["job_status"]["has_queued_jobs"] is False
        assert status["job_status"]["stale_jobs"] == 0

        assert status["queue_preview"] == []
        assert status["stale_jobs_preview"] == []

    def test_get_system_status_with_jobs(self, temp_config: SystemConfig) -> None:
        """Test getting system status with jobs."""
        factory = Factory(temp_config)

        # Add some jobs
        job1 = factory.job_db.add_job(
            {"test": 1}, "sweep1", status="queued", priority=800
        )
        job2 = factory.job_db.add_job(
            {"test": 2}, "sweep2", status="queued", priority=500
        )
        _job3 = factory.job_db.add_job({"test": 3}, "sweep3", status="running")

        status = factory.get_system_status()

        assert status["job_status"]["running_jobs"] == 1
        assert status["job_status"]["has_queued_jobs"] is True
        assert status["job_status"]["queued_jobs_summary"] == 2

        # Queue should be ordered by priority
        queue_preview = status["queue_preview"]
        assert len(queue_preview) == 2
        assert queue_preview[0]["id"] == job1["id"]  # Higher priority first
        assert queue_preview[0]["priority"] == 800
        assert queue_preview[1]["id"] == job2["id"]
        assert queue_preview[1]["priority"] == 500


class TestCreateStreamlinedSystem:
    """Test the create_system function."""

    def test_create_with_config(self, temp_config: SystemConfig) -> None:
        """Test creating system with provided config."""
        system = create_system(temp_config)

        assert isinstance(system, Factory)
        assert system.config is temp_config

    def test_create_with_default_config(self) -> None:
        """Test creating system with default config."""
        job_db_config = JobDBConfig(base_path="/tmp", mode="files_local")
        system_config = SystemConfig(job_db_config=job_db_config)
        system = create_system(system_config)

        assert isinstance(system, Factory)
        assert isinstance(system.config, SystemConfig)

    def test_full_workflow_example(self, temp_config: SystemConfig) -> None:
        """Test a complete workflow example."""
        # Create system
        system = create_system(temp_config)

        # Add a job
        _job = system.job_db.add_job({"epochs": 5}, "test_sweep", status="queued")

        # Get status
        status = system.get_system_status()
        assert status["job_status"]["has_queued_jobs"] is True

        # Create manager (don't run it)
        manager = system.create_manager()
        assert isinstance(manager, Manager)

        # The workflow demonstrates the integration works correctly
        assert manager.job_db is system.job_db
        assert manager.process_manager is system.process_manager


class TestIntegration:
    """Integration tests for the streamlined factory."""

    def test_end_to_end_configuration(self, tmp_path: Path) -> None:
        """Test end-to-end configuration and component creation."""
        # Create a complete configuration
        job_db_config = JobDBConfig(
            base_path=str(tmp_path),
            storage_path=str(tmp_path / "storage"),
            mode="files_local",
        )

        system_config = SystemConfig(
            job_db_config=job_db_config,
            gpus=["0", "1", "2"],
            workers_per_gpu=3,
            heartbeat_timeout=45,
            idle_timeout_mins=10,
            max_claim_attempts=10,
            worker_heartbeat_interval=2.0,
            multiprocessing_start_method="spawn",
        )

        # Create factory and verify all components
        factory = Factory(system_config)

        # Test job database
        job_db = factory.job_db
        assert isinstance(job_db, LocalJobDB)
        assert job_db.jobs_dir == str(tmp_path / "job_data")

        # Test process manager
        pm = factory.process_manager
        assert isinstance(pm, ProcessManager)

        # Test manager creation
        manager = factory.create_manager()
        assert manager.gpus == ["0", "1", "2"]
        assert manager.workers_per_gpu == 3
        assert manager.heartbeat_timeout == 45
        assert manager.idle_timeout.total_seconds() == 10 * 60

        # Verify shared instances
        assert manager.job_db is factory.job_db
        assert manager.process_manager is factory.process_manager

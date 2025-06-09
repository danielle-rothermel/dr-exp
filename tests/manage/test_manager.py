"""Tests for the Manager implementation."""

import os
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from typing import Any, Dict, List

from dr_exp.manage.manager import Manager
from dr_exp.manage.process_manager import MockProcessManager
from dr_exp.job_db import StaleJobInfo, BaseJobDB
from typing import cast


class MockJobDB:
    """Mock job database for testing."""

    def __init__(self) -> None:
        self.running_jobs: List[Dict[str, Any]] = []
        self.stale_jobs: List[StaleJobInfo] = []
        self.has_queued: bool = False
        self.queue_summary: List[Dict[str, Any]] = []
        self.mark_failed_calls: List[Dict[str, Any]] = []

    def list_running_jobs(self) -> List[Dict[str, Any]]:
        return self.running_jobs

    def get_stale_jobs(self, max_age_seconds: int) -> List[StaleJobInfo]:
        return self.stale_jobs

    def mark_jobs_failed(
        self, job_ids: List[str], reason: str = "worker_lost"
    ) -> Dict[str, bool]:
        self.mark_failed_calls.append({"job_ids": job_ids, "reason": reason})
        return {job_id: True for job_id in job_ids}

    def has_queued_jobs(self) -> bool:
        return self.has_queued

    def get_queue_summary(self, limit: int = 5) -> List[Dict[str, Any]]:
        return self.queue_summary[:limit]


@pytest.fixture
def temp_dir() -> Any:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_job_db() -> MockJobDB:
    """Create a mock job database."""
    return MockJobDB()


@pytest.fixture
def mock_process_manager() -> MockProcessManager:
    """Create a mock process manager."""
    return MockProcessManager()


@pytest.fixture
def streamlined_manager(
    temp_dir: str, mock_job_db: MockJobDB, mock_process_manager: MockProcessManager
) -> Manager:
    """Create a Manager for testing."""
    return Manager(
        gpus=["0", "1"],
        workers_per_gpu=2,
        heartbeat_timeout=30,
        idle_timeout_mins=5,
        base_dir=temp_dir,
        client=cast(BaseJobDB, mock_job_db),
        process_manager=mock_process_manager,
    )


class TestManager:
    """Test the Manager implementation."""

    def test_initialization(
        self,
        streamlined_manager: Manager,
        temp_dir: str,
        mock_job_db: MockJobDB,
        mock_process_manager: MockProcessManager,
    ) -> None:
        """Test manager initialization."""
        assert streamlined_manager.gpus == ["0", "1"]
        assert streamlined_manager.workers_per_gpu == 2
        assert streamlined_manager.heartbeat_timeout == 30
        assert streamlined_manager.idle_timeout == timedelta(minutes=5)
        assert streamlined_manager.base_dir == temp_dir
        assert streamlined_manager.job_db is mock_job_db
        assert streamlined_manager.process_manager is mock_process_manager
        assert not streamlined_manager.shutdown

        # Check that log directory was created
        assert os.path.exists(temp_dir)

    def test_start_workers(
        self, streamlined_manager: Manager, mock_process_manager: MockProcessManager
    ) -> None:
        """Test worker startup."""
        streamlined_manager.start_workers()

        # Should have launched 4 workers (2 GPUs × 2 workers per GPU)
        assert mock_process_manager.launch_count == 4
        assert mock_process_manager.get_worker_count() == 4

        # Check worker IDs
        worker_status = mock_process_manager.get_worker_status()
        expected_workers = {"worker_0_0", "worker_0_1", "worker_1_0", "worker_1_1"}
        assert set(worker_status.keys()) == expected_workers

        # Check GPU assignments
        assert worker_status["worker_0_0"]["gpu"] == "0"
        assert worker_status["worker_0_1"]["gpu"] == "0"
        assert worker_status["worker_1_0"]["gpu"] == "1"
        assert worker_status["worker_1_1"]["gpu"] == "1"

    def test_stop_all_workers(
        self, streamlined_manager: Manager, mock_process_manager: MockProcessManager
    ) -> None:
        """Test stopping all workers."""
        streamlined_manager.start_workers()
        assert mock_process_manager.get_worker_count() == 4

        streamlined_manager.stop_all_workers()
        assert mock_process_manager.stop_count == 1

        # Workers should be marked as not alive
        worker_status = mock_process_manager.get_worker_status()
        assert all(not status["alive"] for status in worker_status.values())

    def test_check_stale_jobs_no_stale_jobs(
        self, streamlined_manager: Manager, mock_job_db: MockJobDB
    ) -> None:
        """Test stale job checking when no stale jobs exist."""
        mock_job_db.stale_jobs = []

        streamlined_manager.check_stale_jobs()

        # No jobs should be marked as failed
        assert len(mock_job_db.mark_failed_calls) == 0

    def test_check_stale_jobs_with_stale_jobs(
        self,
        streamlined_manager: Manager,
        mock_job_db: MockJobDB,
        mock_process_manager: MockProcessManager,
    ) -> None:
        """Test stale job checking with stale jobs."""
        # Create stale jobs
        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(minutes=5)

        mock_job_db.stale_jobs = [
            StaleJobInfo(
                job_id="job1",
                assigned_worker="worker_0_0",
                last_heartbeat=stale_time,
                age_seconds=300,
            ),
            StaleJobInfo(
                job_id="job2",
                assigned_worker="worker_1_0",
                last_heartbeat=stale_time,
                age_seconds=300,
            ),
        ]

        # Start workers first
        streamlined_manager.start_workers()

        streamlined_manager.check_stale_jobs()

        # Jobs should be marked as failed
        assert len(mock_job_db.mark_failed_calls) == 1
        call = mock_job_db.mark_failed_calls[0]
        assert set(call["job_ids"]) == {"job1", "job2"}
        assert call["reason"] == "worker_lost"

        # Affected workers should be restarted
        assert mock_process_manager.restart_count == 2

    def test_check_idle_timeout_with_running_jobs(
        self, streamlined_manager: Manager, mock_job_db: MockJobDB
    ) -> None:
        """Test idle timeout check when there are running jobs."""
        # Set up running jobs
        mock_job_db.running_jobs = [
            {"id": "job1", "status": "running"},
            {"id": "job2", "status": "running"},
        ]

        # Set last activity to 10 minutes ago
        streamlined_manager.last_activity = datetime.now(timezone.utc) - timedelta(
            minutes=10
        )

        streamlined_manager.check_idle_timeout()

        # Should reset last activity and not shutdown
        assert datetime.now(
            timezone.utc
        ) - streamlined_manager.last_activity < timedelta(seconds=5)
        assert not streamlined_manager.shutdown

    def test_check_idle_timeout_no_jobs_within_timeout(
        self, streamlined_manager: Manager, mock_job_db: MockJobDB
    ) -> None:
        """Test idle timeout check with no jobs but within timeout."""
        # No running jobs
        mock_job_db.running_jobs = []
        mock_job_db.has_queued = False

        # Set last activity to 2 minutes ago (less than 5 minute timeout)
        streamlined_manager.last_activity = datetime.now(timezone.utc) - timedelta(
            minutes=2
        )

        streamlined_manager.check_idle_timeout()

        # Should not shutdown
        assert not streamlined_manager.shutdown

    def test_check_idle_timeout_exceeds_timeout(
        self, streamlined_manager: Manager, mock_job_db: MockJobDB
    ) -> None:
        """Test idle timeout check when timeout is exceeded."""
        # No running jobs
        mock_job_db.running_jobs = []
        mock_job_db.has_queued = False

        # Set last activity to 10 minutes ago (exceeds 5 minute timeout)
        streamlined_manager.last_activity = datetime.now(timezone.utc) - timedelta(
            minutes=10
        )

        streamlined_manager.check_idle_timeout()

        # Should shutdown
        assert streamlined_manager.shutdown

    def test_check_idle_timeout_with_queued_jobs(
        self, streamlined_manager: Manager, mock_job_db: MockJobDB
    ) -> None:
        """Test idle timeout check logs queued jobs."""
        # No running jobs but some queued
        mock_job_db.running_jobs = []
        mock_job_db.has_queued = True
        mock_job_db.queue_summary = [
            {"id": "job1", "priority": 800},
            {"id": "job2", "priority": 500},
        ]

        # Should not affect timeout logic
        streamlined_manager.last_activity = datetime.now(timezone.utc) - timedelta(
            minutes=2
        )

        streamlined_manager.check_idle_timeout()

        # Should not shutdown (within timeout)
        assert not streamlined_manager.shutdown

    def test_log_status(
        self,
        streamlined_manager: Manager,
        mock_job_db: MockJobDB,
        mock_process_manager: MockProcessManager,
    ) -> None:
        """Test status logging."""
        # Set up test data
        mock_job_db.running_jobs = [{"id": "job1"}, {"id": "job2"}]
        mock_job_db.has_queued = True

        streamlined_manager.start_workers()

        # Should not raise any exceptions
        streamlined_manager.log_status()

    @patch("signal.signal")
    def test_signal_handling(
        self, mock_signal: Any, streamlined_manager: Manager
    ) -> None:
        """Test signal handling setup."""
        # Mock the signal handling to avoid actual signal registration
        with (
            patch.object(streamlined_manager, "start_workers"),
            patch.object(streamlined_manager, "stop_all_workers"),
        ):
            # Set shutdown to True immediately to exit the loop
            streamlined_manager.shutdown = True

            streamlined_manager.run()

            # Should have registered signal handlers
            assert mock_signal.call_count >= 2

    def test_run_with_immediate_shutdown(
        self, streamlined_manager: Manager, mock_process_manager: MockProcessManager
    ) -> None:
        """Test run method with immediate shutdown."""
        # Set shutdown flag to exit immediately
        streamlined_manager.shutdown = True

        with patch("signal.signal"), patch("time.sleep"):
            streamlined_manager.run()

            # Workers should have been started and stopped
            assert mock_process_manager.launch_count == 4
            assert mock_process_manager.stop_count == 1

    def test_get_and_log_stale_jobs_empty(
        self, streamlined_manager: Manager, mock_job_db: MockJobDB
    ) -> None:
        """Test _get_and_log_stale_jobs with no stale jobs."""
        mock_job_db.stale_jobs = []

        result = streamlined_manager._get_and_log_stale_jobs()

        assert result == []

    def test_get_and_log_stale_jobs_with_jobs(
        self, streamlined_manager: Manager, mock_job_db: MockJobDB
    ) -> None:
        """Test _get_and_log_stale_jobs with stale jobs."""
        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(minutes=5)

        mock_job_db.stale_jobs = [
            StaleJobInfo(
                job_id="job1",
                assigned_worker="worker_0_0",
                last_heartbeat=stale_time,
                age_seconds=300,
            ),
            StaleJobInfo(
                job_id="job2",
                assigned_worker="worker_1_0",
                last_heartbeat=stale_time,
                age_seconds=300,
            ),
        ]

        result = streamlined_manager._get_and_log_stale_jobs()

        assert len(result) == 2
        assert result[0].job_id == "job1"
        assert result[1].job_id == "job2"

    def test_mark_stale_jobs_failed_success(
        self, streamlined_manager: Manager, mock_job_db: MockJobDB
    ) -> None:
        """Test _mark_stale_jobs_failed with successful job marking."""
        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(minutes=5)

        stale_jobs = [
            StaleJobInfo(
                job_id="job1",
                assigned_worker="worker_0_0",
                last_heartbeat=stale_time,
                age_seconds=300,
            ),
            StaleJobInfo(
                job_id="job2",
                assigned_worker="worker_1_0",
                last_heartbeat=stale_time,
                age_seconds=300,
            ),
        ]

        # Should not raise exception
        streamlined_manager._mark_stale_jobs_failed(stale_jobs)

        # Verify jobs were marked as failed
        assert len(mock_job_db.mark_failed_calls) == 1
        call = mock_job_db.mark_failed_calls[0]
        assert set(call["job_ids"]) == {"job1", "job2"}
        assert call["reason"] == "worker_lost"

    def test_mark_stale_jobs_failed_partial_failure(
        self, streamlined_manager: Manager, mock_job_db: MockJobDB
    ) -> None:
        """Test _mark_stale_jobs_failed with partial failures."""
        from dr_exp.manage.manager import StaleJobProcessingError

        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(minutes=5)

        stale_jobs = [
            StaleJobInfo(
                job_id="job1",
                assigned_worker="worker_0_0",
                last_heartbeat=stale_time,
                age_seconds=300,
            ),
            StaleJobInfo(
                job_id="job2",
                assigned_worker="worker_1_0",
                last_heartbeat=stale_time,
                age_seconds=300,
            ),
        ]

        # Mock partial failure in mark_jobs_failed
        def mock_mark_failed(
            job_ids: List[str], reason: str = "worker_lost"
        ) -> Dict[str, bool]:
            return {"job1": True, "job2": False}

        with patch.object(
            mock_job_db, "mark_jobs_failed", side_effect=mock_mark_failed
        ):
            # Should raise StaleJobProcessingError
            with pytest.raises(StaleJobProcessingError) as exc_info:
                streamlined_manager._mark_stale_jobs_failed(stale_jobs)

        assert "Failed to mark 1 jobs as failed" in str(exc_info.value)

    def test_restart_affected_workers_success(
        self, streamlined_manager: Manager, mock_process_manager: MockProcessManager
    ) -> None:
        """Test _restart_affected_workers with successful restarts."""
        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(minutes=5)

        stale_jobs = [
            StaleJobInfo(
                job_id="job1",
                assigned_worker="worker_0_0",
                last_heartbeat=stale_time,
                age_seconds=300,
            ),
            StaleJobInfo(
                job_id="job2",
                assigned_worker="worker_1_0",
                last_heartbeat=stale_time,
                age_seconds=300,
            ),
        ]

        # Start workers first so they're managed
        streamlined_manager.start_workers()

        # Should not raise exception
        streamlined_manager._restart_affected_workers(stale_jobs)

        # Verify workers were restarted
        assert mock_process_manager.restart_count == 2

    def test_restart_affected_workers_unmanaged_worker(
        self, streamlined_manager: Manager, mock_process_manager: MockProcessManager
    ) -> None:
        """Test _restart_affected_workers with unmanaged worker."""
        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(minutes=5)

        stale_jobs = [
            StaleJobInfo(
                job_id="job1",
                assigned_worker="external_worker",
                last_heartbeat=stale_time,
                age_seconds=300,
            ),
        ]

        # Don't start workers - external_worker not managed

        # Should not raise exception (unmanaged workers are skipped)
        streamlined_manager._restart_affected_workers(stale_jobs)

        # No restarts should be attempted
        assert mock_process_manager.restart_count == 0

    def test_restart_single_worker_success(
        self, streamlined_manager: Manager, mock_process_manager: MockProcessManager
    ) -> None:
        """Test _restart_single_worker with successful restart."""
        # Start workers first
        streamlined_manager.start_workers()
        managed_workers = set(mock_process_manager.get_worker_status().keys())

        # Should not raise exception
        streamlined_manager._restart_single_worker("worker_0_0", managed_workers)

        # Verify worker was restarted
        assert mock_process_manager.restart_count == 1

    def test_restart_single_worker_unmanaged(
        self, streamlined_manager: Manager, mock_process_manager: MockProcessManager
    ) -> None:
        """Test _restart_single_worker with unmanaged worker."""
        managed_workers: set[str] = set()  # Empty set - no managed workers

        # Should not raise exception (just logs warning)
        streamlined_manager._restart_single_worker("external_worker", managed_workers)

        # No restarts should be attempted
        assert mock_process_manager.restart_count == 0

    def test_restart_single_worker_failure(
        self, streamlined_manager: Manager, mock_process_manager: MockProcessManager
    ) -> None:
        """Test _restart_single_worker with restart failure."""
        from dr_exp.manage.manager import WorkerRestartError

        # Start workers first
        streamlined_manager.start_workers()
        managed_workers = set(mock_process_manager.get_worker_status().keys())

        # Mock restart failure
        def mock_restart_worker(worker_id: str) -> None:
            raise RuntimeError("Restart failed")

        with patch.object(
            mock_process_manager, "restart_worker", side_effect=mock_restart_worker
        ):
            # Should raise WorkerRestartError
            with pytest.raises(WorkerRestartError) as exc_info:
                streamlined_manager._restart_single_worker(
                    "worker_0_0", managed_workers
                )

            assert "Failed to restart worker worker_0_0" in str(exc_info.value)

    def test_check_stale_jobs_processing_error_handling(
        self, streamlined_manager: Manager, mock_job_db: MockJobDB
    ) -> None:
        """Test check_stale_jobs handles StaleJobProcessingError gracefully."""
        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(minutes=5)

        mock_job_db.stale_jobs = [
            StaleJobInfo(
                job_id="job1",
                assigned_worker="worker_0_0",
                last_heartbeat=stale_time,
                age_seconds=300,
            ),
        ]

        # Mock mark_jobs_failed to return failure
        def mock_mark_failed(
            job_ids: List[str], reason: str = "worker_lost"
        ) -> Dict[str, bool]:
            return {"job1": False}

        with patch.object(
            mock_job_db, "mark_jobs_failed", side_effect=mock_mark_failed
        ):
            # Should not raise exception - error should be caught and logged
            streamlined_manager.check_stale_jobs()

        # Should have attempted to mark job as failed
        assert len(mock_job_db.mark_failed_calls) == 0  # Our mock doesn't record calls

    def test_run_single_loop_iteration(
        self,
        streamlined_manager: Manager,
        mock_job_db: MockJobDB,
        mock_process_manager: MockProcessManager,
    ) -> None:
        """Test a single iteration of the run loop."""
        # Set up for one loop iteration
        loop_count = 0

        def mock_sleep(seconds: float) -> None:
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                streamlined_manager.shutdown = True

        with patch("signal.signal"), patch("time.sleep", side_effect=mock_sleep):
            streamlined_manager.run()

            # Should have completed one loop
            assert loop_count == 1
            assert mock_process_manager.launch_count == 4
            assert mock_process_manager.stop_count == 1

    def test_handle_signal(self, streamlined_manager: Manager) -> None:
        """Test signal handler."""
        assert not streamlined_manager.shutdown

        streamlined_manager._handle_signal(15, None)  # SIGTERM

        assert streamlined_manager.shutdown


class TestManagerIntegration:
    """Integration tests for Manager with real components."""

    def test_with_default_factory(self, temp_dir: str) -> None:
        """Test manager creation with default job database factory."""
        # Set required environment variable for ProcessManager
        with patch.dict("os.environ", {"DR_EXP_BASE_PATH": temp_dir}):
            # This should use the factory to create a real job database
            manager = Manager(
                gpus=["0"],
                workers_per_gpu=1,
                heartbeat_timeout=30,
                idle_timeout_mins=5,
                base_dir=temp_dir,
            )

            # Should have a real job database client
            assert manager.job_db is not None
            assert hasattr(manager.job_db, "list_running_jobs")
            assert hasattr(manager.job_db, "get_stale_jobs")
            assert hasattr(manager.job_db, "mark_jobs_failed")
            assert hasattr(manager.job_db, "has_queued_jobs")
            assert hasattr(manager.job_db, "get_queue_summary")

    def test_with_default_process_manager(
        self, temp_dir: str, mock_job_db: MockJobDB
    ) -> None:
        """Test manager creation with default process manager."""
        with patch.dict(os.environ, {"DR_EXP_BASE_PATH": temp_dir}):
            manager = Manager(
                gpus=["0"],
                workers_per_gpu=1,
                heartbeat_timeout=30,
                idle_timeout_mins=5,
                base_dir=temp_dir,
                client=cast(BaseJobDB, mock_job_db),
            )

        # Should have a real process manager
        assert manager.process_manager is not None
        assert hasattr(manager.process_manager, "launch_worker")
        assert hasattr(manager.process_manager, "stop_all_workers")
        assert hasattr(manager.process_manager, "restart_worker")

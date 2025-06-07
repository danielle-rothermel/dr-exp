"""Tests for the Manager implementation."""

import os
import tempfile
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch

from dr_exp.manage.manager import Manager
from dr_exp.manage.process_manager import MockProcessManager
from dr_exp.job_db import StaleJobInfo


class MockJobDB:
    """Mock job database for testing."""
    
    def __init__(self):
        self.running_jobs = []
        self.stale_jobs = []
        self.has_queued = False
        self.queue_summary = []
        self.mark_failed_calls = []
    
    def list_running_jobs(self):
        return self.running_jobs
    
    def get_stale_jobs(self, max_age_seconds):
        return self.stale_jobs
    
    def mark_jobs_failed(self, job_ids, reason="worker_lost"):
        self.mark_failed_calls.append({"job_ids": job_ids, "reason": reason})
        return {job_id: True for job_id in job_ids}
    
    def has_queued_jobs(self):
        return self.has_queued
    
    def get_queue_summary(self, limit=5):
        return self.queue_summary[:limit]


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_job_db():
    """Create a mock job database."""
    return MockJobDB()


@pytest.fixture
def mock_process_manager():
    """Create a mock process manager."""
    return MockProcessManager()


@pytest.fixture
def streamlined_manager(temp_dir, mock_job_db, mock_process_manager):
    """Create a Manager for testing."""
    return Manager(
        gpus=["0", "1"],
        workers_per_gpu=2,
        heartbeat_timeout=30,
        idle_timeout_mins=5,
        base_dir=temp_dir,
        client=mock_job_db,
        process_manager=mock_process_manager
    )


class TestManager:
    """Test the Manager implementation."""
    
    def test_initialization(self, streamlined_manager, temp_dir, mock_job_db, mock_process_manager):
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
    
    def test_start_workers(self, streamlined_manager, mock_process_manager):
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
    
    def test_stop_all_workers(self, streamlined_manager, mock_process_manager):
        """Test stopping all workers."""
        streamlined_manager.start_workers()
        assert mock_process_manager.get_worker_count() == 4
        
        streamlined_manager.stop_all_workers()
        assert mock_process_manager.stop_count == 1
        
        # Workers should be marked as not alive
        worker_status = mock_process_manager.get_worker_status()
        assert all(not status["alive"] for status in worker_status.values())
    
    def test_check_stale_jobs_no_stale_jobs(self, streamlined_manager, mock_job_db):
        """Test stale job checking when no stale jobs exist."""
        mock_job_db.stale_jobs = []
        
        streamlined_manager.check_stale_jobs()
        
        # No jobs should be marked as failed
        assert len(mock_job_db.mark_failed_calls) == 0
    
    def test_check_stale_jobs_with_stale_jobs(self, streamlined_manager, mock_job_db, mock_process_manager):
        """Test stale job checking with stale jobs."""
        # Create stale jobs
        now = datetime.now(timezone.utc)
        stale_time = now - timedelta(minutes=5)
        
        mock_job_db.stale_jobs = [
            StaleJobInfo(
                job_id="job1",
                assigned_worker="worker_0_0",
                last_heartbeat=stale_time,
                age_seconds=300
            ),
            StaleJobInfo(
                job_id="job2", 
                assigned_worker="worker_1_0",
                last_heartbeat=stale_time,
                age_seconds=300
            )
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
    
    def test_check_idle_timeout_with_running_jobs(self, streamlined_manager, mock_job_db):
        """Test idle timeout check when there are running jobs."""
        # Set up running jobs
        mock_job_db.running_jobs = [
            {"id": "job1", "status": "running"},
            {"id": "job2", "status": "running"}
        ]
        
        # Set last activity to 10 minutes ago
        streamlined_manager.last_activity = datetime.now(timezone.utc) - timedelta(minutes=10)
        
        streamlined_manager.check_idle_timeout()
        
        # Should reset last activity and not shutdown
        assert datetime.now(timezone.utc) - streamlined_manager.last_activity < timedelta(seconds=5)
        assert not streamlined_manager.shutdown
    
    def test_check_idle_timeout_no_jobs_within_timeout(self, streamlined_manager, mock_job_db):
        """Test idle timeout check with no jobs but within timeout."""
        # No running jobs
        mock_job_db.running_jobs = []
        mock_job_db.has_queued = False
        
        # Set last activity to 2 minutes ago (less than 5 minute timeout)
        streamlined_manager.last_activity = datetime.now(timezone.utc) - timedelta(minutes=2)
        
        streamlined_manager.check_idle_timeout()
        
        # Should not shutdown
        assert not streamlined_manager.shutdown
    
    def test_check_idle_timeout_exceeds_timeout(self, streamlined_manager, mock_job_db):
        """Test idle timeout check when timeout is exceeded."""
        # No running jobs
        mock_job_db.running_jobs = []
        mock_job_db.has_queued = False
        
        # Set last activity to 10 minutes ago (exceeds 5 minute timeout)
        streamlined_manager.last_activity = datetime.now(timezone.utc) - timedelta(minutes=10)
        
        streamlined_manager.check_idle_timeout()
        
        # Should shutdown
        assert streamlined_manager.shutdown
    
    def test_check_idle_timeout_with_queued_jobs(self, streamlined_manager, mock_job_db):
        """Test idle timeout check logs queued jobs."""
        # No running jobs but some queued
        mock_job_db.running_jobs = []
        mock_job_db.has_queued = True
        mock_job_db.queue_summary = [
            {"id": "job1", "priority": 800},
            {"id": "job2", "priority": 500}
        ]
        
        # Should not affect timeout logic
        streamlined_manager.last_activity = datetime.now(timezone.utc) - timedelta(minutes=2)
        
        streamlined_manager.check_idle_timeout()
        
        # Should not shutdown (within timeout)
        assert not streamlined_manager.shutdown
    
    def test_log_status(self, streamlined_manager, mock_job_db, mock_process_manager):
        """Test status logging."""
        # Set up test data
        mock_job_db.running_jobs = [{"id": "job1"}, {"id": "job2"}]
        mock_job_db.has_queued = True
        
        streamlined_manager.start_workers()
        
        # Should not raise any exceptions
        streamlined_manager.log_status()
    
    @patch('signal.signal')
    def test_signal_handling(self, mock_signal, streamlined_manager):
        """Test signal handling setup."""
        # Mock the signal handling to avoid actual signal registration
        with patch.object(streamlined_manager, 'start_workers'), \
             patch.object(streamlined_manager, 'stop_all_workers'):
            
            # Set shutdown to True immediately to exit the loop
            streamlined_manager.shutdown = True
            
            streamlined_manager.run()
            
            # Should have registered signal handlers
            assert mock_signal.call_count >= 2
    
    def test_run_with_immediate_shutdown(self, streamlined_manager, mock_process_manager):
        """Test run method with immediate shutdown."""
        # Set shutdown flag to exit immediately
        streamlined_manager.shutdown = True
        
        with patch('signal.signal'), \
             patch('time.sleep'):
            
            streamlined_manager.run()
            
            # Workers should have been started and stopped
            assert mock_process_manager.launch_count == 4
            assert mock_process_manager.stop_count == 1
    
    def test_run_single_loop_iteration(self, streamlined_manager, mock_job_db, mock_process_manager):
        """Test a single iteration of the run loop."""
        # Set up for one loop iteration
        loop_count = 0
        original_sleep = None
        
        def mock_sleep(seconds):
            nonlocal loop_count
            loop_count += 1
            if loop_count >= 1:
                streamlined_manager.shutdown = True
        
        with patch('signal.signal'), \
             patch('time.sleep', side_effect=mock_sleep):
            
            streamlined_manager.run()
            
            # Should have completed one loop
            assert loop_count == 1
            assert mock_process_manager.launch_count == 4
            assert mock_process_manager.stop_count == 1
    
    def test_handle_signal(self, streamlined_manager):
        """Test signal handler."""
        assert not streamlined_manager.shutdown
        
        streamlined_manager._handle_signal(15, None)  # SIGTERM
        
        assert streamlined_manager.shutdown


class TestManagerIntegration:
    """Integration tests for Manager with real components."""
    
    def test_with_default_factory(self, temp_dir):
        """Test manager creation with default job database factory."""
        # This should use the factory to create a real job database
        manager = Manager(
            gpus=["0"],
            workers_per_gpu=1,
            heartbeat_timeout=30,
            idle_timeout_mins=5,
            base_dir=temp_dir
        )
        
        # Should have a real job database client
        assert manager.job_db is not None
        assert hasattr(manager.job_db, 'list_running_jobs')
        assert hasattr(manager.job_db, 'get_stale_jobs')
        assert hasattr(manager.job_db, 'mark_jobs_failed')
        assert hasattr(manager.job_db, 'has_queued_jobs')
        assert hasattr(manager.job_db, 'get_queue_summary')
    
    def test_with_default_process_manager(self, temp_dir, mock_job_db):
        """Test manager creation with default process manager."""
        manager = Manager(
            gpus=["0"],
            workers_per_gpu=1,
            heartbeat_timeout=30,
            idle_timeout_mins=5,
            base_dir=temp_dir,
            client=mock_job_db
        )
        
        # Should have a real process manager
        assert manager.process_manager is not None
        assert hasattr(manager.process_manager, 'launch_worker')
        assert hasattr(manager.process_manager, 'stop_all_workers')
        assert hasattr(manager.process_manager, 'restart_worker')
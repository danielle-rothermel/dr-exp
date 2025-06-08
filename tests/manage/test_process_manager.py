"""Simplified tests for process manager implementations."""

import os
import tempfile
import pytest
from unittest.mock import patch

from dr_exp.manage.process_manager import (
    ProcessManager,
    MockProcessManager,
    BaseProcessManager,
    run_worker_main,
    _worker_target,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestBaseProcessManager:
    """Test the abstract base class."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that BaseProcessManager cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseProcessManager()

    def test_abstract_methods_required(self):
        """Test that concrete implementations must implement all abstract methods."""

        class IncompleteManager(BaseProcessManager):
            # Missing implementations
            pass

        with pytest.raises(TypeError):
            IncompleteManager()


class TestMockProcessManager:
    """Test the mock process manager."""

    def test_initialization(self):
        """Test mock manager initialization."""
        manager = MockProcessManager()

        assert manager.get_worker_count() == 0
        assert manager.launch_count == 0
        assert manager.restart_count == 0
        assert manager.stop_count == 0
        assert manager.get_worker_status() == {}

    def test_launch_worker(self):
        """Test launching workers."""
        manager = MockProcessManager()

        result1 = manager.launch_worker("worker1", "0", "/tmp")
        result2 = manager.launch_worker("worker2", "1", "/tmp")

        assert result1 is True
        assert result2 is True
        assert manager.launch_count == 2
        assert manager.get_worker_count() == 2

        status = manager.get_worker_status()
        assert len(status) == 2
        assert status["worker1"]["gpu"] == "0"
        assert status["worker1"]["alive"] is True
        assert status["worker2"]["gpu"] == "1"
        assert status["worker2"]["alive"] is True

    def test_stop_all_workers(self):
        """Test stopping all workers."""
        manager = MockProcessManager()

        manager.launch_worker("worker1", "0", "/tmp")
        manager.launch_worker("worker2", "1", "/tmp")

        manager.stop_all_workers()

        assert manager.stop_count == 1
        status = manager.get_worker_status()
        assert all(not info["alive"] for info in status.values())

    def test_restart_worker_existing(self):
        """Test restarting an existing worker."""
        manager = MockProcessManager()

        manager.launch_worker("worker1", "0", "/tmp")
        manager.stop_all_workers()  # Mark as not alive

        result = manager.restart_worker("worker1")

        assert result is True
        assert manager.restart_count == 1

        status = manager.get_worker_status()
        assert status["worker1"]["alive"] is True

    def test_restart_worker_nonexistent(self):
        """Test restarting a nonexistent worker."""
        manager = MockProcessManager()

        result = manager.restart_worker("nonexistent")

        assert result is False
        assert manager.restart_count == 0


class TestProcessManager:
    """Test the real process manager interface."""

    def test_initialization_default(self):
        """Test process manager initialization with defaults."""
        with patch.dict("os.environ", {"DR_EXP_BASE_PATH": "/test/path"}):
            manager = ProcessManager()

            assert manager.get_worker_count() == 0
            assert manager.get_worker_status() == {}
            assert manager.base_path == "/test/path"

    def test_initialization_custom_start_method(self):
        """Test process manager initialization with custom start method."""
        # Use 'spawn' as an alternative start method
        manager = ProcessManager(start_method="spawn")
        assert manager.ctx.get_start_method() == "spawn"

    def test_initialization_invalid_start_method(self):
        """Test process manager initialization with invalid start method."""
        # Should fall back to default context
        manager = ProcessManager(start_method="invalid")
        assert manager.ctx is not None

    def test_restart_worker_nonexistent(self):
        """Test restarting a nonexistent worker."""
        manager = ProcessManager()

        result = manager.restart_worker("nonexistent")

        assert result is False

    def test_interface_methods_exist(self):
        """Test that ProcessManager implements all required interface methods."""
        manager = ProcessManager()

        # All interface methods should exist and be callable
        assert hasattr(manager, "launch_worker") and callable(manager.launch_worker)
        assert hasattr(manager, "stop_all_workers") and callable(
            manager.stop_all_workers
        )
        assert hasattr(manager, "restart_worker") and callable(manager.restart_worker)
        assert hasattr(manager, "get_worker_count") and callable(
            manager.get_worker_count
        )
        assert hasattr(manager, "get_worker_status") and callable(
            manager.get_worker_status
        )


class TestHelperFunctions:
    """Test helper functions."""

    @patch.dict("os.environ", {"DR_EXP_BASE_PATH": "/custom/path"})
    @patch("dr_exp.manage.process_manager.run_worker")
    def test_run_worker_main_custom_path(self, mock_run_worker):
        """Test run_worker_main with custom base path."""
        run_worker_main("worker1", "/work/dir")

        mock_run_worker.assert_called_once_with(
            base_path="/custom/path", work_dir="/work/dir", worker_id="worker1"
        )

    @patch.dict("os.environ", {}, clear=True)
    @patch("dr_exp.manage.process_manager.run_worker")
    def test_run_worker_main_default_path(self, mock_run_worker):
        """Test run_worker_main with default base path."""
        run_worker_main("worker1", "/work/dir")

        mock_run_worker.assert_called_once_with(
            base_path="./job_data", work_dir="/work/dir", worker_id="worker1"
        )

    @patch("os.makedirs")
    @patch.dict("os.environ", {}, clear=True)
    @patch("dr_exp.manage.process_manager.run_worker_main")
    def test_worker_target(self, mock_run_worker_main, mock_makedirs):
        """Test _worker_target function."""
        _worker_target("/base/path", "worker1", "0", "/worker/dir")

        # Should set environment variables
        assert os.environ["CUDA_VISIBLE_DEVICES"] == "0"
        assert os.environ["DR_EXP_BASE_PATH"] == "/base/path"

        # Should create worker directory
        mock_makedirs.assert_called_once_with("/worker/dir", exist_ok=True)

        # Should call run_worker_main
        mock_run_worker_main.assert_called_once_with(
            worker_id="worker1", work_dir="/worker/dir"
        )

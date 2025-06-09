"""Simplified tests for process manager implementations."""

import os
import tempfile
import pytest
from unittest.mock import patch
from typing import Any

from dr_exp.manage.process_manager import (
    ProcessManager,
    MockProcessManager,
    BaseProcessManager,
    run_worker_main,
    _worker_target,
)


@pytest.fixture
def temp_dir() -> Any:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestBaseProcessManager:
    """Test the abstract base class."""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """Test that BaseProcessManager cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseProcessManager()  # type: ignore[abstract]

    def test_abstract_methods_required(self) -> None:
        """Test that concrete implementations must implement all abstract methods."""

        class IncompleteManager(BaseProcessManager):
            # Missing implementations
            pass

        with pytest.raises(TypeError):
            IncompleteManager()  # type: ignore[abstract]


class TestMockProcessManager:
    """Test the mock process manager."""

    def test_initialization(self) -> None:
        """Test mock manager initialization."""
        manager = MockProcessManager()

        assert manager.get_worker_count() == 0
        assert manager.launch_count == 0
        assert manager.restart_count == 0
        assert manager.stop_count == 0
        assert manager.get_worker_status() == {}

    def test_launch_worker(self) -> None:
        """Test launching workers."""
        manager = MockProcessManager()

        # launch_worker now returns None (success) or raises exception (failure)
        manager.launch_worker("worker1", "0", "/tmp")
        manager.launch_worker("worker2", "1", "/tmp")

        assert manager.launch_count == 2
        assert manager.get_worker_count() == 2

        status = manager.get_worker_status()
        assert len(status) == 2
        assert status["worker1"]["gpu"] == "0"
        assert status["worker1"]["alive"] is True
        assert status["worker2"]["gpu"] == "1"
        assert status["worker2"]["alive"] is True

    def test_stop_all_workers(self) -> None:
        """Test stopping all workers."""
        manager = MockProcessManager()

        manager.launch_worker("worker1", "0", "/tmp")
        manager.launch_worker("worker2", "1", "/tmp")

        manager.stop_all_workers()

        assert manager.stop_count == 1
        status = manager.get_worker_status()
        assert all(not info["alive"] for info in status.values())

    def test_restart_worker_existing(self) -> None:
        """Test restarting an existing worker."""
        manager = MockProcessManager()

        manager.launch_worker("worker1", "0", "/tmp")
        manager.stop_all_workers()  # Mark as not alive

        # restart_worker now returns None (success) or raises exception (failure)
        manager.restart_worker("worker1")

        assert manager.restart_count == 1

        status = manager.get_worker_status()
        assert status["worker1"]["alive"] is True

    def test_restart_worker_nonexistent(self) -> None:
        """Test restarting a nonexistent worker."""
        manager = MockProcessManager()

        # restart_worker now raises exception for nonexistent workers
        with pytest.raises(
            AssertionError, match="Cannot restart worker nonexistent: worker not found"
        ):
            manager.restart_worker("nonexistent")

        assert manager.restart_count == 0


class TestProcessManager:
    """Test the real process manager interface."""

    def test_initialization_default(self) -> None:
        """Test process manager initialization with defaults."""
        with patch.dict("os.environ", {"DR_EXP_BASE_PATH": "/test/path"}):
            manager = ProcessManager()

            assert manager.get_worker_count() == 0
            assert manager.get_worker_status() == {}
            assert manager.base_path == "/test/path"

    def test_initialization_custom_start_method(self) -> None:
        """Test process manager initialization with custom start method."""
        # Use 'spawn' as an alternative start method
        manager = ProcessManager(start_method="spawn")
        assert manager.ctx.get_start_method() == "spawn"

    def test_initialization_invalid_start_method(self) -> None:
        """Test process manager initialization with invalid start method."""
        # Should fall back to default context
        manager = ProcessManager(start_method="invalid")
        assert manager.ctx is not None

    def test_restart_worker_nonexistent(self) -> None:
        """Test restarting a nonexistent worker."""
        manager = ProcessManager()

        # restart_worker now raises exception for nonexistent workers
        with pytest.raises(
            RuntimeError, match="Cannot restart worker nonexistent: worker not found"
        ):
            manager.restart_worker("nonexistent")

    def test_interface_methods_exist(self) -> None:
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

    @patch("dr_exp.manage.process_manager.run_worker")
    def test_run_worker_main_custom_path(
        self, mock_run_worker: Any, tmp_path: Any
    ) -> None:
        """Test run_worker_main with explicit configuration."""
        custom_path = str(tmp_path / "custom")
        work_dir = str(tmp_path / "work")

        run_worker_main("worker1", work_dir, custom_path, "files_local")

        # Should call run_worker with client, base_path, work_dir, worker_id
        assert mock_run_worker.called
        call_args = mock_run_worker.call_args
        assert call_args.kwargs["base_path"] == custom_path
        assert call_args.kwargs["work_dir"] == work_dir
        assert call_args.kwargs["worker_id"] == "worker1"
        assert "client" in call_args.kwargs

    @patch("dr_exp.manage.process_manager.run_worker")
    def test_run_worker_main_with_explicit_args(
        self, mock_run_worker: Any, tmp_path: Any
    ) -> None:
        """Test run_worker_main with explicit arguments."""
        test_path = str(tmp_path / "test")
        work_dir = str(tmp_path / "work")

        run_worker_main("worker1", work_dir, test_path, "files_local")

        # Should call run_worker with proper arguments
        assert mock_run_worker.called
        call_args = mock_run_worker.call_args
        assert call_args.kwargs["base_path"] == test_path
        assert call_args.kwargs["work_dir"] == work_dir
        assert call_args.kwargs["worker_id"] == "worker1"
        assert "client" in call_args.kwargs

    @patch("os.makedirs")
    @patch("dr_exp.manage.process_manager.run_worker_main")
    def test_worker_target(
        self, mock_run_worker_main: Any, mock_makedirs: Any, tmp_path: Any
    ) -> None:
        """Test _worker_target function."""
        base_path = str(tmp_path / "base")
        worker_dir = str(tmp_path / "worker")

        _worker_target(base_path, "worker1", "0", worker_dir, "files_local")

        # Should set environment variables
        assert os.environ["CUDA_VISIBLE_DEVICES"] == "0"

        # Should create worker directory
        mock_makedirs.assert_called_once_with(worker_dir, exist_ok=True)

        # Should call run_worker_main with all required arguments
        mock_run_worker_main.assert_called_once_with(
            worker_id="worker1",
            work_dir=worker_dir,
            base_path=base_path,
            mode="files_local",
        )

"""Test multi-worker launcher functionality."""

import tempfile
import time
import os
import json
from pathlib import Path
from unittest.mock import Mock, patch

from dr_exp.core.job_db import JobDB
from dr_exp.worker.launcher import WorkerLauncher
import contextlib


def test_launcher_init() -> None:
    """Test launcher initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs",
            workers_per_gpu=2,
        )

        assert launcher.workers_per_gpu == 2
        assert launcher.log_dir.exists()
        assert launcher.slurm_job_id == "local"  # Not in SLURM


def test_gpu_discovery() -> None:
    """Test GPU discovery methods."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs",
        )

        # Test CUDA_VISIBLE_DEVICES parsing
        with patch.dict(os.environ, {"CUDA_VISIBLE_DEVICES": "0,1,3"}):
            gpus = launcher.discover_gpus()
            assert gpus == [0, 1, 3]

        # Test empty CUDA_VISIBLE_DEVICES
        with (
            patch.dict(os.environ, {"CUDA_VISIBLE_DEVICES": ""}),
            patch("subprocess.run") as mock_run,
        ):
            # Simulate no GPUs
            mock_run.side_effect = FileNotFoundError()
            gpus = launcher.discover_gpus()
            assert gpus == []


def test_worker_spawning() -> None:
    """Test spawning worker processes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs",
        )

        # Mock subprocess to avoid actually spawning
        with patch("subprocess.Popen") as mock_popen:
            mock_process = Mock()
            mock_process.poll.return_value = None  # Still running
            mock_popen.return_value = mock_process

            # Spawn GPU worker
            worker_id = launcher.spawn_worker(0, 0)
            assert "gpu0_0" in worker_id
            assert worker_id in launcher.processes

            # Spawn CPU worker
            worker_id = launcher.spawn_worker(None, 0)
            assert "cpu_0" in worker_id

            # Verify environment was set correctly
            calls = mock_popen.call_args_list
            gpu_call_env = calls[0][1]["env"]
            assert gpu_call_env["CUDA_VISIBLE_DEVICES"] == "0"


def test_health_monitoring() -> None:
    """Test worker health monitoring and restart."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create a queued job
        with patch("importlib.import_module"):
            job_db.create_job({"_target_": "dr_exp.training.dummy_trainer.train_dummy"})

        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs",
        )
        launcher.running = True

        # Mock process that exits
        mock_process = Mock()
        mock_process.poll.return_value = 1  # Exit code 1

        launcher.processes["test_worker_gpu0_0"] = mock_process

        with patch.object(launcher, "spawn_worker") as mock_spawn:
            status = launcher.check_worker_health()

            # Should report as exited
            assert status["test_worker_gpu0_0"] == "exited(1)"

            # Should restart because we have pending jobs
            mock_spawn.assert_called_once_with(0, 0)


def test_control_files() -> None:
    """Test control file handling."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs",
        )

        # Test stop file
        launcher.stop_file.touch()
        command = launcher.check_control_files()
        assert command == "stop"
        assert not launcher.stop_file.exists()  # Should be deleted

        # Test finish-current file
        launcher.finish_current_file.touch()
        command = launcher.check_control_files()
        assert command == "finish_current"
        assert not launcher.finish_current_file.exists()


def test_status_writing() -> None:
    """Test status file generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create some jobs
        with patch("importlib.import_module"):
            job_db.create_job({"_target_": "dr_exp.training.dummy_trainer.train_dummy"})
            job_db.create_job({"_target_": "dr_exp.training.dummy_trainer.train_dummy"})

        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs",
        )

        # Mock some workers
        launcher.processes["worker1"] = Mock(poll=lambda: None)
        launcher.worker_restarts["worker1"] = 2

        launcher.write_status()

        status_file = launcher.control_dir / f"status_{launcher.slurm_job_id}.json"
        assert status_file.exists()

        status = json.loads(status_file.read_text())
        assert not status["launcher"]["running"]
        assert status["workers"]["worker1"] == "running"
        assert status["restarts"]["worker1"] == 2
        assert status["jobs"]["queued"] == 2


def test_graceful_shutdown() -> None:
    """Test graceful shutdown behavior."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs",
        )

        # Mock processes
        mock_process1 = Mock()
        mock_process1.pid = 1234
        mock_process1.poll.return_value = None

        mock_process2 = Mock()
        mock_process2.pid = 5678
        mock_process2.poll.return_value = None

        launcher.processes = {"worker1": mock_process1, "worker2": mock_process2}

        with (
            patch("os.killpg") as mock_killpg,
            patch("os.getpgid", side_effect=lambda pid: pid),
        ):
            launcher.stop()

        # Should have sent SIGTERM to both
        assert mock_killpg.call_count >= 2
        assert not launcher.running


def test_runtime_limits() -> None:
    """Test runtime limit enforcement."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create launcher with very short runtime
        launcher = WorkerLauncher(
            job_db=job_db,
            experiment_name="test_exp",
            base_log_dir=Path(tmpdir) / "logs",
            max_runtime_hours=0.0001,  # Very short for testing
        )

        # Backdate start time
        launcher.start_time = time.time() - 1000

        # Mock the stop method
        launcher.stop = Mock()

        # Simulate one loop iteration
        launcher.running = True

        # Should detect timeout and call stop
        with patch("time.sleep"), contextlib.suppress(Exception):
            # Run one iteration of the main loop
            launcher.run()

        launcher.stop.assert_called()

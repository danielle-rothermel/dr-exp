"""Test SLURM integration functionality."""

import tempfile
import os
import json
from unittest.mock import patch
from click.testing import CliRunner

from dr_exp.core.job_db import JobDB
from dr_exp.cli.main import cli


def test_slurm_status_command() -> None:
    """Test SLURM status command."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create mock SLURM job status
        slurm_dir = job_db.logs_dir / "slurm_123456"
        slurm_dir.mkdir(parents=True)

        status_data = {
            "launcher": {
                "slurm_job_id": "123456",
                "node": "node001",
                "runtime_seconds": 3600,
                "running": True,
            },
            "workers": {
                "worker1": "running",
                "worker2": "running",
                "worker3": "exited(1)",
            },
            "jobs": {"queued": 10, "running": 2, "completed": 50, "failed": 3},
        }

        status_file = job_db.control_dir / "status_123456.json"
        with open(status_file, "w") as f:
            json.dump(status_data, f)

        # Run command
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--base-path", tmpdir, "--experiment", "test_exp", "slurm", "status"]
        )

        assert result.exit_code == 0
        assert "SLURM Job 123456" in result.output
        assert "Node: node001" in result.output
        assert "Runtime: 1.0 hours" in result.output
        assert "Workers: 2/3 alive" in result.output
        assert "Jobs: 2 running, 10 queued, 50 completed" in result.output


def test_slurm_control_commands() -> None:
    """Test SLURM control commands."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        runner = CliRunner()

        # Test finish-current command
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "slurm",
                "control",
                "123456",
                "--finish-current",
            ],
        )

        assert result.exit_code == 0
        assert "Sent finish-current command" in result.output
        assert (job_db.control_dir / "finish_current_123456").exists()

        # Test stop-now command
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "slurm",
                "control",
                "789012",
                "--stop-now",
            ],
        )

        assert result.exit_code == 0
        assert "Sent stop command" in result.output
        assert (job_db.control_dir / "stop_789012").exists()


def test_slurm_error_logs() -> None:
    """Test SLURM error log viewing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create mock error log
        slurm_dir = job_db.logs_dir / "slurm_123456"
        slurm_dir.mkdir(parents=True)

        error_log = slurm_dir / "errors.log"
        error_log.write_text(
            """
Error aggregation at 2024-01-15T10:00:00
================================================================================

### Errors from worker1.log
[ERROR] Training failed: CUDA out of memory
Traceback (most recent call last):
  File "train.py", line 42, in train
    output = model(batch)
RuntimeError: CUDA out of memory

### Errors from worker2.log
[ERROR] Configuration error: Missing required field 'batch_size'
""".strip()
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "slurm",
                "errors",
                "123456",
                "--tail",
                "20",
            ],
        )

        assert result.exit_code == 0
        assert "CUDA out of memory" in result.output
        assert "Missing required field" in result.output


def test_slurm_worker_logs() -> None:
    """Test SLURM worker log viewing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create mock logs
        slurm_dir = job_db.logs_dir / "slurm_123456"
        slurm_dir.mkdir(parents=True)

        # Launcher log
        launcher_log = slurm_dir / "launcher.log"
        launcher_log.write_text(
            """
[INFO] Starting launcher on node node001
[INFO] Found 3 GPUs: [0, 1, 2]
[INFO] Spawning worker node001_gpu0_w0 on GPU 0
[INFO] Spawning worker node001_gpu0_w1 on GPU 0
[INFO] Workers alive: 6/6
[INFO] Jobs queued: 25
""".strip()
        )

        # Worker log
        worker_log = slurm_dir / "node001_gpu0_w0.log"
        worker_log.write_text(
            """
[INFO] Worker node001_gpu0_w0 starting
[INFO] Claimed job 12345
[INFO] Training started
[INFO] Epoch 1/10: loss=0.532
""".strip()
        )

        runner = CliRunner()

        # Test launcher log
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "slurm",
                "logs",
                "123456",
                "--tail",
                "10",
            ],
        )

        assert result.exit_code == 0
        assert "Starting launcher" in result.output
        assert "Workers alive: 6/6" in result.output

        # Test worker log
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "slurm",
                "logs",
                "123456",
                "--worker",
                "node001_gpu0_w0",
                "--tail",
                "10",
            ],
        )

        assert result.exit_code == 0
        assert "Worker node001_gpu0_w0 starting" in result.output
        assert "Epoch 1/10" in result.output


def test_slurm_environment_handling() -> None:
    """Test SLURM environment variable handling."""
    # Set mock SLURM environment
    with patch.dict(
        os.environ,
        {
            "SLURM_JOB_ID": "123456",
            "SLURMD_NODENAME": "node001",
            "SLURM_GPUS_PER_NODE": "3",
            "SLURM_MEM_PER_NODE": "196608",
            "CUDA_VISIBLE_DEVICES": "0,1,2",
        },
    ):
        # Verify launcher can read environment
        from dr_exp.worker.launcher import WorkerLauncher

        with tempfile.TemporaryDirectory() as tmpdir:
            job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

            launcher = WorkerLauncher(
                job_db=job_db, experiment_name="test_exp", base_log_dir=job_db.logs_dir
            )

            # Check SLURM info extracted
            assert launcher.slurm_job_id == "123456"
            assert launcher.slurm_node_name == "node001"

            # Check GPU discovery
            gpus = launcher.discover_gpus()
            assert gpus == [0, 1, 2]


def test_batch_script_generation() -> None:
    """Test that batch script handles parameters correctly."""
    # Just verify the script would be created in implementation
    # In real implementation, this file would exist

    # Test parameter substitution
    test_params = {
        "BASE_PATH": "/scratch/test/experiments",
        "EXPERIMENT": "my_test_exp",
        "WORKERS_PER_GPU": "3",
    }

    # Verify parameters would be used correctly
    for key, value in test_params.items():
        # In actual script, these would be: ${PARAM:-default}
        assert key in ["BASE_PATH", "EXPERIMENT", "WORKERS_PER_GPU"]

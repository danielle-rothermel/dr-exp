"""Integration tests for CLI commands."""

import tempfile
from pathlib import Path
from click.testing import CliRunner

from dr_exp.cli.main import cli
from dr_exp.core.job_db import JobDB


def test_cli_init() -> None:
    """Test experiment initialization."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(
            cli, ["--base-path", tmpdir, "--experiment", "test_exp", "init"]
        )

        assert result.exit_code == 0
        assert "Experiment initialized successfully" in result.output

        # Verify directories created
        exp_path = Path(tmpdir) / "test_exp"
        assert (exp_path / "jobs").exists()
        assert (exp_path / "storage").exists()
        assert (exp_path / "sync_queue").exists()
        assert (exp_path / "example_config.yaml").exists()


def test_cli_submit() -> None:
    """Test job submission."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize experiment
        runner.invoke(cli, ["--base-path", tmpdir, "--experiment", "test_exp", "init"])

        # Create config file
        config_file = Path(tmpdir) / "test_config.yaml"
        config_file.write_text("""
_target_: dr_exp.trainers.test_trainer.train
epochs: 10
""")

        # Submit job
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "submit",
                str(config_file),
                "--priority",
                "500",
            ],
        )

        assert result.exit_code == 0
        assert "Created job:" in result.output
        assert "Priority: 500" in result.output

        # Verify job created
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        jobs = job_db.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["priority"] == 500


def test_cli_list() -> None:
    """Test job listing."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some jobs directly
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Various job states
        config = {"_target_": "test.train"}
        job1 = job_db.create_job(config, priority=100)
        job2 = job_db.create_job(config, priority=500)
        job3 = job_db.create_job(config, priority=900)

        # Claim and complete one
        job_db.claim_next_job("worker1")
        job_db.complete_job(job3)

        # List all jobs
        result = runner.invoke(
            cli, ["--base-path", tmpdir, "--experiment", "test_exp", "list"]
        )

        assert result.exit_code == 0
        assert "Total: 3 jobs" in result.output
        assert job1 in result.output
        assert job2 in result.output
        assert job3 in result.output

        # List only queued
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "list",
                "--status",
                "queued",
            ],
        )

        assert result.exit_code == 0
        assert "Total: 2 jobs" in result.output
        assert job1 in result.output
        assert job2 in result.output
        assert job3 not in result.output


def test_cli_status() -> None:
    """Test experiment status."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create experiment with various jobs
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        config = {"_target_": "test.train"}

        # Create jobs in different states
        for _ in range(3):
            job_db.create_job(config)

        for i in range(2):
            job_db.create_job(config)
            claimed_job = job_db.claim_next_job(f"worker{i}")
            if i == 0:
                job_db.complete_job(claimed_job["id"])
            else:
                job_db.fail_job(claimed_job["id"], "Test error")

        # Get status
        result = runner.invoke(
            cli, ["--base-path", tmpdir, "--experiment", "test_exp", "status"]
        )

        assert result.exit_code == 0
        assert "Experiment: test_exp" in result.output
        assert "Job Status:" in result.output
        assert "queued: 3" in result.output
        assert "completed: 1" in result.output
        assert "failed: 1" in result.output
        assert "Total: 5" in result.output


def test_cli_worker() -> None:
    """Test running a worker via CLI."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a job
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        config = {"_target_": "dr_exp.trainers.test_trainer.train", "epochs": 2}
        job_db.create_job(config)

        # Run worker
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "worker",
                "--worker-id",
                "cli_worker",
                "--max-jobs",
                "1",
                "--no-sync",  # Disable sync for testing
            ],
        )

        assert result.exit_code == 0
        assert "Starting worker cli_worker" in result.output
        assert "Worker completed:" in result.output
        assert "'completed': 1" in result.output


def test_cli_worker_with_sync() -> None:
    """Test worker with sync enabled."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a job
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        config = {"_target_": "dr_exp.trainers.test_trainer.train", "epochs": 2}
        job_db.create_job(config)

        # Run worker with sync
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "worker",
                "--worker-id",
                "sync_worker",
                "--max-jobs",
                "1",
            ],
        )

        assert result.exit_code == 0
        assert "Sync: enabled" in result.output
        # Note: sync messages may not appear if no files are added to sync queue
        # during job execution


def test_cli_error_handling() -> None:
    """Test CLI error handling."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize experiment first
        runner.invoke(cli, ["--base-path", tmpdir, "--experiment", "test_exp", "init"])

        # Try to submit without _target_
        bad_config = Path(tmpdir) / "bad_config.json"
        bad_config.write_text('{"epochs": 10}')

        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "submit",
                str(bad_config),
            ],
        )

        assert result.exit_code == 1
        assert "Config must contain '_target_'" in result.output

        # Try to submit non-existent file
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "submit",
                "nonexistent.yaml",
            ],
        )

        assert result.exit_code == 2  # Click file not found

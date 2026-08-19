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

        exp_path = Path(tmpdir) / "test_exp"
        assert (exp_path / "jobs").exists()
        assert (exp_path / "storage").exists()
        assert (exp_path / "example_config.yaml").exists()


def test_cli_submit() -> None:
    """Test job submission."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        runner.invoke(cli, ["--base-path", tmpdir, "--experiment", "test_exp", "init"])

        config_dir = Path(tmpdir) / "configs"
        config_dir.mkdir()
        config_file = config_dir / "test_config.yaml"
        config_file.write_text("""
_target_: dr_exp.training.dummy_trainer.train
epochs: 10
""")

        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "submit",
                "--config-path",
                str(config_dir),
                "--config-name",
                "test_config",
                "--priority",
                "500",
            ],
        )

        assert result.exit_code == 0
        assert "Created job:" in result.output
        assert "Priority: 500" in result.output

        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        jobs = job_db.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]["priority"] == 500


def test_cli_list() -> None:
    """Test job listing."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        config = {"_target_": "dr_exp.training.dummy_trainer.train"}
        job1 = job_db.create_job(config, priority=100)
        job2 = job_db.create_job(config, priority=500)
        job3 = job_db.create_job(config, priority=900)

        job_db.claim_next_job("worker1")
        job_db.complete_job(job3)

        result = runner.invoke(
            cli, ["--base-path", tmpdir, "--experiment", "test_exp", "job", "list"]
        )

        assert result.exit_code == 0
        assert "Total: 3 jobs" in result.output
        assert job1[:12] in result.output
        assert job2[:12] in result.output
        assert job3[:12] in result.output

        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "list",
                "--status",
                "queued",
            ],
        )

        assert result.exit_code == 0
        assert "Total: 2 jobs" in result.output
        assert job1[:12] in result.output
        assert job2[:12] in result.output
        assert job3[:12] not in result.output


def test_cli_status() -> None:
    """Test experiment status."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        config = {"_target_": "dr_exp.training.dummy_trainer.train"}

        for _ in range(3):
            job_db.create_job(config)

        for i in range(2):
            job_db.create_job(config)
            claimed_job = job_db.claim_next_job(f"worker{i}")
            if i == 0:
                job_db.complete_job(claimed_job["id"])
            else:
                job_db.fail_job(claimed_job["id"], "Test error")

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
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)
        config = {"_target_": "dr_exp.training.dummy_trainer.train", "epochs": 2}
        job_db.create_job(config)

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
            ],
        )

        assert result.exit_code == 0
        assert "Starting worker cli_worker" in result.output
        assert "Worker completed:" in result.output
        assert "'completed': 1" in result.output


def test_cli_error_handling() -> None:
    """Test CLI error handling."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        runner.invoke(cli, ["--base-path", tmpdir, "--experiment", "test_exp", "init"])

        bad_config_dir = Path(tmpdir) / "bad_configs"
        bad_config_dir.mkdir()
        bad_config = bad_config_dir / "bad_config.yaml"
        bad_config.write_text("epochs: 10")

        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "submit",
                "--config-path",
                str(bad_config_dir),
                "--config-name",
                "bad_config",
            ],
        )

        assert result.exit_code == 1
        assert "Config must contain '_target_'" in result.output

        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "test_exp",
                "job",
                "submit",
                "--config-path",
                str(bad_config_dir),
                "--config-name",
                "nonexistent",
            ],
        )

        assert result.exit_code == 1

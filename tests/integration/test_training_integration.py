"""Integration tests for training functionality."""

import json
import re
import tempfile
from pathlib import Path

from click.testing import CliRunner

from dr_exp.cli.main import cli
from dr_exp.core.job_db import JobDB
from dr_exp.worker.base import Worker


def test_basic_training_integration() -> None:
    """Test basic training integration using dummy trainer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        config = {
            "_target_": "dr_exp.training.dummy_trainer.train",
            "epochs": 3,
            "batch_size": 32,
            "learning_rate": 0.001,
        }

        job_id = job_db.create_job(config)

        worker = Worker(job_db=job_db, worker_id="test_worker")
        status = worker.run_one_job()

        assert status == "completed"

        job = job_db.get_job(job_id)
        assert job["status"] == "completed"
        assert "final_metrics" in job
        assert "loss" in job["final_metrics"]

        storage_path = job_db.get_storage_path(job_id)
        assert (storage_path / "model_final.pt").exists()
        assert (storage_path / "metrics.json").exists()
        assert (storage_path / "config.json").exists()

        metrics = json.loads((storage_path / "metrics.json").read_text())
        assert len(metrics) == 3


def test_trainer_error_handling() -> None:
    """Test trainer error handling."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        config = {
            "_target_": "dr_exp.training.dummy_trainer.train",
            "epochs": 5,
            "fail_rate": 1.0,
        }

        job_id = job_db.create_job(config)

        worker = Worker(job_db=job_db, worker_id="test_worker")
        status = worker.run_one_job()

        assert status == "failed"

        job = job_db.get_job(job_id)
        assert job["status"] == "failed"
        assert "Simulated failure" in job["error"]

        storage_path = job_db.get_storage_path(job_id)
        assert (storage_path / "error.txt").exists()

        error_content = (storage_path / "error.txt").read_text()
        assert "RuntimeError" in error_content
        assert "Traceback" in error_content


def test_full_integration() -> None:
    """Test complete integration from job submission to completion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = CliRunner()

        result = runner.invoke(
            cli, ["--base-path", tmpdir, "--experiment", "integration_test", "init"]
        )
        assert result.exit_code == 0

        config_file = Path(tmpdir) / "train_config.yaml"
        config_file.write_text("""
_target_: dr_exp.training.dummy_trainer.train
epochs: 2
batch_size: 16
learning_rate: 0.001
""")

        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "integration_test",
                "job",
                "submit",
                "--config-path",
                str(config_file.parent),
                "--config-name",
                config_file.stem,
                "--priority",
                "800",
            ],
        )
        assert result.exit_code == 0

        match = re.search(r"Created job: ([\w-]+)", result.output)
        assert match
        job_id = match.group(1)
        job_id_short = job_id[:12]

        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "integration_test",
                "worker",
                "--worker-id",
                "integration_worker",
                "--max-jobs",
                "1",
            ],
        )
        assert result.exit_code == 0
        assert "'completed': 1" in result.output

        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "integration_test",
                "job",
                "list",
                "--status",
                "completed",
            ],
        )
        assert result.exit_code == 0
        assert job_id_short in result.output

        job_db = JobDB(
            base_path=tmpdir, experiment_name="integration_test", validate=False
        )
        storage_path = job_db.get_storage_path(job_id)

        for filename in ["model_final.pt", "metrics.json", "config.json"]:
            assert (storage_path / filename).exists(), f"Missing {filename}"

        job = job_db.get_job(job_id)
        assert "loss" in job["final_metrics"]

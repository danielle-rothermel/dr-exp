"""Integration tests for training functionality."""

import tempfile
import json
from pathlib import Path
from typing import Any

from dr_exp.core.job_db import JobDB
from dr_exp.worker.base import Worker


def test_basic_training_integration() -> None:
    """Test basic training integration using test trainer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create job
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        config = {
            "_target_": "dr_exp.trainers.test_trainer.train",
            "epochs": 3,
            "batch_size": 32,
            "learning_rate": 0.001,
        }

        job_id = job_db.create_job(config)

        # Run with worker
        worker = Worker(job_db=job_db, worker_id="test_worker")
        status = worker.run_one_job()

        assert status == "completed"

        # Verify job results
        job = job_db.get_job(job_id)
        assert job["status"] == "completed"
        assert "final_metrics" in job

        metrics = job["final_metrics"]
        assert "final_accuracy" in metrics
        assert "total_epochs" in metrics
        assert metrics["total_epochs"] == 3

        # Verify artifacts
        storage_path = job_db.get_storage_path(job_id)
        assert (storage_path / "model_final.pt").exists()
        assert (storage_path / "metrics.jsonl").exists()
        assert (storage_path / "config.json").exists()
        assert (storage_path / "events.jsonl").exists()

        # Check metrics file content
        with (storage_path / "metrics.jsonl").open() as f:
            lines = f.readlines()
            assert len(lines) == 3  # One per epoch

            # Check structure
            first_entry = json.loads(lines[0])
            assert "epoch" in first_entry["metrics"]
            assert "metrics" in first_entry
            assert "timestamp" in first_entry


def test_trainer_error_handling() -> None:
    """Test trainer error handling and logging."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create a config that will cause an error
        config = {
            "_target_": "dr_exp.trainers.test_trainer.train",
            "epochs": 5,
            "fail_rate": 1.0,  # Will cause failure
        }

        job_id = job_db.create_job(config)

        # Run with worker
        worker = Worker(job_db=job_db, worker_id="test_worker")
        status = worker.run_one_job()

        assert status == "failed"

        # Verify error captured
        job = job_db.get_job(job_id)
        assert job["status"] == "failed"
        assert "Simulated training failure" in job["error"]

        # Verify error artifact
        storage_path = job_db.get_storage_path(job_id)
        assert (storage_path / "error.txt").exists()

        error_content = (storage_path / "error.txt").read_text()
        assert "RuntimeError" in error_content
        assert "Traceback" in error_content


def test_worker_artifact_discovery() -> None:
    """Test that worker discovers and queues all artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        config = {
            "_target_": "dr_exp.trainers.test_trainer.train",
            "epochs": 2,
            "batch_size": 16,
        }

        job_db.create_job(config)

        # Track what gets queued
        queued_files = []

        # Custom worker that tracks sync queue
        class TrackingWorker(Worker):
            def add_artifact_to_sync(
                self,
                job_id: str,
                file_path: str,
                file_type: str,
                metadata: dict[str, Any] | None = None,
            ) -> None:
                queued_files.append((Path(file_path).name, file_type))
                super().add_artifact_to_sync(job_id, file_path, file_type, metadata)

        worker = TrackingWorker(job_db=job_db, worker_id="tracking_worker")
        worker.run_one_job()

        # Check what was queued
        file_types = {ft for _, ft in queued_files}
        assert "metrics" in file_types
        assert "model" in file_types
        assert "logs" in file_types

        # Verify specific files
        file_names = {fn for fn, _ in queued_files}
        assert "metrics.jsonl" in file_names
        assert "model_final.pt" in file_names
        assert "events.jsonl" in file_names


def test_full_integration() -> None:
    """Test complete integration from job submission to completion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from click.testing import CliRunner
        from dr_exp.cli.main import cli

        runner = CliRunner()

        # Initialize experiment
        result = runner.invoke(
            cli, ["--base-path", tmpdir, "--experiment", "integration_test", "init"]
        )
        assert result.exit_code == 0

        # Create config file
        config_file = Path(tmpdir) / "train_config.yaml"
        config_file.write_text("""
_target_: dr_exp.trainers.test_trainer.train
epochs: 2
batch_size: 16
learning_rate: 0.001
""")

        # Submit job
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
        job_output = result.output

        # Extract job ID from output
        import re

        match = re.search(r"Created job: ([\w-]+)", job_output)
        assert match
        job_id = match.group(1)
        job_id_short = job_id[:12]  # CLI shows truncated IDs

        # Run worker
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
                "--no-sync",
            ],
        )
        assert result.exit_code == 0
        assert "'completed': 1" in result.output

        # Check job status
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

        # Validate artifacts exist
        job_db = JobDB(
            base_path=tmpdir, experiment_name="integration_test", validate=False
        )
        storage_path = job_db.get_storage_path(job_id)

        expected_files = [
            "model_final.pt",
            "metrics.jsonl",
            "config.json",
            "events.jsonl",
        ]

        for filename in expected_files:
            assert (storage_path / filename).exists(), f"Missing {filename}"

        # Check final metrics
        job = job_db.get_job(job_id)
        assert job["final_metrics"]["total_epochs"] == 2
        assert job["final_metrics"]["final_accuracy"] > 0

"""Test training integration."""

import tempfile
import json
from pathlib import Path
from typing import Any

from dr_exp.core.job_db import JobDB
from dr_exp.worker.base import Worker
from dr_exp.logging.structured_logger import StructuredLogger


def test_structured_logger() -> None:
    """Test structured logger functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = StructuredLogger(tmpdir, "test_job", "test_worker")

        # Log config
        config = {"model": {"name": "resnet18"}, "epochs": 10}
        logger.log_config(config)

        # Log metrics
        for i in range(5):
            logger.log_metrics({"loss": 1.0 / (i + 1), "accuracy": i / 5}, step=i)

        # Log events
        logger.log_event("checkpoint_saved", {"epoch": 3})

        # Use phase context
        with logger.phase("validation"):
            logger.log_metrics({"val_loss": 0.5})

        # Verify files created
        assert logger.config_file.exists()
        assert logger.metrics_file.exists()
        assert logger.events_file.exists()
        assert logger.metadata_file.exists()

        # Verify content
        with open(logger.config_file) as f:
            saved_config = json.load(f)
            assert saved_config == config

        # Check metrics entries
        with open(logger.metrics_file) as f:
            lines = f.readlines()
            assert len(lines) == 6  # 5 + 1 validation

            first_entry = json.loads(lines[0])
            assert first_entry["step"] == 0
            assert first_entry["metrics"]["loss"] == 1.0

        # Check events
        with open(logger.events_file) as f:
            events = [json.loads(line) for line in f]
            event_types = [e["event_type"] for e in events]
            assert "checkpoint_saved" in event_types
            assert "validation_start" in event_types
            assert "validation_end" in event_types

        # Test summary
        summary = logger.get_summary()
        assert summary["metrics_entries"] == 6
        assert summary["events_entries"] == 3
        assert summary["final_metrics"]["val_loss"] == 0.5


def test_decon_classification_trainer() -> None:
    """Test deconCNN classification trainer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create job
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        config = {
            "_target_": "dr_exp.trainers.decon_trainer.train_classification",
            "model": {"architecture": "resnet18", "num_classes": 10},
            "optim": {"name": "adamw", "lr": 0.001},
            "epochs": 5,
            "batch_size": 32,
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
        assert "final_train_accuracy" in metrics
        assert "final_val_accuracy" in metrics
        assert "best_val_accuracy" in metrics
        assert metrics["total_epochs"] == 5

        # Verify artifacts
        storage_path = job_db.get_storage_path(job_id)
        assert (storage_path / "model_final.pt").exists()
        assert (storage_path / "metrics.jsonl").exists()
        assert (storage_path / "config.json").exists()
        assert (storage_path / "events.jsonl").exists()

        # Check metrics file content
        with open(storage_path / "metrics.jsonl") as f:
            lines = f.readlines()
            assert len(lines) == 5  # One per epoch

            # Check progression
            first_metrics = json.loads(lines[0])["metrics"]
            last_metrics = json.loads(lines[-1])["metrics"]
            assert last_metrics["train_accuracy"] > first_metrics["train_accuracy"]


def test_decon_autoencoder_trainer() -> None:
    """Test deconCNN autoencoder trainer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        config = {
            "_target_": "dr_exp.trainers.decon_trainer.train_autoencoder",
            "model": {"encoder_dims": [784, 256, 64], "decoder_dims": [64, 256, 784]},
            "optim": {"name": "adam", "lr": 0.0001},
            "epochs": 10,
            "reconstruction_weight": 2.0,
        }

        job_id = job_db.create_job(config)

        # Run with worker
        worker = Worker(job_db=job_db, worker_id="test_worker")
        status = worker.run_one_job()

        assert status == "completed"

        # Verify results
        job = job_db.get_job(job_id)
        metrics = job["final_metrics"]
        assert "reconstruction_loss" in metrics
        assert "total_loss" in metrics

        # Verify model saved
        storage_path = job_db.get_storage_path(job_id)
        assert (storage_path / "autoencoder_final.pt").exists()


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
            "_target_": "dr_exp.trainers.decon_trainer.train_classification",
            "model": {"architecture": "resnet50"},
            "optim": {"lr": 0.01},
            "epochs": 3,
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
        assert any("checkpoint" in fn for fn in file_names)


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
_target_: dr_exp.trainers.decon_trainer.train_classification
model:
  architecture: efficientnet_b0
  num_classes: 100
optim:
  name: sgd
  lr: 0.1
  momentum: 0.9
epochs: 10
batch_size: 256
""")

        # Submit job
        result = runner.invoke(
            cli,
            [
                "--base-path",
                tmpdir,
                "--experiment",
                "integration_test",
                "submit",
                str(config_file),
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
                "list",
                "--status",
                "completed",
            ],
        )
        assert result.exit_code == 0
        assert job_id in result.output

        # Validate artifacts exist
        job_db = JobDB(
            base_path=tmpdir, experiment_name="integration_test", validate=False
        )
        storage_path = job_db.get_storage_path(job_id)

        expected_files = [
            "model_final.pt",
            "metrics.jsonl",
            "config.json",
            "metadata.json",
            "events.jsonl",
        ]

        for filename in expected_files:
            assert (storage_path / filename).exists(), f"Missing {filename}"

        # Check final metrics
        job = job_db.get_job(job_id)
        assert job["final_metrics"]["total_epochs"] == 10
        assert job["final_metrics"]["final_val_accuracy"] > 0

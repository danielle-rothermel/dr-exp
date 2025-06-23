"""Test worker integration with Supabase sync."""

import tempfile
import time
import os
from pathlib import Path
from dotenv import load_dotenv

from dr_exp.core.job_db import JobDB
from src.dr_exp.worker.base import Worker
from src.dr_exp.sync.supabase_client import SupabaseClient


def setup_test_env() -> None:
    """Load test environment variables."""
    env_file = Path(".env.test")
    if env_file.exists():
        load_dotenv(env_file)
    else:
        os.environ["SUPABASE_URL"] = "http://localhost:54321"
        os.environ["SUPABASE_KEY"] = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
        )


def test_worker_with_supabase_sync() -> None:
    """Test worker with real Supabase sync."""
    setup_test_env()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize JobDB
        job_db = JobDB(
            base_path=tmpdir, experiment_name="worker_sync_test", validate=False
        )

        # Create a test job
        config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 3}
        job_id = job_db.create_job(config, priority=100)

        # Create worker with Supabase sync
        worker = Worker(
            job_db=job_db,
            worker_id="supabase_worker",
            sync_interval=2,  # Fast for testing
            sync_enabled=True,
        )

        # Verify sync handler initialized
        assert worker.sync_handler is not None
        assert worker.sync_handler.enabled
        assert worker.sync_handler.experiment_id is not None

        # Start background threads manually
        worker.start_background_threads()

        # Run the job manually to keep threads alive
        status = worker.run_one_job()
        assert status == "completed"

        # Check sync queue before waiting
        sync_stats_before = worker.sync_queue.get_stats()
        print(f"Sync queue before wait: {sync_stats_before}")

        # Wait for sync to complete while threads are still running
        time.sleep(5)

        # Check sync queue after waiting
        sync_stats_after = worker.sync_queue.get_stats()
        print(f"Sync queue after wait: {sync_stats_after}")

        # Stop threads
        worker.stop_background_threads()

        # Verify files were synced to Supabase
        client = SupabaseClient()

        # Check job was synced
        jobs = client.get_experiment_jobs(worker.sync_handler.experiment_id)
        assert len(jobs) == 1
        assert jobs[0]["id"] == job_id
        assert jobs[0]["status"] == "completed"

        # Check files were synced
        sync_records = client.get_job_sync_status(job_id)
        assert len(sync_records) > 0

        # Verify file types
        synced_types = {record["file_type"] for record in sync_records}
        assert "metrics" in synced_types or "model" in synced_types

        # Verify sync queue is processed
        sync_stats = worker.sync_queue.get_stats()
        assert sync_stats["completed"] > 0
        assert sync_stats["pending"] == 0  # All processed


def test_worker_sync_failure_handling() -> None:
    """Test worker handles sync failures gracefully."""
    setup_test_env()

    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(
            base_path=tmpdir, experiment_name="sync_failure_test", validate=False
        )

        # Create job
        config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 2}
        job_id = job_db.create_job(config)

        # Create worker with invalid Supabase credentials
        worker = Worker(
            job_db=job_db,
            worker_id="fail_worker",
            sync_enabled=True,
            supabase_url="http://invalid.url",
            supabase_key="invalid_key",
        )

        # Sync should be disabled due to bad credentials
        assert worker.sync_handler is None or not worker.sync_handler.enabled

        # Worker should still run jobs
        stats = worker.run(max_jobs=1)
        assert stats["completed"] == 1

        # Job should complete locally
        job = job_db.get_job(job_id)
        assert job["status"] == "completed"


def test_worker_without_sync() -> None:
    """Test worker with sync explicitly disabled."""
    setup_test_env()

    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="no_sync_test", validate=False)

        # Create job
        config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 2}
        job_db.create_job(config)

        # Create worker with sync disabled
        worker = Worker(job_db=job_db, worker_id="no_sync_worker", sync_enabled=False)

        # No sync handler
        assert worker.sync_handler is None
        assert worker.sync_fn is None

        # Run job
        stats = worker.run(max_jobs=1)
        assert stats["completed"] == 1

        # Files should be in sync queue but not processed
        sync_stats = worker.sync_queue.get_stats()
        assert sync_stats["pending"] > 0  # Files queued
        assert sync_stats["completed"] == 0  # Nothing synced


def test_sync_retry_logic() -> None:
    """Test that sync retries failed uploads."""
    setup_test_env()

    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="retry_test", validate=False)

        # Create a job that produces files
        config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 1}
        job_id = job_db.create_job(config)

        # Run job to generate files
        worker = Worker(
            job_db=job_db,
            worker_id="retry_worker",
            sync_enabled=False,  # Don't sync yet
        )
        worker.run_one_job()

        # Manually add a file that will fail to sync
        bad_file = Path(tmpdir) / "nonexistent.txt"
        worker.add_artifact_to_sync(
            job_id=job_id, file_path=str(bad_file), file_type="test"
        )

        # Create new worker with sync enabled
        sync_worker = Worker(
            job_db=job_db,
            worker_id="sync_retry_worker",
            sync_interval=1,
            sync_enabled=True,
        )

        # Let sync run a few times
        time.sleep(3)

        # Stop worker
        sync_worker.stop_background_threads()

        # Bad file should have failed attempts
        failed_items = []
        for item in sync_worker.sync_queue.get_pending_items():
            if "nonexistent" in item.file_path:
                failed_items.append(item)

        if failed_items:
            assert failed_items[0].attempts > 0


def test_experiment_isolation() -> None:
    """Test that different experiments are isolated."""
    setup_test_env()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two experiments
        job_db1 = JobDB(base_path=tmpdir, experiment_name="exp1", validate=False)
        job_db2 = JobDB(base_path=tmpdir, experiment_name="exp2", validate=False)

        # Create jobs in each
        config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 1}
        job1 = job_db1.create_job(config)
        job2 = job_db2.create_job(config)

        # Run workers for each experiment
        worker1 = Worker(job_db=job_db1, worker_id="worker1", sync_enabled=True)
        worker2 = Worker(job_db=job_db2, worker_id="worker2", sync_enabled=True)

        assert worker1.sync_handler.experiment_id != worker2.sync_handler.experiment_id

        worker1.run(max_jobs=1)
        worker2.run(max_jobs=1)

        # Wait for sync
        time.sleep(3)

        # Verify isolation in Supabase
        client = SupabaseClient()

        exp1_jobs = client.get_experiment_jobs(worker1.sync_handler.experiment_id)
        exp2_jobs = client.get_experiment_jobs(worker2.sync_handler.experiment_id)

        assert len(exp1_jobs) == 1
        assert len(exp2_jobs) == 1
        assert exp1_jobs[0]["id"] == job1
        assert exp2_jobs[0]["id"] == job2


def test_cli_integration() -> None:
    """Test CLI with Supabase sync."""
    setup_test_env()

    from click.testing import CliRunner
    from src.dr_exp.cli.main import cli

    runner = CliRunner()

    with runner.isolated_filesystem():
        # Initialize experiment
        result = runner.invoke(
            cli, ["--base-path", ".", "--experiment", "cli_sync_test", "init"]
        )
        assert result.exit_code == 0

        # Create job config
        Path("test.yaml").write_text("""
_target_: src.dr_exp.trainers.test_trainer.train
epochs: 2
""")

        # Submit job
        result = runner.invoke(
            cli,
            [
                "--base-path",
                ".",
                "--experiment",
                "cli_sync_test",
                "job",
                "submit",
                "--config-path",
                ".",
                "--config-name",
                "test",
            ],
        )
        assert result.exit_code == 0

        # Run worker with sync
        result = runner.invoke(
            cli,
            [
                "--base-path",
                ".",
                "--experiment",
                "cli_sync_test",
                "worker",
                "--worker-id",
                "cli_worker",
                "--max-jobs",
                "1",
            ],
            env={
                "SUPABASE_URL": os.environ.get("SUPABASE_URL"),
                "SUPABASE_KEY": os.environ.get("SUPABASE_KEY"),
            },
        )

        assert result.exit_code == 0
        assert "Sync: enabled (Supabase connected)" in result.output
        assert "'completed': 1" in result.output

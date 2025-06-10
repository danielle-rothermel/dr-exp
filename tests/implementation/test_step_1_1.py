"""Test basic JobDB functionality."""

import tempfile
import shutil
from pathlib import Path

from src.dr_exp.core.job_db import JobDB


def test_jobdb_basic() -> None:
    """Test creating and retrieving jobs."""
    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize JobDB without validation (like init command)
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Verify all directories created
        exp_path = Path(tmpdir) / "test_exp"
        assert (exp_path / "jobs").exists()
        assert (exp_path / "storage").exists()
        assert (exp_path / "sync_queue").exists()
        assert (exp_path / "logs").exists()
        assert (exp_path / "control").exists()

        # Create a job
        config = {
            "_target_": "dr_exp.trainers.test_trainer.train",
            "model": "resnet18",
            "lr": 0.001,
            "epochs": 10,
        }
        job_id = job_db.create_job(config, priority=500)

        # Verify job file created
        assert (exp_path / "jobs" / f"{job_id}.json").exists()

        # Retrieve the job
        job = job_db.get_job(job_id)
        assert job is not None
        assert job["id"] == job_id
        assert job["experiment_name"] == "test_exp"
        assert job["config"] == config
        assert job["priority"] == 500
        assert job["status"] == "queued"
        assert job["worker_id"] is None

        # Test storage path
        storage_path = job_db.get_storage_path(job_id)
        assert storage_path == exp_path / "storage" / f"run_{job_id}"

        # Test validation mode
        try:
            # Delete a directory and try with validation=True
            shutil.rmtree(exp_path / "logs")
            JobDB(base_path=tmpdir, experiment_name="test_exp", validate=True)
            assert False, "Should have failed"
        except RuntimeError as e:
            assert "Missing directories" in str(e)
            assert "logs" in str(e)

        # Test input validation
        try:
            # Missing _target_
            job_db.create_job({"model": "resnet"}, priority=100)
            assert False, "Should have failed"
        except AssertionError as e:
            assert "_target_" in str(e)

        try:
            # Invalid priority
            job_db.create_job(config, priority=1500)
            assert False, "Should have failed"
        except AssertionError as e:
            assert "Priority" in str(e)

        try:
            # Invalid target module
            bad_config = {"_target_": "nonexistent.module.train"}
            job_db.create_job(bad_config, priority=100)
            assert False, "Should have failed"
        except AssertionError as e:
            assert "Cannot import" in str(e)

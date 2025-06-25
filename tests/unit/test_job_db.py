"""Unit tests for JobDB core functionality."""

from pathlib import Path

import pytest

from dr_exp.core.job_db import JobDB
from tests.utils.job_helpers import create_test_config


def test_jobdb_basic(temp_job_db: JobDB, temp_experiment_dir: Path) -> None:
    """Test creating and retrieving jobs."""
    # Verify all directories created
    exp_path = temp_experiment_dir / "test_exp"
    assert (exp_path / "jobs").exists()
    assert (exp_path / "storage").exists()
    assert (exp_path / "sync_queue").exists()
    assert (exp_path / "logs").exists()
    assert (exp_path / "control").exists()

    # Create a job using test helper
    config = create_test_config(
        model="resnet18",
        lr=0.001,
        epochs=10,
    )
    job_id = temp_job_db.create_job(config, priority=500)

    # Verify job file created
    assert (exp_path / "jobs" / f"{job_id}.json").exists()

    # Retrieve the job
    job = temp_job_db.get_job(job_id)
    assert job is not None
    assert job["id"] == job_id
    assert job["experiment_name"] == "test_exp"
    assert job["config"] == config
    assert job["priority"] == 500
    assert job["status"] == "queued"
    assert job["worker_id"] is None

    # Test storage path
    storage_path = temp_job_db.get_storage_path(job_id)
    expected_path = (exp_path / "storage" / f"run_{job_id}").resolve()
    assert storage_path == expected_path

    # Test validation mode
    # Delete a directory and try with validation=True
    import shutil

    shutil.rmtree(exp_path / "logs")
    with pytest.raises(RuntimeError, match="Missing directories.*logs"):
        JobDB(
            base_path=str(temp_experiment_dir),
            experiment_name="test_exp",
            validate=True,
        )

    # Test input validation
    # Missing _target_
    with pytest.raises(AssertionError, match="_target_"):
        temp_job_db.create_job({"model": "resnet"}, priority=100)

    # Invalid priority
    with pytest.raises(AssertionError, match="Priority"):
        temp_job_db.create_job(config, priority=1500)

    # Invalid target module
    bad_config = {"_target_": "nonexistent.module.train"}
    with pytest.raises(AssertionError, match="Cannot import"):
        temp_job_db.create_job(bad_config, priority=100)

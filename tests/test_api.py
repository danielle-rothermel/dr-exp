"""Test public API functionality."""

from pathlib import Path


from dr_exp import JobDB, submit_job


def test_submit_job_api(tmp_path: Path) -> None:
    """Test programmatic job submission."""
    # Initialize experiment directory structure
    exp_path = tmp_path / "test_exp"
    dirs = ["jobs", "storage", "sync_queue", "logs", "control"]
    for dir_name in dirs:
        (exp_path / dir_name).mkdir(parents=True, exist_ok=True)

    # Submit job via API
    config = {"_target_": "os.path.exists", "path": str(tmp_path)}
    job_id = submit_job(
        base_path=tmp_path,
        experiment="test_exp",
        config=config,
        priority=150,
        tags=["api-test"],
    )

    # Verify job was created
    assert job_id is not None
    job_db = JobDB(tmp_path, "test_exp")
    job = job_db.get_job(job_id)
    assert job["config"] == config
    assert job["priority"] == 150
    assert "api-test" in job["tags"]

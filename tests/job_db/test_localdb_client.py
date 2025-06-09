# tests/mock/test_localdb_client.py
from pathlib import Path
from typing import Dict, Any
from datetime import datetime, timezone
import pytest
import os
import json

from dr_exp.job_db import LocalJobDB, JobDBConfig

# --- Test Fixtures ---


@pytest.fixture
def mock_client(tmp_path: Path) -> LocalJobDB:
    """
    Provides a LocalJobDB instance initialized in a temporary directory.
    This ensures each test runs with a clean mock environment.
    The tmp_path fixture is provided by pytest for creating temporary files/directories.
    """
    config = JobDBConfig(
        base_path=str(tmp_path),
        storage_path=str(tmp_path / "storage"),
        mode="files_local",
    )
    client = LocalJobDB(config)
    return client


@pytest.fixture
def sample_job_config() -> Dict[str, Any]:
    """Provides a sample job configuration."""
    return {"learning_rate": 0.001, "epochs": 10, "model_name": "test_model"}


@pytest.fixture
def sample_sweep_config_id() -> str:
    """Provides a sample sweep_config_id."""
    return "sweep_cfg_abc123"


# --- Test Cases ---


def test_client_initialization(tmp_path: Path) -> None:
    """Tests if the client initializes its directories correctly."""
    config = JobDBConfig(
        base_path=str(tmp_path),
        storage_path=str(tmp_path / "storage"),
        mode="files_local",
    )
    client = LocalJobDB(config)
    assert os.path.exists(client.storage_dir)
    assert os.path.exists(client.jobs_dir)
    assert os.path.exists(client.metrics_dir)
    assert os.path.exists(client.errors_file)
    with open(client.errors_file, "r") as f:
        assert f.read() == ""  # Should be empty


def test_add_job_and_get_details(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Tests adding a new job and retrieving its details and config."""
    added_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="queued"
    )

    assert added_job is not None
    assert "id" in added_job
    job_id = added_job["id"]

    # Verify job file was created
    job_file_path = os.path.join(mock_client.jobs_dir, f"{job_id}.json")
    assert os.path.exists(job_file_path)

    with open(job_file_path, "r") as f:
        job_data_from_file = json.load(f)
        assert job_data_from_file["id"] == job_id
        assert job_data_from_file["status"] == "queued"
        assert job_data_from_file["config_json"] == sample_job_config
        assert job_data_from_file["config_id"] == sample_sweep_config_id

    # Test get_job_details
    retrieved_job_details = mock_client.get_job_details(job_id)
    assert retrieved_job_details is not None
    assert retrieved_job_details["id"] == job_id
    assert retrieved_job_details["config_json"] == sample_job_config

    # Test get_config_for_job
    retrieved_config = mock_client.get_config_for_job(job_id)
    assert retrieved_config is not None
    assert retrieved_config == sample_job_config


def test_claim_job_success(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Tests successfully claiming a queued job."""
    # Add a queued job
    mock_client.add_job(sample_job_config, sample_sweep_config_id, status="queued")

    claimed_job = mock_client.claim_job()
    assert claimed_job is not None
    assert claimed_job["status"] == "running"
    assert "assigned_worker" in claimed_job
    assert claimed_job["assigned_worker"] != "unassigned"
    assert "heartbeat" in claimed_job

    # Verify the job file reflects the change
    job_details = mock_client.get_job_details(claimed_job["id"])
    assert job_details is not None
    assert job_details["status"] == "running"


def test_claim_job_no_queued_jobs(mock_client: LocalJobDB) -> None:
    """Tests claiming a job when no queued jobs are available."""
    # Add a running job
    mock_client.add_job({"config": "details"}, "sweep1", status="running")

    claimed_job = mock_client.claim_job()
    assert claimed_job is None


def test_claim_job_multiple_queued(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Tests claiming one of multiple queued jobs."""
    mock_client.add_job(sample_job_config, sample_sweep_config_id, status="queued")
    job2_config = {"learning_rate": 0.01}
    mock_client.add_job(job2_config, "sweep_cfg_xyz789", status="queued")

    claimed_job1 = mock_client.claim_job()
    assert claimed_job1 is not None
    assert claimed_job1["status"] == "running"

    claimed_job2 = mock_client.claim_job()
    assert claimed_job2 is not None
    assert claimed_job2["status"] == "running"

    assert (
        claimed_job1["id"] != claimed_job2["id"]
    )  # Make sure different jobs were claimed

    # No more queued jobs
    assert mock_client.claim_job() is None


def test_claim_job_with_worker_id(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    mock_client.add_job(sample_job_config, sample_sweep_config_id, status="queued")
    job = mock_client.claim_job(worker_id="wid1")
    assert job is not None
    assert job["assigned_worker"] == "wid1"


def test_update_job(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Tests updating an existing job."""
    added_job = mock_client.add_job(sample_job_config, sample_sweep_config_id)
    job_id = added_job["id"]

    update_data = {
        "status": "running",
        "heartbeat": datetime.now(timezone.utc).isoformat(),
        "num_epochs": 5,
    }
    result = mock_client.update_job(job_id, update_data)
    assert result["success"] is True

    updated_job_details = mock_client.get_job_details(job_id)
    assert updated_job_details is not None
    assert updated_job_details["status"] == "running"
    assert updated_job_details["num_epochs"] == 5
    assert updated_job_details["heartbeat"] == update_data["heartbeat"]


def test_update_non_existent_job(mock_client: LocalJobDB) -> None:
    """Tests updating a job that does not exist."""
    result = mock_client.update_job("non_existent_job_id", {"status": "completed"})
    assert result["success"] is False
    assert "not found" in result["message"].lower()


def test_log_metrics(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Tests logging metrics for a job."""
    added_job = mock_client.add_job(sample_job_config, sample_sweep_config_id)
    job_id = added_job["id"]

    metrics_to_log = [
        {"epoch": 1, "loss": 0.5, "accuracy": 0.8},
        {"epoch": 2, "loss": 0.4, "accuracy": 0.85},
    ]
    mock_client.log_metrics(job_id, metrics_to_log)

    metric_file_path = os.path.join(mock_client.metrics_dir, f"{job_id}.jsonl")
    assert os.path.exists(metric_file_path)

    logged_lines = []
    with open(metric_file_path, "r") as f:
        for line in f:
            logged_lines.append(json.loads(line))

    assert len(logged_lines) == 2
    assert logged_lines[0]["epoch"] == 1
    assert logged_lines[0]["loss"] == 0.5
    assert "timestamp" in logged_lines[0]  # Check if timestamp was added
    assert logged_lines[1]["epoch"] == 2
    assert logged_lines[1]["accuracy"] == 0.85


def test_record_failure(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Tests recording a failure for a job."""
    added_job = mock_client.add_job(sample_job_config, sample_sweep_config_id)
    job_id = added_job["id"]

    error_type = "NaNError"
    message = "Loss became NaN"
    stacktrace = "Traceback..."

    mock_client.record_failure(job_id, error_type, message, stacktrace)

    assert os.path.exists(mock_client.errors_file)

    failure_recorded = False
    with open(mock_client.errors_file, "r") as f:
        for line in f:
            error_entry = json.loads(line)
            if error_entry["job_id"] == job_id:
                assert error_entry["error_type"] == error_type
                assert error_entry["message"] == message
                assert error_entry["stacktrace"] == stacktrace
                assert "timestamp" in error_entry
                failure_recorded = True
                break
    assert failure_recorded, "Failure was not recorded in errors.jsonl"


def test_upload_artifact_file(
    mock_client: LocalJobDB,
    tmp_path: Path,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Tests uploading a file artifact."""
    added_job = mock_client.add_job(sample_job_config, sample_sweep_config_id)
    job_id = added_job["id"]

    # Create a dummy local artifact file within the test's tmp_path scope
    local_artifact_dir = tmp_path / "local_artifacts"
    local_artifact_dir.mkdir()
    local_artifact_file = local_artifact_dir / "plot.png"
    with open(local_artifact_file, "w") as f:
        f.write("dummy plot data")

    remote_suffix = "visuals/accuracy_plot.png"  # Note: client prepends "artifacts/"
    result = mock_client.upload_artifact(
        job_id, str(local_artifact_file), remote_suffix
    )
    assert result["success"] is True

    expected_destination_path = os.path.join(
        mock_client.storage_dir, f"run_{job_id}", "artifacts", remote_suffix
    )
    assert os.path.exists(expected_destination_path)
    assert result["storage_path"] == expected_destination_path
    with open(expected_destination_path, "r") as f:
        assert f.read() == "dummy plot data"


def test_upload_artifact_root_file(
    mock_client: LocalJobDB,
    tmp_path: Path,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Tests uploading a file artifact to the root of the run directory (e.g., metrics.jsonl)."""
    added_job = mock_client.add_job(sample_job_config, sample_sweep_config_id)
    job_id = added_job["id"]

    local_metrics_file = tmp_path / "local_metrics.jsonl"
    with open(local_metrics_file, "w") as f:
        f.write('{"epoch": 1, "loss": 0.5}\n')

    remote_suffix = "metrics.jsonl"  # This should go to run_<job_id>/metrics.jsonl
    result = mock_client.upload_artifact(job_id, str(local_metrics_file), remote_suffix)
    assert result["success"] is True

    expected_destination_path = os.path.join(
        mock_client.storage_dir, f"run_{job_id}", remote_suffix
    )
    assert os.path.exists(expected_destination_path)
    assert result["storage_path"] == expected_destination_path
    with open(expected_destination_path, "r") as f:
        assert f.read() == '{"epoch": 1, "loss": 0.5}\n'


def test_upload_artifact_directory(
    mock_client: LocalJobDB,
    tmp_path: Path,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Tests uploading a directory artifact."""
    added_job = mock_client.add_job(sample_job_config, sample_sweep_config_id)
    job_id = added_job["id"]

    local_artifact_source_dir = tmp_path / "source_artifact_dir"
    local_artifact_source_dir.mkdir()
    (local_artifact_source_dir / "file1.txt").write_text("content1")
    (local_artifact_source_dir / "subdir").mkdir()
    (local_artifact_source_dir / "subdir" / "file2.txt").write_text("content2")

    remote_suffix = "my_output_folder"  # This will be under run_<job_id>/artifacts/
    result = mock_client.upload_artifact(
        job_id, str(local_artifact_source_dir), remote_suffix
    )
    assert result["success"] is True

    expected_destination_base = os.path.join(
        mock_client.storage_dir, f"run_{job_id}", "artifacts", remote_suffix
    )
    assert os.path.exists(expected_destination_base)
    assert os.path.exists(os.path.join(expected_destination_base, "file1.txt"))
    assert os.path.exists(
        os.path.join(expected_destination_base, "subdir", "file2.txt")
    )
    with open(os.path.join(expected_destination_base, "file1.txt"), "r") as f:
        assert f.read() == "content1"


def test_upload_artifact_non_existent_local(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Tests uploading a non-existent local artifact."""
    added_job = mock_client.add_job(sample_job_config, sample_sweep_config_id)
    job_id = added_job["id"]

    result = mock_client.upload_artifact(
        job_id, "non_existent_file.txt", "some_remote_path.txt"
    )
    assert result["success"] is False
    assert "not found" in result["message"].lower()


def test_finalize_job(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Tests finalizing a job."""
    added_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="running"
    )
    job_id = added_job["id"]

    final_metadata = {
        "final_val_acc": 0.95,
        "num_epochs": 10,
        "upload_complete_at": datetime.now(timezone.utc).isoformat(),
        "finalize_success": True,
    }
    result = mock_client.finalize_job(job_id, "completed", final_metadata)
    assert result["success"] is True

    finalized_job_details = mock_client.get_job_details(job_id)
    assert finalized_job_details is not None
    assert finalized_job_details["status"] == "completed"
    assert "end_time" in finalized_job_details
    assert finalized_job_details["final_val_acc"] == 0.95
    assert finalized_job_details["finalize_success"] is True
    flag_path = os.path.join(
        mock_client.storage_dir,
        f"run_{job_id}",
        "finished.flag",
    )
    assert os.path.exists(flag_path)


# --- Test for Reset Utility (Implicitly via fixture, but can add explicit if needed) ---
# The mock_client fixture using tmp_path ensures a clean state for each test.
# If you had a separate reset_mock_db function, you could test it directly.
# For now, the LocalJobDB's own re-initialization on a clean tmp_path serves this.


def test_multiple_operations_on_same_job(
    mock_client: LocalJobDB,
    tmp_path: Path,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Tests a sequence of operations on a single job."""
    # 1. Add job
    added_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="queued"
    )
    job_id = added_job["id"]

    # 2. Claim job
    claimed_job = mock_client.claim_job()  # Assumes this job is the one claimed
    assert claimed_job is not None and claimed_job["id"] == job_id
    assert claimed_job["status"] == "running"

    # 3. Log metrics
    metrics1 = [{"epoch": 1, "loss": 0.7}]
    mock_client.log_metrics(job_id, metrics1)

    # 4. Update job (e.g., heartbeat)
    mock_client.update_job(
        job_id, {"heartbeat": datetime.now(timezone.utc).isoformat()}
    )
    details_after_update = mock_client.get_job_details(job_id)
    assert details_after_update is not None
    assert details_after_update["status"] == "running"  # Should still be running

    # 5. Log more metrics
    metrics2 = [{"epoch": 2, "loss": 0.6}]
    mock_client.log_metrics(job_id, metrics2)

    # 6. Upload artifact
    local_artifact_file = tmp_path / "final_model.pt"
    local_artifact_file.write_text("model data")
    mock_client.upload_artifact(
        job_id, str(local_artifact_file), "checkpoints/final_model.pt"
    )

    # 7. Finalize job
    final_meta = {
        "final_val_acc": 0.9,
        "upload_complete_at": datetime.now(timezone.utc).isoformat(),
        "finalize_success": True,
    }
    mock_client.finalize_job(job_id, "completed", final_meta)

    # Verify final state
    final_details = mock_client.get_job_details(job_id)
    assert final_details is not None
    assert final_details["status"] == "completed"
    assert final_details["final_val_acc"] == 0.9

    metric_file_path = os.path.join(mock_client.metrics_dir, f"{job_id}.jsonl")
    with open(metric_file_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 2  # metrics1 and metrics2

    artifact_path = os.path.join(
        mock_client.storage_dir,
        f"run_{job_id}",
        "artifacts",
        "checkpoints/final_model.pt",
    )
    assert os.path.exists(artifact_path)


# --- Priority System Tests ---


def test_add_job_with_priority(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test adding a job with custom priority."""
    job = mock_client.add_job(sample_job_config, sample_sweep_config_id, priority=500)
    assert job["priority"] == 500
    assert job["priority_boost_count"] == 0

    # Test priority validation - should raise ValueError for invalid priorities
    import pytest

    with pytest.raises(
        ValueError, match="Priority must be between 0 and 1000, got 1500"
    ):
        mock_client.add_job(sample_job_config, sample_sweep_config_id, priority=1500)

    with pytest.raises(
        ValueError, match="Priority must be between 0 and 1000, got -50"
    ):
        mock_client.add_job(sample_job_config, sample_sweep_config_id, priority=-50)


def test_update_job_priority(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test updating job priority."""
    job = mock_client.add_job(sample_job_config, sample_sweep_config_id, priority=100)
    job_id = job["id"]

    # Update priority
    result = mock_client.update_job_priority(job_id, 300, reason="Urgent experiment")
    assert result["success"] is True
    assert result["old_priority"] == 100
    assert result["new_priority"] == 300

    # Verify change was persisted
    updated_job = mock_client.get_job_details(job_id)
    assert updated_job is not None
    assert updated_job["priority"] == 300
    assert len(updated_job["priority_changes"]) == 1
    assert updated_job["priority_changes"][0]["reason"] == "Urgent experiment"

    # Test updating non-existent job
    result = mock_client.update_job_priority("nonexistent", 500)
    assert result["success"] is False


def test_boost_job_priority(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test boosting job priority."""
    job = mock_client.add_job(sample_job_config, sample_sweep_config_id, priority=200)
    job_id = job["id"]

    # Boost priority
    result = mock_client.boost_job_priority(job_id, boost_amount=150)
    assert result["success"] is True
    assert result["old_priority"] == 200
    assert result["new_priority"] == 350
    assert result["boost_amount"] == 150

    # Verify boost count increased
    boosted_job = mock_client.get_job_details(job_id)
    assert boosted_job is not None
    assert boosted_job["priority"] == 350
    assert boosted_job["priority_boost_count"] == 1

    # Test boost with validation - should return failure for out-of-range result
    result = mock_client.boost_job_priority(job_id, boost_amount=800)
    assert result["success"] is False
    assert "Priority must be between 0 and 1000, got 1150" in result["message"]


def test_list_jobs_by_priority(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test listing jobs ordered by priority."""
    # Add jobs with different priorities
    job1 = mock_client.add_job(sample_job_config, sample_sweep_config_id, priority=100)
    job2 = mock_client.add_job(sample_job_config, sample_sweep_config_id, priority=500)
    job3 = mock_client.add_job(sample_job_config, sample_sweep_config_id, priority=200)
    job4 = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="running", priority=300
    )

    # List all jobs by priority
    all_jobs = mock_client.list_jobs_by_priority()
    assert len(all_jobs) == 4
    # Should be ordered by priority descending: 500, 300, 200, 100
    assert all_jobs[0]["id"] == job2["id"]  # priority 500
    assert all_jobs[1]["id"] == job4["id"]  # priority 300
    assert all_jobs[2]["id"] == job3["id"]  # priority 200
    assert all_jobs[3]["id"] == job1["id"]  # priority 100

    # Filter by status
    queued_jobs = mock_client.list_jobs_by_priority(status_filter=["queued"])
    assert len(queued_jobs) == 3
    assert queued_jobs[0]["id"] == job2["id"]  # Highest priority queued job

    # Test limit
    limited_jobs = mock_client.list_jobs_by_priority(limit=2)
    assert len(limited_jobs) == 2
    assert limited_jobs[0]["id"] == job2["id"]
    assert limited_jobs[1]["id"] == job4["id"]


def test_claim_job_respects_priority(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test that claim_job respects priority order."""
    # Add jobs with different priorities
    job1 = mock_client.add_job(sample_job_config, sample_sweep_config_id, priority=100)
    job2 = mock_client.add_job(sample_job_config, sample_sweep_config_id, priority=500)
    job3 = mock_client.add_job(sample_job_config, sample_sweep_config_id, priority=200)

    # Should claim highest priority job first
    claimed = mock_client.claim_job()
    assert claimed is not None
    assert claimed["id"] == job2["id"]  # priority 500

    # Next claim should get second highest
    claimed = mock_client.claim_job()
    assert claimed is not None
    assert claimed["id"] == job3["id"]  # priority 200

    # Last claim should get lowest
    claimed = mock_client.claim_job()
    assert claimed is not None
    assert claimed["id"] == job1["id"]  # priority 100


def test_add_reserved_job(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test adding a job reserved for specific worker."""
    reserved_job = mock_client.add_reserved_job(
        job_config=sample_job_config,
        sweep_config_id=sample_sweep_config_id,
        reserved_for_worker="worker_123",
        reservation_timeout=600,
        priority=800,
    )

    assert reserved_job["reserved_for_worker"] == "worker_123"
    assert reserved_job["priority"] == 800
    assert "reservation_expires_at" in reserved_job

    # Test reservation without timeout
    reserved_job_no_timeout = mock_client.add_reserved_job(
        job_config=sample_job_config,
        sweep_config_id=sample_sweep_config_id,
        reserved_for_worker="worker_456",
        reservation_timeout=None,
        priority=700,
    )

    assert "reservation_expires_at" not in reserved_job_no_timeout


def test_claim_job_respects_reservations(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test that claim_job respects job reservations."""
    # Add regular job and reserved job
    regular_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, priority=500
    )
    reserved_job = mock_client.add_reserved_job(
        job_config=sample_job_config,
        sweep_config_id=sample_sweep_config_id,
        reserved_for_worker="worker_123",
        priority=800,  # Higher priority but reserved
    )

    # Wrong worker should not be able to claim reserved job
    claimed = mock_client.claim_job(worker_id="worker_456", respect_reservations=True)
    assert claimed is not None
    assert claimed["id"] == regular_job["id"]  # Gets regular job instead

    # Correct worker should be able to claim reserved job
    claimed = mock_client.claim_job(worker_id="worker_123", respect_reservations=True)
    assert claimed is not None
    assert claimed["id"] == reserved_job["id"]

    # Test without respecting reservations
    reserved_job2 = mock_client.add_reserved_job(
        job_config=sample_job_config,
        sweep_config_id=sample_sweep_config_id,
        reserved_for_worker="worker_999",
        priority=900,
    )

    claimed = mock_client.claim_job(worker_id="worker_456", respect_reservations=False)
    assert claimed is not None
    assert claimed["id"] == reserved_job2["id"]  # Can claim despite reservation


# --- Tests for new helper methods ---


def test_safe_read_job_success(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test _safe_read_job successfully reads a valid job file."""
    # Add a job to create a valid job file
    added_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="queued"
    )
    job_id = added_job["id"]
    job_file_path = os.path.join(mock_client.jobs_dir, f"{job_id}.json")

    # Test reading the job file
    job_data = mock_client._safe_read_job(job_file_path)

    assert job_data is not None
    assert job_data["id"] == job_id
    assert job_data["status"] == "queued"
    assert job_data["config_json"] == sample_job_config


def test_safe_read_job_nonexistent_file(mock_client: LocalJobDB) -> None:
    """Test _safe_read_job returns None for nonexistent file."""
    nonexistent_path = os.path.join(mock_client.jobs_dir, "nonexistent.json")

    job_data = mock_client._safe_read_job(nonexistent_path)

    assert job_data is None


def test_safe_read_job_invalid_json(mock_client: LocalJobDB, tmp_path: Path) -> None:
    """Test _safe_read_job returns None for invalid JSON file."""
    # Create a file with invalid JSON
    invalid_json_path = os.path.join(mock_client.jobs_dir, "invalid.json")
    with open(invalid_json_path, "w") as f:
        f.write("{ invalid json content")

    job_data = mock_client._safe_read_job(invalid_json_path)

    assert job_data is None


def test_is_job_claimable_queued_job(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test _is_job_claimable returns True for queued job."""
    added_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="queued"
    )
    job_file_path = os.path.join(mock_client.jobs_dir, f"{added_job['id']}.json")

    claimable = mock_client._is_job_claimable(
        added_job, "worker_123", respect_reservations=True, job_file_path=job_file_path
    )

    assert claimable is True


def test_is_job_claimable_running_job(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test _is_job_claimable returns False for running job."""
    added_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="running"
    )
    job_file_path = os.path.join(mock_client.jobs_dir, f"{added_job['id']}.json")

    claimable = mock_client._is_job_claimable(
        added_job, "worker_123", respect_reservations=True, job_file_path=job_file_path
    )

    assert claimable is False


def test_is_job_claimable_ignore_reservations(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test _is_job_claimable ignores reservations when respect_reservations=False."""
    from datetime import timedelta

    # Set reservation to expire 1 hour in the future (not expired)
    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    # Create a job with a reservation for another worker
    job_data = {
        "id": "test_job_123",
        "status": "queued",
        "config_json": sample_job_config,
        "reserved_for_worker": "other_worker",
        "reservation_expires_at": future_time.isoformat() + "Z",
    }
    job_file_path = os.path.join(mock_client.jobs_dir, "test_job_123.json")

    claimable = mock_client._is_job_claimable(
        job_data, "worker_123", respect_reservations=False, job_file_path=job_file_path
    )

    assert claimable is True


def test_handle_job_reservation_no_reservation(mock_client: LocalJobDB) -> None:
    """Test _handle_job_reservation returns True when job has no reservation."""
    job_data = {"id": "test_job_123", "status": "queued"}
    job_file_path = os.path.join(mock_client.jobs_dir, "test_job_123.json")

    claimable = mock_client._handle_job_reservation(
        job_data, "worker_123", job_file_path
    )

    assert claimable is True


def test_handle_job_reservation_correct_worker(mock_client: LocalJobDB) -> None:
    """Test _handle_job_reservation returns True when job is reserved for this worker."""
    from datetime import timedelta

    # Set reservation to expire 1 hour in the future (not expired)
    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    job_data = {
        "id": "test_job_123",
        "status": "queued",
        "reserved_for_worker": "worker_123",
        "reservation_expires_at": future_time.isoformat() + "Z",
    }
    job_file_path = os.path.join(mock_client.jobs_dir, "test_job_123.json")

    claimable = mock_client._handle_job_reservation(
        job_data, "worker_123", job_file_path
    )

    assert claimable is True


def test_handle_job_reservation_wrong_worker(mock_client: LocalJobDB) -> None:
    """Test _handle_job_reservation returns False when job is reserved for different worker."""
    from datetime import timedelta

    # Set reservation to expire 1 hour in the future (not expired)
    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    job_data = {
        "id": "test_job_123",
        "status": "queued",
        "reserved_for_worker": "other_worker",
        "reservation_expires_at": future_time.isoformat() + "Z",
    }
    job_file_path = os.path.join(mock_client.jobs_dir, "test_job_123.json")

    claimable = mock_client._handle_job_reservation(
        job_data, "worker_123", job_file_path
    )

    assert claimable is False


def test_clear_expired_reservation(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test _clear_expired_reservation removes reservation fields."""
    # Add a job and manually set an expired reservation
    added_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="queued"
    )
    job_id = added_job["id"]
    job_file_path = os.path.join(mock_client.jobs_dir, f"{job_id}.json")

    # Add reservation fields
    job_data = added_job.copy()
    job_data["reserved_for_worker"] = "expired_worker"
    job_data["reservation_expires_at"] = "2020-01-01T00:00:00Z"  # Expired

    # Call clear reservation
    mock_client._clear_expired_reservation(job_data, job_file_path)

    # Check that reservation fields are removed from in-memory data
    assert "reserved_for_worker" not in job_data
    assert "reservation_expires_at" not in job_data


def test_attempt_claim_job_success(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test _attempt_claim_job successfully claims a queued job."""
    # Add a queued job
    added_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="queued"
    )
    job_id = added_job["id"]
    job_file_path = os.path.join(mock_client.jobs_dir, f"{job_id}.json")

    # Attempt to claim the job
    claimed_job = mock_client._attempt_claim_job(job_file_path, "worker_123")

    assert claimed_job is not None
    assert claimed_job["id"] == job_id
    assert claimed_job["status"] == "running"
    assert claimed_job["assigned_worker"] == "worker_123"
    assert "heartbeat" in claimed_job
    assert "started_at" in claimed_job


def test_attempt_claim_job_already_claimed(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test _attempt_claim_job returns None when job is already claimed."""
    # Add a job that's already running
    added_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="running"
    )
    job_id = added_job["id"]
    job_file_path = os.path.join(mock_client.jobs_dir, f"{job_id}.json")

    # Attempt to claim the job
    claimed_job = mock_client._attempt_claim_job(job_file_path, "worker_123")

    assert claimed_job is None


def test_attempt_claim_job_nonexistent_file(mock_client: LocalJobDB) -> None:
    """Test _attempt_claim_job returns None for nonexistent file."""
    nonexistent_path = os.path.join(mock_client.jobs_dir, "nonexistent.json")

    claimed_job = mock_client._attempt_claim_job(nonexistent_path, "worker_123")

    assert claimed_job is None


def test_discover_claimable_jobs_sorts_by_priority(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test _discover_claimable_jobs returns jobs sorted by priority and age."""
    # Add jobs with different priorities
    low_priority_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="queued", priority=100
    )
    high_priority_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="queued", priority=500
    )
    medium_priority_job = mock_client.add_job(
        sample_job_config, sample_sweep_config_id, status="queued", priority=300
    )

    # Discover claimable jobs
    available_jobs = mock_client._discover_claimable_jobs(
        "worker_123", respect_reservations=True
    )

    # Should be sorted by priority (highest first)
    assert len(available_jobs) == 3
    assert available_jobs[0][1]["id"] == high_priority_job["id"]  # Priority 500
    assert available_jobs[1][1]["id"] == medium_priority_job["id"]  # Priority 300
    assert available_jobs[2][1]["id"] == low_priority_job["id"]  # Priority 100


def test_discover_claimable_jobs_excludes_non_queued(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test _discover_claimable_jobs excludes non-queued jobs."""
    # Add jobs with different statuses
    mock_client.add_job(sample_job_config, sample_sweep_config_id, status="queued")
    mock_client.add_job(sample_job_config, sample_sweep_config_id, status="running")
    mock_client.add_job(sample_job_config, sample_sweep_config_id, status="completed")

    # Discover claimable jobs
    available_jobs = mock_client._discover_claimable_jobs(
        "worker_123", respect_reservations=True
    )

    # Should only include queued job
    assert len(available_jobs) == 1
    assert available_jobs[0][1]["status"] == "queued"


# --- Stale Jobs Tests ---


def test_parse_heartbeat_timestamp_valid(mock_client: LocalJobDB) -> None:
    """Test _parse_heartbeat_timestamp with valid timestamps."""
    from datetime import timezone

    # Test with Z suffix
    result = mock_client._parse_heartbeat_timestamp("2023-06-08T10:30:45Z")
    assert result.tzinfo == timezone.utc
    assert result.year == 2023
    assert result.month == 6
    assert result.day == 8

    # Test without timezone (should add UTC)
    result = mock_client._parse_heartbeat_timestamp("2023-06-08T10:30:45")
    assert result.tzinfo == timezone.utc

    # Test with explicit timezone
    result = mock_client._parse_heartbeat_timestamp("2023-06-08T10:30:45+00:00")
    assert result.tzinfo == timezone.utc


def test_parse_heartbeat_timestamp_invalid(mock_client: LocalJobDB) -> None:
    """Test _parse_heartbeat_timestamp with invalid timestamps."""
    from dr_exp.job_db.local_job_db import HeartbeatParseError

    # Test invalid format
    with pytest.raises(HeartbeatParseError, match="Invalid heartbeat timestamp"):
        mock_client._parse_heartbeat_timestamp("invalid-date")

    # Test empty string
    with pytest.raises(HeartbeatParseError, match="Invalid heartbeat timestamp"):
        mock_client._parse_heartbeat_timestamp("")

    # Test None (should raise TypeError)
    with pytest.raises(HeartbeatParseError, match="Invalid heartbeat timestamp"):
        mock_client._parse_heartbeat_timestamp(None)  # type: ignore[arg-type]


def test_process_job_for_staleness_missing_fields(mock_client: LocalJobDB) -> None:
    """Test _process_job_for_staleness with missing required fields."""
    from dr_exp.job_db.local_job_db import JobValidationError
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    max_age = 3600

    # Test missing job_id
    with pytest.raises(JobValidationError, match="Missing job_id"):
        mock_client._process_job_for_staleness({}, now, max_age)

    # Test missing assigned_worker
    with pytest.raises(JobValidationError, match="missing assigned_worker"):
        mock_client._process_job_for_staleness({"id": "test_job"}, now, max_age)

    # Test missing heartbeat (should return None, not raise)
    result = mock_client._process_job_for_staleness(
        {"id": "test_job", "assigned_worker": "worker1"}, now, max_age
    )
    assert result is None


def test_process_job_for_staleness_valid_job_not_stale(mock_client: LocalJobDB) -> None:
    """Test _process_job_for_staleness with valid job that is not stale."""
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    recent_heartbeat = (now - timedelta(seconds=30)).isoformat() + "Z"
    max_age = 3600  # 1 hour

    job = {
        "id": "test_job",
        "assigned_worker": "worker1",
        "heartbeat": recent_heartbeat,
    }

    result = mock_client._process_job_for_staleness(job, now, max_age)
    assert result is None


def test_process_job_for_staleness_valid_job_is_stale(mock_client: LocalJobDB) -> None:
    """Test _process_job_for_staleness with valid job that is stale."""
    from datetime import datetime, timezone, timedelta
    from dr_exp.job_db.base_job_db import StaleJobInfo

    now = datetime.now(timezone.utc)
    old_heartbeat = (now - timedelta(seconds=7200)).isoformat() + "Z"  # 2 hours ago
    max_age = 3600  # 1 hour

    job = {"id": "test_job", "assigned_worker": "worker1", "heartbeat": old_heartbeat}

    result = mock_client._process_job_for_staleness(job, now, max_age)
    assert result is not None
    assert isinstance(result, StaleJobInfo)
    assert result.job_id == "test_job"
    assert result.assigned_worker == "worker1"
    assert result.age_seconds > max_age


def test_process_job_for_staleness_invalid_heartbeat(mock_client: LocalJobDB) -> None:
    """Test _process_job_for_staleness with invalid heartbeat."""
    from dr_exp.job_db.local_job_db import HeartbeatParseError
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    max_age = 3600

    job = {
        "id": "test_job",
        "assigned_worker": "worker1",
        "heartbeat": "invalid-timestamp",
    }

    with pytest.raises(HeartbeatParseError, match="Invalid heartbeat timestamp"):
        mock_client._process_job_for_staleness(job, now, max_age)


def test_get_stale_jobs_integration(
    mock_client: LocalJobDB,
    sample_job_config: Dict[str, Any],
    sample_sweep_config_id: str,
) -> None:
    """Test get_stale_jobs integration with real job data."""
    from datetime import datetime, timezone, timedelta

    # Create jobs with different heartbeat ages
    job1 = mock_client.add_job(sample_job_config, sample_sweep_config_id)
    job2 = mock_client.add_job(sample_job_config, sample_sweep_config_id)
    job3 = mock_client.add_job(sample_job_config, sample_sweep_config_id)

    # Claim jobs to make them running
    mock_client.claim_job("worker1")  # Claims job1
    mock_client.claim_job("worker2")  # Claims job2
    mock_client.claim_job("worker3")  # Claims job3

    # Set up heartbeats manually
    now = datetime.now(timezone.utc)
    recent_heartbeat = (now - timedelta(seconds=30)).isoformat() + "Z"  # Fresh
    old_heartbeat = (now - timedelta(seconds=7200)).isoformat() + "Z"  # 2 hours old

    # Update job files directly to set heartbeats
    import json
    import os

    job1_data = mock_client.get_job_details(job1["id"])
    assert job1_data is not None
    job1_data["heartbeat"] = recent_heartbeat
    job1_file_path = os.path.join(mock_client.jobs_dir, f"{job1['id']}.json")
    mock_client._atomic_write(job1_file_path, json.dumps(job1_data, indent=4))

    job2_data = mock_client.get_job_details(job2["id"])
    assert job2_data is not None
    job2_data["heartbeat"] = old_heartbeat
    job2_file_path = os.path.join(mock_client.jobs_dir, f"{job2['id']}.json")
    mock_client._atomic_write(job2_file_path, json.dumps(job2_data, indent=4))

    job3_data = mock_client.get_job_details(job3["id"])
    assert job3_data is not None
    job3_data["heartbeat"] = old_heartbeat
    job3_file_path = os.path.join(mock_client.jobs_dir, f"{job3['id']}.json")
    mock_client._atomic_write(job3_file_path, json.dumps(job3_data, indent=4))

    # Test get_stale_jobs
    max_age = 3600  # 1 hour
    stale_jobs = mock_client.get_stale_jobs(max_age)

    # Should find 2 stale jobs (job2 and job3)
    assert len(stale_jobs) == 2
    stale_job_ids = {job.job_id for job in stale_jobs}
    assert job2["id"] in stale_job_ids
    assert job3["id"] in stale_job_ids
    assert job1["id"] not in stale_job_ids

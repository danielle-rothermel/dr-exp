# tests/mock/test_supabase_mock_client.py
import pytest
import os
import json
from datetime import datetime, timezone
from dr_exp.mock.supabase_mock_client import (
    SupabaseMockClient,
)  # Assuming this is the correct path

# --- Test Fixtures ---


@pytest.fixture
def mock_client(tmp_path):
    """
    Provides a SupabaseMockClient instance initialized in a temporary directory.
    This ensures each test runs with a clean mock environment.
    The tmp_path fixture is provided by pytest for creating temporary files/directories.
    """
    # The SupabaseMockClient will create mock_db and mock_storage inside tmp_path
    client = SupabaseMockClient(base_path=str(tmp_path))
    return client


@pytest.fixture
def sample_job_config():
    """Provides a sample job configuration."""
    return {"learning_rate": 0.001, "epochs": 10, "model_name": "test_model"}


@pytest.fixture
def sample_sweep_config_id():
    """Provides a sample sweep_config_id."""
    return "sweep_cfg_abc123"


# --- Test Cases ---


def test_client_initialization(tmp_path):
    """Tests if the client initializes its directories correctly."""
    client = SupabaseMockClient(base_path=str(tmp_path))
    assert os.path.exists(client.mock_db_path)
    assert os.path.exists(client.jobs_dir)
    assert os.path.exists(client.metrics_dir)
    assert os.path.exists(client.errors_file)
    assert os.path.exists(client.mock_storage_path)
    with open(client.errors_file, "r") as f:
        assert f.read() == ""  # Should be empty


def test_add_job_and_get_details(
    mock_client, sample_job_config, sample_sweep_config_id
):
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


def test_claim_job_success(mock_client, sample_job_config, sample_sweep_config_id):
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
    assert job_details["status"] == "running"


def test_claim_job_no_queued_jobs(mock_client):
    """Tests claiming a job when no queued jobs are available."""
    # Add a running job
    mock_client.add_job({"config": "details"}, "sweep1", status="running")

    claimed_job = mock_client.claim_job()
    assert claimed_job is None


def test_claim_job_multiple_queued(
    mock_client, sample_job_config, sample_sweep_config_id
):
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


def test_update_job(mock_client, sample_job_config, sample_sweep_config_id):
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
    assert updated_job_details["status"] == "running"
    assert updated_job_details["num_epochs"] == 5
    assert updated_job_details["heartbeat"] == update_data["heartbeat"]


def test_update_non_existent_job(mock_client):
    """Tests updating a job that does not exist."""
    result = mock_client.update_job("non_existent_job_id", {"status": "completed"})
    assert result["success"] is False
    assert "not found" in result["message"].lower()


def test_log_metrics(mock_client, sample_job_config, sample_sweep_config_id):
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


def test_record_failure(mock_client, sample_job_config, sample_sweep_config_id):
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
    mock_client, tmp_path, sample_job_config, sample_sweep_config_id
):
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
        mock_client.mock_storage_path, f"run_{job_id}", "artifacts", remote_suffix
    )
    assert os.path.exists(expected_destination_path)
    assert result["storage_path"] == expected_destination_path
    with open(expected_destination_path, "r") as f:
        assert f.read() == "dummy plot data"


def test_upload_artifact_root_file(
    mock_client, tmp_path, sample_job_config, sample_sweep_config_id
):
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
        mock_client.mock_storage_path, f"run_{job_id}", remote_suffix
    )
    assert os.path.exists(expected_destination_path)
    assert result["storage_path"] == expected_destination_path
    with open(expected_destination_path, "r") as f:
        assert f.read() == '{"epoch": 1, "loss": 0.5}\n'


def test_upload_artifact_directory(
    mock_client, tmp_path, sample_job_config, sample_sweep_config_id
):
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
        mock_client.mock_storage_path, f"run_{job_id}", "artifacts", remote_suffix
    )
    assert os.path.exists(expected_destination_base)
    assert os.path.exists(os.path.join(expected_destination_base, "file1.txt"))
    assert os.path.exists(
        os.path.join(expected_destination_base, "subdir", "file2.txt")
    )
    with open(os.path.join(expected_destination_base, "file1.txt"), "r") as f:
        assert f.read() == "content1"


def test_upload_artifact_non_existent_local(
    mock_client, sample_job_config, sample_sweep_config_id
):
    """Tests uploading a non-existent local artifact."""
    added_job = mock_client.add_job(sample_job_config, sample_sweep_config_id)
    job_id = added_job["id"]

    result = mock_client.upload_artifact(
        job_id, "non_existent_file.txt", "some_remote_path.txt"
    )
    assert result["success"] is False
    assert "not found" in result["message"].lower()


def test_finalize_job(mock_client, sample_job_config, sample_sweep_config_id):
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
    assert finalized_job_details["status"] == "completed"
    assert "end_time" in finalized_job_details
    assert finalized_job_details["final_val_acc"] == 0.95
    assert finalized_job_details["finalize_success"] is True
    flag_path = os.path.join(
        mock_client.mock_storage_path,
        f"run_{job_id}",
        "finished.flag",
    )
    assert os.path.exists(flag_path)


# --- Test for Reset Utility (Implicitly via fixture, but can add explicit if needed) ---
# The mock_client fixture using tmp_path ensures a clean state for each test.
# If you had a separate reset_mock_db function, you could test it directly.
# For now, the SupabaseMockClient's own re-initialization on a clean tmp_path serves this.


def test_multiple_operations_on_same_job(
    mock_client, tmp_path, sample_job_config, sample_sweep_config_id
):
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
    assert final_details["status"] == "completed"
    assert final_details["final_val_acc"] == 0.9

    metric_file_path = os.path.join(mock_client.metrics_dir, f"{job_id}.jsonl")
    with open(metric_file_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 2  # metrics1 and metrics2

    artifact_path = os.path.join(
        mock_client.mock_storage_path,
        f"run_{job_id}",
        "artifacts",
        "checkpoints/final_model.pt",
    )
    assert os.path.exists(artifact_path)

"""Test database operations in Supabase client."""

import os
import tempfile
import uuid
from pathlib import Path
from datetime import datetime, timedelta, UTC
from dotenv import load_dotenv

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


def test_experiment_operations() -> str:
    """Test experiment creation and retrieval."""
    setup_test_env()

    client = SupabaseClient()

    # Create new experiment
    exp_name = f"test_exp_{int(datetime.now(UTC).timestamp())}"
    base_path = "/tmp/test"
    metadata = {"created_by": "test", "purpose": "testing"}

    exp_id = client.get_or_create_experiment(exp_name, base_path, metadata)
    assert exp_id is not None
    assert len(exp_id) == 36  # UUID format

    # Get same experiment again (should return same ID)
    exp_id2 = client.get_or_create_experiment(exp_name, base_path)
    assert exp_id2 == exp_id

    # Create different experiment
    exp_id3 = client.get_or_create_experiment(exp_name + "_2", base_path)
    assert exp_id3 != exp_id

    return exp_id


def test_job_sync() -> tuple[str, str]:
    """Test syncing jobs to database."""
    setup_test_env()

    client = SupabaseClient()

    # Create experiment
    exp_name = f"job_sync_test_{int(datetime.now(UTC).timestamp())}"
    exp_id = client.get_or_create_experiment(exp_name, "/tmp/test")

    # Create job data (mimicking local JobDB format)
    job_id = str(uuid.uuid4())
    job_data = {
        "id": job_id,
        "config": {"_target_": "test.train", "epochs": 10, "lr": 0.001},
        "priority": 500,
        "status": "queued",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "attempts": 0,
    }

    # Sync job
    success = client.sync_job(job_data, exp_id)
    assert success

    # Update job and sync again
    job_data["status"] = "running"
    job_data["worker_id"] = "test_worker"
    job_data["started_at"] = datetime.now(UTC).isoformat()
    job_data["last_heartbeat"] = datetime.now(UTC).isoformat()

    success = client.sync_job(job_data, exp_id)
    assert success

    # Complete job
    job_data["status"] = "completed"
    job_data["completed_at"] = datetime.now(UTC).isoformat()
    job_data["final_metrics"] = {"accuracy": 0.95, "loss": 0.15}

    success = client.sync_job(job_data, exp_id)
    assert success

    return exp_id, job_id


def test_sync_status() -> None:
    """Test sync status tracking."""
    setup_test_env()

    client = SupabaseClient()

    # Create experiment and job
    exp_name = f"sync_status_test_{int(datetime.now(UTC).timestamp())}"
    exp_id = client.get_or_create_experiment(exp_name, "/tmp/test")

    job_id = str(uuid.uuid4())
    job_data = {
        "id": job_id,
        "config": {"_target_": "test.train"},
        "priority": 100,
        "status": "running",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    client.sync_job(job_data, exp_id)

    # Create sync status for uploaded file
    sync_id = client.create_sync_status(
        job_id=job_id,
        file_path="/tmp/test/metrics.jsonl",
        file_type="metrics",
        checksum="abc123def456",
        size_bytes=1024,
        storage_url="http://example.com/storage/metrics.jsonl",
        metadata={"lines": 100},
    )

    assert sync_id is not None

    # Get sync status for job
    sync_records = client.get_job_sync_status(job_id)
    assert len(sync_records) == 1
    assert sync_records[0]["file_type"] == "metrics"
    assert sync_records[0]["status"] == "completed"


def test_experiment_stats() -> None:
    """Test getting experiment statistics."""
    setup_test_env()

    client = SupabaseClient()

    # Create experiment with multiple jobs
    exp_name = f"stats_test_{int(datetime.now(UTC).timestamp())}"
    exp_id = client.get_or_create_experiment(exp_name, "/tmp/test")

    # Create jobs in different states
    job_configs = [
        {"status": "queued", "priority": 100},
        {"status": "queued", "priority": 200},
        {"status": "running", "worker_id": "worker1"},
        {"status": "completed", "final_metrics": {"acc": 0.9}},
        {"status": "failed", "error": "OOM"},
    ]

    for i, config in enumerate(job_configs):
        job_data = {
            "id": str(uuid.uuid4()),
            "config": {"_target_": "test.train"},
            "priority": config.get("priority", 100),
            "status": config["status"],
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        # Add status-specific fields
        if config["status"] == "running":
            job_data["worker_id"] = config["worker_id"]
            job_data["started_at"] = datetime.now(UTC).isoformat()
        elif config["status"] == "completed":
            job_data["completed_at"] = datetime.now(UTC).isoformat()
            job_data["final_metrics"] = config["final_metrics"]
        elif config["status"] == "failed":
            job_data["error"] = config["error"]
            job_data["completed_at"] = datetime.now(UTC).isoformat()

        client.sync_job(job_data, exp_id)

    # Get stats
    stats = client.get_experiment_stats(exp_id)

    assert stats["total_jobs"] == 5
    assert stats["queued_jobs"] == 2
    assert stats["running_jobs"] == 1
    assert stats["completed_jobs"] == 1
    assert stats["failed_jobs"] == 1


def test_batch_operations() -> None:
    """Test batch syncing of jobs."""
    setup_test_env()

    client = SupabaseClient()

    # Create experiment
    exp_name = f"batch_test_{int(datetime.now(UTC).timestamp())}"
    exp_id = client.get_or_create_experiment(exp_name, "/tmp/test")

    # Create multiple jobs
    jobs = []
    for i in range(10):
        job = {
            "id": str(uuid.uuid4()),
            "config": {"_target_": "test.train", "index": i},
            "priority": i * 100,
            "status": "queued",
            "created_at": (datetime.now(UTC) - timedelta(minutes=i)).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        jobs.append(job)

    # Batch sync
    results = client.batch_sync_jobs(jobs, exp_id)

    assert results["success"] == 10
    assert results["failed"] == 0

    # Verify jobs exist
    db_jobs = client.get_experiment_jobs(exp_id)
    assert len(db_jobs) == 10

    # Check ordering (newest first)
    assert db_jobs[0]["config"]["index"] == 0  # Most recent


def test_job_queries() -> None:
    """Test querying jobs with filters."""
    setup_test_env()

    client = SupabaseClient()

    # Create experiment
    exp_name = f"query_test_{int(datetime.now(UTC).timestamp())}"
    exp_id = client.get_or_create_experiment(exp_name, "/tmp/test")

    # Create jobs with different statuses
    statuses = ["queued", "queued", "running", "completed", "failed"]
    job_ids = []

    for i, status in enumerate(statuses):
        job_data = {
            "id": str(uuid.uuid4()),
            "config": {"_target_": "test.train"},
            "priority": 100,
            "status": status,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        client.sync_job(job_data, exp_id)
        job_ids.append(job_data["id"])

    # Query all jobs
    all_jobs = client.get_experiment_jobs(exp_id)
    assert len(all_jobs) == 5

    # Query by status
    queued_jobs = client.get_experiment_jobs(exp_id, status="queued")
    assert len(queued_jobs) == 2

    running_jobs = client.get_experiment_jobs(exp_id, status="running")
    assert len(running_jobs) == 1

    # Test limit
    limited_jobs = client.get_experiment_jobs(exp_id, limit=3)
    assert len(limited_jobs) == 3


def test_full_sync_workflow() -> None:
    """Test complete sync workflow from file upload to status tracking."""
    setup_test_env()

    client = SupabaseClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create experiment
        exp_name = f"workflow_test_{int(datetime.now(UTC).timestamp())}"
        exp_id = client.get_or_create_experiment(exp_name, tmpdir)

        # Create and sync job
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "config": {"_target_": "test.train", "epochs": 5},
            "priority": 800,
            "status": "running",
            "worker_id": "workflow_worker",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "started_at": datetime.now(UTC).isoformat(),
        }

        client.sync_job(job_data, exp_id)

        # Create and upload a file
        test_file = Path(tmpdir) / "results.json"
        test_file.write_text('{"accuracy": 0.92, "loss": 0.23}')

        storage_url, checksum = client.upload_file(
            file_path=test_file,
            experiment_name=exp_name,
            job_id=job_id,
            file_type="metrics",
        )

        # Track sync status
        sync_id = client.create_sync_status(
            job_id=job_id,
            file_path=str(test_file),
            file_type="metrics",
            checksum=checksum,
            size_bytes=test_file.stat().st_size,
            storage_url=storage_url,
        )

        assert sync_id is not None

        # Complete the job
        job_data["status"] = "completed"
        job_data["completed_at"] = datetime.now(UTC).isoformat()
        job_data["final_metrics"] = {"accuracy": 0.92, "loss": 0.23}

        client.sync_job(job_data, exp_id)

        # Verify everything
        stats = client.get_experiment_stats(exp_id)
        assert stats["completed_jobs"] == 1

        sync_records = client.get_job_sync_status(job_id)
        assert len(sync_records) == 1
        assert sync_records[0]["status"] == "completed"

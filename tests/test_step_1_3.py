"""Test job lifecycle management."""

import tempfile
import time
import json
from pathlib import Path

from dr_exp.core.job_db import JobDB


def test_job_lifecycle() -> None:
    """Test complete job lifecycle from creation to completion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create a job
        config = {"_target_": "test.train", "epochs": 10}
        job_id = job_db.create_job(config, priority=200)

        # Verify initial state
        job = job_db.get_job(job_id)
        assert job["status"] == "queued"
        assert job["attempts"] == 0

        # Claim the job
        claimed_job = job_db.claim_next_job("worker_1")
        assert claimed_job is not None
        assert claimed_job["id"] == job_id
        assert claimed_job["status"] == "running"
        assert claimed_job["worker_id"] == "worker_1"
        assert claimed_job["attempts"] == 1
        assert "started_at" in claimed_job

        # Send heartbeats
        for _i in range(3):
            time.sleep(0.1)
            success = job_db.heartbeat(job_id)
            assert success

            # Verify heartbeat updated
            job = job_db.get_job(job_id)
            assert "last_heartbeat" in job

        # Complete the job with metrics
        metrics = {"final_loss": 0.23, "final_accuracy": 0.95, "total_epochs": 10}
        success = job_db.complete_job(job_id, metrics)
        assert success

        # Verify completion
        job = job_db.get_job(job_id)
        assert job["status"] == "completed"
        assert job["error"] is None
        assert "completed_at" in job
        assert job["final_metrics"] == metrics


def test_job_failure() -> None:
    """Test job failure handling."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create and claim a job
        config = {"_target_": "test.train"}
        job_id = job_db.create_job(config)
        job_db.claim_next_job("worker_1")

        # Fail the job
        error_msg = "CUDA out of memory"
        success = job_db.fail_job(job_id, error_msg)
        assert success

        # Verify failure
        job = job_db.get_job(job_id)
        assert job["status"] == "failed"
        assert job["error"] == error_msg
        assert "completed_at" in job


def test_job_listing() -> None:
    """Test listing jobs with filters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create jobs in different states
        config = {"_target_": "test.train"}

        # Create all jobs first, then manipulate their states
        all_job_ids = []
        for _i in range(5):
            job_id = job_db.create_job(config, priority=100)
            all_job_ids.append(job_id)

        # Claim 2 jobs to make them running
        claimed_job1 = job_db.claim_next_job("worker_0")
        claimed_job2 = job_db.claim_next_job("worker_1")
        running_ids = [claimed_job1["id"], claimed_job2["id"]]

        # Claim 1 job and complete it
        claimed_job = job_db.claim_next_job("worker_complete")
        job_db.complete_job(claimed_job["id"])
        completed_id = claimed_job["id"]

        # Claim 1 job and fail it
        claimed_job = job_db.claim_next_job("worker_fail")
        job_db.fail_job(claimed_job["id"], "Test error")
        failed_id = claimed_job["id"]

        # The remaining job should be queued

        # Test listing all jobs
        all_jobs = job_db.list_jobs()
        assert len(all_jobs) == 5

        # Test filtering by status
        queued_jobs = job_db.list_jobs(status="queued")
        assert len(queued_jobs) == 1

        running_jobs = job_db.list_jobs(status="running")
        assert len(running_jobs) == 2
        assert all(j["id"] in running_ids for j in running_jobs)

        completed_jobs = job_db.list_jobs(status="completed")
        assert len(completed_jobs) == 1
        assert completed_jobs[0]["id"] == completed_id

        failed_jobs = job_db.list_jobs(status="failed")
        assert len(failed_jobs) == 1
        assert failed_jobs[0]["id"] == failed_id


def test_sync_queue(tmp_path: Path) -> None:
    """Test sync queue functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create a job
        config = {"_target_": "test.train"}
        job_id = job_db.create_job(config)

        # Add items to sync queue
        sync_ids = []

        # Add metrics file
        sync_id1 = job_db.add_to_sync_queue(
            job_id=job_id,
            file_path=str(tmp_path / "metrics.json"),
            file_type="metrics",
            metadata={"lines": 100},
        )
        sync_ids.append(sync_id1)

        # Small delay to ensure different timestamps
        time.sleep(0.001)

        # Add model file
        sync_id2 = job_db.add_to_sync_queue(
            job_id=job_id,
            file_path=str(tmp_path / "model.pt"),
            file_type="model",
            metadata={"epoch": 10, "size_mb": 250},
        )
        sync_ids.append(sync_id2)

        # Verify sync files created
        sync_files = list(job_db.sync_queue_dir.glob("*.json"))
        assert len(sync_files) == 2

        # Verify files are ordered by timestamp
        sync_files.sort()
        for sync_file in sync_files:
            with Path(sync_file).open() as f:
                sync_data = json.load(f)
                assert sync_data["id"] in sync_ids
                assert sync_data["job_id"] == job_id
                assert sync_data["status"] == "pending"
                assert sync_data["attempts"] == 0


def test_experiment_info() -> None:
    """Test experiment info gathering."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create jobs in various states
        config = {"_target_": "test.train"}

        # Create a bunch of jobs first (11 total)
        job_ids = []
        for _ in range(11):
            job_id = job_db.create_job(config)
            job_ids.append(job_id)

        # Claim and set states to get desired distribution
        # 2 running
        job_db.claim_next_job("worker_1")
        job_db.claim_next_job("worker_2")

        # 3 completed
        for _i in range(3):
            claimed_job = job_db.claim_next_job("worker_temp")
            job_db.complete_job(claimed_job["id"])

        # 1 failed
        claimed_job = job_db.claim_next_job("worker_temp")
        job_db.fail_job(claimed_job["id"], "Error")

        # Remaining should be queued (5 jobs)

        # Get experiment info
        info = job_db.get_experiment_info()

        assert info["experiment_name"] == "test_exp"
        assert info["total_jobs"] == 11
        assert info["status_counts"]["queued"] == 5
        assert info["status_counts"]["running"] == 2
        assert info["status_counts"]["completed"] == 3
        assert info["status_counts"]["failed"] == 1
        assert "created_at" in info

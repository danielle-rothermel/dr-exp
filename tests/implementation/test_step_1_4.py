"""Test operational features."""

import tempfile
import time
from datetime import datetime, timedelta, UTC

from src.dr_exp.core.job_db import JobDB


def test_mark_job_failed():
    """Test marking jobs as failed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create jobs in different states
        config = {"_target_": "dr_exp.trainers.test_trainer.train"}

        # Running job (high priority so it gets claimed first)
        running_id = job_db.create_job(config, priority=200)
        claimed = job_db.claim_next_job("worker_1")
        if claimed:
            running_id = claimed["id"]

        # Completed job (medium priority)
        completed_id = job_db.create_job(config, priority=150)
        claimed2 = job_db.claim_next_job("worker_2")
        if claimed2:
            completed_id = claimed2["id"]
        job_db.complete_job(completed_id)

        # Queued job (low priority so it stays queued)
        queued_id = job_db.create_job(config, priority=100)

        # Cannot mark queued job as failed
        success = job_db.mark_job_failed(queued_id, "Test kill")
        assert not success
        job = job_db.get_job(queued_id)
        assert job["status"] == "queued"  # Unchanged

        # Mark running job as failed
        success = job_db.mark_job_failed(running_id, "Test kill")
        assert success
        job = job_db.get_job(running_id)
        assert job["status"] == "failed"
        assert "Killed: Test kill" in job["error"]

        # Cannot mark completed job as failed
        success = job_db.mark_job_failed(completed_id, "Test kill")
        assert not success
        job = job_db.get_job(completed_id)
        assert job["status"] == "completed"  # Unchanged

        # Cannot mark non-existent job as failed
        success = job_db.mark_job_failed("fake_id", "Test kill")
        assert not success


def test_boost_priority():
    """Test priority boosting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        config = {"_target_": "dr_exp.trainers.test_trainer.train"}

        # Create low priority jobs
        job1_id = job_db.create_job(config, priority=100)
        job2_id = job_db.create_job(config, priority=150)

        # Boost priority of multiple jobs
        updated = job_db.boost_priority([job1_id, job2_id], 900)
        assert updated == 2

        # Verify boost
        job1 = job_db.get_job(job1_id)
        assert job1["priority"] == 900
        job2 = job_db.get_job(job2_id)
        assert job2["priority"] == 900

        # Create more jobs to test ordering
        job3_id = job_db.create_job(config, priority=200)

        # Boosted jobs should be claimed first (job1 first due to earlier creation)
        claimed = job_db.claim_next_job("worker_1")
        assert claimed["id"] == job1_id

        # Cannot boost running job
        running_job_id = job_db.create_job(config)
        claimed_running = job_db.claim_next_job("worker_2")
        if claimed_running:
            running_job_id = claimed_running["id"]
        updated = job_db.boost_priority([running_job_id], 950)
        assert updated == 0  # No jobs updated

        # Cannot boost with invalid priority
        try:
            job_db.boost_priority([job3_id], 1500)
            assert False, "Should have failed"
        except AssertionError as e:
            assert "Priority must be 0-1000" in str(e)


def test_recover_stale_jobs():
    """Test stale job recovery."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        config = {"_target_": "dr_exp.trainers.test_trainer.train"}

        # Create and claim jobs
        fresh_id = job_db.create_job(config)
        claimed_fresh = job_db.claim_next_job("worker_fresh")
        if claimed_fresh:
            fresh_id = claimed_fresh["id"]
        job_db.heartbeat(fresh_id)  # Recent heartbeat

        stale_id = job_db.create_job(config)
        claimed_stale = job_db.claim_next_job("worker_stale")
        if claimed_stale:
            stale_id = claimed_stale["id"]
        # No heartbeat - will be stale

        # Make the stale job actually stale by backdating its heartbeat
        old_time = (datetime.now(UTC) - timedelta(seconds=400)).isoformat()
        job_db.update_job(stale_id, {"last_heartbeat": old_time})

        # Recover with 5 minute threshold
        recovered = job_db.recover_stale_jobs(heartbeat_timeout=300)

        assert len(recovered) == 1
        assert stale_id in recovered

        # Verify stale job is queued again
        stale_job = job_db.get_job(stale_id)
        assert stale_job["status"] == "queued"
        assert stale_job["worker_id"] is None
        assert "Worker died" in stale_job["error"]

        # Fresh job should still be running
        fresh_job = job_db.get_job(fresh_id)
        assert fresh_job["status"] == "running"


def test_complete_jobdb():
    """Integration test of complete JobDB functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="final_test", validate=False)

        # Simulate a complete workflow
        config = {
            "_target_": "dr_exp.trainers.test_trainer.train",
            "model": "resnet50",
            "epochs": 100,
        }

        # 1. Create urgent job
        urgent_id = job_db.create_job(config, priority=950)

        # 2. Create normal jobs
        normal_ids = []
        for i in range(3):
            job_id = job_db.create_job(config, priority=200 + i * 50)
            normal_ids.append(job_id)

        # 3. Worker claims urgent job first
        claimed = job_db.claim_next_job("gpu_worker_1")
        assert claimed["id"] == urgent_id

        # 4. Send heartbeats while working
        for _ in range(5):
            job_db.heartbeat(urgent_id)
            time.sleep(0.01)

        # 5. Add files to sync queue during training
        job_db.add_to_sync_queue(
            urgent_id, f"{job_db.get_storage_path(urgent_id)}/metrics.jsonl", "metrics"
        )

        # 6. Complete the job
        job_db.complete_job(urgent_id, {"accuracy": 0.98})

        # 7. Get experiment summary
        info = job_db.get_experiment_info()
        assert info["total_jobs"] == 4
        assert info["status_counts"]["completed"] == 1
        assert info["status_counts"]["queued"] == 3

"""Test basic worker functionality."""

import tempfile
from pathlib import Path

from src.dr_exp.core.job_db import JobDB
from src.dr_exp.worker.base import Worker


def test_basic_worker():
    """Test worker can execute a single job."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize JobDB
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create a test job
        config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 5}
        job_id = job_db.create_job(config, priority=100)

        # Create worker with specific working directory
        work_dir = Path(tmpdir) / "worker_dir"
        worker = Worker(
            job_db=job_db, worker_id="test_worker", working_dir=str(work_dir)
        )

        # Run one job
        status = worker.run_one_job()
        assert status == "completed"

        # Verify job completed
        job = job_db.get_job(job_id)
        assert job["status"] == "completed"
        assert job["error"] is None
        assert "final_metrics" in job
        assert job["final_metrics"]["total_epochs"] == 5

        # Verify artifacts created
        storage_path = job_db.get_storage_path(job_id)
        assert (storage_path / "metrics.jsonl").exists()
        assert (storage_path / "model_final.pt").exists()

        # Verify working directory structure
        assert work_dir.exists()
        assert (work_dir / f"job_{job_id}").exists()


def test_worker_failure_handling():
    """Test worker handles job failures correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create a job that will fail
        config = {
            "_target_": "src.dr_exp.trainers.test_trainer.train",
            "epochs": 5,
            "fail_rate": 1.0,  # Always fail
        }
        job_id = job_db.create_job(config)

        # Create and run worker
        worker = Worker(job_db=job_db, worker_id="test_worker")
        status = worker.run_one_job()

        assert status == "failed"

        # Verify job marked as failed
        job = job_db.get_job(job_id)
        assert job["status"] == "failed"
        assert "Simulated training failure" in job["error"]


def test_worker_no_jobs():
    """Test worker behavior when no jobs available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # No jobs created
        worker = Worker(job_db=job_db, worker_id="test_worker")
        status = worker.run_one_job()

        assert status == "no_job"


def test_worker_run_multiple():
    """Test worker running multiple jobs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create multiple jobs
        job_ids = []
        for i in range(5):
            config = {
                "_target_": "src.dr_exp.trainers.test_trainer.train",
                "epochs": 2,
                "index": i,
                "fail_rate": 0.2 if i == 2 else 0.0,  # One job will fail
            }
            job_id = job_db.create_job(config, priority=i * 100)
            job_ids.append(job_id)

        # Run worker
        worker = Worker(job_db=job_db, worker_id="batch_worker")
        stats = worker.run()

        # Verify stats
        assert stats["total"] == 5
        assert stats["completed"] >= 4  # At least 4 should complete
        assert stats["failed"] <= 1  # At most 1 should fail

        # Verify all jobs processed
        for job_id in job_ids:
            job = job_db.get_job(job_id)
            assert job["status"] in ["completed", "failed"]


def test_worker_max_jobs():
    """Test worker respects max_jobs limit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create 10 jobs
        for i in range(10):
            config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 1}
            job_db.create_job(config)

        # Run worker with limit
        worker = Worker(job_db=job_db, worker_id="limited_worker")
        stats = worker.run(max_jobs=3)

        assert stats["total"] == 3
        assert stats["completed"] == 3

        # Verify only 3 jobs processed
        queued_count = len(job_db.list_jobs(status="queued"))
        assert queued_count == 7


def test_worker_priority_order():
    """Test worker processes jobs in priority order."""
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="test_exp", validate=False)

        # Create jobs with different priorities
        config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 1}

        low_id = job_db.create_job(config, priority=100)
        high_id = job_db.create_job(config, priority=900)
        med_id = job_db.create_job(config, priority=500)

        # Track execution order
        execution_order = []

        # Custom worker that tracks order
        class TrackingWorker(Worker):
            def execute_job(self, job):
                execution_order.append(job["id"])
                return super().execute_job(job)

        worker = TrackingWorker(job_db=job_db, worker_id="tracking_worker")
        worker.run()

        # Verify priority order (high, med, low)
        assert execution_order == [high_id, med_id, low_id]

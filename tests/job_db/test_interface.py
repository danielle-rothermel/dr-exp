"""Tests for the new streamlined interface methods."""

import os
import tempfile
import pytest
from datetime import datetime, UTC, timedelta
from typing import Generator

from dr_exp.job_db import LocalJobDB, JobDBConfig, StaleJobInfo


@pytest.fixture
def temp_local_db() -> Generator[LocalJobDB, None, None]:
    """Create a temporary LocalJobDB for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = JobDBConfig(
            mode="files_local",
            base_path=tmpdir,
            storage_path=os.path.join(tmpdir, "storage"),
        )
        yield LocalJobDB(config)


class TestStreamlinedInterface:
    """Test the new streamlined interface methods."""

    def test_list_running_jobs_empty(self, temp_local_db: LocalJobDB) -> None:
        """Test listing running jobs when none exist."""
        result = temp_local_db.list_running_jobs()
        assert result == []

    def test_list_running_jobs_with_data(self, temp_local_db: LocalJobDB) -> None:
        """Test listing running jobs with mixed statuses."""
        # Create test jobs with different statuses
        _job1 = temp_local_db.add_job({"test": 1}, "sweep1", status="queued")
        job2 = temp_local_db.add_job({"test": 2}, "sweep2", status="running")
        _job3 = temp_local_db.add_job({"test": 3}, "sweep3", status="completed")
        job4 = temp_local_db.add_job({"test": 4}, "sweep4", status="running")

        running_jobs = temp_local_db.list_running_jobs()

        # Should only return running jobs
        assert len(running_jobs) == 2
        running_ids = {job["id"] for job in running_jobs}
        assert running_ids == {job2["id"], job4["id"]}

    def test_get_stale_jobs_no_running_jobs(self, temp_local_db: LocalJobDB) -> None:
        """Test stale job detection with no running jobs."""
        result = temp_local_db.get_stale_jobs(120)
        assert result == []

    def test_get_stale_jobs_no_heartbeats(self, temp_local_db: LocalJobDB) -> None:
        """Test stale job detection with running jobs but no heartbeats."""
        # Create running job without heartbeat
        temp_local_db.add_job({"test": 1}, "sweep1", status="running")

        result = temp_local_db.get_stale_jobs(120)
        assert result == []

    def test_get_stale_jobs_with_fresh_heartbeat(
        self, temp_local_db: LocalJobDB
    ) -> None:
        """Test stale job detection with fresh heartbeat."""
        # Create running job
        job = temp_local_db.add_job({"test": 1}, "sweep1", status="running")

        # Update with recent heartbeat
        recent_time = datetime.now(UTC).isoformat() + "Z"
        temp_local_db.update_job(
            job["id"], {"heartbeat": recent_time, "assigned_worker": "test-worker"}
        )

        result = temp_local_db.get_stale_jobs(120)  # 2 minutes
        assert result == []

    def test_get_stale_jobs_with_stale_heartbeat(
        self, temp_local_db: LocalJobDB
    ) -> None:
        """Test stale job detection with old heartbeat."""
        # Create running job
        job = temp_local_db.add_job({"test": 1}, "sweep1", status="running")

        # Update with old heartbeat (5 minutes ago)
        old_time = (datetime.now(UTC) - timedelta(minutes=5)).isoformat() + "Z"
        temp_local_db.update_job(
            job["id"], {"heartbeat": old_time, "assigned_worker": "test-worker"}
        )

        result = temp_local_db.get_stale_jobs(120)  # 2 minutes

        assert len(result) == 1
        stale_job = result[0]
        assert isinstance(stale_job, StaleJobInfo)
        assert stale_job.job_id == job["id"]
        assert stale_job.assigned_worker == "test-worker"
        assert stale_job.age_seconds > 120

    def test_mark_jobs_failed_empty_list(self, temp_local_db: LocalJobDB) -> None:
        """Test marking empty list of jobs as failed."""
        result = temp_local_db.mark_jobs_failed([])
        assert result == {}

    def test_mark_jobs_failed_nonexistent_jobs(self, temp_local_db: LocalJobDB) -> None:
        """Test marking nonexistent jobs as failed."""
        result = temp_local_db.mark_jobs_failed(["fake-id-1", "fake-id-2"])
        assert result == {"fake-id-1": False, "fake-id-2": False}

    def test_mark_jobs_failed_success(self, temp_local_db: LocalJobDB) -> None:
        """Test successfully marking jobs as failed."""
        # Create test jobs
        job1 = temp_local_db.add_job({"test": 1}, "sweep1", status="running")
        job2 = temp_local_db.add_job({"test": 2}, "sweep2", status="running")
        job3 = temp_local_db.add_job({"test": 3}, "sweep3", status="queued")

        # Mark some jobs as failed
        result = temp_local_db.mark_jobs_failed([job1["id"], job2["id"]], "test_reason")

        assert result == {job1["id"]: True, job2["id"]: True}

        # Verify jobs were actually updated
        updated_job1 = temp_local_db.get_job_details(job1["id"])
        updated_job2 = temp_local_db.get_job_details(job2["id"])
        unchanged_job3 = temp_local_db.get_job_details(job3["id"])

        assert updated_job1 is not None
        assert updated_job1["status"] == "failed"
        assert updated_job1["status_reason"] == "test_reason"
        assert "end_time" in updated_job1

        assert updated_job2 is not None
        assert updated_job2["status"] == "failed"
        assert updated_job2["status_reason"] == "test_reason"

        assert unchanged_job3 is not None
        assert unchanged_job3["status"] == "queued"
        assert "status_reason" not in unchanged_job3

    def test_has_queued_jobs_empty(self, temp_local_db: LocalJobDB) -> None:
        """Test has_queued_jobs with no jobs."""
        assert temp_local_db.has_queued_jobs() is False

    def test_has_queued_jobs_no_queued(self, temp_local_db: LocalJobDB) -> None:
        """Test has_queued_jobs with no queued jobs."""
        temp_local_db.add_job({"test": 1}, "sweep1", status="running")
        temp_local_db.add_job({"test": 2}, "sweep2", status="completed")

        assert temp_local_db.has_queued_jobs() is False

    def test_has_queued_jobs_with_queued(self, temp_local_db: LocalJobDB) -> None:
        """Test has_queued_jobs with queued jobs."""
        temp_local_db.add_job({"test": 1}, "sweep1", status="running")
        temp_local_db.add_job({"test": 2}, "sweep2", status="queued")

        assert temp_local_db.has_queued_jobs() is True

    def test_get_queue_summary_empty(self, temp_local_db: LocalJobDB) -> None:
        """Test queue summary with no queued jobs."""
        result = temp_local_db.get_queue_summary()
        assert result == []

    def test_get_queue_summary_with_jobs(self, temp_local_db: LocalJobDB) -> None:
        """Test queue summary with queued jobs."""
        # Create jobs with different priorities and statuses
        job1 = temp_local_db.add_job(
            {"test": 1}, "sweep1", status="queued", priority=500
        )
        _job2 = temp_local_db.add_job(
            {"test": 2}, "sweep2", status="running", priority=800
        )  # Should be ignored
        job3 = temp_local_db.add_job(
            {"test": 3}, "sweep3", status="queued", priority=100
        )
        job4 = temp_local_db.add_job(
            {"test": 4}, "sweep4", status="queued", priority=900
        )

        result = temp_local_db.get_queue_summary(limit=10)

        # Should only include queued jobs, ordered by priority (highest first)
        assert len(result) == 3
        assert result[0]["id"] == job4["id"]  # priority 900
        assert result[0]["priority"] == 900
        assert result[1]["id"] == job1["id"]  # priority 500
        assert result[1]["priority"] == 500
        assert result[2]["id"] == job3["id"]  # priority 100
        assert result[2]["priority"] == 100

        # Test limit
        limited_result = temp_local_db.get_queue_summary(limit=2)
        assert len(limited_result) == 2
        assert limited_result[0]["id"] == job4["id"]
        assert limited_result[1]["id"] == job1["id"]

    def test_stale_job_info_dataclass(self) -> None:
        """Test StaleJobInfo dataclass functionality."""
        now = datetime.now(UTC)
        stale_job = StaleJobInfo(
            job_id="test-job",
            assigned_worker="test-worker",
            last_heartbeat=now,
            age_seconds=300,
        )

        assert stale_job.job_id == "test-job"
        assert stale_job.assigned_worker == "test-worker"
        assert stale_job.last_heartbeat == now
        assert stale_job.age_seconds == 300

        # Test string representation
        str_repr = str(stale_job)
        assert "test-job" in str_repr
        assert "test-worker" in str_repr

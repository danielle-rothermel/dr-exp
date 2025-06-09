from datetime import datetime, UTC, timedelta
from unittest.mock import Mock
import pytest

from dr_exp.job_db import LocalJobDB, JobDBConfig
from dr_exp.utils.job_reaper import (
    reap_stale_jobs,
    _get_jobs_list,
    _should_mark_job_stale,
    _mark_job_stale,
    JobValidationError,
    HeartbeatParseError,
)


def test_reap_marks_stale_job(tmp_path):
    client = LocalJobDB(
        JobDBConfig(
            base_path=str(tmp_path),
            storage_path=str(tmp_path / "storage"),
            mode="files_local",
        )
    )
    job = client.add_job({"cfg": 1}, "sweep1", status="running")
    old = datetime.now(UTC) - timedelta(minutes=10)
    client.update_job(job["id"], {"heartbeat": old.isoformat() + "Z"})

    count = reap_stale_jobs(client, max_age_mins=5)
    assert count == 1
    data = client.get_job_details(job["id"])
    assert data["status"] == "failed"
    assert data["status_reason"] == "manager_died"


def test_reap_ignores_recent_job(tmp_path):
    client = LocalJobDB(
        JobDBConfig(
            base_path=str(tmp_path),
            storage_path=str(tmp_path / "storage"),
            mode="files_local",
        )
    )
    job = client.add_job({"cfg": 1}, "sweep1", status="running")
    now = datetime.now(UTC)
    client.update_job(job["id"], {"heartbeat": now.isoformat() + "Z"})

    count = reap_stale_jobs(client, max_age_mins=5)
    assert count == 0
    data = client.get_job_details(job["id"])
    assert data["status"] == "running"


def test_reap_handles_invalid_jobs_gracefully(tmp_path, caplog):
    """Test that reap_stale_jobs handles invalid job data gracefully."""
    client = LocalJobDB(
        JobDBConfig(
            base_path=str(tmp_path),
            storage_path=str(tmp_path / "storage"),
            mode="files_local",
        )
    )

    # Create jobs with various invalid states
    job1 = client.add_job({"cfg": 1}, "sweep1", status="completed")  # Not running
    job2 = client.add_job({"cfg": 2}, "sweep2", status="running")  # No heartbeat
    job3 = client.add_job({"cfg": 3}, "sweep3", status="running")  # Invalid heartbeat
    job4 = client.add_job({"cfg": 4}, "sweep4", status="running")  # Valid stale job

    # Set heartbeats
    client.update_job(job3["id"], {"heartbeat": "invalid-timestamp"})
    old_time = datetime.now(UTC) - timedelta(minutes=10)
    client.update_job(job4["id"], {"heartbeat": old_time.isoformat() + "Z"})

    count = reap_stale_jobs(client, max_age_mins=5)

    # Only the valid stale job should be reaped
    assert count == 1

    # Check that appropriate warnings/errors were logged
    assert "Skipping invalid job" in caplog.text
    assert "Invalid heartbeat for job" in caplog.text

    # Verify final states
    assert client.get_job_details(job1["id"])["status"] == "completed"
    assert client.get_job_details(job2["id"])["status"] == "running"
    assert client.get_job_details(job3["id"])["status"] == "running"
    assert client.get_job_details(job4["id"])["status"] == "failed"


class TestGetJobsList:
    """Test _get_jobs_list helper function."""

    def test_get_jobs_list_with_list_jobs_method(self):
        """Test client with list_jobs method."""
        mock_client = Mock()
        mock_client.list_jobs.return_value = [{"id": "test"}]

        result = _get_jobs_list(mock_client)

        assert list(result) == [{"id": "test"}]
        mock_client.list_jobs.assert_called_once()

    def test_get_jobs_list_without_list_jobs_method(self):
        """Test client without list_jobs method (direct supabase access)."""
        mock_client = Mock()
        del mock_client.list_jobs  # Remove the method

        # Mock the supabase chain
        mock_response = Mock()
        mock_response.data = [{"id": "test"}]
        mock_client.supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_response

        result = _get_jobs_list(mock_client)

        assert list(result) == [{"id": "test"}]
        mock_client.supabase.table.assert_called_once_with("jobs")


class TestShouldMarkJobStale:
    """Test _should_mark_job_stale helper function."""

    def test_non_running_job_raises_validation_error(self):
        """Test that non-running jobs raise JobValidationError."""
        job = {"status": "completed", "heartbeat": "2024-01-01T00:00:00Z"}
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)

        with pytest.raises(JobValidationError, match="Job is not in running status"):
            _should_mark_job_stale(job, now, cutoff)

    def test_missing_heartbeat_raises_validation_error(self):
        """Test that missing heartbeat raises JobValidationError."""
        job = {"status": "running"}
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)

        with pytest.raises(JobValidationError, match="Job missing heartbeat timestamp"):
            _should_mark_job_stale(job, now, cutoff)

    def test_empty_heartbeat_raises_validation_error(self):
        """Test that empty heartbeat raises JobValidationError."""
        job = {"status": "running", "heartbeat": ""}
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)

        with pytest.raises(JobValidationError, match="Job missing heartbeat timestamp"):
            _should_mark_job_stale(job, now, cutoff)

    def test_invalid_heartbeat_format_raises_parse_error(self):
        """Test that invalid heartbeat format raises HeartbeatParseError."""
        job = {"status": "running", "heartbeat": "invalid-format"}
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)

        with pytest.raises(
            HeartbeatParseError, match="Invalid timestamp format 'invalid-format'"
        ):
            _should_mark_job_stale(job, now, cutoff)

    def test_stale_job_returns_true(self):
        """Test that stale job returns True."""
        old_time = datetime.now(UTC) - timedelta(minutes=10)
        job = {"status": "running", "heartbeat": old_time.isoformat() + "Z"}
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)

        result = _should_mark_job_stale(job, now, cutoff)

        assert result is True

    def test_recent_job_returns_false(self):
        """Test that recent job returns False."""
        recent_time = datetime.now(UTC) - timedelta(minutes=2)
        job = {"status": "running", "heartbeat": recent_time.isoformat() + "Z"}
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)

        result = _should_mark_job_stale(job, now, cutoff)

        assert result is False

    def test_heartbeat_with_z_suffix_parsed_correctly(self):
        """Test that heartbeat with Z suffix is parsed correctly."""
        old_time = datetime.now(UTC) - timedelta(minutes=10)
        job = {"status": "running", "heartbeat": old_time.isoformat() + "Z"}
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)

        result = _should_mark_job_stale(job, now, cutoff)

        assert result is True

    def test_heartbeat_without_z_suffix_parsed_correctly(self):
        """Test that heartbeat without Z suffix is parsed correctly."""
        old_time = datetime.now(UTC) - timedelta(minutes=10)
        job = {"status": "running", "heartbeat": old_time.isoformat()}
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)

        result = _should_mark_job_stale(job, now, cutoff)

        assert result is True


class TestMarkJobStale:
    """Test _mark_job_stale helper function."""

    def test_mark_job_stale_calls_update_job(self):
        """Test that _mark_job_stale calls client.update_job correctly."""
        mock_client = Mock()
        job = {"id": "test-job-id"}

        _mark_job_stale(mock_client, job)

        mock_client.update_job.assert_called_once_with(
            "test-job-id", {"status": "failed", "status_reason": "manager_died"}
        )

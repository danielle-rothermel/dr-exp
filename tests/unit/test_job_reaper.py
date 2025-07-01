"""Unit tests for JobReaper functionality."""

from datetime import datetime, UTC, timedelta
from unittest.mock import Mock
import pytest

from dr_exp.utils.job_reaper import (
    reap_stale_jobs,
    _get_jobs_list,
    _should_mark_job_stale,
    _mark_job_stale,
)


class TestJobReaper:
    """Test cases for job reaper functionality."""

    def test_reap_stale_jobs_success(self) -> None:
        """Test successful reaping of stale jobs."""
        # Create mock client
        mock_client = Mock()
        now = datetime.now(UTC)
        old_time = (now - timedelta(minutes=30)).isoformat()
        recent_time = (now - timedelta(minutes=1)).isoformat()

        # Mock job data - mix of stale and fresh
        jobs = [
            {
                "id": "job_1",
                "status": "running",
                "heartbeat": old_time,  # Stale
            },
            {
                "id": "job_2",
                "status": "running",
                "heartbeat": recent_time,  # Fresh
            },
            {
                "id": "job_3",
                "status": "running",
                "heartbeat": old_time,  # Stale
            },
        ]

        mock_client.list_jobs.return_value = jobs

        # Run reaper with 5 minute threshold
        count = reap_stale_jobs(mock_client, max_age_mins=5)

        # Should have reaped 2 stale jobs
        assert count == 2

        # Verify update_job was called for stale jobs only
        assert mock_client.update_job.call_count == 2
        mock_client.update_job.assert_any_call(
            "job_1", {"status": "failed", "status_reason": "manager_died"}
        )
        mock_client.update_job.assert_any_call(
            "job_3", {"status": "failed", "status_reason": "manager_died"}
        )

    def test_reap_stale_jobs_no_stale_jobs(self) -> None:
        """Test reaper when no jobs are stale."""
        mock_client = Mock()
        now = datetime.now(UTC)
        recent_time = (now - timedelta(minutes=1)).isoformat()

        jobs = [
            {"id": "job_1", "status": "running", "heartbeat": recent_time},
            {"id": "job_2", "status": "running", "heartbeat": recent_time},
        ]

        mock_client.list_jobs.return_value = jobs

        count = reap_stale_jobs(mock_client, max_age_mins=5)

        assert count == 0
        mock_client.update_job.assert_not_called()

    def test_reap_stale_jobs_empty_list(self) -> None:
        """Test reaper with empty job list."""
        mock_client = Mock()
        mock_client.list_jobs.return_value = []

        count = reap_stale_jobs(mock_client, max_age_mins=5)

        assert count == 0
        mock_client.update_job.assert_not_called()

    def test_reap_stale_jobs_invalid_job_warning(self) -> None:
        """Test reaper handles invalid jobs with warning."""
        mock_client = Mock()

        # Mix of valid and invalid jobs
        jobs = [
            {
                "id": "job_1",
                "status": "completed",  # Not running - invalid
                "heartbeat": datetime.now(UTC).isoformat(),
            },
            {
                "id": "job_2",
                "status": "running",
                "heartbeat": None,  # Missing heartbeat - invalid
            },
            {
                "id": "job_3",
                "status": "running",
                "heartbeat": (
                    datetime.now(UTC) - timedelta(minutes=30)
                ).isoformat(),  # Valid stale
            },
        ]

        mock_client.list_jobs.return_value = jobs

        # Just test that it handles invalid jobs gracefully
        count = reap_stale_jobs(mock_client, max_age_mins=5)

        # Should only process the valid stale job
        assert count == 1
        mock_client.update_job.assert_called_once_with(
            "job_3", {"status": "failed", "status_reason": "manager_died"}
        )

    def test_reap_stale_jobs_update_failure(self) -> None:
        """Test reaper handles update failures gracefully."""
        mock_client = Mock()
        now = datetime.now(UTC)
        old_time = (now - timedelta(minutes=30)).isoformat()

        jobs = [
            {"id": "job_1", "status": "running", "heartbeat": old_time},
            {"id": "job_2", "status": "running", "heartbeat": old_time},
        ]

        mock_client.list_jobs.return_value = jobs

        # Make first update fail, second succeed
        mock_client.update_job.side_effect = [Exception("DB error"), None]

        count = reap_stale_jobs(mock_client, max_age_mins=5)

        # Should still return 1 for successful update
        assert count == 1
        assert mock_client.update_job.call_count == 2

    def test_get_jobs_list_with_list_jobs_method(self) -> None:
        """Test _get_jobs_list when client has list_jobs method."""
        mock_client = Mock()
        expected_jobs = [{"id": "job_1"}, {"id": "job_2"}]
        mock_client.list_jobs.return_value = expected_jobs

        jobs = _get_jobs_list(mock_client)

        assert jobs == expected_jobs
        mock_client.list_jobs.assert_called_once()

    def test_get_jobs_list_with_supabase_fallback(self) -> None:
        """Test _get_jobs_list fallback to Supabase client."""
        mock_client = Mock()
        del mock_client.list_jobs  # Remove list_jobs method

        # Mock Supabase response
        mock_response = Mock()
        mock_response.data = [{"id": "job_1", "status": "running"}]

        mock_supabase = Mock()
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()

        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq
        mock_eq.execute.return_value = mock_response

        mock_client.supabase = mock_supabase

        jobs = _get_jobs_list(mock_client)

        assert jobs == [{"id": "job_1", "status": "running"}]
        mock_supabase.table.assert_called_once_with("jobs")
        mock_table.select.assert_called_once_with("*")
        mock_select.eq.assert_called_once_with("status", "running")

    def test_get_jobs_list_supabase_no_data(self) -> None:
        """Test _get_jobs_list when Supabase returns no data."""
        mock_client = Mock()
        del mock_client.list_jobs

        mock_response = Mock()
        mock_response.data = None

        mock_supabase = Mock()
        mock_table = Mock()
        mock_select = Mock()
        mock_eq = Mock()

        mock_supabase.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.eq.return_value = mock_eq
        mock_eq.execute.return_value = mock_response

        mock_client.supabase = mock_supabase

        jobs = _get_jobs_list(mock_client)

        assert jobs == []

    def test_should_mark_job_stale_true(self) -> None:
        """Test _should_mark_job_stale returns True for stale job."""
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)
        old_time = (now - timedelta(minutes=10)).isoformat()

        job = {"id": "job_1", "status": "running", "heartbeat": old_time}

        assert _should_mark_job_stale(job, now, cutoff) is True

    def test_should_mark_job_stale_false(self) -> None:
        """Test _should_mark_job_stale returns False for fresh job."""
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)
        recent_time = (now - timedelta(minutes=1)).isoformat()

        job = {"id": "job_1", "status": "running", "heartbeat": recent_time}

        assert _should_mark_job_stale(job, now, cutoff) is False

    def test_should_mark_job_stale_not_running(self) -> None:
        """Test _should_mark_job_stale raises AssertionError for non-running job."""
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)

        job = {
            "id": "job_1",
            "status": "completed",  # Not running
            "heartbeat": datetime.now(UTC).isoformat(),
        }

        with pytest.raises(AssertionError, match="Job is not in running status"):
            _should_mark_job_stale(job, now, cutoff)

    def test_should_mark_job_stale_missing_heartbeat(self) -> None:
        """Test _should_mark_job_stale raises AssertionError for missing heartbeat."""
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)

        job = {
            "id": "job_1",
            "status": "running",
            "heartbeat": None,  # Missing heartbeat
        }

        with pytest.raises(AssertionError, match="Job missing heartbeat timestamp"):
            _should_mark_job_stale(job, now, cutoff)

    def test_should_mark_job_stale_empty_heartbeat(self) -> None:
        """Test _should_mark_job_stale raises AssertionError for empty heartbeat."""
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)

        job = {
            "id": "job_1",
            "status": "running",
            "heartbeat": "",  # Empty heartbeat
        }

        with pytest.raises(AssertionError, match="Job missing heartbeat timestamp"):
            _should_mark_job_stale(job, now, cutoff)

    def test_should_mark_job_stale_invalid_timestamp(self) -> None:
        """Test _should_mark_job_stale raises AssertionError for invalid timestamp."""
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)

        job = {"id": "job_1", "status": "running", "heartbeat": "invalid-timestamp"}

        with pytest.raises(AssertionError, match="Invalid timestamp format"):
            _should_mark_job_stale(job, now, cutoff)

    def test_should_mark_job_stale_with_z_suffix(self) -> None:
        """Test _should_mark_job_stale handles Z suffix in timestamp."""
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)
        old_time = (now - timedelta(minutes=10)).isoformat() + "Z"

        job = {"id": "job_1", "status": "running", "heartbeat": old_time}

        assert _should_mark_job_stale(job, now, cutoff) is True

    def test_should_mark_job_stale_exact_cutoff(self) -> None:
        """Test _should_mark_job_stale at exact cutoff boundary."""
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)
        exact_time = (now - cutoff).isoformat()

        job = {"id": "job_1", "status": "running", "heartbeat": exact_time}

        # At exact cutoff, should not be marked stale (> not >=)
        assert _should_mark_job_stale(job, now, cutoff) is False

    def test_should_mark_job_stale_just_over_cutoff(self) -> None:
        """Test _should_mark_job_stale just over cutoff boundary."""
        now = datetime.now(UTC)
        cutoff = timedelta(minutes=5)
        just_over_time = (now - cutoff - timedelta(seconds=1)).isoformat()

        job = {"id": "job_1", "status": "running", "heartbeat": just_over_time}

        assert _should_mark_job_stale(job, now, cutoff) is True

    def test_mark_job_stale(self) -> None:
        """Test _mark_job_stale calls update_job correctly."""
        mock_client = Mock()
        job = {"id": "job_123"}

        _mark_job_stale(mock_client, job)

        mock_client.update_job.assert_called_once_with(
            "job_123", {"status": "failed", "status_reason": "manager_died"}
        )

    def test_reap_stale_jobs_zero_cutoff(self) -> None:
        """Test reaper with zero minute cutoff (immediate stale)."""
        mock_client = Mock()
        now = datetime.now(UTC)
        # Even 1 second ago should be stale with 0 minute cutoff
        recent_time = (now - timedelta(seconds=1)).isoformat()

        jobs = [{"id": "job_1", "status": "running", "heartbeat": recent_time}]

        mock_client.list_jobs.return_value = jobs

        count = reap_stale_jobs(mock_client, max_age_mins=0)

        assert count == 1
        mock_client.update_job.assert_called_once()

    def test_reap_stale_jobs_large_cutoff(self) -> None:
        """Test reaper with very large cutoff (nothing stale)."""
        mock_client = Mock()
        now = datetime.now(UTC)
        # Even very old jobs should not be stale with large cutoff
        old_time = (now - timedelta(hours=1)).isoformat()

        jobs = [{"id": "job_1", "status": "running", "heartbeat": old_time}]

        mock_client.list_jobs.return_value = jobs

        count = reap_stale_jobs(mock_client, max_age_mins=1440)  # 24 hours

        assert count == 0
        mock_client.update_job.assert_not_called()

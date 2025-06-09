"""Integration tests for SupabaseJobDB using local Supabase instance.

These tests require a running local Supabase instance:
    supabase start

Run with: EXPMGR_MODE=supabase_local pytest tests/job_db/test_supabase_integration.py
"""

import os
from typing import Generator
from datetime import datetime, timezone, timedelta

import pytest

from dr_exp.job_db import SupabaseJobDB, JobDBConfig, StaleJobInfo
from dr_exp.utils.jobdb_factory import get_job_db_client


@pytest.fixture(scope="session")
def requires_local_supabase() -> None:
    """Skip tests if local Supabase mode is not configured."""
    mode = os.getenv("EXPMGR_MODE")
    if mode != "supabase_local":
        pytest.skip("Tests require EXPMGR_MODE=supabase_local and running Supabase")


@pytest.fixture
def supabase_client(
    requires_local_supabase: None,
) -> Generator[SupabaseJobDB, None, None]:
    """Provide a SupabaseJobDB client with transaction rollback."""
    config = JobDBConfig.from_env()
    config.validate()
    client = SupabaseJobDB(config)

    # Start a transaction that we'll rollback after the test
    # Note: This requires manual transaction management
    yield client

    # Clean up: Delete any test data created during the test
    # For now, we'll use a simple cleanup approach
    _cleanup_test_data(client)


def _cleanup_test_data(client: SupabaseJobDB) -> None:
    """Clean up test data by removing jobs with test prefixes."""
    try:
        # Delete test sweep config clusters
        response = (
            client.supabase.table("sweep_config_clusters")
            .select("id")
            .like("name", "test-%")
            .execute()
        )
        for cluster in response.data or []:
            # Delete associated configs and jobs first (cascade should handle this, but being explicit)
            client.supabase.table("jobs").delete().match(
                {"config_id": cluster["id"]}
            ).execute()
            client.supabase.table("sweep_configs").delete().match(
                {"cluster_id": cluster["id"]}
            ).execute()
            client.supabase.table("sweep_config_clusters").delete().match(
                {"id": cluster["id"]}
            ).execute()
    except Exception as e:
        # Don't fail tests due to cleanup issues
        print(f"Warning: Cleanup failed: {e}")


class TestSupabaseIntegration:
    """Integration tests for SupabaseJobDB with real local database."""

    def test_basic_job_workflow(self, supabase_client: SupabaseJobDB) -> None:
        """Test creating a cluster, config, and job."""
        # Create test cluster
        cluster = supabase_client.add_sweep_config_cluster(
            "test-basic-workflow", "Test cluster for basic workflow"
        )
        assert cluster is not None
        assert cluster["name"] == "test-basic-workflow"

        # Create test config
        config_json = {"model": "test", "lr": 0.01}
        config = supabase_client.add_sweep_config(
            cluster["id"], config_json, "test-hash-123"
        )
        assert config is not None
        assert config["config_json"] == config_json
        assert config["config_hash"] == "test-hash-123"

        # Create test job
        job = supabase_client.add_job_entry(config["id"], priority=500, status="queued")
        assert job is not None
        assert job["config_id"] == config["id"]
        assert job["priority"] == 500
        assert job["status"] == "queued"

    def test_job_claiming_priority(self, supabase_client: SupabaseJobDB) -> None:
        """Test job claiming respects priority ordering."""
        # Create cluster and config
        cluster = supabase_client.add_sweep_config_cluster(
            "test-priority", "Priority test"
        )
        config = supabase_client.add_sweep_config(
            cluster["id"], {"test": True}, "hash-priority"
        )

        # Create jobs with different priorities
        low_job = supabase_client.add_job_entry(config["id"], priority=100)
        high_job = supabase_client.add_job_entry(config["id"], priority=800)
        medium_job = supabase_client.add_job_entry(config["id"], priority=400)

        # Claim jobs - should get highest priority first
        claimed1 = supabase_client.claim_job("test-worker-1")
        assert claimed1 is not None
        assert claimed1["id"] == high_job["id"]
        assert claimed1["priority"] == 800

        claimed2 = supabase_client.claim_job("test-worker-2")
        assert claimed2 is not None
        assert claimed2["id"] == medium_job["id"]
        assert claimed2["priority"] == 400

        claimed3 = supabase_client.claim_job("test-worker-3")
        assert claimed3 is not None
        assert claimed3["id"] == low_job["id"]
        assert claimed3["priority"] == 100

    def test_job_reservations(self, supabase_client: SupabaseJobDB) -> None:
        """Test job reservation system."""
        # Create cluster and config
        cluster = supabase_client.add_sweep_config_cluster(
            "test-reservations", "Reservation test"
        )
        config = supabase_client.add_sweep_config(
            cluster["id"], {"test": True}, "hash-reservation"
        )

        # Create a reserved job
        reserved_job = supabase_client.add_reserved_job(
            {"test": True},
            config["id"],
            "specific-worker",
            reservation_timeout=300,
            priority=600,
        )
        assert reserved_job is not None
        assert reserved_job["reserved_for_worker"] == "specific-worker"
        assert reserved_job["priority"] == 600

        # Wrong worker can't claim it
        claimed_wrong = supabase_client.claim_job("other-worker")
        assert claimed_wrong is None

        # Correct worker can claim it
        claimed_correct = supabase_client.claim_job("specific-worker")
        assert claimed_correct is not None
        assert claimed_correct["id"] == reserved_job["id"]

    def test_priority_management(self, supabase_client: SupabaseJobDB) -> None:
        """Test priority boost and update operations."""
        # Create test data
        cluster = supabase_client.add_sweep_config_cluster(
            "test-priority-mgmt", "Priority management test"
        )
        config = supabase_client.add_sweep_config(
            cluster["id"], {"test": True}, "hash-priority-mgmt"
        )
        job = supabase_client.add_job_entry(config["id"], priority=200)

        # Test priority boost
        result = supabase_client.boost_job_priority(job["id"], boost_amount=150)
        assert result["success"] is True
        assert result["old_priority"] == 200
        assert result["new_priority"] == 350

        # Test priority update
        result = supabase_client.update_job_priority(
            job["id"], 750, reason="Urgent deadline"
        )
        assert result["success"] is True
        assert result["new_priority"] == 750

    def test_job_listing_by_priority(self, supabase_client: SupabaseJobDB) -> None:
        """Test listing jobs ordered by priority."""
        # Create test data
        cluster = supabase_client.add_sweep_config_cluster(
            "test-listing", "Listing test"
        )
        config = supabase_client.add_sweep_config(
            cluster["id"], {"test": True}, "hash-listing"
        )

        # Create jobs with different priorities
        job1 = supabase_client.add_job_entry(config["id"], priority=100)
        job2 = supabase_client.add_job_entry(config["id"], priority=900)
        job3 = supabase_client.add_job_entry(config["id"], priority=400)

        # List jobs by priority
        jobs = supabase_client.list_jobs_by_priority(status_filter=["queued"], limit=10)

        # Should be ordered by priority (highest first)
        job_priorities = [
            job["priority"]
            for job in jobs
            if job["id"] in [job1["id"], job2["id"], job3["id"]]
        ]
        assert job_priorities == [900, 400, 100]


@pytest.mark.slow
class TestSupabasePerformance:
    """Performance tests for Supabase operations."""

    def test_bulk_job_creation(self, supabase_client: SupabaseJobDB) -> None:
        """Test creating many jobs efficiently."""
        cluster = supabase_client.add_sweep_config_cluster(
            "test-bulk", "Bulk creation test"
        )
        config = supabase_client.add_sweep_config(
            cluster["id"], {"test": True}, "hash-bulk"
        )

        # Create many jobs
        job_count = 50
        jobs = []
        for i in range(job_count):
            job = supabase_client.add_job_entry(config["id"], priority=i)
            jobs.append(job)

        assert len(jobs) == job_count

        # Verify they can be listed efficiently
        listed_jobs = supabase_client.list_jobs_by_priority(
            status_filter=["queued"], limit=job_count
        )
        created_job_ids = {job["id"] for job in jobs}
        listed_job_ids = {
            job["id"] for job in listed_jobs if job["id"] in created_job_ids
        }

        assert len(listed_job_ids) == job_count


class TestSupabaseStreamlined:
    """Test streamlined interface methods with Supabase."""

    def test_list_running_jobs_empty(self, supabase_client: SupabaseJobDB) -> None:
        """Test listing running jobs when none exist."""
        _cleanup_test_data(supabase_client, "streamlined-test")

        result = supabase_client.list_running_jobs()
        assert isinstance(result, list)
        # May contain other running jobs, so just check it's a list

    def test_streamlined_workflow(self, supabase_client: SupabaseJobDB) -> None:
        """Test a complete workflow using streamlined methods."""
        _cleanup_test_data(supabase_client, "streamlined-test")

        try:
            # Create test data
            cluster = supabase_client.add_sweep_config_cluster(
                "streamlined-test-workflow", "Test streamlined interface"
            )
            config = supabase_client.add_sweep_config(
                cluster["id"], {"model": "test"}, "streamlined-hash"
            )

            # Create jobs with different statuses
            running_job = supabase_client.add_job_entry(
                config["id"], status="running", priority=500
            )
            queued_job1 = supabase_client.add_job_entry(
                config["id"], status="queued", priority=800
            )
            queued_job2 = supabase_client.add_job_entry(
                config["id"], status="queued", priority=200
            )

            # Update running job with worker assignment and heartbeat
            current_time = datetime.now(timezone.utc).isoformat()
            supabase_client.update_job(
                running_job["id"],
                {"assigned_worker": "test-worker", "heartbeat": current_time},
            )

            # Test list_running_jobs
            running_jobs = supabase_client.list_running_jobs()
            our_running_jobs = [
                job for job in running_jobs if job["id"] == running_job["id"]
            ]
            assert len(our_running_jobs) == 1
            assert our_running_jobs[0]["assigned_worker"] == "test-worker"

            # Test has_queued_jobs
            assert supabase_client.has_queued_jobs() is True

            # Test get_queue_summary
            queue_summary = supabase_client.get_queue_summary(limit=10)
            our_queued_jobs = [
                job
                for job in queue_summary
                if job["id"] in [queued_job1["id"], queued_job2["id"]]
            ]
            assert len(our_queued_jobs) == 2
            # Should be ordered by priority (highest first)
            if len(our_queued_jobs) == 2:
                assert our_queued_jobs[0]["priority"] >= our_queued_jobs[1]["priority"]

            # Test get_stale_jobs with recent heartbeat (should be empty)
            stale_jobs = supabase_client.get_stale_jobs(60)  # 1 minute
            our_stale_jobs = [
                job for job in stale_jobs if job.job_id == running_job["id"]
            ]
            assert len(our_stale_jobs) == 0

            # Update with old heartbeat
            old_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
            supabase_client.update_job(running_job["id"], {"heartbeat": old_time})

            # Test get_stale_jobs with old heartbeat
            stale_jobs = supabase_client.get_stale_jobs(60)  # 1 minute
            our_stale_jobs = [
                job for job in stale_jobs if job.job_id == running_job["id"]
            ]
            assert len(our_stale_jobs) == 1
            stale_job = our_stale_jobs[0]
            assert isinstance(stale_job, StaleJobInfo)
            assert stale_job.assigned_worker == "test-worker"
            assert stale_job.age_seconds > 60

            # Test mark_jobs_failed
            job_ids_to_fail = [running_job["id"]]
            results = supabase_client.mark_jobs_failed(job_ids_to_fail, "test_failure")
            assert results[running_job["id"]] is True

            # Verify job was marked as failed
            updated_job = supabase_client.get_job_details(running_job["id"])
            assert updated_job is not None
            assert updated_job["status"] == "failed"
            assert updated_job["status_reason"] == "test_failure"
            assert "end_time" in updated_job

        finally:
            # Clean up
            _cleanup_test_data(supabase_client, "streamlined-test")

    def test_mark_jobs_failed_batch(self, supabase_client: SupabaseJobDB) -> None:
        """Test batch job failure marking."""
        _cleanup_test_data(supabase_client, "streamlined-test")

        try:
            # Create test data
            cluster = supabase_client.add_sweep_config_cluster(
                "streamlined-test-batch", "Test batch operations"
            )
            config = supabase_client.add_sweep_config(
                cluster["id"], {"model": "test"}, "batch-hash"
            )

            # Create multiple running jobs
            job1 = supabase_client.add_job_entry(config["id"], status="running")
            job2 = supabase_client.add_job_entry(config["id"], status="running")
            job3 = supabase_client.add_job_entry(
                config["id"], status="queued"
            )  # Should not be affected

            # Mark multiple jobs as failed
            job_ids = [job1["id"], job2["id"]]
            results = supabase_client.mark_jobs_failed(job_ids, "batch_test")

            assert results[job1["id"]] is True
            assert results[job2["id"]] is True

            # Verify jobs were updated
            updated_job1 = supabase_client.get_job_details(job1["id"])
            updated_job2 = supabase_client.get_job_details(job2["id"])
            unchanged_job3 = supabase_client.get_job_details(job3["id"])

            assert updated_job1 is not None
            assert updated_job1["status"] == "failed"
            assert updated_job1["status_reason"] == "batch_test"
            assert updated_job2 is not None
            assert updated_job2["status"] == "failed"
            assert updated_job2["status_reason"] == "batch_test"
            assert unchanged_job3 is not None
            assert unchanged_job3["status"] == "queued"

        finally:
            _cleanup_test_data(supabase_client, "streamlined-test")


def _cleanup_test_data(client: SupabaseJobDB, test_prefix: str = "test") -> None:
    """Clean up test data with given prefix."""
    try:
        # Delete test clusters and associated data
        response = (
            client.supabase.table("sweep_config_clusters")
            .select("id")
            .like("name", f"{test_prefix}-%")
            .execute()
        )
        for cluster in response.data or []:
            client.supabase.table("jobs").delete().match(
                {"config_id": cluster["id"]}
            ).execute()
            client.supabase.table("sweep_configs").delete().match(
                {"cluster_id": cluster["id"]}
            ).execute()
            client.supabase.table("sweep_config_clusters").delete().match(
                {"id": cluster["id"]}
            ).execute()
    except Exception:
        pass  # Best effort cleanup


# Test using the factory function
def test_factory_integration() -> None:
    """Test that factory function works with local Supabase."""
    if os.getenv("EXPMGR_MODE") != "supabase_local":
        pytest.skip("Requires EXPMGR_MODE=supabase_local")

    client = get_job_db_client()
    assert isinstance(client, SupabaseJobDB)
    assert client.config.mode == "supabase_local"
    assert client.config.supabase_url is not None
    assert "127.0.0.1:54321" in client.config.supabase_url

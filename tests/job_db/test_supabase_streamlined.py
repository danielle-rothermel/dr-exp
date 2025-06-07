"""Tests for streamlined interface methods with Supabase."""

import os
import pytest
from datetime import datetime, timezone, timedelta

from dr_exp.job_db import SupabaseJobDB, JobDBConfig, StaleJobInfo


@pytest.fixture
def supabase_client():
    """Provide a SupabaseJobDB client for testing."""
    if os.getenv("EXPMGR_MODE") != "supabase_local":
        pytest.skip("Requires EXPMGR_MODE=supabase_local")
    
    config = JobDBConfig.from_env()
    config.validate()
    return SupabaseJobDB(config)


def cleanup_test_data(client, test_prefix="streamlined-test"):
    """Clean up test data."""
    try:
        # Delete test clusters and associated data
        response = client.supabase.table("sweep_config_clusters").select("id").like("name", f"{test_prefix}-%").execute()
        for cluster in response.data or []:
            client.supabase.table("jobs").delete().match({"config_id": cluster["id"]}).execute()
            client.supabase.table("sweep_configs").delete().match({"cluster_id": cluster["id"]}).execute()
            client.supabase.table("sweep_config_clusters").delete().match({"id": cluster["id"]}).execute()
    except Exception:
        pass  # Best effort cleanup


class TestSupabaseStreamlined:
    """Test streamlined interface methods with Supabase."""
    
    def test_list_running_jobs_empty(self, supabase_client):
        """Test listing running jobs when none exist."""
        cleanup_test_data(supabase_client)
        
        result = supabase_client.list_running_jobs()
        assert isinstance(result, list)
        # May contain other running jobs, so just check it's a list
    
    def test_streamlined_workflow(self, supabase_client):
        """Test a complete workflow using streamlined methods."""
        cleanup_test_data(supabase_client)
        
        try:
            # Create test data
            cluster = supabase_client.add_sweep_config_cluster(
                "streamlined-test-workflow", 
                "Test streamlined interface"
            )
            config = supabase_client.add_sweep_config(
                cluster["id"], 
                {"model": "test"}, 
                "streamlined-hash"
            )
            
            # Create jobs with different statuses
            running_job = supabase_client.add_job_entry(config["id"], status="running", priority=500)
            queued_job1 = supabase_client.add_job_entry(config["id"], status="queued", priority=800)
            queued_job2 = supabase_client.add_job_entry(config["id"], status="queued", priority=200)
            
            # Update running job with worker assignment and heartbeat
            current_time = datetime.now(timezone.utc).isoformat()
            supabase_client.update_job(running_job["id"], {
                "assigned_worker": "test-worker",
                "heartbeat": current_time
            })
            
            # Test list_running_jobs
            running_jobs = supabase_client.list_running_jobs()
            our_running_jobs = [job for job in running_jobs if job["id"] == running_job["id"]]
            assert len(our_running_jobs) == 1
            assert our_running_jobs[0]["assigned_worker"] == "test-worker"
            
            # Test has_queued_jobs
            assert supabase_client.has_queued_jobs() is True
            
            # Test get_queue_summary
            queue_summary = supabase_client.get_queue_summary(limit=10)
            our_queued_jobs = [job for job in queue_summary if job["id"] in [queued_job1["id"], queued_job2["id"]]]
            assert len(our_queued_jobs) == 2
            # Should be ordered by priority (highest first)
            if len(our_queued_jobs) == 2:
                assert our_queued_jobs[0]["priority"] >= our_queued_jobs[1]["priority"]
            
            # Test get_stale_jobs with recent heartbeat (should be empty)
            stale_jobs = supabase_client.get_stale_jobs(60)  # 1 minute
            our_stale_jobs = [job for job in stale_jobs if job.job_id == running_job["id"]]
            assert len(our_stale_jobs) == 0
            
            # Update with old heartbeat
            old_time = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
            supabase_client.update_job(running_job["id"], {"heartbeat": old_time})
            
            # Test get_stale_jobs with old heartbeat
            stale_jobs = supabase_client.get_stale_jobs(60)  # 1 minute
            our_stale_jobs = [job for job in stale_jobs if job.job_id == running_job["id"]]
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
            assert updated_job["status"] == "failed"
            assert updated_job["status_reason"] == "test_failure"
            assert "end_time" in updated_job
            
        finally:
            # Clean up
            cleanup_test_data(supabase_client)
    
    def test_mark_jobs_failed_batch(self, supabase_client):
        """Test batch job failure marking."""
        cleanup_test_data(supabase_client)
        
        try:
            # Create test data
            cluster = supabase_client.add_sweep_config_cluster(
                "streamlined-test-batch", 
                "Test batch operations"
            )
            config = supabase_client.add_sweep_config(
                cluster["id"], 
                {"model": "test"}, 
                "batch-hash"
            )
            
            # Create multiple running jobs
            job1 = supabase_client.add_job_entry(config["id"], status="running")
            job2 = supabase_client.add_job_entry(config["id"], status="running")
            job3 = supabase_client.add_job_entry(config["id"], status="queued")  # Should not be affected
            
            # Mark multiple jobs as failed
            job_ids = [job1["id"], job2["id"]]
            results = supabase_client.mark_jobs_failed(job_ids, "batch_test")
            
            assert results[job1["id"]] is True
            assert results[job2["id"]] is True
            
            # Verify jobs were updated
            updated_job1 = supabase_client.get_job_details(job1["id"])
            updated_job2 = supabase_client.get_job_details(job2["id"])
            unchanged_job3 = supabase_client.get_job_details(job3["id"])
            
            assert updated_job1["status"] == "failed"
            assert updated_job1["status_reason"] == "batch_test"
            assert updated_job2["status"] == "failed"
            assert updated_job2["status_reason"] == "batch_test"
            assert unchanged_job3["status"] == "queued"
            
        finally:
            cleanup_test_data(supabase_client)
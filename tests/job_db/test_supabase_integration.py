"""Integration tests for SupabaseJobDB using local Supabase instance.

These tests require a running local Supabase instance:
    supabase start

Run with: EXPMGR_MODE=supabase_local pytest tests/job_db/test_supabase_integration.py
"""

import os
import pytest
from unittest.mock import patch

from dr_exp.job_db import SupabaseJobDB, JobDBConfig
from dr_exp.utils.jobdb_factory import get_job_db_client


@pytest.fixture(scope="session")
def requires_local_supabase():
    """Skip tests if local Supabase mode is not configured."""
    mode = os.getenv("EXPMGR_MODE")
    if mode != "supabase_local":
        pytest.skip("Tests require EXPMGR_MODE=supabase_local and running Supabase")


@pytest.fixture
def supabase_client(requires_local_supabase):
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


def _cleanup_test_data(client):
    """Clean up test data by removing jobs with test prefixes."""
    try:
        # Delete test sweep config clusters
        response = client.supabase.table("sweep_config_clusters").select("id").like("name", "test-%").execute()
        for cluster in response.data or []:
            # Delete associated configs and jobs first (cascade should handle this, but being explicit)
            client.supabase.table("jobs").delete().match({"config_id": cluster["id"]}).execute()
            client.supabase.table("sweep_configs").delete().match({"cluster_id": cluster["id"]}).execute()
            client.supabase.table("sweep_config_clusters").delete().match({"id": cluster["id"]}).execute()
    except Exception as e:
        # Don't fail tests due to cleanup issues
        print(f"Warning: Cleanup failed: {e}")


class TestSupabaseIntegration:
    """Integration tests for SupabaseJobDB with real local database."""

    def test_basic_job_workflow(self, supabase_client):
        """Test creating a cluster, config, and job."""
        # Create test cluster
        cluster = supabase_client.add_sweep_config_cluster(
            "test-basic-workflow", 
            "Test cluster for basic workflow"
        )
        assert cluster is not None
        assert cluster["name"] == "test-basic-workflow"
        
        # Create test config
        config_json = {"model": "test", "lr": 0.01}
        config = supabase_client.add_sweep_config(
            cluster["id"], 
            config_json, 
            "test-hash-123"
        )
        assert config is not None
        assert config["config_json"] == config_json
        assert config["config_hash"] == "test-hash-123"
        
        # Create test job
        job = supabase_client.add_job_entry(
            config["id"], 
            priority=500,
            status="queued"
        )
        assert job is not None
        assert job["config_id"] == config["id"]
        assert job["priority"] == 500
        assert job["status"] == "queued"

    def test_job_claiming_priority(self, supabase_client):
        """Test job claiming respects priority ordering."""
        # Create cluster and config
        cluster = supabase_client.add_sweep_config_cluster("test-priority", "Priority test")
        config = supabase_client.add_sweep_config(cluster["id"], {"test": True}, "hash-priority")
        
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

    def test_job_reservations(self, supabase_client):
        """Test job reservation system."""
        # Create cluster and config
        cluster = supabase_client.add_sweep_config_cluster("test-reservations", "Reservation test")
        config = supabase_client.add_sweep_config(cluster["id"], {"test": True}, "hash-reservation")
        
        # Create a reserved job
        reserved_job = supabase_client.add_reserved_job(
            {"test": True},
            config["id"],
            "specific-worker",
            reservation_timeout=300,
            priority=600
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

    def test_priority_management(self, supabase_client):
        """Test priority boost and update operations."""
        # Create test data
        cluster = supabase_client.add_sweep_config_cluster("test-priority-mgmt", "Priority management test")
        config = supabase_client.add_sweep_config(cluster["id"], {"test": True}, "hash-priority-mgmt")
        job = supabase_client.add_job_entry(config["id"], priority=200)
        
        # Test priority boost
        result = supabase_client.boost_job_priority(job["id"], boost_amount=150)
        assert result["success"] is True
        assert result["old_priority"] == 200
        assert result["new_priority"] == 350
        
        # Test priority update
        result = supabase_client.update_job_priority(job["id"], 750, reason="Urgent deadline")
        assert result["success"] is True
        assert result["new_priority"] == 750

    def test_job_listing_by_priority(self, supabase_client):
        """Test listing jobs ordered by priority."""
        # Create test data
        cluster = supabase_client.add_sweep_config_cluster("test-listing", "Listing test")
        config = supabase_client.add_sweep_config(cluster["id"], {"test": True}, "hash-listing")
        
        # Create jobs with different priorities
        job1 = supabase_client.add_job_entry(config["id"], priority=100)
        job2 = supabase_client.add_job_entry(config["id"], priority=900)
        job3 = supabase_client.add_job_entry(config["id"], priority=400)
        
        # List jobs by priority
        jobs = supabase_client.list_jobs_by_priority(status_filter=["queued"], limit=10)
        
        # Should be ordered by priority (highest first)
        job_priorities = [job["priority"] for job in jobs if job["id"] in [job1["id"], job2["id"], job3["id"]]]
        assert job_priorities == [900, 400, 100]


@pytest.mark.slow
class TestSupabasePerformance:
    """Performance tests for Supabase operations."""
    
    def test_bulk_job_creation(self, supabase_client):
        """Test creating many jobs efficiently."""
        cluster = supabase_client.add_sweep_config_cluster("test-bulk", "Bulk creation test")
        config = supabase_client.add_sweep_config(cluster["id"], {"test": True}, "hash-bulk")
        
        # Create many jobs
        job_count = 50
        jobs = []
        for i in range(job_count):
            job = supabase_client.add_job_entry(config["id"], priority=i)
            jobs.append(job)
        
        assert len(jobs) == job_count
        
        # Verify they can be listed efficiently
        listed_jobs = supabase_client.list_jobs_by_priority(status_filter=["queued"], limit=job_count)
        created_job_ids = {job["id"] for job in jobs}
        listed_job_ids = {job["id"] for job in listed_jobs if job["id"] in created_job_ids}
        
        assert len(listed_job_ids) == job_count


# Test using the factory function
def test_factory_integration():
    """Test that factory function works with local Supabase."""
    if os.getenv("EXPMGR_MODE") != "supabase_local":
        pytest.skip("Requires EXPMGR_MODE=supabase_local")
    
    client = get_job_db_client()
    assert isinstance(client, SupabaseJobDB)
    assert client.config.mode == "supabase_local"
    assert "127.0.0.1:54321" in client.config.supabase_url
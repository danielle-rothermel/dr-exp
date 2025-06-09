"""Isolated Supabase tests using test namespacing.

These tests create test data with specific prefixes and clean up after themselves.
No database reset required - can run concurrently.
"""

import os
import uuid
import pytest
from datetime import datetime

from dr_exp.job_db import SupabaseJobDB, JobDBConfig


@pytest.fixture
def test_namespace():
    """Provide a unique test namespace for isolation."""
    return f"test-{uuid.uuid4().hex[:8]}-{datetime.now().strftime('%H%M%S')}"


@pytest.fixture
def isolated_supabase_client(test_namespace):
    """Provide a SupabaseJobDB client with automatic cleanup."""
    if os.getenv("EXPMGR_MODE") != "supabase_local":
        pytest.skip("Requires EXPMGR_MODE=supabase_local")

    config = JobDBConfig.from_env()
    config.validate()
    client = SupabaseJobDB(config)

    # Track created test data for cleanup
    client._test_namespace = test_namespace
    client._test_clusters = []
    client._test_configs = []
    client._test_jobs = []

    # Override methods to track created data
    original_add_cluster = client.add_sweep_config_cluster
    original_add_config = client.add_sweep_config
    original_add_job = client.add_job_entry

    def tracked_add_cluster(name, description=None):
        # Prefix name with test namespace
        test_name = f"{test_namespace}-{name}"
        result = original_add_cluster(test_name, description)
        if result:
            client._test_clusters.append(result["id"])
        return result

    def tracked_add_config(
        cluster_id, config_json, config_hash, interface_version=None
    ):
        # Prefix hash with test namespace
        test_hash = f"{test_namespace}-{config_hash}"
        result = original_add_config(
            cluster_id, config_json, test_hash, interface_version
        )
        if result:
            client._test_configs.append(result["id"])
        return result

    def tracked_add_job(config_id, **kwargs):
        result = original_add_job(config_id, **kwargs)
        if result:
            client._test_jobs.append(result["id"])
        return result

    client.add_sweep_config_cluster = tracked_add_cluster
    client.add_sweep_config = tracked_add_config
    client.add_job_entry = tracked_add_job

    yield client

    # Cleanup: Delete all test data
    try:
        # Delete jobs first (foreign key constraints)
        for job_id in client._test_jobs:
            try:
                client.supabase.table("jobs").delete().eq("id", job_id).execute()
            except Exception:
                pass  # Job might have been deleted by cascade

        # Delete configs
        for config_id in client._test_configs:
            try:
                client.supabase.table("sweep_configs").delete().eq(
                    "id", config_id
                ).execute()
            except Exception:
                pass

        # Delete clusters
        for cluster_id in client._test_clusters:
            try:
                client.supabase.table("sweep_config_clusters").delete().eq(
                    "id", cluster_id
                ).execute()
            except Exception:
                pass

    except Exception as e:
        print(f"Warning: Test cleanup failed: {e}")


class TestSupabaseIsolated:
    """Isolated tests that clean up after themselves."""

    def test_job_workflow_isolated(self, isolated_supabase_client):
        """Test basic job workflow with automatic cleanup."""
        client = isolated_supabase_client

        # Create test data (automatically namespaced)
        cluster = client.add_sweep_config_cluster("workflow", "Test workflow")
        config = client.add_sweep_config(cluster["id"], {"model": "test"}, "hash1")
        job = client.add_job_entry(config["id"], priority=300)

        # Verify creation
        assert cluster["name"].startswith(client._test_namespace)
        assert config["config_hash"].startswith(client._test_namespace)
        assert job["priority"] == 300

        # Test job claiming
        claimed = client.claim_job("test-worker")
        assert claimed["id"] == job["id"]
        assert claimed["status"] == "running"

    def test_concurrent_workers_isolated(self, isolated_supabase_client):
        """Test multiple workers don't interfere with each other."""
        client = isolated_supabase_client

        # Create multiple jobs
        cluster = client.add_sweep_config_cluster("concurrent", "Concurrent test")
        config = client.add_sweep_config(
            cluster["id"], {"test": True}, "hash-concurrent"
        )

        jobs = []
        for i in range(3):
            job = client.add_job_entry(config["id"], priority=500 + i)
            jobs.append(job)

        # Multiple workers claim jobs
        claimed1 = client.claim_job("worker-1")
        claimed2 = client.claim_job("worker-2")
        claimed3 = client.claim_job("worker-3")

        # Each worker should get a different job
        claimed_ids = {claimed1["id"], claimed2["id"], claimed3["id"]}
        job_ids = {job["id"] for job in jobs}
        assert claimed_ids == job_ids

        # No more jobs available
        claimed4 = client.claim_job("worker-4")
        assert claimed4 is None


# Utility function for manual testing
def manual_test_supabase():
    """Manual test function that can be run outside pytest."""
    if os.getenv("EXPMGR_MODE") != "supabase_local":
        print("Set EXPMGR_MODE=supabase_local first")
        return

    config = JobDBConfig.from_env()
    client = SupabaseJobDB(config)

    # Create test data
    cluster = client.add_sweep_config_cluster("manual-test", "Manual test cluster")
    config_obj = client.add_sweep_config(cluster["id"], {"manual": True}, "manual-hash")
    job = client.add_job_entry(config_obj["id"], priority=999)

    print(f"Created job {job['id']} with priority {job['priority']}")

    # Test claiming
    claimed = client.claim_job("manual-worker")
    if claimed:
        print(f"Successfully claimed job {claimed['id']}")
    else:
        print("No job available to claim")


if __name__ == "__main__":
    manual_test_supabase()

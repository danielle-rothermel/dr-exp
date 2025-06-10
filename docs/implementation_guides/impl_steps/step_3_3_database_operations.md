# Step 3.3: Database Operations

## Goal (1 sentence)
Add database operations to the Supabase client for creating experiments, syncing job data, and tracking sync status.

## Prerequisites
- [ ] Step 3.2 completed with file upload working
- [ ] Supabase client can connect and upload files
- [ ] test_step_3_2.py passes

## Implementation

### 1. Update src/dr_exp/sync/supabase_client.py
Add these methods to the SupabaseClient class:
```python
    def get_or_create_experiment(
        self, 
        experiment_name: str, 
        base_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Get or create an experiment in the database.
        
        Args:
            experiment_name: Name of the experiment
            base_path: Base path for the experiment
            metadata: Optional metadata
            
        Returns:
            Experiment ID (UUID string)
        """
        try:
            # Try to get existing experiment
            response = self.client.table("experiments").select("id").eq(
                "experiment_name", experiment_name
            ).eq(
                "base_path", base_path
            ).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]["id"]
            
            # Create new experiment
            data = {
                "experiment_name": experiment_name,
                "base_path": base_path,
                "metadata": metadata or {}
            }
            
            response = self.client.table("experiments").insert(data).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]["id"]
            else:
                raise Exception("Failed to create experiment")
                
        except Exception as e:
            raise Exception(f"Failed to get/create experiment: {str(e)}")
    
    def sync_job(
        self,
        job_data: Dict[str, Any],
        experiment_id: str
    ) -> bool:
        """Sync a job to the database.
        
        Args:
            job_data: Job data from local JobDB
            experiment_id: Experiment ID
            
        Returns:
            True if synced successfully
        """
        try:
            # Prepare job data for database
            db_job = {
                "id": job_data["id"],
                "experiment_id": experiment_id,
                "config": job_data["config"],
                "priority": job_data.get("priority", 100),
                "status": job_data["status"],
                "worker_id": job_data.get("worker_id"),
                "created_at": job_data.get("created_at"),
                "updated_at": job_data.get("updated_at"),
                "started_at": job_data.get("started_at"),
                "completed_at": job_data.get("completed_at"),
                "last_heartbeat": job_data.get("last_heartbeat"),
                "attempts": job_data.get("attempts", 0),
                "error": job_data.get("error"),
                "final_metrics": job_data.get("final_metrics"),
                "reserved_for": job_data.get("reserved_for"),
                "reservation_time": job_data.get("reservation_time"),
                "priority_boosted": job_data.get("priority_boosted", False),
                "recovery_count": job_data.get("recovery_count", 0),
                "last_recovery": job_data.get("last_recovery")
            }
            
            # Remove None values
            db_job = {k: v for k, v in db_job.items() if v is not None}
            
            # Upsert job (insert or update)
            response = self.client.table("jobs").upsert(
                db_job,
                on_conflict="id"
            ).execute()
            
            return response.data is not None
            
        except Exception as e:
            raise Exception(f"Failed to sync job {job_data.get('id')}: {str(e)}")
    
    def create_sync_status(
        self,
        job_id: str,
        file_path: str,
        file_type: str,
        checksum: str,
        size_bytes: int,
        storage_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a sync status record.
        
        Args:
            job_id: Job that created the file
            file_path: Original file path
            file_type: Type of file
            checksum: File checksum
            size_bytes: File size
            storage_url: URL in storage
            metadata: Optional metadata
            
        Returns:
            Sync status ID
        """
        try:
            data = {
                "job_id": job_id,
                "file_path": file_path,
                "file_type": file_type,
                "checksum": checksum,
                "size_bytes": size_bytes,
                "storage_url": storage_url,
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "metadata": metadata or {}
            }
            
            response = self.client.table("sync_status").insert(data).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]["id"]
            else:
                raise Exception("Failed to create sync status")
                
        except Exception as e:
            raise Exception(f"Failed to create sync status: {str(e)}")
    
    def update_sync_status(
        self,
        sync_id: str,
        status: str,
        error: Optional[str] = None
    ) -> bool:
        """Update sync status for a file.
        
        Args:
            sync_id: Sync status ID
            status: New status
            error: Optional error message
            
        Returns:
            True if updated successfully
        """
        try:
            data = {
                "status": status,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if error:
                data["error"] = error
                data["last_attempt"] = datetime.utcnow().isoformat()
            
            if status == "completed":
                data["completed_at"] = datetime.utcnow().isoformat()
            
            response = self.client.table("sync_status").update(data).eq(
                "id", sync_id
            ).execute()
            
            return response.data is not None
            
        except Exception as e:
            raise Exception(f"Failed to update sync status: {str(e)}")
    
    def get_experiment_jobs(
        self,
        experiment_id: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> list[Dict[str, Any]]:
        """Get jobs for an experiment.
        
        Args:
            experiment_id: Experiment ID
            status: Optional status filter
            limit: Maximum number of jobs
            
        Returns:
            List of job records
        """
        try:
            query = self.client.table("jobs").select("*").eq(
                "experiment_id", experiment_id
            ).order(
                "created_at", desc=True
            ).limit(limit)
            
            if status:
                query = query.eq("status", status)
            
            response = query.execute()
            
            return response.data or []
            
        except Exception as e:
            raise Exception(f"Failed to get experiment jobs: {str(e)}")
    
    def get_experiment_stats(self, experiment_id: str) -> Dict[str, Any]:
        """Get statistics for an experiment.
        
        Args:
            experiment_id: Experiment ID
            
        Returns:
            Dictionary with experiment statistics
        """
        try:
            # Use the experiment_stats view
            response = self.client.table("experiment_stats").select("*").eq(
                "id", experiment_id
            ).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]
            
            # Fallback to manual calculation
            jobs = self.get_experiment_jobs(experiment_id, limit=1000)
            
            stats = {
                "total_jobs": len(jobs),
                "queued_jobs": len([j for j in jobs if j["status"] == "queued"]),
                "running_jobs": len([j for j in jobs if j["status"] == "running"]),
                "completed_jobs": len([j for j in jobs if j["status"] == "completed"]),
                "failed_jobs": len([j for j in jobs if j["status"] == "failed"]),
                "killed_jobs": len([j for j in jobs if j["status"] == "killed"])
            }
            
            return stats
            
        except Exception as e:
            raise Exception(f"Failed to get experiment stats: {str(e)}")
    
    def get_job_sync_status(self, job_id: str) -> list[Dict[str, Any]]:
        """Get sync status for all files from a job.
        
        Args:
            job_id: Job ID
            
        Returns:
            List of sync status records
        """
        try:
            response = self.client.table("sync_status").select("*").eq(
                "job_id", job_id
            ).order("created_at", desc=True).execute()
            
            return response.data or []
            
        except Exception as e:
            raise Exception(f"Failed to get job sync status: {str(e)}")
    
    def batch_sync_jobs(
        self,
        jobs: list[Dict[str, Any]],
        experiment_id: str
    ) -> Dict[str, int]:
        """Sync multiple jobs in batch.
        
        Args:
            jobs: List of job data dictionaries
            experiment_id: Experiment ID
            
        Returns:
            Dictionary with success/failed counts
        """
        results = {"success": 0, "failed": 0}
        
        for job_data in jobs:
            try:
                if self.sync_job(job_data, experiment_id):
                    results["success"] += 1
                else:
                    results["failed"] += 1
            except Exception:
                results["failed"] += 1
        
        return results
```

### 2. Create tests/implementation/test_step_3_3.py
```python
"""Test database operations in Supabase client."""
import os
import tempfile
import uuid
import pytest
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

from src.dr_exp.sync.supabase_client import SupabaseClient


def setup_test_env():
    """Load test environment variables."""
    env_file = Path(".env.test")
    if env_file.exists():
        load_dotenv(env_file)
    else:
        os.environ["SUPABASE_URL"] = "http://localhost:54321"
        os.environ["SUPABASE_KEY"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"


def test_experiment_operations():
    """Test experiment creation and retrieval."""
    setup_test_env()
    
    client = SupabaseClient()
    
    # Create new experiment
    exp_name = f"test_exp_{int(datetime.now().timestamp())}"
    base_path = "/tmp/test"
    metadata = {"created_by": "test", "purpose": "testing"}
    
    exp_id = client.get_or_create_experiment(exp_name, base_path, metadata)
    assert exp_id is not None
    assert len(exp_id) == 36  # UUID format
    
    # Get same experiment again (should return same ID)
    exp_id2 = client.get_or_create_experiment(exp_name, base_path)
    assert exp_id2 == exp_id
    
    # Create different experiment
    exp_id3 = client.get_or_create_experiment(exp_name + "_2", base_path)
    assert exp_id3 != exp_id
    
    return exp_id


def test_job_sync():
    """Test syncing jobs to database."""
    setup_test_env()
    
    client = SupabaseClient()
    
    # Create experiment
    exp_name = f"job_sync_test_{int(datetime.now().timestamp())}"
    exp_id = client.get_or_create_experiment(exp_name, "/tmp/test")
    
    # Create job data (mimicking local JobDB format)
    job_id = str(uuid.uuid4())
    job_data = {
        "id": job_id,
        "config": {
            "_target_": "test.train",
            "epochs": 10,
            "lr": 0.001
        },
        "priority": 500,
        "status": "queued",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "attempts": 0
    }
    
    # Sync job
    success = client.sync_job(job_data, exp_id)
    assert success
    
    # Update job and sync again
    job_data["status"] = "running"
    job_data["worker_id"] = "test_worker"
    job_data["started_at"] = datetime.utcnow().isoformat()
    job_data["last_heartbeat"] = datetime.utcnow().isoformat()
    
    success = client.sync_job(job_data, exp_id)
    assert success
    
    # Complete job
    job_data["status"] = "completed"
    job_data["completed_at"] = datetime.utcnow().isoformat()
    job_data["final_metrics"] = {
        "accuracy": 0.95,
        "loss": 0.15
    }
    
    success = client.sync_job(job_data, exp_id)
    assert success
    
    return exp_id, job_id


def test_sync_status():
    """Test sync status tracking."""
    setup_test_env()
    
    client = SupabaseClient()
    
    # Create experiment and job
    exp_name = f"sync_status_test_{int(datetime.now().timestamp())}"
    exp_id = client.get_or_create_experiment(exp_name, "/tmp/test")
    
    job_id = str(uuid.uuid4())
    job_data = {
        "id": job_id,
        "config": {"_target_": "test.train"},
        "priority": 100,
        "status": "running",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    client.sync_job(job_data, exp_id)
    
    # Create sync status for uploaded file
    sync_id = client.create_sync_status(
        job_id=job_id,
        file_path="/tmp/test/metrics.jsonl",
        file_type="metrics",
        checksum="abc123def456",
        size_bytes=1024,
        storage_url="http://example.com/storage/metrics.jsonl",
        metadata={"lines": 100}
    )
    
    assert sync_id is not None
    
    # Get sync status for job
    sync_records = client.get_job_sync_status(job_id)
    assert len(sync_records) == 1
    assert sync_records[0]["file_type"] == "metrics"
    assert sync_records[0]["status"] == "completed"


def test_experiment_stats():
    """Test getting experiment statistics."""
    setup_test_env()
    
    client = SupabaseClient()
    
    # Create experiment with multiple jobs
    exp_name = f"stats_test_{int(datetime.now().timestamp())}"
    exp_id = client.get_or_create_experiment(exp_name, "/tmp/test")
    
    # Create jobs in different states
    job_configs = [
        {"status": "queued", "priority": 100},
        {"status": "queued", "priority": 200},
        {"status": "running", "worker_id": "worker1"},
        {"status": "completed", "final_metrics": {"acc": 0.9}},
        {"status": "failed", "error": "OOM"}
    ]
    
    for i, config in enumerate(job_configs):
        job_data = {
            "id": str(uuid.uuid4()),
            "config": {"_target_": "test.train"},
            "priority": config.get("priority", 100),
            "status": config["status"],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Add status-specific fields
        if config["status"] == "running":
            job_data["worker_id"] = config["worker_id"]
            job_data["started_at"] = datetime.utcnow().isoformat()
        elif config["status"] == "completed":
            job_data["completed_at"] = datetime.utcnow().isoformat()
            job_data["final_metrics"] = config["final_metrics"]
        elif config["status"] == "failed":
            job_data["error"] = config["error"]
            job_data["completed_at"] = datetime.utcnow().isoformat()
        
        client.sync_job(job_data, exp_id)
    
    # Get stats
    stats = client.get_experiment_stats(exp_id)
    
    assert stats["total_jobs"] == 5
    assert stats["queued_jobs"] == 2
    assert stats["running_jobs"] == 1
    assert stats["completed_jobs"] == 1
    assert stats["failed_jobs"] == 1


def test_batch_operations():
    """Test batch syncing of jobs."""
    setup_test_env()
    
    client = SupabaseClient()
    
    # Create experiment
    exp_name = f"batch_test_{int(datetime.now().timestamp())}"
    exp_id = client.get_or_create_experiment(exp_name, "/tmp/test")
    
    # Create multiple jobs
    jobs = []
    for i in range(10):
        job = {
            "id": str(uuid.uuid4()),
            "config": {
                "_target_": "test.train",
                "index": i
            },
            "priority": i * 100,
            "status": "queued",
            "created_at": (datetime.utcnow() - timedelta(minutes=i)).isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        jobs.append(job)
    
    # Batch sync
    results = client.batch_sync_jobs(jobs, exp_id)
    
    assert results["success"] == 10
    assert results["failed"] == 0
    
    # Verify jobs exist
    db_jobs = client.get_experiment_jobs(exp_id)
    assert len(db_jobs) == 10
    
    # Check ordering (newest first)
    assert db_jobs[0]["config"]["index"] == 0  # Most recent


def test_job_queries():
    """Test querying jobs with filters."""
    setup_test_env()
    
    client = SupabaseClient()
    
    # Create experiment
    exp_name = f"query_test_{int(datetime.now().timestamp())}"
    exp_id = client.get_or_create_experiment(exp_name, "/tmp/test")
    
    # Create jobs with different statuses
    statuses = ["queued", "queued", "running", "completed", "failed"]
    job_ids = []
    
    for i, status in enumerate(statuses):
        job_data = {
            "id": str(uuid.uuid4()),
            "config": {"_target_": "test.train"},
            "priority": 100,
            "status": status,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        client.sync_job(job_data, exp_id)
        job_ids.append(job_data["id"])
    
    # Query all jobs
    all_jobs = client.get_experiment_jobs(exp_id)
    assert len(all_jobs) == 5
    
    # Query by status
    queued_jobs = client.get_experiment_jobs(exp_id, status="queued")
    assert len(queued_jobs) == 2
    
    running_jobs = client.get_experiment_jobs(exp_id, status="running")
    assert len(running_jobs) == 1
    
    # Test limit
    limited_jobs = client.get_experiment_jobs(exp_id, limit=3)
    assert len(limited_jobs) == 3


def test_full_sync_workflow():
    """Test complete sync workflow from file upload to status tracking."""
    setup_test_env()
    
    client = SupabaseClient()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create experiment
        exp_name = f"workflow_test_{int(datetime.now().timestamp())}"
        exp_id = client.get_or_create_experiment(exp_name, tmpdir)
        
        # Create and sync job
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "config": {
                "_target_": "test.train",
                "epochs": 5
            },
            "priority": 800,
            "status": "running",
            "worker_id": "workflow_worker",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "started_at": datetime.utcnow().isoformat()
        }
        
        client.sync_job(job_data, exp_id)
        
        # Create and upload a file
        test_file = Path(tmpdir) / "results.json"
        test_file.write_text('{"accuracy": 0.92, "loss": 0.23}')
        
        storage_url, checksum = client.upload_file(
            file_path=test_file,
            experiment_name=exp_name,
            job_id=job_id,
            file_type="metrics"
        )
        
        # Track sync status
        sync_id = client.create_sync_status(
            job_id=job_id,
            file_path=str(test_file),
            file_type="metrics",
            checksum=checksum,
            size_bytes=test_file.stat().st_size,
            storage_url=storage_url
        )
        
        # Complete the job
        job_data["status"] = "completed"
        job_data["completed_at"] = datetime.utcnow().isoformat()
        job_data["final_metrics"] = {"accuracy": 0.92, "loss": 0.23}
        
        client.sync_job(job_data, exp_id)
        
        # Verify everything
        stats = client.get_experiment_stats(exp_id)
        assert stats["completed_jobs"] == 1
        
        sync_records = client.get_job_sync_status(job_id)
        assert len(sync_records) == 1
        assert sync_records[0]["status"] == "completed"


```

## Validation
```bash
# Run database operations tests
pt tests/implementation/test_step_3_3.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_3_3.py::test_experiment_operations PASSED
# tests/implementation/test_step_3_3.py::test_job_sync PASSED
# tests/implementation/test_step_3_3.py::test_sync_status PASSED
# tests/implementation/test_step_3_3.py::test_experiment_stats PASSED
# tests/implementation/test_step_3_3.py::test_batch_operations PASSED
# tests/implementation/test_step_3_3.py::test_job_queries PASSED
# tests/implementation/test_step_3_3.py::test_full_sync_workflow PASSED
# ============================== 7 passed in X.XXs ===============================

# Check data in Supabase Studio
open http://localhost:54323
# Navigate to Table Editor → experiments, jobs, sync_status

# Run all Phase 3 tests so far
pt tests/implementation/test_step_3_1.py -v
pt tests/implementation/test_step_3_2.py -v
pt tests/implementation/test_step_3_3.py -v

# Code quality check
ckdr
```

## Common Mistakes
- DO NOT: Sync incomplete job data - validate required fields first
- DO NOT: Forget to handle upsert conflicts - use on_conflict parameter
- DO NOT: Store large data in JSONB fields - use storage for files
- DO NOT: Query without limits - always set reasonable limits
- DO NOT: Ignore timezone issues - use UTC everywhere

## Next Step
Proceed to Step 3.4: Worker Sync Integration
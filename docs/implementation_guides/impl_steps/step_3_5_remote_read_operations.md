# Step 3.5: Remote Read Operations

## Goal (1 sentence)
Add remote read capabilities to JobDB and update the API to support reading job data from Supabase for true remote monitoring.

## Prerequisites
- [ ] Step 3.4 completed with worker sync working
- [ ] Jobs and files are being synced to Supabase
- [ ] test_step_3_4.py passes

## Implementation

### 1. Update src/dr_exp/core/job_db.py
Add these imports at the top:
```python
from typing import Tuple, List, Dict, Any, Optional
from pathlib import Path
```

Add these methods to the JobDB class:
```python
    def enable_remote_read(self, supabase_url: Optional[str] = None, 
                          supabase_key: Optional[str] = None) -> bool:
        """Enable remote read operations from Supabase.
        
        Args:
            supabase_url: Supabase URL (uses env var if not provided)
            supabase_key: Supabase key (uses env var if not provided)
            
        Returns:
            True if remote read enabled successfully
        """
        try:
            from ..sync.supabase_client import SupabaseClient
            
            self.remote_client = SupabaseClient(url=supabase_url, key=supabase_key)
            self.remote_experiment_id = self.remote_client.get_or_create_experiment(
                experiment_name=self.experiment_name,
                base_path=str(self.base_path)
            )
            self.remote_enabled = True
            return True
            
        except Exception as e:
            print(f"Failed to enable remote read: {e}")
            self.remote_client = None
            self.remote_experiment_id = None
            self.remote_enabled = False
            return False
    
    def list_jobs_remote(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List jobs from remote Supabase database.
        
        Args:
            status: Optional status filter
            
        Returns:
            List of job data dicts from Supabase
        """
        if not self.remote_enabled or not self.remote_client:
            return []
        
        try:
            return self.remote_client.get_experiment_jobs(
                self.remote_experiment_id,
                status=status,
                limit=1000
            )
        except Exception as e:
            print(f"Failed to list remote jobs: {e}")
            return []
    
    def get_job_remote(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a job from remote Supabase database.
        
        Args:
            job_id: Job ID to retrieve
            
        Returns:
            Job data dict or None if not found
        """
        if not self.remote_enabled or not self.remote_client:
            return None
        
        try:
            jobs = self.remote_client.get_experiment_jobs(
                self.remote_experiment_id,
                limit=1
            )
            
            # Filter by ID (since we don't have direct ID query)
            for job in jobs:
                if job["id"] == job_id:
                    return job
            
            return None
            
        except Exception as e:
            print(f"Failed to get remote job: {e}")
            return None
    
    def get_experiment_info_remote(self) -> Dict[str, Any]:
        """Get experiment info from remote Supabase.
        
        Returns:
            Dict with experiment metadata and stats
        """
        if not self.remote_enabled or not self.remote_client:
            return self.get_experiment_info()  # Fallback to local
        
        try:
            stats = self.remote_client.get_experiment_stats(self.remote_experiment_id)
            
            return {
                "experiment_name": self.experiment_name,
                "base_path": str(self.base_path),
                "experiment_path": str(self.experiment_path),
                "experiment_id": self.remote_experiment_id,
                "total_jobs": stats.get("total_jobs", 0),
                "status_counts": {
                    "queued": stats.get("queued_jobs", 0),
                    "running": stats.get("running_jobs", 0),
                    "completed": stats.get("completed_jobs", 0),
                    "failed": stats.get("failed_jobs", 0),
                    "killed": stats.get("killed_jobs", 0)
                },
                "remote": True
            }
            
        except Exception as e:
            print(f"Failed to get remote experiment info: {e}")
            return self.get_experiment_info()
    
    def download_job_artifacts(self, job_id: str, 
                             target_dir: Optional[Path] = None) -> List[Path]:
        """Download job artifacts from remote storage.
        
        Args:
            job_id: Job ID to download artifacts for
            target_dir: Directory to download to (defaults to storage path)
            
        Returns:
            List of downloaded file paths
        """
        if not self.remote_enabled or not self.remote_client:
            return []
        
        if target_dir is None:
            target_dir = self.get_storage_path(job_id)
        
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        
        downloaded = []
        
        try:
            # Get sync status for job
            sync_records = self.remote_client.get_job_sync_status(job_id)
            
            for record in sync_records:
                if record["status"] != "completed":
                    continue
                
                # Extract storage path from URL or metadata
                file_name = Path(record["file_path"]).name
                storage_path = f"{self.experiment_name}/jobs/{job_id}/{file_name}"
                
                local_path = target_dir / file_name
                
                try:
                    self.remote_client.download_file(storage_path, local_path)
                    downloaded.append(local_path)
                    print(f"Downloaded: {file_name}")
                except Exception as e:
                    print(f"Failed to download {file_name}: {e}")
            
            return downloaded
            
        except Exception as e:
            print(f"Failed to download artifacts: {e}")
            return []
    
    def sync_mode(self) -> str:
        """Get current sync mode.
        
        Returns:
            'local', 'remote', or 'hybrid'
        """
        if self.remote_enabled:
            return 'remote'
        else:
            return 'local'
```

Add initialization in `__init__`:
```python
        # Remote read support (disabled by default)
        self.remote_enabled = False
        self.remote_client = None
        self.remote_experiment_id = None
```

### 2. Create src/dr_exp/api/__init__.py
```python
# Empty file to make this a package
```

### 3. Create src/dr_exp/api/simple_api.py
```python
"""Simple FastAPI application for remote monitoring."""
import os
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from ..core.job_db import JobDB


app = FastAPI(title="dr_exp API", version="1.0.0")

# Enable CORS for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global JobDB instance (initialized on startup)
job_db: Optional[JobDB] = None


@app.on_event("startup")
async def startup_event():
    """Initialize JobDB with remote read enabled."""
    global job_db
    
    # Get configuration from environment
    base_path = os.environ.get("DR_EXP_BASE_PATH")
    experiment = os.environ.get("DR_EXP_EXPERIMENT")
    
    if not base_path or not experiment:
        print("ERROR: DR_EXP_BASE_PATH and DR_EXP_EXPERIMENT must be set")
        return
    
    # Initialize JobDB
    job_db = JobDB(base_path=base_path, experiment_name=experiment)
    
    # Enable remote read
    if job_db.enable_remote_read():
        print(f"Remote read enabled for {experiment}")
        print(f"Sync mode: {job_db.sync_mode()}")
    else:
        print(f"Remote read not available - using local data only")


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "service": "dr_exp API",
        "version": "1.0.0",
        "experiment": job_db.experiment_name if job_db else None,
        "sync_mode": job_db.sync_mode() if job_db else "not_initialized"
    }


@app.get("/experiment/info")
async def get_experiment_info():
    """Get experiment information and statistics."""
    if not job_db:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    info = job_db.get_experiment_info_remote()
    return info


@app.get("/jobs")
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
    use_remote: bool = Query(True, description="Use remote data if available")
):
    """List jobs in the experiment."""
    if not job_db:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if use_remote and job_db.remote_enabled:
        jobs = job_db.list_jobs_remote(status=status)
    else:
        jobs = job_db.list_jobs(status=status)
    
    # Apply limit
    jobs = jobs[:limit]
    
    return {
        "jobs": jobs,
        "count": len(jobs),
        "source": "remote" if (use_remote and job_db.remote_enabled) else "local"
    }


@app.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    use_remote: bool = Query(True, description="Use remote data if available")
):
    """Get details for a specific job."""
    if not job_db:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if use_remote and job_db.remote_enabled:
        job = job_db.get_job_remote(job_id)
    else:
        job = job_db.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job


@app.get("/jobs/{job_id}/artifacts")
async def list_job_artifacts(job_id: str):
    """List artifacts for a job."""
    if not job_db or not job_db.remote_enabled:
        raise HTTPException(
            status_code=503, 
            detail="Remote storage not available"
        )
    
    try:
        sync_records = job_db.remote_client.get_job_sync_status(job_id)
        
        artifacts = []
        for record in sync_records:
            if record["status"] == "completed":
                artifacts.append({
                    "file_name": Path(record["file_path"]).name,
                    "file_type": record["file_type"],
                    "size_bytes": record["size_bytes"],
                    "checksum": record["checksum"],
                    "uploaded_at": record["completed_at"]
                })
        
        return {
            "job_id": job_id,
            "artifacts": artifacts,
            "count": len(artifacts)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/jobs/{job_id}/download")
async def download_job_artifacts(job_id: str):
    """Download all artifacts for a job."""
    if not job_db:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    if not job_db.remote_enabled:
        raise HTTPException(
            status_code=503,
            detail="Remote storage not available"
        )
    
    try:
        downloaded = job_db.download_job_artifacts(job_id)
        
        return {
            "job_id": job_id,
            "downloaded_files": [str(p.name) for p in downloaded],
            "count": len(downloaded),
            "target_dir": str(job_db.get_storage_path(job_id))
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/queue/stats")
async def get_queue_stats():
    """Get job queue statistics."""
    if not job_db:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    info = job_db.get_experiment_info_remote()
    
    return {
        "total_jobs": info["total_jobs"],
        "by_status": info["status_counts"],
        "queue_length": info["status_counts"].get("queued", 0),
        "active_jobs": info["status_counts"].get("running", 0)
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    health = {
        "status": "healthy" if job_db else "unhealthy",
        "job_db": job_db is not None,
        "remote_enabled": job_db.remote_enabled if job_db else False
    }
    
    if job_db and job_db.remote_enabled:
        try:
            # Test remote connection
            job_db.remote_client.test_connection()
            health["remote_connection"] = True
        except Exception:
            health["remote_connection"] = False
    
    return health
```

### 4. Create tests/implementation/test_step_3_5.py
```python
"""Test remote read operations."""
import os
import tempfile
import asyncio
import pytest
import json
import shutil
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, UTC
from dotenv import load_dotenv

from fastapi.testclient import TestClient

from src.dr_exp.core.job_db import JobDB
from src.dr_exp.worker.base import Worker
from src.dr_exp.api.simple_api import app, job_db as api_job_db


def setup_test_env() -> None:
    """Load test environment variables."""
    env_file = Path(".env.test")
    if env_file.exists():
        load_dotenv(env_file)
    else:
        os.environ["SUPABASE_URL"] = "http://localhost:54321"
        os.environ["SUPABASE_KEY"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"


def test_remote_read_operations() -> None:
    """Test JobDB remote read functionality."""
    setup_test_env()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create JobDB and enable remote
        job_db = JobDB(base_path=tmpdir, experiment_name="remote_read_test", validate=False)
        
        success = job_db.enable_remote_read()
        assert success
        assert job_db.remote_enabled
        assert job_db.remote_experiment_id is not None
        
        assert job_db.experiment_name == "remote_read_test"
        
        # Create and sync a job
        config = {
            "_target_": "src.dr_exp.trainers.test_trainer.train",
            "epochs": 2
        }
        job_id = job_db.create_job(config, priority=500)
        
        # Run with worker to sync
        worker = Worker(job_db=job_db, worker_id="sync_worker", sync_enabled=True)
        worker.run(max_jobs=1)
        
        # Wait for sync
        time.sleep(3)
        
        # Test remote list
        remote_jobs = job_db.list_jobs_remote()
        assert len(remote_jobs) > 0
        assert any(j["id"] == job_id for j in remote_jobs)
        
        # Test remote get
        remote_job = job_db.get_job_remote(job_id)
        assert remote_job is not None
        assert remote_job["id"] == job_id
        assert remote_job["status"] == "completed"
        
        # Test remote experiment info
        remote_info = job_db.get_experiment_info_remote()
        assert remote_info["total_jobs"] >= 1
        assert remote_info["status_counts"]["completed"] >= 1
        assert remote_info["remote"] is True
        
        # Test sync mode
        assert job_db.sync_mode() == "remote"


def test_artifact_download() -> None:
    """Test downloading artifacts from remote storage."""
    setup_test_env()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup and run a job
        job_db = JobDB(base_path=tmpdir, experiment_name="download_test", validate=False)
        job_db.enable_remote_read()
        
        config = {
            "_target_": "src.dr_exp.trainers.decon_trainer.train_classification",
            "model": {"architecture": "resnet18"},
            "optim": {"lr": 0.001},
            "epochs": 2
        }
        job_id = job_db.create_job(config)
        
        # Run and sync
        worker = Worker(job_db=job_db, worker_id="download_worker", sync_enabled=True)
        worker.run(max_jobs=1)
        
        time.sleep(5)  # Wait for sync
        
        # Clear local storage to test download
        storage_path = job_db.get_storage_path(job_id)
        if storage_path.exists():
            shutil.rmtree(storage_path)
        
        # Download artifacts
        download_dir = Path(tmpdir) / "downloads"
        downloaded = job_db.download_job_artifacts(job_id, download_dir)
        
        assert len(downloaded) > 0
        
        for file_path in downloaded:
            assert file_path.exists()
        
        # Verify content
        expected_files = ["metrics.jsonl", "config.json"]
        downloaded_names = [p.name for p in downloaded]
        
        for expected in expected_files:
            assert any(expected in name for name in downloaded_names)


def test_api_endpoints() -> None:
    """Test API endpoints with remote data."""
    setup_test_env()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set environment for API
        os.environ["DR_EXP_BASE_PATH"] = tmpdir
        os.environ["DR_EXP_EXPERIMENT"] = "api_test"
        
        # Create test data
        job_db = JobDB(base_path=tmpdir, experiment_name="api_test", validate=False)
        job_db.enable_remote_read()
        
        # Create jobs
        job_ids = []
        for i in range(3):
            config = {"_target_": "test.train", "index": i}
            job_id = job_db.create_job(config, priority=i * 100)
            job_ids.append(job_id)
        
        # Run one job
        worker = Worker(job_db=job_db, worker_id="api_worker", sync_enabled=True)
        worker.run(max_jobs=1)
        
        time.sleep(3)
        
        # Initialize API
        from src.dr_exp import api
        api.simple_api.job_db = job_db
        
        # Create test client
        client = TestClient(app)
        
        # Test root endpoint
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["experiment"] == "api_test"
        assert data["sync_mode"] == "remote"
        
        # Test experiment info
        response = client.get("/experiment/info")
        assert response.status_code == 200
        info = response.json()
        assert info["experiment_name"] == "api_test"
        assert info["total_jobs"] >= 3
        
        # Test job listing
        response = client.get("/jobs")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 3
        assert data["source"] == "remote"
        
        # Test specific job
        response = client.get(f"/jobs/{job_ids[0]}")
        assert response.status_code == 200
        job = response.json()
        assert job["id"] == job_ids[0]
        
        # Test queue stats
        response = client.get("/queue/stats")
        assert response.status_code == 200
        stats = response.json()
        assert stats["total_jobs"] >= 3
        assert "by_status" in stats
        
        # Test health check
        response = client.get("/health")
        assert response.status_code == 200
        health = response.json()
        assert health["status"] == "healthy"
        assert health["remote_enabled"] is True


def test_fallback_to_local() -> None:
    """Test fallback to local data when remote unavailable."""
    setup_test_env()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create JobDB without remote
        job_db = JobDB(base_path=tmpdir, experiment_name="fallback_test", validate=False)
        
        # Try to enable with bad credentials
        success = job_db.enable_remote_read(
            supabase_url="http://invalid",
            supabase_key="invalid"
        )
        assert not success
        assert not job_db.remote_enabled
        
        # Create local job
        config = {"_target_": "test.train"}
        job_id = job_db.create_job(config)
        
        # Should fall back to local operations
        jobs = job_db.list_jobs_remote()  # Should return empty
        assert len(jobs) == 0
        
        local_jobs = job_db.list_jobs()
        assert len(local_jobs) == 1
        
        info = job_db.get_experiment_info_remote()
        assert info["total_jobs"] == 1
        assert "remote" not in info or not info["remote"]
        
        assert job_db.sync_mode() == "local"


def test_remote_status_filter() -> None:
    """Test filtering remote jobs by status."""
    setup_test_env()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="filter_test", validate=False)
        job_db.enable_remote_read()
        
        # Create jobs with different statuses
        configs = [
            {"status": "queued"},
            {"status": "queued"},
            {"status": "running"},
            {"status": "completed"},
            {"status": "failed"}
        ]
        
        for cfg in configs:
            job_id = job_db.create_job({"_target_": "test.train"})
            
            if cfg["status"] == "running":
                job_db.claim_next_job("worker")
            elif cfg["status"] == "completed":
                job = job_db.claim_next_job("worker")
                job_db.complete_job(job["id"])
            elif cfg["status"] == "failed":
                job = job_db.claim_next_job("worker")
                job_db.fail_job(job["id"], "Test error")
        
        # Sync to remote
        if job_db.remote_enabled:
            for job in job_db.list_jobs():
                job_db.remote_client.sync_job(job, job_db.remote_experiment_id)
        
        # Test filters
        queued = job_db.list_jobs_remote(status="queued")
        assert len(queued) == 2
        
        running = job_db.list_jobs_remote(status="running")
        assert len(running) == 1
        
        completed = job_db.list_jobs_remote(status="completed")
        assert len(completed) == 1


def test_full_remote_workflow() -> None:
    """Test complete workflow with remote operations."""
    setup_test_env()
    
    from click.testing import CliRunner
    from src.dr_exp.cli.main import cli
    
    runner = CliRunner()
    
    with runner.isolated_filesystem():
        # Setup environment
        os.environ["DR_EXP_BASE_PATH"] = "."
        os.environ["DR_EXP_EXPERIMENT"] = "remote_workflow"
        
        # Initialize
        result = runner.invoke(cli, [
            '--base-path', '.',
            '--experiment', 'remote_workflow',
            'init'
        ])
        assert result.exit_code == 0
        
        # Submit jobs
        Path("job.yaml").write_text("""
_target_: src.dr_exp.trainers.decon_trainer.train_classification
model: {architecture: resnet18}
optim: {lr: 0.001}
epochs: 3
""")
        
        for i in range(3):
            result = runner.invoke(cli, [
                '--base-path', '.',
                '--experiment', 'remote_workflow',
                'submit', 'job.yaml',
                '--priority', str(100 + i * 100)
            ])
            assert result.exit_code == 0
        
        # Run worker with sync
        result = runner.invoke(cli, [
            '--base-path', '.',
            '--experiment', 'remote_workflow',
            'worker',
            '--worker-id', 'remote_worker',
            '--max-jobs', '2'
        ])
        assert result.exit_code == 0
        
        # Now test remote read via API
        job_db = JobDB(base_path=".", experiment_name="remote_workflow", validate=False)
        job_db.enable_remote_read()
        
        # Should see jobs in remote
        remote_jobs = job_db.list_jobs_remote()
        assert len(remote_jobs) >= 2  # At least 2 synced
        
        # Check statuses
        statuses = {j["status"] for j in remote_jobs}
        assert "completed" in statuses
        
        # Download artifacts for completed job
        completed = [j for j in remote_jobs if j["status"] == "completed"][0]
        downloaded = job_db.download_job_artifacts(completed["id"])
        assert len(downloaded) > 0


```

## Validation
```bash
# Install dependencies
uv add fastapi uvicorn httpx

# Run remote read tests
pt tests/implementation/test_step_3_5.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_3_5.py::test_remote_read_operations PASSED
# tests/implementation/test_step_3_5.py::test_artifact_download PASSED
# tests/implementation/test_step_3_5.py::test_api_endpoints PASSED
# tests/implementation/test_step_3_5.py::test_fallback_to_local PASSED
# tests/implementation/test_step_3_5.py::test_remote_status_filter PASSED
# tests/implementation/test_step_3_5.py::test_full_remote_workflow PASSED
# ============================== 6 passed in X.XXs ===============================

# 🎉 Phase 3 (Supabase Integration) complete!

# Start API server
export DR_EXP_BASE_PATH=/tmp/test
export DR_EXP_EXPERIMENT=api_test
export SUPABASE_URL=http://localhost:54321
export SUPABASE_KEY=<your-key>

uvicorn src.dr_exp.api.simple_api:app --reload

# Test API endpoints
curl http://localhost:8000/
curl http://localhost:8000/experiment/info
curl http://localhost:8000/jobs
curl http://localhost:8000/health

# Run ALL tests to ensure nothing broke
for i in {1..3}; do
  for j in {1..9}; do
    test_file="tests/implementation/test_step_${i}_${j}.py"
    if [ -f "$test_file" ]; then
      echo "Running $test_file..."
      pt "$test_file" -v || exit 1
    fi
  done
done

# Code quality check
ckdr
```

## Common Mistakes
- DO NOT: Always use remote - respect the use_remote parameter
- DO NOT: Fail if remote is unavailable - gracefully fall back to local
- DO NOT: Download all artifacts automatically - it can be expensive
- DO NOT: Cache remote data indefinitely - it can become stale
- DO NOT: Expose Supabase credentials in API responses

## Complete Implementation! 🎉

You have successfully implemented all 15 steps across 3 phases:

### Phase 1: JobDB Foundation ✓
- Basic JobDB with file storage
- Concurrent job claiming with locks
- Complete job lifecycle management
- Operational features (kill, boost, recover)

### Phase 2: Worker System ✓
- Basic worker with Hydra dispatch
- Sync queue with retry logic
- Background sync and heartbeat threads
- Full CLI with job management
- Training integration with structured logging

### Phase 3: Supabase Integration ✓
- Database schema and storage bucket
- File upload with checksums
- Job and sync status tracking
- Worker integration with real sync
- Remote read operations and API

The system now provides:
- Local-first operation with optional cloud sync
- Priority-based job scheduling
- Concurrent worker support
- Full job lifecycle tracking
- Remote monitoring capabilities
- Artifact storage and retrieval
- Comprehensive CLI interface
- RESTful API for remote access

## Next Steps
The implementation guides are complete! The system is ready for:
- Phase 4: Enhanced API with WebSocket support
- Phase 5: Cloud deployment (Vercel)
- Phase 6: Storage cleanup tools

But the core functionality is fully implemented and tested!
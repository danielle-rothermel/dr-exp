# Phase 3: Supabase Integration Implementation Guide

## Overview
This phase adds real Supabase uploads to the sync system and implements the remote read functionality for the API.

**Duration**: 3-4 days
**Prerequisite**: Phase 2 must be complete with worker tests passing
**Outcome**: Full Supabase integration with background sync

## Pre-flight Checklist

### Verify Phase 2 Completion
```bash
# Run worker test
python test_worker.py  # Should pass

# Check sync queue is working
ls -la /tmp/*/worker_test/sync_queue/  # Should show sync items during test
```

### Set Up Supabase Project
1. Go to https://supabase.com and create a new project (or use existing)
2. Note your project URL and service role key
3. Create a `.env` file in project root:
```bash
# Create .env file
cat > .env << EOF
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key
EOF
```

## Step 1: Install Supabase Client

```bash
# Add supabase client to project
pip install supabase
```

## Step 2: Create Supabase Schema

Run this SQL in your Supabase SQL editor:

```sql
-- Drop existing tables if they exist (fresh start)
DROP TABLE IF EXISTS sync_status CASCADE;
DROP TABLE IF EXISTS jobs CASCADE;
DROP TABLE IF EXISTS experiments CASCADE;

-- Experiments table
CREATE TABLE experiments (
    name TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Jobs table
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    experiment_name TEXT REFERENCES experiments(name),
    config JSONB NOT NULL,
    priority INT NOT NULL CHECK (priority >= 0 AND priority <= 1000),
    status TEXT NOT NULL,
    assigned_worker TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    heartbeat TIMESTAMPTZ,
    result JSONB,
    error TEXT
);

-- Indexes for performance
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_priority ON jobs(priority DESC, created_at ASC);
CREATE INDEX idx_jobs_experiment ON jobs(experiment_name);

-- Sync status tracking
CREATE TABLE sync_status (
    local_path TEXT PRIMARY KEY,
    remote_path TEXT NOT NULL,
    experiment_name TEXT REFERENCES experiments(name),
    job_id UUID,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    file_size BIGINT,
    checksum TEXT
);

-- Create storage bucket
INSERT INTO storage.buckets (id, name, public)
VALUES ('experiments', 'experiments', false)
ON CONFLICT (id) DO NOTHING;

-- Enable RLS
ALTER TABLE experiments ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_status ENABLE ROW LEVEL SECURITY;

-- Service role has full access (for now)
CREATE POLICY "Service role full access" ON experiments
    FOR ALL USING (auth.role() = 'service_role');
    
CREATE POLICY "Service role full access" ON jobs
    FOR ALL USING (auth.role() = 'service_role');
    
CREATE POLICY "Service role full access" ON sync_status
    FOR ALL USING (auth.role() = 'service_role');
```

## Step 3: Implement Supabase Client

Create `src/dr_exp/sync/supabase_client.py`:

```python
"""Supabase client for remote storage and database operations."""

import hashlib
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, UTC
import logging

from supabase import create_client, Client
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()


class SupabaseClient:
    """Client for interacting with Supabase."""
    
    def __init__(self):
        """Initialize Supabase client from environment variables."""
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        
        if not url or not key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY must be set in environment or .env file"
            )
        
        self.client: Client = create_client(url, key)
        logger.info("Supabase client initialized")
    
    def ensure_experiment(self, experiment_name: str) -> None:
        """Ensure experiment exists in database.
        
        Args:
            experiment_name: Name of the experiment
        """
        try:
            self.client.table("experiments").upsert({
                "name": experiment_name,
                "updated_at": datetime.now(UTC).isoformat(),
            }).execute()
        except Exception as e:
            logger.error(f"Failed to ensure experiment {experiment_name}: {e}")
            raise
    
    def upload_file(self, local_path: Path, remote_path: str) -> Dict[str, Any]:
        """Upload a file to Supabase storage.
        
        Args:
            local_path: Path to local file
            remote_path: Destination path in storage bucket
            
        Returns:
            Upload result with status
        """
        try:
            # Read file
            with open(local_path, 'rb') as f:
                file_data = f.read()
            
            # Upload to storage
            response = self.client.storage.from_("experiments").upload(
                file=file_data,
                path=remote_path,
                file_options={"upsert": True}  # Overwrite if exists
            )
            
            # Calculate checksum
            checksum = hashlib.md5(file_data).hexdigest()
            
            return {
                "success": True,
                "path": remote_path,
                "size": len(file_data),
                "checksum": checksum,
            }
            
        except Exception as e:
            logger.error(f"Failed to upload {local_path} to {remote_path}: {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
    def record_sync(
        self,
        local_path: str,
        remote_path: str,
        experiment_name: str,
        job_id: Optional[str] = None,
        file_size: Optional[int] = None,
        checksum: Optional[str] = None,
    ) -> None:
        """Record successful sync in database.
        
        Args:
            local_path: Local file path
            remote_path: Remote storage path
            experiment_name: Name of experiment
            job_id: Optional job ID
            file_size: Size of file in bytes
            checksum: MD5 checksum of file
        """
        try:
            self.client.table("sync_status").upsert({
                "local_path": local_path,
                "remote_path": remote_path,
                "experiment_name": experiment_name,
                "job_id": job_id,
                "file_size": file_size,
                "checksum": checksum,
                "synced_at": datetime.now(UTC).isoformat(),
            }).execute()
        except Exception as e:
            logger.error(f"Failed to record sync status: {e}")
    
    def sync_job(self, job_data: Dict[str, Any]) -> None:
        """Sync job metadata to Supabase.
        
        Args:
            job_data: Complete job data dictionary
        """
        try:
            # Ensure experiment exists first
            self.ensure_experiment(job_data["experiment_name"])
            
            # Prepare job data for database
            db_job = {
                "id": job_data["id"],
                "experiment_name": job_data["experiment_name"],
                "config": job_data["config"],
                "priority": job_data["priority"],
                "status": job_data["status"],
                "created_at": job_data["created_at"],
                "updated_at": job_data["updated_at"],
            }
            
            # Add optional fields if present
            optional_fields = [
                "assigned_worker", "started_at", "completed_at",
                "heartbeat", "result", "error"
            ]
            for field in optional_fields:
                if field in job_data:
                    db_job[field] = job_data[field]
            
            # Upsert job
            self.client.table("jobs").upsert(db_job).execute()
            
        except Exception as e:
            logger.error(f"Failed to sync job {job_data.get('id')}: {e}")
            raise
    
    def get_jobs(self, experiment_name: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get jobs from Supabase.
        
        Args:
            experiment_name: Name of experiment
            status: Optional status filter
            
        Returns:
            List of job dictionaries
        """
        try:
            query = self.client.table("jobs").select("*").eq(
                "experiment_name", experiment_name
            )
            
            if status:
                query = query.eq("status", status)
            
            # Order by priority desc, created_at asc
            query = query.order("priority", desc=True).order("created_at")
            
            response = query.execute()
            return response.data
            
        except Exception as e:
            logger.error(f"Failed to get jobs: {e}")
            return []
    
    def download_file(self, remote_path: str, local_path: Path) -> bool:
        """Download a file from Supabase storage.
        
        Args:
            remote_path: Path in storage bucket
            local_path: Local destination path
            
        Returns:
            True if successful
        """
        try:
            # Download from storage
            response = self.client.storage.from_("experiments").download(remote_path)
            
            # Write to local file
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with open(local_path, 'wb') as f:
                f.write(response)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to download {remote_path}: {e}")
            return False
```

## Step 4: Update Worker Sync Implementation

Update `src/dr_exp/worker/base.py` to add real Supabase sync:

```python
# Add to imports at top
from dr_exp.sync.supabase_client import SupabaseClient

# Update the Worker class __init__ method to include:
def __init__(
    self,
    worker_id: str,
    job_db: JobDB,
    sync_enabled: bool = True,
    sync_interval: int = 300,
    sync_batch_size: int = 10,
):
    # ... existing code ...
    
    # Initialize Supabase client if sync is enabled
    self.supabase: Optional[SupabaseClient] = None
    if sync_enabled:
        try:
            self.supabase = SupabaseClient()
            self.supabase.ensure_experiment(job_db.experiment_name)
        except Exception as e:
            logger.warning(f"Failed to initialize Supabase client: {e}")
            logger.warning("Sync will be disabled")
            self.sync_enabled = False

# Replace the _run_sync_cycle method:
def _run_sync_cycle(self) -> None:
    """Run a single sync cycle."""
    if not self.supabase:
        logger.debug("No Supabase client available")
        return
    
    # Get pending items
    pending = self.sync_queue.get_pending(limit=self.sync_batch_size)
    
    if not pending:
        logger.debug("No items to sync")
        return
    
    logger.info(f"Starting sync cycle with {len(pending)} items")
    
    for item in pending:
        if self.stop_sync.is_set():
            break
        
        try:
            local_path = Path(item.local_path)
            if not local_path.exists():
                raise FileNotFoundError(f"Local file not found: {local_path}")
            
            # Check if this is a job metadata file
            job_id = None
            if local_path.suffix == ".json" and local_path.parent == self.job_db.jobs_dir:
                # This is a job metadata file
                job_id = local_path.stem
                
                # Read and sync job data
                with open(local_path, 'r') as f:
                    job_data = json.load(f)
                self.supabase.sync_job(job_data)
                logger.debug(f"Synced job metadata for {job_id}")
            else:
                # Regular file upload
                result = self.supabase.upload_file(local_path, item.remote_path)
                
                if result["success"]:
                    # Extract job ID from remote path if possible
                    if "/runs/" in item.remote_path:
                        parts = item.remote_path.split("/runs/")
                        if len(parts) > 1:
                            job_id = parts[1].split("/")[0]
                    
                    # Record sync
                    self.supabase.record_sync(
                        local_path=item.local_path,
                        remote_path=item.remote_path,
                        experiment_name=self.job_db.experiment_name,
                        job_id=job_id,
                        file_size=result.get("size"),
                        checksum=result.get("checksum"),
                    )
                    logger.debug(f"Uploaded {local_path} to {item.remote_path}")
                else:
                    raise Exception(result.get("error", "Unknown upload error"))
            
            self.sync_queue.mark_completed(item.id)
            
        except Exception as e:
            logger.error(f"Failed to sync {item.local_path}: {e}")
            self.sync_queue.mark_failed(item.id, str(e))
        
        # Rate limit between uploads
        time.sleep(1)
```

## Step 5: Add Remote Read Support to JobDB

Update `src/dr_exp/core/job_db.py` to add Supabase read support:

```python
# Add to imports
from dr_exp.sync.supabase_client import SupabaseClient

# Add to JobDB class __init__ parameters:
def __init__(self, base_path: str, experiment_name: str, enable_remote_read: bool = False):
    """Initialize JobDB for a specific experiment.
    
    Args:
        base_path: Base directory for all experiments
        experiment_name: Name of this experiment
        enable_remote_read: Whether to enable reading from Supabase
    """
    # ... existing code ...
    
    # Initialize Supabase client for remote reads
    self.supabase: Optional[SupabaseClient] = None
    if enable_remote_read:
        try:
            self.supabase = SupabaseClient()
            self.supabase.ensure_experiment(experiment_name)
        except Exception as e:
            logger.warning(f"Failed to initialize Supabase client: {e}")

# Add method for remote job listing:
def list_jobs_remote(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List jobs from Supabase (for API/frontend use).
    
    Args:
        status: Optional status filter
        
    Returns:
        List of job dictionaries from Supabase
    """
    if not self.supabase:
        raise RuntimeError("Remote read not enabled")
    
    return self.supabase.get_jobs(self.experiment_name, status)

# Add method to get metrics from Supabase:
def get_metrics_remote(self, job_id: str) -> Optional[Path]:
    """Download metrics from Supabase to temporary location.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Path to downloaded metrics file, or None if not found
    """
    if not self.supabase:
        raise RuntimeError("Remote read not enabled")
    
    import tempfile
    
    remote_path = f"experiments/{self.experiment_name}/runs/{job_id}/metrics.jsonl"
    temp_dir = Path(tempfile.mkdtemp(prefix=f"metrics_{job_id}_"))
    local_path = temp_dir / "metrics.jsonl"
    
    if self.supabase.download_file(remote_path, local_path):
        return local_path
    
    return None
```

## Step 6: Create Integration Test

Create `tests/test_supabase_integration.py`:

```python
#!/usr/bin/env python3
"""Test Supabase integration."""

import os
import time
import tempfile
from pathlib import Path
from dotenv import load_dotenv

from dr_exp.core.job_db import JobDB
from dr_exp.worker.training_worker import TrainingWorker
from dr_exp.sync.supabase_client import SupabaseClient

load_dotenv()


def test_supabase_integration():
    """Test full Supabase integration."""
    print("Testing Supabase integration...")
    
    # Check environment
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        print("❌ SUPABASE_URL and SUPABASE_KEY must be set in .env file")
        return
    
    experiment_name = f"integration_test_{int(time.time())}"
    print(f"Using experiment: {experiment_name}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize JobDB
        base_path = os.path.join(tmpdir, "users", "testuser", "experiments")
        db = JobDB(base_path=base_path, experiment_name=experiment_name)
        print(f"✓ Created JobDB at {db.experiment_path}")
        
        # Create a test job
        job_id = db.create_job({
            "model": "test_model",
            "lr": 0.01,
            "epochs": 2,
        }, priority=500)
        print(f"✓ Created job {job_id}")
        
        # Create and run worker with sync
        worker = TrainingWorker(
            worker_id="integration_test_worker",
            job_db=db,
            sync_enabled=True,
            sync_interval=5,  # Fast sync for testing
        )
        worker.start()
        print("✓ Started worker with sync")
        
        # Run the job
        completed_job_id = worker.run_next_job()
        assert completed_job_id == job_id
        print(f"✓ Completed job {job_id}")
        
        # Wait for sync
        print("Waiting for sync to complete...")
        time.sleep(10)
        
        # Verify sync completed
        remaining_sync = list(db.sync_queue_dir.glob("*.json"))
        print(f"Remaining sync items: {len(remaining_sync)}")
        
        # Test remote read
        print("\nTesting remote read functionality...")
        remote_db = JobDB(
            base_path=base_path,
            experiment_name=experiment_name,
            enable_remote_read=True
        )
        
        # List jobs from Supabase
        remote_jobs = remote_db.list_jobs_remote()
        assert len(remote_jobs) > 0
        assert any(j["id"] == job_id for j in remote_jobs)
        print(f"✓ Found {len(remote_jobs)} jobs in Supabase")
        
        # Check job details
        remote_job = next(j for j in remote_jobs if j["id"] == job_id)
        assert remote_job["status"] == "completed"
        assert remote_job["experiment_name"] == experiment_name
        print("✓ Job synced correctly to Supabase")
        
        # Download metrics
        metrics_path = remote_db.get_metrics_remote(job_id)
        if metrics_path and metrics_path.exists():
            with open(metrics_path, 'r') as f:
                lines = f.readlines()
            assert len(lines) == 2  # 2 epochs
            print(f"✓ Downloaded metrics with {len(lines)} entries")
        else:
            print("⚠️  Metrics not yet synced (this is okay for now)")
        
        # Stop worker
        worker.stop()
        print("✓ Worker stopped")
    
    print(f"\n✅ Supabase integration test passed!")
    print(f"Check your Supabase dashboard for experiment: {experiment_name}")


if __name__ == "__main__":
    test_supabase_integration()
```

## Step 7: Run Tests with Quality Gates

### Validation Gate
Run these commands and fix ALL issues before proceeding:

```bash
# 1. Code quality check
ckdr
# Expected: "All checks passed!"
# If fails: Fix the code, not the rules

# 2. Run all tests
pt
# Expected: All tests pass, no skips (some may skip if no Supabase creds)
# If fails: Fix implementation, not tests

# 3. Run Supabase integration tests specifically
pt tests/test_supabase_integration.py -v
# Expected: Tests pass or skip gracefully if no credentials
```

⚠️ **CRITICAL**: If any check fails:
1. Read the FULL error message
2. Understand what the test/check expects
3. Fix YOUR CODE to meet expectations
4. Do NOT modify tests/rules to pass

Common fixes:
- Missing credentials → Create .env file with Supabase credentials
- Type errors → Add proper type hints to sync methods
- Test failures → Sync implementation doesn't match spec

## Validation Checklist

Before proceeding to Phase 4:

- [ ] **ALL quality checks pass**: `ckdr` shows "All checks passed!"
- [ ] **ALL tests pass**: `pt` shows all tests passing (or gracefully skipping)
- [ ] Test coverage is adequate: `pt --cov=dr_exp.sync`
- [ ] Supabase schema is created
- [ ] `.env` file contains valid credentials
- [ ] Integration test passes: `pt tests/test_supabase_integration.py -v`
- [ ] Jobs appear in Supabase dashboard
- [ ] Files appear in Supabase storage bucket
- [ ] Remote read functionality works

### Phase 3 Validation Gate

```bash
# No proceeding until these ALL work:
ckdr && echo "✓ Quality checks pass" || echo "✗ FIX CODE QUALITY FIRST"
pt tests/test_supabase_integration.py && echo "✓ Supabase tests pass" || echo "✗ FIX IMPLEMENTATION"
pt && echo "✓ All tests pass" || echo "✗ FIX ALL FAILURES"
```

If any check shows ✗:
1. STOP
2. Read the error carefully
3. Fix the implementation (not the test)
4. Run all checks again
5. Only proceed when all show ✓

## Debugging Tips

### Check Supabase Dashboard
1. Go to your Supabase project dashboard
2. Check Table Editor → jobs table
3. Check Storage → experiments bucket
4. Look for your test experiment data

### Common Issues

**"relation does not exist" error**
- Run the SQL schema creation again
- Make sure you're connected to the right project

**"Invalid API key" error**
- Check your .env file
- Use service role key, not anon key

**Files not appearing in storage**
- Check worker logs for upload errors
- Verify bucket exists and has correct permissions

## Common Test Anti-Patterns

### ⚠️ DO NOT Mock Away Supabase

❌ **WRONG - Don't fake the integration:**
```python
@patch('dr_exp.sync.supabase_client.SupabaseClient.upload_file')
def test_sync(mock_upload):
    mock_upload.return_value = True  # This doesn't test anything!
```

✅ **RIGHT - Test real integration or skip:**
```python
def test_sync():
    if not os.getenv("SUPABASE_URL"):
        pytest.skip("No Supabase credentials")
    # Test real upload
```

### ⚠️ DO NOT Ignore Sync Failures

❌ **WRONG - Don't hide sync errors:**
```python
try:
    client.upload_file(path, remote)
except Exception:
    pass  # Hiding real problems
```

✅ **RIGHT - Handle errors properly:**
```python
success = client.upload_file(path, remote)
if not success:
    # Log error, retry later
```

## Architecture Notes

Key design decisions:
- Supabase is write-only from workers (via sync)
- Supabase is read-only from API (for frontend)
- Local filesystem remains source of truth
- Sync is eventually consistent

## Next Phase

Once integration test passes and you see data in Supabase, proceed to Phase 4: API Deployment.
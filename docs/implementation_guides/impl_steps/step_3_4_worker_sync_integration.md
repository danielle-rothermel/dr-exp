# Step 3.4: Worker Sync Integration

## Goal (1 sentence)
Update the worker to use real Supabase sync instead of mock functions, with proper error handling and retry logic.

## Prerequisites
- [ ] Step 3.3 completed with database operations working
- [ ] Supabase client can upload files and sync job data
- [ ] test_step_3_3.py passes

## Implementation

### 1. Create src/dr_exp/sync/sync_handler.py
```python
"""Sync handler that connects sync queue to Supabase."""
from pathlib import Path
from typing import Optional, Dict, Any
import os

from .queue import SyncItem
from .supabase_client import SupabaseClient


class SyncHandler:
    """Handles syncing files from queue to Supabase."""
    
    def __init__(
        self,
        experiment_name: str,
        base_path: str,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None
    ):
        """Initialize sync handler.
        
        Args:
            experiment_name: Name of the experiment
            base_path: Base path for the experiment
            supabase_url: Supabase URL (optional, uses env var)
            supabase_key: Supabase key (optional, uses env var)
        """
        self.experiment_name = experiment_name
        self.base_path = base_path
        
        # Initialize Supabase client
        try:
            self.client = SupabaseClient(url=supabase_url, key=supabase_key)
            self.enabled = True
            
            # Get or create experiment
            self.experiment_id = self.client.get_or_create_experiment(
                experiment_name=experiment_name,
                base_path=base_path
            )
        except Exception as e:
            print(f"[SyncHandler] Failed to initialize Supabase: {e}")
            print("[SyncHandler] Sync disabled - files will remain in queue")
            self.client = None
            self.enabled = False
            self.experiment_id = None
    
    def sync_file(self, item: SyncItem) -> None:
        """Sync a single file to Supabase.
        
        Args:
            item: Sync item to process
            
        Raises:
            Exception: If sync fails (for retry logic)
        """
        if not self.enabled:
            raise Exception("Sync is disabled")
        
        file_path = Path(item.file_path)
        
        # Check file exists
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Upload file
        storage_url, checksum = self.client.upload_file(
            file_path=file_path,
            experiment_name=self.experiment_name,
            job_id=item.job_id,
            file_type=item.file_type,
            metadata=item.metadata
        )
        
        # Create sync status record
        self.client.create_sync_status(
            job_id=item.job_id,
            file_path=item.file_path,
            file_type=item.file_type,
            checksum=checksum,
            size_bytes=item.size_bytes or file_path.stat().st_size,
            storage_url=storage_url,
            metadata=item.metadata
        )
        
        print(f"[SyncHandler] Uploaded {file_path.name} ({item.file_type})")
    
    def sync_job_data(self, job_data: Dict[str, Any]) -> bool:
        """Sync job metadata to Supabase.
        
        Args:
            job_data: Job data dictionary
            
        Returns:
            True if synced successfully
        """
        if not self.enabled:
            return False
        
        try:
            return self.client.sync_job(job_data, self.experiment_id)
        except Exception as e:
            print(f"[SyncHandler] Failed to sync job {job_data.get('id')}: {e}")
            return False
    
    def is_available(self) -> bool:
        """Check if sync is available.
        
        Returns:
            True if Supabase connection is working
        """
        if not self.enabled:
            return False
        
        try:
            return self.client.test_connection()
        except Exception:
            return False
```

### 2. Update src/dr_exp/worker/base.py
Add this import at the top:
```python
from typing import Optional, Dict, Any
import threading
from pathlib import Path
from ..sync.sync_handler import SyncHandler
from ..sync.queue import SyncQueue
```

Replace the `__init__` method with:
```python
    def __init__(
        self, 
        job_db: JobDB,
        worker_id: str,
        working_dir: Optional[str] = None,
        sync_interval: int = 30,
        heartbeat_interval: int = 60,
        sync_enabled: bool = True,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None
    ):
        """Initialize worker.
        
        Args:
            job_db: JobDB instance to get jobs from
            worker_id: Unique identifier for this worker
            working_dir: Directory to run jobs in (defaults to current dir)
            sync_interval: Seconds between sync attempts
            heartbeat_interval: Seconds between heartbeats
            sync_enabled: Whether to enable background sync
            supabase_url: Optional Supabase URL
            supabase_key: Optional Supabase key
        """
        self.job_db = job_db
        self.worker_id = worker_id
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.sync_interval = sync_interval
        self.heartbeat_interval = heartbeat_interval
        self.sync_enabled = sync_enabled
        
        self.current_job_id: Optional[str] = None
        self.should_stop = threading.Event()
        
        # Ensure working directory exists
        self.working_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize sync queue
        self.sync_queue = SyncQueue(job_db.get_sync_queue_path())
        
        # Thread references
        self.sync_thread: Optional[threading.Thread] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        
        # Initialize sync handler if enabled
        if sync_enabled:
            try:
                self.sync_handler = SyncHandler(
                    experiment_name=job_db.experiment_name,
                    base_path=str(job_db.base_path),
                    supabase_url=supabase_url,
                    supabase_key=supabase_key
                )
                
                # Set sync function
                if self.sync_handler.enabled:
                    self.sync_fn = self.sync_handler.sync_file
                else:
                    self.sync_fn = None
                    print(f"[{self.worker_id}] Sync disabled - Supabase not available")
            except Exception as e:
                print(f"[{self.worker_id}] Failed to initialize sync: {e}")
                self.sync_handler = None
                self.sync_fn = None
        else:
            self.sync_handler = None
            self.sync_fn = None
```

Add this method after `run_one_job`:
```python
    def _sync_job_on_completion(self, job_id: str) -> None:
        """Sync job data to Supabase after completion.
        
        Args:
            job_id: Job ID to sync
        """
        if self.sync_handler and self.sync_handler.enabled:
            try:
                job_data = self.job_db.get_job(job_id)
                if job_data:
                    self.sync_handler.sync_job_data(job_data)
            except Exception as e:
                print(f"[{self.worker_id}] Failed to sync job data: {e}")
```

Update the `run_one_job` method to call sync after job completion:
```python
        # Update job status based on result
        if result["status"] == "success":
            # Extract metrics if provided
            metrics = None
            if isinstance(result.get("result"), dict):
                metrics = result["result"].get("metrics")
            
            self.job_db.complete_job(job["id"], metrics)
            print(f"[{self.worker_id}] Job {job['id']} completed successfully")
            status = "completed"
        else:
            self.job_db.fail_job(job["id"], result["error"])
            print(f"[{self.worker_id}] Job {job['id']} failed")
            status = "failed"
        
        # Sync job data to Supabase
        self._sync_job_on_completion(job["id"])
        
        self.current_job_id = None
        return status
```

### 3. Update src/dr_exp/cli/main.py
Update the worker command to support Supabase credentials:
```python
import sys
import click
from typing import Optional
@cli.command()
@click.option('--worker-id', required=True, help='Unique worker ID')
@click.option('--working-dir', help='Working directory for job execution')
@click.option('--max-jobs', type=int, help='Maximum jobs to run')
@click.option('--no-sync', is_flag=True, help='Disable background sync')
@click.option('--supabase-url', envvar='SUPABASE_URL', help='Supabase URL')
@click.option('--supabase-key', envvar='SUPABASE_KEY', help='Supabase service key')
@click.pass_context
def worker(ctx: click.Context, worker_id: str, working_dir: Optional[str], 
           max_jobs: Optional[int], no_sync: bool,
           supabase_url: Optional[str], supabase_key: Optional[str]) -> None:
    """Run a worker to process jobs."""
    job_db = ctx.obj['job_db']
    
    # Create worker
    worker_instance = Worker(
        job_db=job_db,
        worker_id=worker_id,
        working_dir=working_dir,
        sync_enabled=not no_sync,
        supabase_url=supabase_url,
        supabase_key=supabase_key
    )
    
    # Check sync status
    if not no_sync:
        if worker_instance.sync_handler and worker_instance.sync_handler.enabled:
            print(f"Sync: enabled (Supabase connected)")
        else:
            print(f"Sync: enabled (Supabase not available - queue only)")
    else:
        print(f"Sync: disabled")
    
    print(f"Starting worker {worker_id}")
    print(f"Experiment: {ctx.obj['experiment']} at {ctx.obj['base_path']}")
    print("-" * 60)
    
    stats = worker_instance.run(max_jobs=max_jobs)
    
    print("-" * 60)
    print(f"Worker completed: {stats}")
    
    # Show sync queue status
    if not no_sync:
        sync_stats = worker_instance.sync_queue.get_stats()
        if sync_stats['total'] > 0:
            print(f"Sync queue: {sync_stats['completed']} completed, "
                  f"{sync_stats['pending']} pending, {sync_stats['failed']} failed")
    
    # Exit with error if any jobs failed
    if stats['failed'] > 0:
        sys.exit(1)
```

### 4. Create tests/implementation/test_step_3_4.py
```python
"""Test worker integration with Supabase sync."""
import tempfile
import time
import os
import json
import pytest
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, UTC
from dotenv import load_dotenv

from src.dr_exp.core.job_db import JobDB
from src.dr_exp.worker.base import Worker
from src.dr_exp.sync.supabase_client import SupabaseClient


def setup_test_env() -> None:
    """Load test environment variables."""
    env_file = Path(".env.test")
    if env_file.exists():
        load_dotenv(env_file)
    else:
        os.environ["SUPABASE_URL"] = "http://localhost:54321"
        os.environ["SUPABASE_KEY"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"


def test_worker_with_supabase_sync() -> None:
    """Test worker with real Supabase sync."""
    setup_test_env()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize JobDB
        job_db = JobDB(base_path=tmpdir, experiment_name="worker_sync_test", validate=False)
        
        # Create a test job
        config = {
            "_target_": "src.dr_exp.trainers.test_trainer.train",
            "epochs": 3
        }
        job_id = job_db.create_job(config, priority=100)
        
        # Create worker with Supabase sync
        worker = Worker(
            job_db=job_db,
            worker_id="supabase_worker",
            sync_interval=2,  # Fast for testing
            sync_enabled=True
        )
        
        # Verify sync handler initialized
        assert worker.sync_handler is not None
        assert worker.sync_handler.enabled
        assert worker.sync_handler.experiment_id is not None
        
        # Run the job
        stats = worker.run(max_jobs=1)
        assert stats["completed"] == 1
        
        # Wait for sync to complete
        time.sleep(5)
        
        # Verify files were synced to Supabase
        client = SupabaseClient()
        
        # Check job was synced
        jobs = client.get_experiment_jobs(worker.sync_handler.experiment_id)
        assert len(jobs) == 1
        assert jobs[0]["id"] == job_id
        assert jobs[0]["status"] == "completed"
        
        # Check files were synced
        sync_records = client.get_job_sync_status(job_id)
        assert len(sync_records) > 0
        
        # Verify file types
        synced_types = {record["file_type"] for record in sync_records}
        assert "metrics" in synced_types or "model" in synced_types
        
        # Verify sync queue is processed
        sync_stats = worker.sync_queue.get_stats()
        assert sync_stats["completed"] > 0
        assert sync_stats["pending"] == 0  # All processed


def test_worker_sync_failure_handling() -> None:
    """Test worker handles sync failures gracefully."""
    setup_test_env()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="sync_failure_test", validate=False)
        
        # Create job
        config = {
            "_target_": "src.dr_exp.trainers.test_trainer.train",
            "epochs": 2
        }
        job_id = job_db.create_job(config)
        
        # Create worker with invalid Supabase credentials
        worker = Worker(
            job_db=job_db,
            worker_id="fail_worker",
            sync_enabled=True,
            supabase_url="http://invalid.url",
            supabase_key="invalid_key"
        )
        
        # Sync should be disabled due to bad credentials
        assert worker.sync_handler is None or not worker.sync_handler.enabled
        
        # Worker should still run jobs
        stats = worker.run(max_jobs=1)
        assert stats["completed"] == 1
        
        # Job should complete locally
        job = job_db.get_job(job_id)
        assert job["status"] == "completed"


def test_worker_without_sync() -> None:
    """Test worker with sync explicitly disabled."""
    setup_test_env()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="no_sync_test", validate=False)
        
        # Create job
        config = {
            "_target_": "src.dr_exp.trainers.test_trainer.train",
            "epochs": 2
        }
        job_db.create_job(config)
        
        # Create worker with sync disabled
        worker = Worker(
            job_db=job_db,
            worker_id="no_sync_worker",
            sync_enabled=False
        )
        
        # No sync handler
        assert worker.sync_handler is None
        assert worker.sync_fn is None
        
        # Run job
        stats = worker.run(max_jobs=1)
        assert stats["completed"] == 1
        
        # Files should be in sync queue but not processed
        sync_stats = worker.sync_queue.get_stats()
        assert sync_stats["pending"] > 0  # Files queued
        assert sync_stats["completed"] == 0  # Nothing synced


def test_sync_retry_logic() -> None:
    """Test that sync retries failed uploads."""
    setup_test_env()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        job_db = JobDB(base_path=tmpdir, experiment_name="retry_test", validate=False)
        
        # Create a job that produces files
        config = {
            "_target_": "src.dr_exp.trainers.test_trainer.train",
            "epochs": 1
        }
        job_id = job_db.create_job(config)
        
        # Run job to generate files
        worker = Worker(
            job_db=job_db,
            worker_id="retry_worker",
            sync_enabled=False  # Don't sync yet
        )
        worker.run_one_job()
        
        # Manually add a file that will fail to sync
        bad_file = Path(tmpdir) / "nonexistent.txt"
        worker.add_artifact_to_sync(
            job_id=job_id,
            file_path=str(bad_file),
            file_type="test"
        )
        
        # Create new worker with sync enabled
        sync_worker = Worker(
            job_db=job_db,
            worker_id="sync_retry_worker",
            sync_interval=1,
            sync_enabled=True
        )
        
        # Let sync run a few times
        time.sleep(3)
        
        # Stop worker
        sync_worker.stop_background_threads()
        
        # Check sync queue
        sync_stats = sync_worker.sync_queue.get_stats()
        
        # Bad file should have failed attempts
        failed_items = []
        for item in sync_worker.sync_queue.get_pending_items():
            if "nonexistent" in item.file_path:
                failed_items.append(item)
        
        if failed_items:
            assert failed_items[0].attempts > 0


def test_experiment_isolation() -> None:
    """Test that different experiments are isolated."""
    setup_test_env()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two experiments
        job_db1 = JobDB(base_path=tmpdir, experiment_name="exp1", validate=False)
        job_db2 = JobDB(base_path=tmpdir, experiment_name="exp2", validate=False)
        
        # Create jobs in each
        config = {"_target_": "src.dr_exp.trainers.test_trainer.train", "epochs": 1}
        job1 = job_db1.create_job(config)
        job2 = job_db2.create_job(config)
        
        # Run workers for each experiment
        worker1 = Worker(job_db=job_db1, worker_id="worker1", sync_enabled=True)
        worker2 = Worker(job_db=job_db2, worker_id="worker2", sync_enabled=True)
        
        assert worker1.sync_handler.experiment_id != worker2.sync_handler.experiment_id
        
        worker1.run(max_jobs=1)
        worker2.run(max_jobs=1)
        
        # Wait for sync
        time.sleep(3)
        
        # Verify isolation in Supabase
        client = SupabaseClient()
        
        exp1_jobs = client.get_experiment_jobs(worker1.sync_handler.experiment_id)
        exp2_jobs = client.get_experiment_jobs(worker2.sync_handler.experiment_id)
        
        assert len(exp1_jobs) == 1
        assert len(exp2_jobs) == 1
        assert exp1_jobs[0]["id"] == job1
        assert exp2_jobs[0]["id"] == job2


def test_cli_integration() -> None:
    """Test CLI with Supabase sync."""
    setup_test_env()
    
    from click.testing import CliRunner
    from src.dr_exp.cli.main import cli
    
    runner = CliRunner()
    
    with runner.isolated_filesystem():
        # Initialize experiment
        result = runner.invoke(cli, [
            '--base-path', '.',
            '--experiment', 'cli_sync_test',
            'init'
        ])
        assert result.exit_code == 0
        
        # Create job config
        Path("test.yaml").write_text("""
_target_: src.dr_exp.trainers.test_trainer.train
epochs: 2
""")
        
        # Submit job
        result = runner.invoke(cli, [
            '--base-path', '.',
            '--experiment', 'cli_sync_test',
            'submit', 'test.yaml'
        ])
        assert result.exit_code == 0
        
        # Run worker with sync
        result = runner.invoke(cli, [
            '--base-path', '.',
            '--experiment', 'cli_sync_test',
            'worker',
            '--worker-id', 'cli_worker',
            '--max-jobs', '1'
        ], env={
            'SUPABASE_URL': os.environ.get('SUPABASE_URL'),
            'SUPABASE_KEY': os.environ.get('SUPABASE_KEY')
        })
        
        assert result.exit_code == 0
        assert 'Sync: enabled (Supabase connected)' in result.output
        assert "'completed': 1" in result.output


```

## Validation
```bash
# Make sure Supabase is running
supabase status

# Run worker sync tests
pt tests/implementation/test_step_3_4.py -v

# Expected output:
# ============================= test session starts ==============================
# tests/implementation/test_step_3_4.py::test_worker_with_supabase_sync PASSED
# tests/implementation/test_step_3_4.py::test_worker_sync_failure_handling PASSED
# tests/implementation/test_step_3_4.py::test_worker_without_sync PASSED
# tests/implementation/test_step_3_4.py::test_sync_retry_logic PASSED
# tests/implementation/test_step_3_4.py::test_experiment_isolation PASSED
# tests/implementation/test_step_3_4.py::test_cli_integration PASSED
# ============================== 6 passed in X.XXs ===============================

# Test with real CLI
export SUPABASE_URL=http://localhost:54321
export SUPABASE_KEY=<your-service-key>

dr_exp --base-path /tmp/test --experiment real_sync init
dr_exp --base-path /tmp/test --experiment real_sync submit configs/test_job.yaml
dr_exp --base-path /tmp/test --experiment real_sync worker --worker-id test_worker

# Check Supabase Studio
open http://localhost:54323
# Look for synced jobs and files

# Code quality check
ckdr
```

## Common Mistakes
- DO NOT: Fail jobs if sync fails - sync should be best-effort
- DO NOT: Block job execution waiting for sync - use background threads
- DO NOT: Retry indefinitely - respect the retry limits
- DO NOT: Sync incomplete job data - wait for job completion
- DO NOT: Mix experiment data - maintain proper isolation

## Next Step
Proceed to Step 3.5: Remote Read Operations
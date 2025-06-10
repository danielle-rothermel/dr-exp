# Phase 2: Worker Integration Implementation Guide

## Overview
This phase implements a clean worker design with embedded sync thread for background uploads to Supabase.

**Duration**: 3-4 days
**Prerequisite**: Phase 1 must be complete with all tests passing
**Outcome**: Workers that write locally and sync in background

## Pre-flight Checklist

### Verify Phase 1 Completion
```bash
# Ensure you're on the correct branch
git branch --show-current  # Should show: architecture-redesign

# Run Phase 1 test
python test_job_db.py  # Should pass

# Verify old code is gone
grep -r "LocalJobDB\|SupabaseJobDB" src/  # Should return nothing
```

## Step 1: Create Worker Module Structure

```bash
# Create worker module
mkdir -p src/dr_exp/worker/

# Create sync module
mkdir -p src/dr_exp/sync/
```

## Step 2: Implement Sync Queue Manager

Create `src/dr_exp/sync/queue.py`:

```python
"""Background sync queue for uploading to Supabase."""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, UTC
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SyncItem:
    """A single item in the sync queue."""
    id: str
    local_path: str
    remote_path: str
    queued_at: str
    status: str = "pending"
    attempts: int = 0
    last_error: Optional[str] = None


class SyncQueue:
    """Manages the queue of files to sync to Supabase."""
    
    def __init__(self, queue_dir: Path):
        """Initialize sync queue.
        
        Args:
            queue_dir: Directory containing sync queue files
        """
        self.queue_dir = queue_dir
        self.queue_dir.mkdir(parents=True, exist_ok=True)
    
    def add(self, local_path: Path, remote_path: str) -> str:
        """Add a file to the sync queue.
        
        Args:
            local_path: Path to local file
            remote_path: Destination path in Supabase storage
            
        Returns:
            Sync item ID
        """
        # Generate unique ID
        timestamp = datetime.now(UTC).timestamp()
        sync_id = f"{timestamp}_{local_path.name}"
        
        item = SyncItem(
            id=sync_id,
            local_path=str(local_path),
            remote_path=remote_path,
            queued_at=datetime.now(UTC).isoformat(),
        )
        
        # Write to queue
        queue_file = self.queue_dir / f"{sync_id}.json"
        with open(queue_file, 'w') as f:
            json.dump(item.__dict__, f, indent=2)
        
        logger.debug(f"Queued {local_path} for sync as {sync_id}")
        return sync_id
    
    def get_pending(self, limit: int = 10) -> List[SyncItem]:
        """Get pending items from the queue.
        
        Args:
            limit: Maximum number of items to return
            
        Returns:
            List of pending sync items
        """
        items = []
        
        for queue_file in sorted(self.queue_dir.glob("*.json"))[:limit]:
            try:
                with open(queue_file, 'r') as f:
                    data = json.load(f)
                    item = SyncItem(**data)
                    
                    # Only return items that are pending or failed (for retry)
                    if item.status in ["pending", "failed"]:
                        items.append(item)
            except Exception as e:
                logger.error(f"Error reading sync item {queue_file}: {e}")
                continue
        
        return items
    
    def mark_completed(self, sync_id: str) -> None:
        """Mark a sync item as completed.
        
        Args:
            sync_id: ID of the sync item
        """
        queue_file = self.queue_dir / f"{sync_id}.json"
        if queue_file.exists():
            # We delete completed items to keep queue clean
            queue_file.unlink()
            logger.debug(f"Sync item {sync_id} completed and removed")
    
    def mark_failed(self, sync_id: str, error: str) -> None:
        """Mark a sync item as failed.
        
        Args:
            sync_id: ID of the sync item
            error: Error message
        """
        queue_file = self.queue_dir / f"{sync_id}.json"
        if queue_file.exists():
            with open(queue_file, 'r') as f:
                data = json.load(f)
            
            data["status"] = "failed"
            data["attempts"] = data.get("attempts", 0) + 1
            data["last_error"] = error
            data["last_attempt"] = datetime.now(UTC).isoformat()
            
            with open(queue_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Sync item {sync_id} marked as failed: {error}")
```

## Step 3: Implement Base Worker Class

Create `src/dr_exp/worker/base.py`:

```python
"""Base worker implementation with embedded sync thread."""

import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, UTC

from omegaconf import OmegaConf
import hydra

from dr_exp.core.job_db import JobDB
from dr_exp.sync.queue import SyncQueue

logger = logging.getLogger(__name__)


class Worker:
    """Base worker that executes jobs and syncs results in background.
    
    Designed for multiple workers per node. Each worker operates independently.
    No inter-worker communication needed - JobDB handles all coordination.
    Start 2-4 workers per GPU for optimal throughput."""
    
    def __init__(
        self,
        worker_id: str,
        job_db: JobDB,
        sync_enabled: bool = True,
        sync_interval: int = 300,  # 5 minutes
        sync_batch_size: int = 10,
    ):
        """Initialize worker.
        
        Args:
            worker_id: Unique identifier for this worker
            job_db: JobDB instance
            sync_enabled: Whether to run background sync
            sync_interval: Seconds between sync cycles
            sync_batch_size: Max files to upload per cycle
        """
        self.worker_id = worker_id
        self.job_db = job_db
        self.sync_enabled = sync_enabled
        self.sync_interval = sync_interval
        self.sync_batch_size = sync_batch_size
        
        # Sync queue
        self.sync_queue = SyncQueue(job_db.sync_queue_dir)
        
        # Sync thread management
        self.sync_thread: Optional[threading.Thread] = None
        self.stop_sync = threading.Event()
        
        # Current job tracking
        self.current_job_id: Optional[str] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.stop_heartbeat = threading.Event()
        
        logger.info(f"Worker {worker_id} initialized for experiment {job_db.experiment_name}")
    
    def start(self) -> None:
        """Start the worker and background sync thread."""
        if self.sync_enabled and self.sync_thread is None:
            self.sync_thread = threading.Thread(
                target=self._sync_loop,
                daemon=True,
                name=f"sync-{self.worker_id}"
            )
            self.sync_thread.start()
            logger.info(f"Started background sync thread for worker {self.worker_id}")
    
    def stop(self) -> None:
        """Stop the worker and cleanup."""
        # Stop sync thread
        if self.sync_thread:
            self.stop_sync.set()
            self.sync_thread.join(timeout=10)
            logger.info(f"Stopped sync thread for worker {self.worker_id}")
        
        # Stop heartbeat if running
        if self.heartbeat_thread:
            self.stop_heartbeat.set()
            self.heartbeat_thread.join(timeout=5)
    
    def run_next_job(self) -> Optional[str]:
        """Claim and run the next available job.
        
        Returns:
            Job ID if a job was run, None if no jobs available
        """
        # Claim a job
        job = self.job_db.claim_next_job(self.worker_id)
        if job is None:
            logger.debug(f"No jobs available for worker {self.worker_id}")
            return None
        
        self.current_job_id = job["id"]
        logger.info(f"Worker {self.worker_id} claimed job {job['id']}")
        
        # Start heartbeat
        self._start_heartbeat(job["id"])
        
        try:
            # Get job storage directory
            storage_dir = self.job_db.get_storage_path(job["id"])
            
            # Run the job
            result = self._execute_job(job, storage_dir)
            
            # Update job status
            self.job_db.update_job(job["id"], {
                "status": "completed" if result["success"] else "failed",
                "completed_at": datetime.now(UTC).isoformat(),
                "result": result,
            })
            
            # Queue artifacts for sync
            self._queue_job_artifacts(job["id"], storage_dir)
            
            logger.info(f"Job {job['id']} completed with status: {result.get('status', 'unknown')}")
            return job["id"]
            
        except Exception as e:
            logger.error(f"Job {job['id']} failed with exception: {e}", exc_info=True)
            self.job_db.update_job(job["id"], {
                "status": "failed",
                "completed_at": datetime.now(UTC).isoformat(),
                "error": str(e),
            })
            return job["id"]
        finally:
            # Stop heartbeat
            self._stop_heartbeat()
            self.current_job_id = None
    
    def run_specific_job(self, job_id: str) -> Optional[str]:
        """Run a specific job immediately, bypassing the queue.
        
        Useful for debugging or high-priority single job execution.
        
        Args:
            job_id: ID of the job to run
            
        Returns:
            Job ID if successful, None if job not found
        """
        job = self.job_db.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return None
        
        # Force claim it if queued
        if job["status"] == "queued":
            self.job_db.update_job(job_id, {
                "status": "running",
                "assigned_worker": self.worker_id,
                "started_at": datetime.now(UTC).isoformat()
            })
            job = self.job_db.get_job(job_id)  # Refresh
        elif job["status"] != "running":
            logger.error(f"Job {job_id} is not runnable (status: {job['status']})")
            return None
        
        # Run it using the normal execution flow
        self.current_job_id = job_id
        logger.info(f"Worker {self.worker_id} running specific job {job_id}")
        
        # Start heartbeat
        self._start_heartbeat(job_id)
        
        try:
            # Get job storage directory
            storage_dir = self.job_db.get_storage_path(job_id)
            
            # Run the job
            result = self._execute_job(job, storage_dir)
            
            # Update job status
            self.job_db.update_job(job_id, {
                "status": "completed" if result["success"] else "failed",
                "completed_at": datetime.now(UTC).isoformat(),
                "result": result,
            })
            
            # Queue artifacts for sync
            self._queue_job_artifacts(job_id, storage_dir)
            
            logger.info(f"Specific job {job_id} completed with status: {result.get('status', 'unknown')}")
            return job_id
            
        except Exception as e:
            logger.error(f"Specific job {job_id} failed with exception: {e}", exc_info=True)
            self.job_db.update_job(job_id, {
                "status": "failed",
                "completed_at": datetime.now(UTC).isoformat(),
                "error": str(e),
            })
            return job_id
        finally:
            # Stop heartbeat
            self._stop_heartbeat()
            self.current_job_id = None
    
    def _execute_job(self, job: Dict[str, Any], storage_dir: Path) -> Dict[str, Any]:
        """Execute a job using Hydra instantiation.
        
        Args:
            job: Job data with config containing _target_
            storage_dir: Directory to write outputs
            
        Returns:
            Result dictionary with at least {"success": bool}
        """
        config = job["config"]
        
        # Validate _target_ exists
        assert "_target_" in config, "Job config must include _target_ field"
        
        # Add runtime paths to config
        config["_dr_exp_storage_dir"] = str(storage_dir)
        config["_dr_exp_job_id"] = job["id"]
        
        # Let Hydra do all the work!
        cfg = OmegaConf.create(config)
        result = hydra.utils.call(cfg)
        
        # Ensure result follows our standard format
        assert isinstance(result, dict), "Training function must return dict"
        assert "success" in result, "Result must include 'success' field"
        
        return result
    
    def _queue_job_artifacts(self, job_id: str, storage_dir: Path) -> None:
        """Queue all job artifacts for sync.
        
        Args:
            job_id: Job identifier
            storage_dir: Job's storage directory
        """
        if not self.sync_enabled:
            return
        
        # Queue all files in storage directory
        for file_path in storage_dir.rglob("*"):
            if file_path.is_file():
                # Compute relative path
                rel_path = file_path.relative_to(storage_dir)
                remote_path = f"experiments/{self.job_db.experiment_name}/runs/{job_id}/{rel_path}"
                
                self.sync_queue.add(file_path, remote_path)
        
        # Also queue the job metadata
        job_file = self.job_db.jobs_dir / f"{job_id}.json"
        if job_file.exists():
            remote_path = f"experiments/{self.job_db.experiment_name}/jobs/{job_id}.json"
            self.sync_queue.add(job_file, remote_path)
    
    def _start_heartbeat(self, job_id: str) -> None:
        """Start heartbeat thread for a job."""
        self.stop_heartbeat.clear()
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(job_id,),
            daemon=True,
            name=f"heartbeat-{job_id}"
        )
        self.heartbeat_thread.start()
    
    def _stop_heartbeat(self) -> None:
        """Stop the heartbeat thread."""
        if self.heartbeat_thread:
            self.stop_heartbeat.set()
            self.heartbeat_thread.join(timeout=5)
            self.heartbeat_thread = None
    
    def _heartbeat_loop(self, job_id: str) -> None:
        """Send periodic heartbeats for a job."""
        while not self.stop_heartbeat.is_set():
            try:
                self.job_db.update_job(job_id, {
                    "heartbeat": datetime.now(UTC).isoformat(),
                })
            except Exception as e:
                logger.error(f"Heartbeat failed for job {job_id}: {e}")
            
            # Wait 30 seconds between heartbeats
            if self.stop_heartbeat.wait(timeout=30):
                break
    
    def _sync_loop(self) -> None:
        """Background thread that syncs files to Supabase."""
        logger.info(f"Sync thread started for worker {self.worker_id}")
        
        while not self.stop_sync.is_set():
            try:
                self._run_sync_cycle()
            except Exception as e:
                logger.error(f"Sync cycle failed: {e}", exc_info=True)
            
            # Wait for next cycle
            if self.stop_sync.wait(timeout=self.sync_interval):
                break
        
        logger.info(f"Sync thread stopped for worker {self.worker_id}")
    
    def _run_sync_cycle(self) -> None:
        """Run a single sync cycle."""
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
                # For now, just simulate upload (Phase 3 will implement real upload)
                local_path = Path(item.local_path)
                if not local_path.exists():
                    raise FileNotFoundError(f"Local file not found: {local_path}")
                
                # Simulate upload delay
                time.sleep(0.1)
                
                logger.debug(f"Synced {item.local_path} to {item.remote_path}")
                self.sync_queue.mark_completed(item.id)
                
            except Exception as e:
                logger.error(f"Failed to sync {item.local_path}: {e}")
                self.sync_queue.mark_failed(item.id, str(e))
            
            # Rate limit between uploads
            time.sleep(1)
```

⚠️ IMPORTANT: Do NOT add worker pools, process managers, or coordination logic.
Each worker is standalone. The JobDB's file locking handles everything.

## Step 4: Create Example Training Functions

Since the worker now uses Hydra to instantiate training functions, we need example trainer modules.

Create `src/dr_exp/trainers/decon_trainer.py`:

```python
"""DeconCNN training integration."""

import logging
from pathlib import Path
from typing import Dict, Any, Optional
from omegaconf import OmegaConf

import deconcnn
from dr_exp.logging.structured_logger import StructuredLogger

logger = logging.getLogger(__name__)


def train_classification(
    # All deconCNN config fields as kwargs
    model: Dict[str, Any],
    optim: Dict[str, Any],
    data: Dict[str, Any],
    epochs: int,
    batch_size: int,
    
    # Special dr_exp fields (injected by worker)
    _dr_exp_storage_dir: Optional[str] = None,
    _dr_exp_job_id: Optional[str] = None,
    
    # Collect any extra fields
    **kwargs
) -> Dict[str, Any]:
    """Train a classification model using deconCNN.
    
    This function is called via Hydra instantiation from job configs.
    
    Returns:
        Dict with keys: success, final_metrics, epochs_completed, artifacts
    """
    # Create our logger
    logger_instance = StructuredLogger(_dr_exp_storage_dir) if _dr_exp_storage_dir else None
    
    # Reconstruct config for deconCNN (it expects OmegaConf)
    cfg = OmegaConf.create({
        "model": model,
        "optim": optim,
        "data": data,
        "epochs": epochs,
        "batch_size": batch_size,
        **kwargs
    })
    
    try:
        # Use deconCNN's components
        trainer, module, data_module = deconcnn.create_cifar10_training_components(cfg)
        
        # Add deconCNN's metrics callback
        metrics_callback = deconcnn.MetricsCallback()
        trainer.callbacks.append(metrics_callback)
        
        # If we have a logger, log initial config
        if logger_instance:
            logger_instance.log({
                "config_summary": {
                    "model_architecture": model.get("architecture", "unknown"),
                    "epochs": epochs,
                    "batch_size": batch_size,
                    "learning_rate": optim.get("lr", 0.001),
                }
            })
        
        # Train using deconCNN
        deconcnn.train_model(trainer, module, data_module, cfg)
        
        # Get final metrics from callback
        final_metrics = {}
        if metrics_callback.metrics_history:
            last_metrics = metrics_callback.metrics_history[-1]
            final_metrics = {
                "final_train_loss": last_metrics.get("train_loss"),
                "final_train_acc": last_metrics.get("train_acc"),
                "final_val_loss": last_metrics.get("val_loss"),
                "final_val_acc": last_metrics.get("val_acc"),
            }
        
        # Log metrics history if we have a logger
        if logger_instance and metrics_callback.metrics_history:
            for metrics in metrics_callback.metrics_history:
                logger_instance.log(metrics)
        
        # Finalize logger
        if logger_instance:
            logger_instance.finalize()
        
        return {
            "success": True,
            "final_metrics": final_metrics,
            "epochs_completed": trainer.current_epoch,
            "artifacts": {
                "metrics_path": f"{_dr_exp_storage_dir}/metrics.jsonl",
                "checkpoint_dir": trainer.checkpoint_callback.dirpath if cfg.get("enable_checkpointing") else None,
            }
        }
        
    except Exception as e:
        logger.error(f"Training failed: {e}")
        if logger_instance:
            logger_instance.log({"error": str(e), "status": "failed"})
            logger_instance.finalize()
        
        return {
            "success": False,
            "error": str(e),
            "epochs_completed": 0,
        }
```

Create example config `configs/experiments/decon/resnet18_baseline.yaml`:

```yaml
# This tells dr_exp what function to call
_target_: dr_exp.trainers.decon_trainer.train_classification

# Standard deconCNN config fields
model:
  architecture: resnet18
  num_classes: 10

optim:
  name: adamw
  lr: 0.001

data:
  name: cifar10

epochs: 100
batch_size: 128
enable_checkpointing: false
```

## Step 5: Create Minimal Test Trainer

For testing without deconCNN, create `src/dr_exp/trainers/test_trainer.py`:

```python
"""Minimal test trainer for worker testing."""

import time
import json
from pathlib import Path
from typing import Dict, Any, Optional

def train_test(
    epochs: int = 5,
    model_name: str = "test_model",
    _dr_exp_storage_dir: Optional[str] = None,
    _dr_exp_job_id: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Minimal training function for testing.
    
    Returns:
        Standard result dict
    """
    if _dr_exp_storage_dir:
        storage_path = Path(_dr_exp_storage_dir)
        metrics_file = storage_path / "metrics.jsonl"
        
        # Write fake metrics
        with open(metrics_file, 'w') as f:
            for epoch in range(epochs):
                metrics = {
                    "epoch": epoch,
                    "train_loss": 1.0 / (epoch + 1),
                    "val_acc": 0.5 + epoch * 0.1,
                }
                f.write(json.dumps(metrics) + "\n")
                time.sleep(0.1)  # Simulate work
    
    return {
        "success": True,
        "final_metrics": {
            "final_train_loss": 0.2,
            "final_val_acc": 0.9,
        },
        "epochs_completed": epochs,
    }
```

## Step 6: Create Test Script for Worker

Create `test_worker.py`:

```python
#!/usr/bin/env python3
"""Test the worker implementation."""

import os
import tempfile
import time
from pathlib import Path
from dr_exp.core.job_db import JobDB
from dr_exp.worker.base import Worker


def test_worker():
    """Test worker operations."""
    print("Testing Worker implementation...")
    
    # Create temporary scratch directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize JobDB
        base_path = os.path.join(tmpdir, "users", "testuser", "experiments")
        db = JobDB(base_path=base_path, experiment_name="worker_test")
        print(f"✓ Created JobDB at {db.experiment_path}")
        
        # Create some test jobs with _target_
        job_ids = []
        for i in range(3):
            job_id = db.create_job({
                "_target_": "dr_exp.trainers.test_trainer.train_test",
                "epochs": 2,  # Quick test
                "model_name": f"model_{i}",
            }, priority=100 + i * 100)
            job_ids.append(job_id)
            print(f"✓ Created job {job_id}")
        
        # Create and start worker
        worker = Worker(
            worker_id="test_worker_1",
            job_db=db,
            sync_enabled=True,
            sync_interval=5,  # Fast sync for testing
        )
        worker.start()
        print("✓ Started worker with sync thread")
        
        # Run all jobs
        for i in range(3):
            job_id = worker.run_next_job()
            assert job_id in job_ids
            print(f"✓ Completed job {job_id}")
        
        # Verify no more jobs
        job_id = worker.run_next_job()
        assert job_id is None
        print("✓ No more jobs available")
        
        # Check that files were created
        for job_id in job_ids:
            storage_dir = db.get_storage_path(job_id)
            assert (storage_dir / "metrics.jsonl").exists()
            assert (storage_dir / "training.log").exists()
            assert (storage_dir / "model_final.pt").exists()
            assert (storage_dir / "summary.json").exists()
            print(f"✓ All outputs created for job {job_id}")
        
        # Check sync queue
        sync_items = list(db.sync_queue_dir.glob("*.json"))
        print(f"✓ {len(sync_items)} items queued for sync")
        
        # Wait a bit for sync to process
        print("Waiting for sync cycle...")
        time.sleep(6)
        
        # Check that sync processed items
        remaining_items = list(db.sync_queue_dir.glob("*.json"))
        assert len(remaining_items) < len(sync_items)
        print(f"✓ Sync processed {len(sync_items) - len(remaining_items)} items")
        
        # Stop worker
        worker.stop()
        print("✓ Worker stopped cleanly")
    
    print("\n✅ All worker tests passed!")


if __name__ == "__main__":
    test_worker()
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
# Expected: All tests pass, no skips
# If fails: Fix implementation, not tests

# 3. Verify Worker tests specifically
pt tests/test_worker.py -v
# Expected: Detailed passing output
```

⚠️ **CRITICAL**: If any check fails:
1. Read the FULL error message
2. Understand what the test/check expects
3. Fix YOUR CODE to meet expectations
4. Do NOT modify tests/rules to pass

Common fixes:
- Import errors → Ensure all modules properly imported
- Type errors → Add proper type hints to Worker methods
- Test failures → Worker implementation doesn't match spec

## Step 8: Create Launcher for Multi-Worker Deployment

For production use, especially on HPC clusters, we need a launcher that spawns and monitors multiple workers. This is critical for GPU utilization and long-running allocations.

Create `src/dr_exp/launcher.py`:

```python
"""Launcher for spawning and monitoring multiple workers."""

import logging
import signal
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, UTC
import os
import sys

from dr_exp.core.job_db import JobDB

logger = logging.getLogger(__name__)


class WorkerLauncher:
    """Spawns and monitors multiple workers for long-running HPC jobs.
    
    Designed for SLURM environments where you want to hold GPU allocations
    for extended periods (e.g., 2 days) to enable rapid job submission without
    waiting for new allocations.
    
    Key features:
    - Spawns workers based on GPU availability
    - Monitors and restarts failed workers
    - Periodic stale job recovery
    - Graceful shutdown before SLURM timeout
    - No artificial GPU keep-alive (respects other users)
    """
    
    def __init__(
        self,
        job_db: JobDB,
        workers_per_gpu: int = 2,
        max_runtime_hours: float = 47,  # Just under 2-day SLURM limit
        heartbeat_timeout: int = 300,    # 5 minutes
        worker_restart_delay: int = 30,  # 30 seconds
    ):
        """Initialize launcher.
        
        Args:
            job_db: JobDB instance
            workers_per_gpu: Number of workers to spawn per GPU
            max_runtime_hours: Maximum runtime before graceful shutdown
            heartbeat_timeout: Seconds before job is considered stale
            worker_restart_delay: Seconds to wait before restarting dead worker
        """
        self.job_db = job_db
        self.workers_per_gpu = workers_per_gpu
        self.max_runtime_hours = max_runtime_hours
        self.heartbeat_timeout = heartbeat_timeout
        self.worker_restart_delay = worker_restart_delay
        
        self.start_time = time.time()
        self.max_runtime_seconds = max_runtime_hours * 3600
        self.workers: Dict[str, subprocess.Popen] = {}
        self.worker_configs: Dict[str, Dict] = {}
        self.shutdown_requested = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        
        logger.info(f"Launcher initialized for experiment {job_db.experiment_name}")
        logger.info(f"Will run for up to {max_runtime_hours} hours")
    
    def discover_gpus(self) -> List[int]:
        """Discover available GPUs from CUDA_VISIBLE_DEVICES or nvidia-smi.
        
        Returns:
            List of GPU IDs
        """
        # First check CUDA_VISIBLE_DEVICES
        cuda_visible = os.environ.get('CUDA_VISIBLE_DEVICES')
        if cuda_visible:
            gpu_ids = [int(x) for x in cuda_visible.split(',')]
            logger.info(f"Found {len(gpu_ids)} GPUs from CUDA_VISIBLE_DEVICES: {gpu_ids}")
            return gpu_ids
        
        # Fall back to nvidia-smi
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=index', '--format=csv,noheader'],
                capture_output=True,
                text=True,
                check=True
            )
            gpu_ids = [int(x) for x in result.stdout.strip().split('\n')]
            logger.info(f"Found {len(gpu_ids)} GPUs from nvidia-smi: {gpu_ids}")
            return gpu_ids
        except Exception as e:
            logger.warning(f"Failed to detect GPUs: {e}")
            return []
    
    def spawn_workers(self) -> None:
        """Spawn workers based on GPU configuration."""
        gpus = self.discover_gpus()
        
        if not gpus:
            # CPU-only mode
            logger.warning("No GPUs found, running in CPU mode")
            for i in range(self.workers_per_gpu):
                worker_id = f"cpu_worker_{i}"
                self._spawn_worker(worker_id, gpu_id=None)
        else:
            # GPU mode
            for gpu_id in gpus:
                for i in range(self.workers_per_gpu):
                    # Generate unique worker ID
                    node_id = os.environ.get('SLURM_NODEID', 'node0')
                    worker_id = f"{node_id}_gpu{gpu_id}_w{i}"
                    self._spawn_worker(worker_id, gpu_id=gpu_id)
        
        logger.info(f"Spawned {len(self.workers)} workers")
    
    def _spawn_worker(self, worker_id: str, gpu_id: Optional[int]) -> None:
        """Spawn a single worker process.
        
        Args:
            worker_id: Unique worker identifier
            gpu_id: GPU to assign (None for CPU mode)
        """
        # Build command
        cmd = [
            sys.executable,  # Use same Python interpreter
            '-m', 'dr_exp.cli',
            '--base-path', str(self.job_db.base_path),
            '--experiment', self.job_db.experiment_name,
            'worker',
            '--worker-id', worker_id,
            '--sync',  # Enable background sync
        ]
        
        # Setup environment
        env = os.environ.copy()
        if gpu_id is not None:
            env['CUDA_VISIBLE_DEVICES'] = str(gpu_id)
        
        # Store config for restart
        self.worker_configs[worker_id] = {
            'cmd': cmd,
            'env': env,
            'gpu_id': gpu_id,
        }
        
        # Spawn worker
        logger.info(f"Spawning worker {worker_id} on GPU {gpu_id}")
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.workers[worker_id] = proc
    
    def monitor_workers(self) -> None:
        """Check worker health and restart if needed."""
        dead_workers = []
        
        for worker_id, proc in self.workers.items():
            if proc.poll() is not None:
                # Worker died
                dead_workers.append(worker_id)
                logger.warning(f"Worker {worker_id} died with code {proc.returncode}")
        
        # Restart dead workers if we're not shutting down
        if dead_workers and not self.shutdown_requested:
            # Check if we have pending jobs before restarting
            has_work = bool(self.job_db.list_jobs(status="queued", limit=1))
            
            for worker_id in dead_workers:
                del self.workers[worker_id]
                
                if has_work:
                    logger.info(f"Restarting worker {worker_id} after {self.worker_restart_delay}s")
                    time.sleep(self.worker_restart_delay)
                    
                    config = self.worker_configs[worker_id]
                    proc = subprocess.Popen(
                        config['cmd'],
                        env=config['env'],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    self.workers[worker_id] = proc
                else:
                    logger.info(f"Not restarting worker {worker_id} - no pending jobs")
    
    def recover_stale_jobs(self) -> None:
        """Recover jobs from workers that missed heartbeats."""
        recovered = self.job_db.recover_stale_jobs(self.heartbeat_timeout)
        if recovered:
            logger.info(f"Recovered {len(recovered)} stale jobs")
            for job_id in recovered:
                logger.debug(f"  - Recovered job {job_id}")
    
    def log_status(self) -> None:
        """Log current system status."""
        # Count job statuses
        running = len(self.job_db.list_jobs(status="running"))
        queued = len(self.job_db.list_jobs(status="queued", limit=100))
        completed = len(self.job_db.list_jobs(status="completed", limit=1000))
        failed = len(self.job_db.list_jobs(status="failed", limit=100))
        
        # Worker status
        alive_workers = sum(1 for p in self.workers.values() if p.poll() is None)
        
        # Runtime
        runtime_hours = (time.time() - self.start_time) / 3600
        
        logger.info(
            f"Status: {alive_workers}/{len(self.workers)} workers alive | "
            f"Jobs: {running} running, {queued} queued, {completed} completed, {failed} failed | "
            f"Runtime: {runtime_hours:.1f}h"
        )
    
    def exceeded_runtime(self) -> bool:
        """Check if we've exceeded maximum runtime."""
        return (time.time() - self.start_time) > self.max_runtime_seconds
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        self.shutdown_requested = True
    
    def stop_all_workers(self) -> None:
        """Stop all workers gracefully."""
        logger.info("Stopping all workers...")
        
        # Send SIGTERM to all workers
        for worker_id, proc in self.workers.items():
            if proc.poll() is None:
                logger.debug(f"Sending SIGTERM to worker {worker_id}")
                proc.terminate()
        
        # Wait up to 30 seconds for graceful shutdown
        wait_start = time.time()
        while time.time() - wait_start < 30:
            alive = sum(1 for p in self.workers.values() if p.poll() is None)
            if alive == 0:
                break
            time.sleep(1)
        
        # Force kill any remaining
        for worker_id, proc in self.workers.items():
            if proc.poll() is None:
                logger.warning(f"Force killing worker {worker_id}")
                proc.kill()
        
        logger.info("All workers stopped")
    
    def run(self) -> None:
        """Main launcher loop."""
        logger.info("Starting launcher main loop")
        
        # Initial spawn
        self.spawn_workers()
        
        # Status and maintenance intervals
        last_status_log = time.time()
        last_recovery = time.time()
        status_interval = 300  # 5 minutes
        recovery_interval = 600  # 10 minutes
        
        # Main monitoring loop
        while not self.shutdown_requested and not self.exceeded_runtime():
            # Monitor and restart workers
            self.monitor_workers()
            
            # Periodic status log
            if time.time() - last_status_log > status_interval:
                self.log_status()
                last_status_log = time.time()
            
            # Periodic stale job recovery
            if time.time() - last_recovery > recovery_interval:
                self.recover_stale_jobs()
                last_recovery = time.time()
            
            # Sleep briefly
            time.sleep(30)
        
        # Graceful shutdown
        if self.exceeded_runtime():
            logger.info("Maximum runtime reached, shutting down gracefully")
        else:
            logger.info("Shutdown requested, stopping gracefully")
        
        self.stop_all_workers()
        
        # Final status
        self.log_status()
        logger.info("Launcher stopped")


def main():
    """CLI entry point for launcher."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Launch multiple workers")
    parser.add_argument('--base-path', required=True, help='Base directory for experiments')
    parser.add_argument('--experiment', required=True, help='Experiment name')
    parser.add_argument('--workers-per-gpu', type=int, default=2, help='Workers per GPU')
    parser.add_argument('--max-hours', type=float, default=47, help='Maximum runtime hours')
    parser.add_argument('--heartbeat-timeout', type=int, default=300, help='Job heartbeat timeout')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    # Create JobDB
    job_db = JobDB(base_path=args.base_path, experiment_name=args.experiment)
    
    # Create and run launcher
    launcher = WorkerLauncher(
        job_db=job_db,
        workers_per_gpu=args.workers_per_gpu,
        max_runtime_hours=args.max_hours,
        heartbeat_timeout=args.heartbeat_timeout,
    )
    
    try:
        launcher.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Launcher failed: {e}", exc_info=True)
        raise
    finally:
        launcher.stop_all_workers()


if __name__ == '__main__':
    main()
```

## Step 8: Create CLI Interface

Now update the CLI to include the launcher command.

Create `src/dr_exp/cli.py` for a unified command-line interface:

```python
"""Command-line interface for dr_exp."""

import click
import yaml
import json
from pathlib import Path
from typing import Optional

from dr_exp.core.job_db import JobDB
from dr_exp.worker.base import Worker


@click.group()
@click.option('--base-path', required=True, help='Base directory for experiments')
@click.option('--experiment', required=True, help='Experiment name')
@click.pass_context
def cli(ctx, base_path, experiment):
    """dr_exp - Distributed experiment management.
    
    Examples:
        dr_exp --base-path /scratch/exp --experiment my_exp list
        dr_exp --base-path /scratch/exp --experiment my_exp submit config.yaml
    """
    ctx.obj = JobDB(base_path=base_path, experiment_name=experiment)


@cli.command()
@click.argument('config_file', type=click.Path(exists=True))
@click.option('--priority', default=100, help='Job priority (0-1000)')
@click.pass_obj
def submit(db, config_file, priority):
    """Submit a job from config file."""
    with open(config_file) as f:
        if config_file.endswith('.yaml') or config_file.endswith('.yml'):
            config = yaml.safe_load(f)
        else:
            config = json.load(f)
    
    job_id = db.create_job(config, priority)
    click.echo(f"Created job {job_id}")


@cli.command()
@click.option('--status', help='Filter by status (queued, running, completed, failed)')
@click.option('--limit', default=50, help='Maximum jobs to show')
@click.pass_obj
def list(db, status, limit):
    """List jobs."""
    jobs = db.list_jobs(status=status)[:limit]
    
    if not jobs:
        click.echo("No jobs found")
        return
    
    # Header
    click.echo(f"{'ID':8} {'Status':10} {'Pri':4} {'Worker':15} {'Created'}")
    click.echo("-" * 60)
    
    for job in jobs:
        job_id_short = job['id'][:8]
        status = job['status']
        priority = job['priority']
        worker = job.get('assigned_worker', '')[:15]
        created = job['created_at'].split('T')[0]
        
        click.echo(f"{job_id_short} {status:10} {priority:4} {worker:15} {created}")


@cli.command()
@click.argument('job_id')
@click.pass_obj
def show(db, job_id):
    """Show detailed job information."""
    job = db.get_job(job_id)
    if not job:
        click.echo(f"Job {job_id} not found")
        return
    
    click.echo(json.dumps(job, indent=2))


@cli.command()
@click.argument('job_id')
@click.pass_obj
def kill(db, job_id):
    """Kill a running job."""
    if db.mark_job_failed(job_id, "User requested kill"):
        click.echo(f"Killed job {job_id}")
    else:
        click.echo(f"Could not kill job {job_id} (not found or not running)")


@cli.command()
@click.argument('job_ids', nargs=-1, required=True)
@click.option('--priority', default=900, help='New priority (0-1000)')
@click.pass_obj
def boost(db, job_ids, priority):
    """Boost job priority."""
    updated = db.boost_priority(list(job_ids), priority)
    click.echo(f"Updated {updated} jobs to priority {priority}")


@cli.command()
@click.option('--timeout', default=300, help='Heartbeat timeout in seconds')
@click.pass_obj
def recover(db, timeout):
    """Recover jobs from dead workers."""
    recovered = db.recover_stale_jobs(timeout)
    if recovered:
        click.echo(f"Recovered {len(recovered)} jobs:")
        for job_id in recovered:
            click.echo(f"  - {job_id}")
    else:
        click.echo("No stale jobs found")


@cli.command()
@click.argument('job_id')
@click.option('--worker-id', default='cli_worker', help='Worker ID to use')
@click.option('--sync/--no-sync', default=False, help='Enable background sync')
@click.pass_obj
def run_one(db, job_id, worker_id, sync):
    """Run a single job immediately."""
    # Create a temporary worker
    worker = Worker(
        worker_id=worker_id,
        job_db=db,
        sync_enabled=sync
    )
    
    if sync:
        worker.start()
    
    try:
        result = worker.run_specific_job(job_id)
        if result:
            click.echo(f"Job {job_id} completed successfully")
        else:
            click.echo(f"Job {job_id} failed")
    finally:
        if sync:
            worker.stop()


@cli.command()
@click.option('--worker-id', required=True, help='Unique worker identifier')
@click.option('--max-jobs', default=0, help='Maximum jobs to run (0=unlimited)')
@click.option('--sync/--no-sync', default=True, help='Enable background sync')
@click.pass_obj
def worker(db, worker_id, max_jobs, sync):
    """Run a worker process.
    
    In production, use the 'launcher' command instead to spawn multiple workers.
    """
    worker = Worker(
        worker_id=worker_id,
        job_db=db,
        sync_enabled=sync
    )
    
    click.echo(f"Starting worker {worker_id}")
    worker.start()
    
    jobs_run = 0
    try:
        while True:
            job_id = worker.run_next_job()
            if job_id is None:
                # No jobs available - wait and retry
                time.sleep(10)
                continue
            
            jobs_run += 1
            click.echo(f"Completed job {job_id} ({jobs_run} total)")
            
            if max_jobs > 0 and jobs_run >= max_jobs:
                click.echo(f"Reached max jobs limit ({max_jobs})")
                break
    finally:
        worker.stop()
        click.echo(f"Worker {worker_id} stopped after {jobs_run} jobs")


@cli.command()
@click.option('--workers-per-gpu', default=2, help='Workers to spawn per GPU')
@click.option('--max-hours', default=47, help='Maximum runtime in hours')
@click.option('--heartbeat-timeout', default=300, help='Job heartbeat timeout seconds')
@click.pass_obj
def launcher(db, workers_per_gpu, max_hours, heartbeat_timeout):
    """Launch and monitor multiple workers (recommended for production).
    
    Spawns workers based on available GPUs and monitors them for the specified
    duration. Designed for long-running HPC allocations.
    
    Example:
        dr_exp --base-path /scratch/exp --experiment my_exp launcher
    """
    from dr_exp.launcher import WorkerLauncher
    
    launcher = WorkerLauncher(
        job_db=db,
        workers_per_gpu=workers_per_gpu,
        max_runtime_hours=max_hours,
        heartbeat_timeout=heartbeat_timeout,
    )
    
    try:
        launcher.run()
    except KeyboardInterrupt:
        click.echo("\nShutdown requested")
    finally:
        launcher.stop_all_workers()


if __name__ == '__main__':
    cli()
```

Create the entry point script `dr_exp`:

```bash
#!/usr/bin/env python
from dr_exp.cli import cli
cli()
```

Make it executable and add to PATH:

```bash
chmod +x dr_exp
# Add to your shell config or use pip install -e . to install properly
```

## Step 9: Add Config Submission Commands

The CLI needs commands to submit jobs using Hydra configs. This replaces the old `upload_configs.py` script.

### Add Hydra Config Support

First, update `src/dr_exp/cli.py` to add config submission commands:

```python
# Add these imports at the top
import tempfile
from pathlib import Path
from typing import List, Dict, Any
import itertools

import hydra
from hydra.core.global_hydra import GlobalHydra
from omegaconf import OmegaConf

# Add these functions before the CLI commands

def parse_sweep_params(params_str: str) -> Dict[str, List[str]]:
    """Parse sweep parameters from string format.
    
    Example: "model=resnet18,resnet50 optim.lr=0.001,0.01"
    Returns: {"model": ["resnet18", "resnet50"], "optim.lr": ["0.001", "0.01"]}
    """
    if not params_str:
        return {}
    
    result = {}
    # Split by whitespace to get individual param=values pairs
    pairs = params_str.split()
    for pair in pairs:
        if '=' not in pair:
            continue
        key, values = pair.split('=', 1)
        result[key] = [v.strip() for v in values.split(',')]
    return result


def generate_sweep_configs(
    base_config: str,
    sweep_params: Dict[str, List[str]]
) -> List[Dict[str, Any]]:
    """Generate all config combinations for a parameter sweep.
    
    Args:
        base_config: Path to base Hydra config file
        sweep_params: Parameters to sweep over
        
    Returns:
        List of composed configs
    """
    if not sweep_params:
        # No sweep, just load base config
        return [load_hydra_config(base_config, [])]
    
    # Generate all combinations
    keys = list(sweep_params.keys())
    values = [sweep_params[k] for k in keys]
    
    configs = []
    for combo in itertools.product(*values):
        overrides = [f"{k}={v}" for k, v in zip(keys, combo)]
        config = load_hydra_config(base_config, overrides)
        configs.append(config)
    
    return configs


def load_hydra_config(config_path: str, overrides: List[str]) -> Dict[str, Any]:
    """Load and compose a Hydra config with overrides.
    
    Args:
        config_path: Path to config file
        overrides: List of override strings (e.g., ["model=resnet50", "lr=0.01"])
        
    Returns:
        Composed config as dictionary
    """
    config_path = Path(config_path).resolve()
    config_dir = config_path.parent
    config_name = config_path.name
    
    # Clear any existing Hydra state
    GlobalHydra.instance().clear()
    
    # Initialize and compose
    with hydra.initialize_config_dir(config_dir=str(config_dir), version_base=None):
        cfg = hydra.compose(config_name=config_name, overrides=overrides)
        # Convert to regular dict and resolve
        return OmegaConf.to_container(cfg, resolve=True, throw_on_missing=True)


def validate_target(target: str) -> None:
    """Validate that a target function is importable.
    
    Args:
        target: Module path to function (e.g., "dr_exp.trainers.decon.train")
        
    Raises:
        AssertionError: If target cannot be imported
    """
    try:
        module_path, func_name = target.rsplit('.', 1)
        import importlib
        module = importlib.import_module(module_path)
        assert hasattr(module, func_name), f"Function {func_name} not found in {module_path}"
    except Exception as e:
        assert False, f"Cannot import target {target}: {e}"


# Now add the new CLI commands

@cli.command()
@click.argument('config_file', type=click.Path(exists=True))
@click.option('--target', help='Training function target (e.g., dr_exp.trainers.decon_trainer.train)')
@click.option('--priority', default=100, help='Job priority (0-1000)')
@click.option('--dry-run', is_flag=True, help='Show what would be created without creating')
@click.pass_obj
def submit(db, config_file, target, priority, dry_run):
    """Submit a job from Hydra config file.
    
    Examples:
        dr_exp --base-path /scratch --experiment exp1 submit config.yaml --target my.module.train
        dr_exp --base-path /scratch --experiment exp1 submit config.yaml --priority 500
    """
    # Load config
    config = load_hydra_config(config_file, [])
    
    # Handle _target_ field
    if target:
        config['_target_'] = target
    elif '_target_' not in config:
        click.echo("Error: Config must include _target_ field or --target must be specified")
        return
    
    # Validate
    validate_target(config['_target_'])
    assert 0 <= priority <= 1000, f"Priority must be 0-1000, got {priority}"
    
    if dry_run:
        click.echo("Would create job with config:")
        click.echo(json.dumps(config, indent=2))
        click.echo(f"Priority: {priority}")
        return
    
    # Create job
    job_id = db.create_job(config, priority)
    click.echo(f"Created job {job_id}")


@cli.command()
@click.argument('config_pattern')
@click.option('--target', help='Training function target to use for all configs')
@click.option('--priority', default=100, help='Job priority (0-1000) for all jobs')
@click.option('--dry-run', is_flag=True, help='Show what would be created')
@click.pass_obj
def submit_batch(db, config_pattern, target, priority, dry_run):
    """Submit multiple jobs from config files matching a pattern.
    
    Examples:
        dr_exp --base-path /scratch --experiment exp1 submit-batch "configs/*.yaml" --target my.train
        dr_exp --base-path /scratch --experiment exp1 submit-batch "configs/exp_*.yaml"
    """
    from glob import glob
    
    config_files = sorted(glob(config_pattern))
    if not config_files:
        click.echo(f"No files matching pattern: {config_pattern}")
        return
    
    click.echo(f"Found {len(config_files)} config files")
    
    created = 0
    for config_file in config_files:
        try:
            config = load_hydra_config(config_file, [])
            
            # Handle _target_
            if target:
                config['_target_'] = target
            elif '_target_' not in config:
                click.echo(f"Skipping {config_file}: No _target_ field and --target not specified")
                continue
            
            validate_target(config['_target_'])
            
            if dry_run:
                click.echo(f"\nWould create job from {config_file}")
                click.echo(f"Target: {config['_target_']}")
            else:
                job_id = db.create_job(config, priority)
                click.echo(f"Created job {job_id} from {config_file}")
                created += 1
                
        except Exception as e:
            click.echo(f"Error processing {config_file}: {e}")
    
    if not dry_run:
        click.echo(f"\nCreated {created} jobs")


@cli.command()
@click.option('--config', required=True, help='Base Hydra config file')
@click.option('--target', help='Training function target')
@click.option('--params', required=True, help='Sweep parameters (e.g., "model=r18,r50 lr=0.01,0.001")')
@click.option('--priority', default=100, help='Job priority (0-1000)')
@click.option('--dry-run', is_flag=True, help='Show parameter combinations without creating jobs')
@click.pass_obj
def sweep(db, config, target, params, priority, dry_run):
    """Submit a parameter sweep based on a config file.
    
    Examples:
        dr_exp --base-path /scratch --experiment exp1 sweep \\
            --config base.yaml \\
            --params "model=resnet18,resnet50 optim.lr=0.001,0.01" \\
            --target my.module.train
    """
    # Parse sweep parameters
    sweep_params = parse_sweep_params(params)
    
    if not sweep_params:
        click.echo("Error: No valid parameters found in sweep string")
        return
    
    # Show what we're sweeping
    click.echo("Sweep parameters:")
    for key, values in sweep_params.items():
        click.echo(f"  {key}: {values}")
    
    # Generate all configs
    configs = generate_sweep_configs(config, sweep_params)
    click.echo(f"\nGenerating {len(configs)} configurations")
    
    if dry_run:
        for i, cfg in enumerate(configs):
            click.echo(f"\n--- Config {i+1} ---")
            # Show only the swept parameters
            for key in sweep_params:
                value = cfg
                for part in key.split('.'):
                    value = value.get(part, 'NOT FOUND')
                click.echo(f"{key}: {value}")
        return
    
    # Create all jobs
    created = 0
    for i, cfg in enumerate(configs):
        try:
            # Handle _target_
            if target:
                cfg['_target_'] = target
            elif '_target_' not in cfg:
                click.echo(f"Error: Config must include _target_ or --target must be specified")
                return
            
            validate_target(cfg['_target_'])
            
            job_id = db.create_job(cfg, priority)
            created += 1
            
            # Show progress for large sweeps
            if (i + 1) % 10 == 0:
                click.echo(f"Created {i + 1}/{len(configs)} jobs...")
                
        except Exception as e:
            click.echo(f"Error creating job {i+1}: {e}")
    
    click.echo(f"\nCreated {created} jobs from sweep")
```

### Create Test Configs

Create a test config file `test_configs/simple_test.yaml`:

```yaml
# Test config for CLI testing
_target_: dr_exp.trainers.test_trainer.train_test

epochs: 5
model_name: test_model
learning_rate: 0.001
```

Create a test config without target `test_configs/no_target.yaml`:

```yaml
# Test config that needs --target specified
epochs: 10
model_name: test_model_2
batch_size: 32
```

### Update Test Script

Update the end of `test_worker.py` to test config submission:

```python
        # ... existing worker tests ...
        
        # Test config submission
        print("\nTesting config submission...")
        
        # Create test config file
        test_config = {
            "_target_": "dr_exp.trainers.test_trainer.train_test",
            "epochs": 3,
            "model_name": "config_test"
        }
        
        import json
        config_file = tmpdir / "test_config.json"
        with open(config_file, 'w') as f:
            json.dump(test_config, f)
        
        # Test single submission (would use CLI in practice)
        job_id = db.create_job(test_config, priority=200)
        assert db.get_job(job_id)["priority"] == 200
        assert db.get_job(job_id)["config"]["_target_"] == test_config["_target_"]
        print("✓ Config submission working")
        
        # Test sweep generation
        from dr_exp.cli import parse_sweep_params
        sweep_params = parse_sweep_params("epochs=1,2,3 model_name=a,b")
        assert len(sweep_params) == 2
        assert sweep_params["epochs"] == ["1", "2", "3"]
        assert sweep_params["model_name"] == ["a", "b"]
        print("✓ Sweep parsing working")
    
    print("\n✅ All tests passed!")
```

## Step 10: Run Complete Integration Tests

```bash
# Run worker test
python test_worker.py

# Test CLI submission commands (after installation)
# Single config
dr_exp --base-path /tmp/test --experiment cli_test submit test_configs/simple_test.yaml

# Batch submission
dr_exp --base-path /tmp/test --experiment cli_test submit-batch "test_configs/*.yaml" --target dr_exp.trainers.test_trainer.train_test

# Parameter sweep
dr_exp --base-path /tmp/test --experiment cli_test sweep \
    --config test_configs/simple_test.yaml \
    --params "epochs=5,10,20 learning_rate=0.001,0.01"

# Verify jobs were created
dr_exp --base-path /tmp/test --experiment cli_test list

# Run a worker to process them
dr_exp --base-path /tmp/test --experiment cli_test worker --worker-id test_worker --max-jobs 5
```

## Validation Checklist

Before proceeding to Phase 3:

- [ ] **ALL quality checks pass**: `ckdr` shows "All checks passed!"
- [ ] **ALL tests pass**: `pt` shows all tests passing with no skips
- [ ] Test coverage is adequate: `pt --cov=dr_exp.worker --cov=dr_exp.sync`
- [ ] Worker test passes successfully: `pt tests/test_worker.py -v`
- [ ] Integration tests pass: `pt tests/test_integration_phase2.py -v`
- [ ] Background sync thread starts and processes items
- [ ] Job outputs are created in correct locations
- [ ] Heartbeat updates work during job execution
- [ ] No references to old worker code remain:
  ```bash
  grep -r "run_worker\|JobExecutor\|HeartbeatManager" src/
  ```

### Phase 2 Validation Gate

```bash
# No proceeding until these ALL work:
ckdr && echo "✓ Quality checks pass" || echo "✗ FIX CODE QUALITY FIRST"
pt tests/test_worker.py tests/test_integration_phase2.py && echo "✓ Worker tests pass" || echo "✗ FIX IMPLEMENTATION"
pt && echo "✓ All tests pass" || echo "✗ FIX ALL FAILURES"
```

If any check shows ✗:
1. STOP
2. Read the error carefully
3. Fix the implementation (not the test)
4. Run all checks again
5. Only proceed when all show ✓

## Common Mistakes to Avoid

1. **DO NOT** implement actual Supabase uploads yet - just queue them
2. **DO NOT** add complex retry logic - keep it simple
3. **DO NOT** create separate sync services - embed in worker
4. **DO NOT** add configuration files - use constructor parameters
5. **DO NOT** implement distributed locking - single worker per job

### ⚠️ Test Anti-Patterns to AVOID

❌ **DO NOT weaken tests to pass:**
```python
# WRONG - Don't remove assertions
# assert worker.sync_thread.is_alive()  # Commented out because failing
```

❌ **DO NOT add sleeps to fix race conditions:**
```python
# WRONG - Fix the synchronization properly
time.sleep(10)  # Added to make test pass
```

❌ **DO NOT mock away the functionality being tested:**
```python
# WRONG - Test the real implementation
@patch('dr_exp.worker.base.Worker.run_job', return_value="success")
```

✅ **DO write tests that verify actual behavior**

## Architecture Notes

The key design decisions:
- Workers are self-contained with their own sync threads
- All writes go to `/scratch` first
- Sync is best-effort and non-blocking
- Failed syncs are retried in next cycle
- No complex state management

## Operational Considerations

### Worker Failures
- Jobs automatically recover after 5 minutes (default 300s heartbeat timeout)
- The launcher periodically calls recover_stale_jobs (every 10 minutes)
- Workers can be killed safely - launcher will restart them if jobs are pending

### Priority Management
- **Normal jobs**: 100-399 (default: 100)
- **Important jobs**: 400-699
- **Urgent jobs**: 700-899
- **System/debug jobs**: 900-1000
- Use `dr_exp boost` to move jobs to front of queue

### Common Workflows

```bash
# Submit a batch of jobs
for config in configs/*.yaml; do
    dr_exp --base-path /scratch/exp --experiment my_exp submit $config
done

# Monitor progress
watch -n 5 'dr_exp --base-path /scratch/exp --experiment my_exp list --status running'

# Handle stuck job
dr_exp --base-path /scratch/exp --experiment my_exp kill job_id
dr_exp --base-path /scratch/exp --experiment my_exp recover

# Debug a failing job
dr_exp --base-path /scratch/exp --experiment my_exp run_one job_id --no-sync

# Boost urgent jobs
dr_exp --base-path /scratch/exp --experiment my_exp boost job1 job2 job3 --priority 800
```

### Monitoring Health
- Check launcher logs for worker status updates (every 5 minutes)
- Monitor sync_queue size: large backlog indicates sync issues
- Watch for repeated failures: same job failing multiple times

### Running at Scale

#### Local Testing (Manual Workers)
```bash
# Start multiple workers per node (e.g., 2 per GPU)
for i in {0..3}; do
    dr_exp --base-path /scratch/exp --experiment my_exp worker \
        --worker-id node1_gpu${i/2}_worker${i} &
done
```

#### Production (Use Launcher)
```bash
# Start launcher which spawns all workers automatically
dr_exp --base-path /scratch/exp --experiment my_exp launcher \
    --workers-per-gpu 2 \
    --max-hours 47
```

## SLURM Integration

### Basic SLURM Script

Create `launcher.sbatch`:

```bash
#!/bin/bash
#SBATCH --job-name=dr_exp_launcher
#SBATCH --output=/scratch/%u/logs/slurm/%x_%j.out
#SBATCH --error=/scratch/%u/logs/slurm/%x_%j.err
#SBATCH --time=47:00:00
#SBATCH --gres=gpu:rtx8000:2
#SBATCH --mem=80G
#SBATCH --cpus-per-task=12

set -euo pipefail

# Configuration
EXPERIMENT_NAME="${EXPERIMENT_NAME:-my_experiment}"
WORKERS_PER_GPU="${WORKERS_PER_GPU:-2}"
BASE_PATH="/scratch/${USER}/experiments"

# Setup CUDA MPS
export CUDA_MPS_PIPE_DIRECTORY="/tmp/nvidia-mps-${SLURM_JOB_ID}"
export CUDA_MPS_LOG_DIRECTORY="/tmp/nvidia-log-${SLURM_JOB_ID}"
mkdir -p "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"

cleanup_mps() {
    echo quit | nvidia-cuda-mps-control || true
    rm -rf "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"
}
trap cleanup_mps EXIT

# Start MPS
nvidia-cuda-mps-control -d

# Activate environment (adjust as needed)
source /path/to/venv/bin/activate

# Run launcher
dr_exp --base-path "$BASE_PATH" --experiment "$EXPERIMENT_NAME" launcher \
    --workers-per-gpu "$WORKERS_PER_GPU" \
    --max-hours 46.5  # Leave buffer for cleanup
```

### Advanced SLURM Script (Multiple GPU Configurations)

For flexibility with 1-3 GPUs:

```bash
#!/bin/bash
#SBATCH --job-name=dr_exp_launcher
#SBATCH --output=/scratch/%u/logs/slurm/%x_%j.out
#SBATCH --error=/scratch/%u/logs/slurm/%x_%j.err
#SBATCH --time=47:00:00
#SBATCH --mem=80G
#SBATCH --cpus-per-task=12

# GPU configuration passed as argument
# Usage: sbatch launcher.sbatch 2  # for 2 GPUs
GPU_COUNT="${1:-2}"

#SBATCH --gres=gpu:rtx8000:${GPU_COUNT}

# Rest of script as above...
```

### Submitting Jobs

```bash
# Submit with 2 GPUs
sbatch launcher.sbatch

# Submit with different GPU counts
sbatch --export=EXPERIMENT_NAME=resnet_sweep,WORKERS_PER_GPU=3 launcher.sbatch

# Submit multiple experiments
for exp in exp1 exp2 exp3; do
    sbatch --export=EXPERIMENT_NAME=$exp launcher.sbatch
done
```

### Monitoring SLURM Jobs

```bash
# Check job status
squeue -u $USER

# View launcher output
tail -f /scratch/$USER/logs/slurm/dr_exp_launcher_*.out

# Check GPU utilization
ssh <node> nvidia-smi
```

### Key Design Decisions for SLURM

1. **Single Launcher Process**: One SLURM job spawns all workers internally
2. **MPS Enabled**: Better GPU sharing for multiple workers
3. **Long Runtime**: 47 hours to maximize GPU allocation usage
4. **Auto Recovery**: Launcher handles all worker restarts and job recovery
5. **Graceful Shutdown**: Clean stop before SLURM time limit

### Best Practices

1. **Submit Jobs Anytime**: With launcher running, new jobs start immediately
2. **Monitor via Logs**: Launcher logs status every 5 minutes
3. **Let It Run**: Don't manually manage workers - launcher handles everything
4. **Plan Experiments**: Submit all configs early to maximize GPU time

## Next Phase

Once worker tests pass, proceed to Phase 3: Supabase Integration.
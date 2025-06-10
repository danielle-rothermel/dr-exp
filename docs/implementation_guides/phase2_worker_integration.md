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
        logger.debug(f"Worker {self.worker_id} attempting to claim next job...")
        
        # Claim a job
        job = self.job_db.claim_next_job(self.worker_id)
        if job is None:
            logger.debug(f"No jobs available for worker {self.worker_id}")
            return None
        
        self.current_job_id = job["id"]
        logger.info(f"Worker {self.worker_id} claimed job {job['id']} (priority: {job['priority']})")
        logger.debug(f"Job created at: {job['created_at']}")
        logger.debug(f"Job config target: {job['config'].get('_target_', 'NO TARGET!')}")
        
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
        
        logger.debug(f"Importing target: {config['_target_']}")
        
        # Validate target is importable before execution
        target = config['_target_']
        module_path, func_name = target.rsplit('.', 1)
        try:
            import importlib
            module = importlib.import_module(module_path)
            if not hasattr(module, func_name):
                raise AttributeError(f"Function '{func_name}' not found in module '{module_path}'")
            logger.debug(f"Target function verified: {target}")
        except Exception as e:
            logger.error(f"Failed to import target {target}: {e}")
            raise
        
        # Add runtime paths to config
        config["_dr_exp_storage_dir"] = str(storage_dir)
        config["_dr_exp_job_id"] = job["id"]
        
        logger.debug(f"Writing job outputs to: {storage_dir}")
        logger.debug(f"Full config for job {job['id']}: {json.dumps(config, indent=2)}")
        
        # Let Hydra do all the work!
        cfg = OmegaConf.create(config)
        
        logger.info(f"Starting execution of job {job['id']} with target {target}")
        start_time = time.time()
        
        result = hydra.utils.call(cfg)
        
        execution_time = time.time() - start_time
        logger.info(f"Job {job['id']} execution completed in {execution_time:.2f} seconds")
        
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
            logger.debug(f"Sync disabled, skipping artifact queueing for job {job_id}")
            return
        
        logger.debug(f"Queueing artifacts for job {job_id} from {storage_dir}")
        artifact_count = 0
        
        # Queue all files in storage directory
        for file_path in storage_dir.rglob("*"):
            if file_path.is_file():
                # Compute relative path
                rel_path = file_path.relative_to(storage_dir)
                remote_path = f"experiments/{self.job_db.experiment_name}/runs/{job_id}/{rel_path}"
                
                sync_id = self.sync_queue.add(file_path, remote_path)
                artifact_count += 1
                logger.debug(f"Queued artifact: {rel_path} -> {remote_path} (sync_id: {sync_id})")
        
        # Also queue the job metadata
        job_file = self.job_db.jobs_dir / f"{job_id}.json"
        if job_file.exists():
            remote_path = f"experiments/{self.job_db.experiment_name}/jobs/{job_id}.json"
            sync_id = self.sync_queue.add(job_file, remote_path)
            artifact_count += 1
            logger.debug(f"Queued job metadata: {job_file.name} -> {remote_path} (sync_id: {sync_id})")
        
        logger.info(f"Queued {artifact_count} artifacts for sync from job {job_id}")
    
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
        logger.debug(f"Started heartbeat thread for job {job_id}")
    
    def _stop_heartbeat(self) -> None:
        """Stop the heartbeat thread."""
        if self.heartbeat_thread:
            self.stop_heartbeat.set()
            self.heartbeat_thread.join(timeout=5)
            self.heartbeat_thread = None
            logger.debug("Stopped heartbeat thread")
    
    def _heartbeat_loop(self, job_id: str) -> None:
        """Send periodic heartbeats for a job."""
        logger.debug(f"Heartbeat loop started for job {job_id}")
        heartbeat_count = 0
        
        while not self.stop_heartbeat.is_set():
            try:
                heartbeat_time = datetime.now(UTC).isoformat()
                self.job_db.update_job(job_id, {
                    "heartbeat": heartbeat_time,
                })
                heartbeat_count += 1
                if heartbeat_count % 10 == 1:  # Log every 10th heartbeat to avoid spam
                    logger.debug(f"Heartbeat #{heartbeat_count} sent for job {job_id} at {heartbeat_time}")
            except Exception as e:
                logger.error(f"Heartbeat failed for job {job_id}: {e}")
            
            # Wait 30 seconds between heartbeats
            if self.stop_heartbeat.wait(timeout=30):
                break
        
        logger.debug(f"Heartbeat loop stopped for job {job_id} after {heartbeat_count} heartbeats")
    
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
        logger.debug(f"Starting sync cycle check for worker {self.worker_id}")
        
        # Get pending items
        pending = self.sync_queue.get_pending(limit=self.sync_batch_size)
        
        if not pending:
            logger.debug("No items to sync")
            return
        
        logger.info(f"Starting sync cycle with {len(pending)} items")
        
        for idx, item in enumerate(pending, 1):
            if self.stop_sync.is_set():
                logger.debug("Sync cycle interrupted by stop signal")
                break
            
            try:
                # For now, just simulate upload (Phase 3 will implement real upload)
                local_path = Path(item.local_path)
                if not local_path.exists():
                    raise FileNotFoundError(f"Local file not found: {local_path}")
                
                file_size = local_path.stat().st_size
                logger.debug(f"Syncing item {idx}/{len(pending)}: {item.local_path} ({file_size} bytes)")
                
                # Simulate upload delay
                time.sleep(0.1)
                
                logger.debug(f"Successfully synced {item.local_path} to {item.remote_path}")
                self.sync_queue.mark_completed(item.id)
                
            except Exception as e:
                logger.error(f"Failed to sync {item.local_path}: {e}")
                self.sync_queue.mark_failed(item.id, str(e))
                logger.debug(f"Sync item {item.id} marked as failed after attempt #{item.attempts + 1}")
            
            # Rate limit between uploads
            time.sleep(1)
        
        logger.debug(f"Sync cycle completed for worker {self.worker_id}")
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

## Step 7.5: Debugging Features

The CLI now includes two important debugging features to help troubleshoot job submission and worker execution:

### Verbose Job Submission

Use the `--verbose` flag with the submit command to see detailed validation output:

```bash
dr_exp --base-path /scratch/exp --experiment my_exp submit config.yaml --verbose
```

Expected output:
```
Loading config from: config.yaml
✓ Config validated: _target_ = dr_exp.trainers.decon_trainer.train
✓ Target function verified as importable
✓ Job created: job_abc123
✓ Job file written: /scratch/exp/my_exp/jobs/job_abc123.json
✓ Job queued with priority 100
```

This helps catch configuration issues early by:
- Validating the `_target_` field exists
- Checking that the target module/function is importable
- Showing exactly where the job file was written
- Confirming the priority level

### Worker Debug Logging

Use the `--log-level DEBUG` flag with the worker command to see detailed execution logs:

```bash
dr_exp --base-path /scratch/exp --experiment my_exp worker --worker-id debug_worker --log-level DEBUG
```

Expected debug output includes:
```
[DEBUG] dr_exp: Worker debug_worker starting...
[DEBUG] dr_exp: Experiment path: /scratch/exp/my_exp
[DEBUG] dr_exp: Sync enabled: True
[DEBUG] dr_exp: Max jobs: unlimited
[DEBUG] dr_exp: Initialized sync queue at /scratch/exp/my_exp/sync_queue
[DEBUG] dr_exp: Background sync thread will be started
[DEBUG] dr_exp: Worker debug_worker attempting to claim next job...
[INFO] dr_exp: Worker debug_worker claimed job job_abc123 (priority: 500)
[DEBUG] dr_exp: Job created at: 2024-01-15T10:30:00
[DEBUG] dr_exp: Job config target: dr_exp.trainers.decon_trainer.train
[DEBUG] dr_exp: Started heartbeat thread for job job_abc123
[DEBUG] dr_exp: Importing target: dr_exp.trainers.decon_trainer.train
[DEBUG] dr_exp: Target function verified: dr_exp.trainers.decon_trainer.train
[DEBUG] dr_exp: Writing job outputs to: /scratch/exp/my_exp/storage/run_job_abc123
[DEBUG] dr_exp: Full config for job job_abc123: {
  "_target_": "dr_exp.trainers.decon_trainer.train",
  "model": {"architecture": "resnet18"},
  ...
}
[INFO] dr_exp: Starting execution of job job_abc123 with target dr_exp.trainers.decon_trainer.train
[DEBUG] dr_exp: Heartbeat #1 sent for job job_abc123 at 2024-01-15T10:35:30
[INFO] dr_exp: Job job_abc123 execution completed in 312.45 seconds
[DEBUG] dr_exp: Queueing artifacts for job job_abc123 from /scratch/exp/my_exp/storage/run_job_abc123
[DEBUG] dr_exp: Queued artifact: metrics.jsonl -> experiments/my_exp/runs/job_abc123/metrics.jsonl
[INFO] dr_exp: Queued 5 artifacts for sync from job job_abc123
[DEBUG] dr_exp: Starting sync cycle check for worker debug_worker
[DEBUG] dr_exp: Syncing item 1/5: /scratch/.../metrics.jsonl (2451 bytes)
```

The debug logging provides visibility into:
- Worker initialization and configuration
- Job claiming process with lock acquisition
- Target validation and import checking
- Config validation before execution
- Heartbeat thread operation
- Job execution timing
- Artifact queueing for sync
- Background sync operations

This is especially useful for:
- Debugging why jobs aren't being claimed
- Understanding import/validation failures
- Tracking sync queue behavior
- Monitoring heartbeat operation
- Performance profiling of job execution

### Config Validation Command

Use the `validate config` subcommand to check configuration files before submission:

```bash
# Validate a single config
dr_exp --base-path /scratch/exp --experiment my_exp validate config configs/train.yaml

# Validate with detailed parameter analysis
dr_exp --base-path /scratch/exp --experiment my_exp validate config configs/train.yaml --detailed

# Validate multiple configs at once
dr_exp --base-path /scratch/exp --experiment my_exp validate config configs/*.yaml
```

Basic validation output:
```
Validating config: configs/train.yaml
✓ YAML syntax valid
✓ Required field '_target_' present: dr_exp.trainers.decon_trainer.train
✓ Target module 'dr_exp.trainers.decon_trainer' found
✓ Target function 'train' found and callable
✓ Config parameters match function signature
✓ Hydra instantiation test passed

Config is valid and ready for submission!
```

Detailed validation output with `--detailed`:
```
Validating config: configs/train.yaml
✓ YAML syntax valid
✓ Required field '_target_' present: dr_exp.trainers.decon_trainer.train_classification
✓ Target module found
✓ Target function found

Function signature analysis:
  Required parameters:
    - model: Dict[str, Any] ✓ provided
    - optim: Dict[str, Any] ✓ provided  
    - data: Dict[str, Any] ✓ provided
    - epochs: int ✓ provided (value: 100)
    - batch_size: int ✓ provided (value: 128)
  
  Optional parameters with defaults:
    - _dr_exp_storage_dir: Optional[str] = None (injected by worker)
    - _dr_exp_job_id: Optional[str] = None (injected by worker)
  
  Extra config keys (will be passed as **kwargs):
    - learning_rate_schedule
    - early_stopping

✓ All required parameters provided
✓ No type mismatches detected
✓ Hydra instantiation test passed

Config is valid and ready for submission!
```

The validation command helps catch common errors:
- Missing or malformed `_target_` field
- Non-existent modules or functions
- Missing required parameters
- Invalid YAML/JSON syntax
- Incompatible parameter types

This is especially useful when:
- Testing new training functions
- Debugging configuration issues
- Validating configs before batch submission
- Ensuring configs work across different environments

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
from omegaconf import OmegaConf


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
    # For init command, we need to pass validate=False
    ctx.obj = {'base_path': base_path, 'experiment': experiment}


@cli.command()
@click.option('--force', is_flag=True, help='Overwrite existing experiment')
@click.option('--with-examples', is_flag=True, help='Create example configs')
@click.pass_context
def init(ctx, force, with_examples):
    """Initialize a new experiment with proper directory structure.
    
    Creates all required directories and optionally adds example configurations.
    """
    base_path = ctx.obj['base_path']
    experiment = ctx.obj['experiment']
    
    # Create JobDB with validate=False for initialization
    db = JobDB(base_path=base_path, experiment_name=experiment, validate=False)
    experiment_path = db.experiment_path
    
    # Check if experiment already exists
    if experiment_path.exists() and not force:
        # Check if it's already properly initialized
        required_dirs = ['jobs', 'storage', 'sync_queue', 'logs', 'control']
        missing_dirs = [d for d in required_dirs if not (experiment_path / d).exists()]
        
        if not missing_dirs:
            click.echo(f"✓ Experiment already initialized at {experiment_path}")
            return
        else:
            click.echo(f"⚠ Experiment exists but is missing directories: {missing_dirs}")
            click.echo("Use --force to reinitialize or create missing directories manually")
            return
    
    # Create directory structure
    directories = {
        'jobs': 'Job metadata storage',
        'storage': 'Job outputs and artifacts', 
        'sync_queue': 'Pending Supabase uploads',
        'logs': 'Operational logs',
        'control': 'Control files for graceful shutdown',
        'slurm_logs': 'SLURM output files',
    }
    
    click.echo(f"Initializing experiment: {experiment}")
    click.echo(f"Location: {experiment_path}")
    click.echo("")
    
    for dir_name, description in directories.items():
        dir_path = experiment_path / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
        click.echo(f"✓ Created {dir_name}/ - {description}")
    
    # Create .gitignore
    gitignore_content = """# dr_exp experiment directories
storage/
logs/
slurm_logs/
sync_queue/
*.log
*.out
*.err

# But keep job definitions
!jobs/*.json
"""
    gitignore_path = experiment_path / '.gitignore'
    gitignore_path.write_text(gitignore_content)
    click.echo("✓ Created .gitignore")
    
    # Create README
    from datetime import datetime
    readme_content = f"""# {experiment}

This is a dr_exp experiment directory.

## Directory Structure
- `jobs/` - Job metadata (JSON files)
- `storage/` - Job outputs and artifacts
- `sync_queue/` - Pending uploads to Supabase
- `logs/` - Worker and launcher logs
- `control/` - Control files for job management
- `slurm_logs/` - SLURM output files

## Usage

Submit jobs:
```bash
dr_exp --base-path {base_path} --experiment {experiment} submit config.yaml
```

Start workers:
```bash
dr_exp --base-path {base_path} --experiment {experiment} launcher
```

Check status:
```bash
dr_exp --base-path {base_path} --experiment {experiment} list
```

Created: {datetime.now().isoformat()}
"""
    readme_path = experiment_path / 'README.md'
    readme_path.write_text(readme_content)
    click.echo("✓ Created README.md")
    
    # Create example configs if requested
    if with_examples:
        examples_dir = experiment_path / 'example_configs'
        examples_dir.mkdir(exist_ok=True)
        
        # Simple test config
        test_config = {
            '_target_': 'dr_exp.trainers.test_trainer.train_test',
            'epochs': 5,
            'model_name': 'test_model',
            'learning_rate': 0.001
        }
        
        import yaml
        with open(examples_dir / 'test_simple.yaml', 'w') as f:
            yaml.dump(test_config, f)
        
        # DeconCNN example
        decon_config = {
            '_target_': 'dr_exp.trainers.decon_trainer.train_classification',
            'model': {
                'architecture': 'resnet18',
                'num_classes': 10
            },
            'optim': {
                'name': 'adamw',
                'lr': 0.001
            },
            'data': {
                'name': 'cifar10'
            },
            'epochs': 100,
            'batch_size': 128
        }
        
        with open(examples_dir / 'decon_example.yaml', 'w') as f:
            yaml.dump(decon_config, f)
        
        click.echo("✓ Created example_configs/")
        click.echo("  - test_simple.yaml")
        click.echo("  - decon_example.yaml")
    
    # Validate permissions
    test_file = experiment_path / '.test_write'
    try:
        test_file.touch()
        test_file.unlink()
        click.echo("✓ Write permissions verified")
    except Exception as e:
        click.echo(f"⚠ Warning: Permission test failed: {e}")
    
    # Show summary
    click.echo("")
    click.echo("✅ Experiment initialized successfully!")
    click.echo("")
    click.echo("Next steps:")
    click.echo(f"1. Create job configs (see example_configs/ for templates)")
    click.echo(f"2. Submit jobs: dr_exp --base-path {base_path} --experiment {experiment} submit config.yaml")
    click.echo(f"3. Start workers: sbatch scripts/dr_exp_slurm.sbatch")
    
    # Check for common issues
    import shutil
    disk_usage = shutil.disk_usage(experiment_path)
    free_gb = disk_usage.free / (1024**3)
    if free_gb < 100:
        click.echo(f"\n⚠ Warning: Only {free_gb:.1f} GB free space available")


@cli.group()
def validate():
    """Validation commands for experiment and configs."""
    pass


@validate.command('experiment')
@click.pass_context
def validate_experiment(ctx):
    """Validate experiment setup and configuration.
    
    Checks directory structure, permissions, and system requirements.
    """
    base_path = ctx.obj['base_path']
    experiment = ctx.obj['experiment']
    
    # Try to create JobDB - will fail if not initialized
    try:
        db = JobDB(base_path=base_path, experiment_name=experiment, validate=True)
    except RuntimeError as e:
        click.echo(f"❌ Validation failed: {e}")
        return
    
    click.echo("Validating experiment setup...")
    click.echo(f"Experiment: {experiment}")
    click.echo(f"Location: {db.experiment_path}")
    click.echo("")
    
    issues = []
    warnings = []
    
    # Check directories
    directories = ['jobs', 'storage', 'sync_queue', 'logs', 'control', 'slurm_logs']
    for dir_name in directories:
        dir_path = db.experiment_path / dir_name
        if dir_path.exists():
            click.echo(f"✓ {dir_name}/ exists")
        else:
            click.echo(f"✗ {dir_name}/ missing")
            issues.append(f"Missing directory: {dir_name}")
    
    # Check permissions
    try:
        test_file = db.jobs_dir / '.test_write'
        test_file.touch()
        test_file.unlink()
        click.echo("✓ Write permissions OK")
    except:
        click.echo("✗ Write permission failed")
        issues.append("Cannot write to jobs directory")
    
    # Check disk space
    import shutil
    disk_usage = shutil.disk_usage(db.experiment_path)
    free_gb = disk_usage.free / (1024**3)
    if free_gb > 100:
        click.echo(f"✓ Disk space OK ({free_gb:.1f} GB free)")
    else:
        click.echo(f"⚠ Low disk space ({free_gb:.1f} GB free)")
        warnings.append(f"Low disk space: {free_gb:.1f} GB")
    
    # Check Python environment
    import sys
    python_version = sys.version.split()[0]
    if sys.version_info >= (3, 10):
        click.echo(f"✓ Python version OK ({python_version})")
    else:
        click.echo(f"✗ Python version too old ({python_version})")
        issues.append(f"Python 3.10+ required, found {python_version}")
    
    # Check for GPUs (optional)
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            gpus = result.stdout.strip().split('\n')
            click.echo(f"✓ Found {len(gpus)} GPU(s)")
            for gpu in gpus:
                click.echo(f"  - {gpu}")
        else:
            click.echo("⚠ No GPUs detected (CPU mode)")
            warnings.append("No GPUs detected")
    except:
        click.echo("⚠ Could not check GPU status")
        warnings.append("Could not check GPU status")
    
    # Summary
    click.echo("")
    if issues:
        click.echo(f"❌ Validation failed with {len(issues)} issue(s):")
        for issue in issues:
            click.echo(f"  - {issue}")
        click.echo("\nRun 'dr_exp init' to fix these issues")
    else:
        click.echo("✅ All checks passed!")
    
    if warnings:
        click.echo(f"\n⚠ {len(warnings)} warning(s):")
        for warning in warnings:
            click.echo(f"  - {warning}")


@validate.command('config')
@click.argument('config_files', nargs=-1, required=True, type=click.Path(exists=True))
@click.option('--detailed', is_flag=True, help='Show detailed parameter analysis')
@click.pass_context
def validate_config(ctx, config_files, detailed):
    """Validate job configuration files before submission.
    
    Checks YAML syntax, _target_ validity, and parameter compatibility.
    
    Examples:
        dr_exp validate config configs/train.yaml
        dr_exp validate config configs/*.yaml --detailed
    """
    import yaml
    import json
    import importlib
    import inspect
    from pathlib import Path
    from typing import get_type_hints
    
    # Get database for experiment context (but we don't need to use it)
    base_path = ctx.obj['base_path']
    experiment = ctx.obj['experiment']
    
    total_files = len(config_files)
    valid_files = 0
    
    for config_file in config_files:
        click.echo(f"\nValidating config: {config_file}")
        issues = []
        
        # 1. Check YAML/JSON syntax
        try:
            with open(config_file) as f:
                if config_file.endswith('.yaml') or config_file.endswith('.yml'):
                    config = yaml.safe_load(f)
                else:
                    config = json.load(f)
            click.echo("✓ YAML syntax valid")
        except Exception as e:
            click.echo(f"✗ Invalid syntax: {e}")
            continue
        
        # 2. Check required fields
        if '_target_' not in config:
            click.echo("✗ Required field '_target_' not found")
            issues.append("Missing _target_ field")
            continue
        
        target = config['_target_']
        click.echo(f"✓ Required field '_target_' present: {target}")
        
        # 3. Validate target
        try:
            module_path, func_name = target.rsplit('.', 1)
        except ValueError:
            click.echo(f"✗ Invalid target format: {target}")
            issues.append("Target must be in format 'module.function'")
            continue
        
        # Check module exists
        try:
            module = importlib.import_module(module_path)
            click.echo(f"✓ Target module '{module_path}' found")
        except ImportError as e:
            click.echo(f"✗ Target module '{module_path}' not found")
            click.echo(f"  Error: {e}")
            issues.append(f"Module not found: {module_path}")
            continue
        
        # Check function exists
        if not hasattr(module, func_name):
            click.echo(f"✗ Target function '{func_name}' not found in module")
            issues.append(f"Function '{func_name}' not found in {module_path}")
            continue
        
        func = getattr(module, func_name)
        if not callable(func):
            click.echo(f"✗ Target '{func_name}' is not callable")
            issues.append(f"'{func_name}' is not a function")
            continue
        
        click.echo("✓ Target function found and callable")
        
        # 4. Analyze function signature
        if detailed:
            click.echo("\nFunction signature analysis:")
            try:
                sig = inspect.signature(func)
                params = sig.parameters
                
                # Get type hints if available
                try:
                    type_hints = get_type_hints(func)
                except:
                    type_hints = {}
                
                required_params = []
                optional_params = []
                
                for param_name, param in params.items():
                    # Skip special dr_exp parameters
                    if param_name.startswith('_dr_exp_'):
                        optional_params.append((param_name, param, True))
                        continue
                    
                    if param.default == inspect.Parameter.empty and param.kind not in [
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD
                    ]:
                        required_params.append((param_name, param, False))
                    else:
                        optional_params.append((param_name, param, False))
                
                # Check required parameters
                click.echo("  Required parameters:")
                for param_name, param, is_special in required_params:
                    param_type = type_hints.get(param_name, 'Any')
                    if param_name in config:
                        click.echo(f"    - {param_name}: {param_type} ✓ provided")
                    else:
                        click.echo(f"    - {param_name}: {param_type} ✗ MISSING")
                        issues.append(f"Missing required parameter: {param_name}")
                
                # Show optional parameters
                if optional_params:
                    click.echo("\n  Optional parameters with defaults:")
                    for param_name, param, is_special in optional_params:
                        param_type = type_hints.get(param_name, 'Any')
                        default = param.default if param.default != inspect.Parameter.empty else 'None'
                        if is_special:
                            click.echo(f"    - {param_name}: {param_type} = {default} (injected by worker)")
                        else:
                            status = "✓ provided" if param_name in config else f"(default: {default})"
                            click.echo(f"    - {param_name}: {param_type} {status}")
                
                # Check for VAR_KEYWORD (**kwargs)
                has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
                
                # Check for extra config keys
                func_params = set(params.keys())
                config_keys = set(config.keys()) - {'_target_'}
                extra_keys = config_keys - func_params
                
                if extra_keys:
                    if has_kwargs:
                        click.echo(f"\n  Extra config keys (will be passed as **kwargs):")
                        for key in sorted(extra_keys):
                            click.echo(f"    - {key}")
                    else:
                        click.echo(f"\n  ⚠ Extra config keys (function has no **kwargs):")
                        for key in sorted(extra_keys):
                            click.echo(f"    - {key}")
                        warnings.append("Extra parameters without **kwargs support")
                
            except Exception as e:
                click.echo(f"  Could not analyze signature: {e}")
        
        # 5. Test Hydra instantiation
        click.echo("✓ Config parameters match function signature") if not issues else None
        
        try:
            # Test creating OmegaConf object
            cfg = OmegaConf.create(config)
            click.echo("✓ Hydra instantiation test passed")
        except Exception as e:
            click.echo(f"✗ Hydra instantiation failed: {e}")
            issues.append("Hydra instantiation error")
        
        # Summary for this file
        if issues:
            click.echo(f"\n❌ Config validation failed!")
            for issue in issues:
                click.echo(f"  - {issue}")
        else:
            click.echo(f"\n✅ Config is valid and ready for submission!")
            valid_files += 1
    
    # Overall summary for multiple files
    if total_files > 1:
        click.echo(f"\n{'='*50}")
        click.echo(f"Summary: {valid_files}/{total_files} configs are valid")
        if valid_files < total_files:
            click.echo("Fix the issues above before submitting jobs.")


# Update the pass_obj decorators to handle both dict and JobDB
def get_db(ctx):
    """Get JobDB from context, creating if needed."""
    if isinstance(ctx.obj, dict):
        return JobDB(base_path=ctx.obj['base_path'], 
                    experiment_name=ctx.obj['experiment'],
                    validate=True)
    return ctx.obj


@cli.command()
@click.argument('config_file', type=click.Path(exists=True))
@click.option('--priority', default=100, help='Job priority (0-1000)')
@click.option('--verbose', is_flag=True, help='Show detailed submission output')
@click.pass_context
def submit(ctx, config_file, priority, verbose):
    """Submit a job from config file with validation.
    
    For pre-submission validation without creating a job, use:
        dr_exp validate config <config_file>
    """
    db = get_db(ctx)
    
    # Verbose: Show config loading
    if verbose:
        click.echo(f"Loading config from: {config_file}")
    
    # Load config file
    with open(config_file) as f:
        if config_file.endswith('.yaml') or config_file.endswith('.yml'):
            config = yaml.safe_load(f)
        else:
            config = json.load(f)
    
    # Validate _target_ field exists
    if '_target_' not in config:
        click.echo(f"❌ Error: Config must include '_target_' field")
        return
    
    # Verbose: Show target validation
    target = config['_target_']
    if verbose:
        click.echo(f"✓ Config validated: _target_ = {target}")
    
    # Validate target is importable
    module_path, func_name = target.rsplit('.', 1)
    try:
        import importlib
        module = importlib.import_module(module_path)
        if not hasattr(module, func_name):
            click.echo(f"❌ Error: Function '{func_name}' not found in module '{module_path}'")
            return
        if verbose:
            click.echo(f"✓ Target function verified as importable")
    except ImportError as e:
        click.echo(f"❌ Error: Cannot import target module {module_path}: {e}")
        return
    
    # Create the job
    try:
        job_id = db.create_job(config, priority)
        
        if verbose:
            job_path = db.jobs_dir / f"{job_id}.json"
            click.echo(f"✓ Job created: {job_id}")
            click.echo(f"✓ Job file written: {job_path}")
            click.echo(f"✓ Job queued with priority {priority}")
        else:
            # Always show job ID even in non-verbose mode
            click.echo(f"Created job {job_id}")
            
    except Exception as e:
        click.echo(f"❌ Error creating job: {e}")


@cli.command()
@click.option('--status', help='Filter by status (queued, running, completed, failed)')
@click.option('--limit', default=50, help='Maximum jobs to show')
@click.pass_context
def list(ctx, status, limit):
    """List jobs."""
    db = get_db(ctx)
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
@click.pass_context
def show(ctx, job_id):
    """Show detailed job information."""
    db = get_db(ctx)
    job = db.get_job(job_id)
    if not job:
        click.echo(f"Job {job_id} not found")
        return
    
    click.echo(json.dumps(job, indent=2))


# NOTE: All remaining commands should be updated similarly to use @click.pass_context
# and get_db(ctx) instead of @click.pass_obj. This ensures proper handling of
# both the init command (which needs validate=False) and regular commands.

@cli.command()
@click.argument('job_id')
@click.pass_context
def kill(ctx, job_id):
    """Kill a running job."""
    db = get_db(ctx)
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
@click.option('--log-level', default='INFO', 
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR'], case_sensitive=False),
              help='Set logging level')
@click.pass_obj
def worker(db, worker_id, max_jobs, sync, log_level):
    """Run a worker process with configurable logging.
    
    In production, use the 'launcher' command instead to spawn multiple workers.
    """
    # Configure logging level
    import logging
    numeric_level = getattr(logging, log_level.upper())
    logging.basicConfig(
        level=numeric_level,
        format='[%(levelname)s] %(name)s: %(message)s',
        force=True  # Override any existing configuration
    )
    logger = logging.getLogger('dr_exp')
    
    if log_level == 'DEBUG':
        logger.debug(f"Worker {worker_id} starting...")
        logger.debug(f"Experiment path: {db.experiment_path}")
        logger.debug(f"Sync enabled: {sync}")
        logger.debug(f"Max jobs: {max_jobs if max_jobs > 0 else 'unlimited'}")
    
    worker = Worker(
        worker_id=worker_id,
        job_db=db,
        sync_enabled=sync
    )
    
    click.echo(f"Starting worker {worker_id} (log level: {log_level})")
    
    if log_level == 'DEBUG':
        logger.debug(f"Initialized sync queue at {db.sync_queue_dir}")
        if sync:
            logger.debug("Background sync thread will be started")
    
    worker.start()
    
    jobs_run = 0
    try:
        while True:
            if log_level == 'DEBUG':
                logger.debug(f"Worker {worker_id} checking for next job...")
            
            job_id = worker.run_next_job()
            if job_id is None:
                # No jobs available - wait and retry
                if log_level == 'DEBUG':
                    logger.debug("No jobs available, waiting 10 seconds...")
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

## Section 2.5: Enhanced SLURM Integration

### Overview
This section adds robust SLURM support with proper resource isolation, multi-job support, centralized logging, and graceful shutdown mechanisms.

### Key Requirements
1. **Multiple SLURM jobs** can run for the same experiment without conflicts
2. **Resource isolation**: Each worker gets specific GPU and memory limits
3. **Centralized logging**: All logs go to `{experiment}/logs/slurm_{job_id}/`
4. **Graceful control**: Support for finish-current and immediate stop
5. **Error aggregation**: Collect errors from all workers in one place

### Updated Directory Structure

```
{base_path}/{experiment}/
├── jobs/                    # Job metadata (unchanged)
├── storage/                 # Job outputs (unchanged)
├── sync_queue/             # Pending uploads (unchanged)
├── logs/                   # NEW: All operational logs
│   ├── slurm_123456/      # Per SLURM job
│   │   ├── launcher.log   # Main launcher process
│   │   ├── workers/       # Individual worker logs
│   │   │   ├── slurm123456_node042_gpu0_w0.log
│   │   │   ├── slurm123456_node042_gpu0_w1.log
│   │   │   └── ...
│   │   ├── errors.log     # Aggregated error messages
│   │   └── status.json    # Current status snapshot
│   └── slurm_123457/      # Another SLURM job (concurrent)
├── control/                # NEW: Control files
│   ├── slurm_123456.control
│   └── slurm_123457.control
└── slurm_logs/            # SLURM's own outputs
    └── slurm-123456.out
```

### Step 2.5.1: Update Launcher for SLURM Support

Update `src/dr_exp/launcher.py` to add SLURM-specific features:

```python
# Add to imports
import json

# Update WorkerLauncher.__init__ to accept SLURM parameters
def __init__(
    self,
    job_db: JobDB,
    workers_per_gpu: int = 2,
    max_runtime_hours: float = 47,
    heartbeat_timeout: int = 300,
    worker_restart_delay: int = 30,
    slurm_job_id: Optional[str] = None,
    node_name: Optional[str] = None,
    total_memory_mb: Optional[int] = None,
    log_dir: Optional[Path] = None,
):
    """Initialize launcher with SLURM support.
    
    Args:
        ... existing args ...
        slurm_job_id: SLURM job ID for unique worker names
        node_name: SLURM node name
        total_memory_mb: Total memory allocated by SLURM
        log_dir: Directory for launcher and worker logs
    """
    # ... existing init code ...
    
    self.slurm_job_id = slurm_job_id or os.environ.get('SLURM_JOB_ID', 'local')
    self.node_name = node_name or os.environ.get('SLURMD_NODENAME', 'localhost')
    self.total_memory_mb = total_memory_mb or self._get_total_memory()
    
    # Setup logging directory
    if log_dir:
        self.log_dir = Path(log_dir)
    else:
        self.log_dir = job_db.experiment_path / 'logs' / f'slurm_{self.slurm_job_id}'
    self.log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories
    self.worker_log_dir = self.log_dir / 'workers'
    self.worker_log_dir.mkdir(exist_ok=True)
    
    # Control file for graceful operations
    self.control_dir = job_db.experiment_path / 'control'
    self.control_dir.mkdir(exist_ok=True)
    self.control_file = self.control_dir / f'slurm_{self.slurm_job_id}.control'
    
    # Setup error aggregation
    self.error_log = self.log_dir / 'errors.log'
    self.status_file = self.log_dir / 'status.json'
    
    # Track if we should finish after current jobs
    self.finish_after_current = False
    
    logger.info(f"Launcher initialized for SLURM job {self.slurm_job_id} on {self.node_name}")

# Add method to get total memory
def _get_total_memory(self) -> int:
    """Get total system memory in MB."""
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    return int(line.split()[1]) // 1024  # KB to MB
    except:
        return 32768  # Default 32GB

# Update _spawn_worker to include resource limits and unique names
def _spawn_worker(self, worker_id: str, gpu_id: Optional[int]) -> None:
    """Spawn a single worker process with resource limits.
    
    Args:
        worker_id: Unique worker identifier  
        gpu_id: GPU to assign (None for CPU mode)
    """
    # Include SLURM job ID in worker name for uniqueness
    full_worker_id = f"slurm{self.slurm_job_id}_{self.node_name}_gpu{gpu_id}_w{worker_id.split('_')[-1]}"
    
    # Calculate memory limit per worker
    gpu_count = len(self.discover_gpus()) or 1
    memory_per_worker_mb = self.total_memory_mb // gpu_count // self.workers_per_gpu
    
    # Build command with log file
    worker_log = self.worker_log_dir / f"{full_worker_id}.log"
    cmd = [
        sys.executable,
        '-m', 'dr_exp.cli',
        '--base-path', str(self.job_db.base_path),
        '--experiment', self.job_db.experiment_name,
        'worker',
        '--worker-id', full_worker_id,
        '--sync',
        '--log-file', str(worker_log),
    ]
    
    # Setup environment with resource limits
    env = os.environ.copy()
    if gpu_id is not None:
        env['CUDA_VISIBLE_DEVICES'] = str(gpu_id)
    env['WORKER_MEMORY_LIMIT_MB'] = str(memory_per_worker_mb)
    
    # Apply memory limit via ulimit wrapper
    wrapped_cmd = [
        'bash', '-c',
        f"ulimit -v {memory_per_worker_mb * 1024}; exec {' '.join(cmd)}"
    ]
    
    # Store config for restart
    self.worker_configs[full_worker_id] = {
        'cmd': wrapped_cmd,
        'env': env,
        'gpu_id': gpu_id,
        'log_file': worker_log,
    }
    
    # Spawn worker
    logger.info(f"Spawning worker {full_worker_id} on GPU {gpu_id} with {memory_per_worker_mb}MB memory")
    proc = subprocess.Popen(
        wrapped_cmd,
        env=env,
        stdout=open(worker_log, 'a'),
        stderr=subprocess.STDOUT,
    )
    self.workers[full_worker_id] = proc

# Add control file checking
def check_control_file(self) -> None:
    """Check for control commands."""
    if not self.control_file.exists():
        return
        
    try:
        with open(self.control_file, 'r') as f:
            command = f.read().strip()
        
        logger.info(f"Control command received: {command}")
        
        if command == "finish_current":
            self.finish_after_current = True
            logger.info("Will stop after current jobs complete")
            # Don't delete file yet - remove when actually stopping
            
        elif command == "stop_now":
            logger.info("Immediate stop requested")
            self.shutdown_requested = True
            self.control_file.unlink()
            
    except Exception as e:
        logger.error(f"Error reading control file: {e}")

# Add error aggregation
def aggregate_errors(self) -> None:
    """Aggregate recent errors from all workers."""
    errors_found = []
    
    for worker_id, config in self.worker_configs.items():
        log_file = config.get('log_file')
        if not log_file or not Path(log_file).exists():
            continue
            
        # Check for errors in last 100 lines
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                for i, line in enumerate(lines[-100:]):
                    if 'ERROR' in line or 'Traceback' in line:
                        # Capture error context
                        start = max(0, len(lines) - 100 + i - 5)
                        end = min(len(lines), len(lines) - 100 + i + 10)
                        context = lines[start:end]
                        errors_found.append({
                            'worker': worker_id,
                            'timestamp': datetime.now(UTC).isoformat(),
                            'context': ''.join(context)
                        })
                        break
        except Exception as e:
            logger.debug(f"Could not read log for {worker_id}: {e}")
    
    # Write aggregated errors
    if errors_found:
        with open(self.error_log, 'a') as f:
            for error in errors_found:
                f.write(f"\n=== Error from {error['worker']} at {error['timestamp']} ===\n")
                f.write(error['context'])
                f.write("\n")

# Update status tracking
def write_status(self) -> None:
    """Write current status to JSON file."""
    # Collect worker states
    worker_states = {}
    for worker_id, proc in self.workers.items():
        worker_states[worker_id] = {
            'alive': proc.poll() is None,
            'pid': proc.pid,
            'return_code': proc.returncode,
        }
    
    # Job statistics
    job_stats = {
        'queued': len(self.job_db.list_jobs(status='queued', limit=1000)),
        'running': len(self.job_db.list_jobs(status='running')),
        'completed': len(self.job_db.list_jobs(status='completed', limit=10000)),
        'failed': len(self.job_db.list_jobs(status='failed', limit=1000)),
    }
    
    status = {
        'slurm_job_id': self.slurm_job_id,
        'node': self.node_name,
        'started_at': datetime.fromtimestamp(self.start_time, UTC).isoformat(),
        'last_updated': datetime.now(UTC).isoformat(),
        'runtime_hours': (time.time() - self.start_time) / 3600,
        'workers': worker_states,
        'job_stats': job_stats,
        'finish_after_current': self.finish_after_current,
    }
    
    with open(self.status_file, 'w') as f:
        json.dump(status, f, indent=2)

# Update monitor_workers to check finish_after_current
def monitor_workers(self) -> None:
    """Check worker health and restart if needed."""
    dead_workers = []
    
    for worker_id, proc in self.workers.items():
        if proc.poll() is not None:
            dead_workers.append(worker_id)
            logger.warning(f"Worker {worker_id} died with code {proc.returncode}")
    
    # Check if we should stop after current jobs
    if self.finish_after_current:
        running_jobs = self.job_db.list_jobs(status="running")
        if not running_jobs:
            logger.info("No running jobs and finish_after_current set, shutting down")
            self.shutdown_requested = True
            if self.control_file.exists():
                self.control_file.unlink()
            return
    
    # Restart dead workers if needed
    if dead_workers and not self.shutdown_requested and not self.finish_after_current:
        # ... existing restart logic ...

# Update main loop to include new features
def run(self) -> None:
    """Main launcher loop with SLURM enhancements."""
    logger.info(f"Starting SLURM launcher for job {self.slurm_job_id}")
    logger.info(f"Logs directory: {self.log_dir}")
    logger.info(f"Control file: {self.control_file}")
    
    # Write initial status
    self.write_status()
    
    # Initial spawn
    self.spawn_workers()
    
    # Intervals
    last_status_log = time.time()
    last_recovery = time.time()
    last_error_check = time.time()
    last_control_check = time.time()
    
    status_interval = 300      # 5 minutes
    recovery_interval = 600    # 10 minutes  
    error_interval = 60        # 1 minute
    control_interval = 5       # 5 seconds
    
    # Main monitoring loop
    while not self.shutdown_requested and not self.exceeded_runtime():
        # Check control file frequently
        if time.time() - last_control_check > control_interval:
            self.check_control_file()
            last_control_check = time.time()
        
        # Monitor and restart workers
        self.monitor_workers()
        
        # Periodic status log
        if time.time() - last_status_log > status_interval:
            self.log_status()
            self.write_status()
            last_status_log = time.time()
        
        # Periodic stale job recovery
        if time.time() - last_recovery > recovery_interval:
            self.recover_stale_jobs()
            last_recovery = time.time()
        
        # Periodic error aggregation
        if time.time() - last_error_check > error_interval:
            self.aggregate_errors()
            last_error_check = time.time()
        
        # Sleep briefly
        time.sleep(5)
    
    # ... rest of shutdown logic ...
```

### Step 2.5.2: Create Enhanced SLURM Script

Create `scripts/dr_exp_slurm.sbatch`:

```bash
#!/bin/bash
#SBATCH --job-name=dr_exp_workers
#SBATCH --time=47:00:00
#SBATCH --nodes=1
#SBATCH --gpus-per-node=3
#SBATCH --cpus-per-task=8
#SBATCH --mem=192G

# Parameters from environment or defaults
BASE_PATH=${BASE_PATH:-/scratch/users/$USER/experiments}
EXPERIMENT=${EXPERIMENT:-default_experiment}
WORKERS_PER_GPU=${WORKERS_PER_GPU:-2}

# Create log directory for this SLURM job
LOG_DIR="$BASE_PATH/$EXPERIMENT/logs/slurm_${SLURM_JOB_ID}"
mkdir -p "$LOG_DIR/workers"
mkdir -p "$BASE_PATH/$EXPERIMENT/control"

# Redirect SLURM output
SLURM_LOG_DIR="$BASE_PATH/$EXPERIMENT/slurm_logs"
mkdir -p "$SLURM_LOG_DIR"
exec &> >(tee -a "$SLURM_LOG_DIR/slurm-${SLURM_JOB_ID}.out")

# Log startup info
echo "========================================"
echo "DR_EXP SLURM Job Starting"
echo "========================================"
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURMD_NODENAME"
echo "Time: $(date)"
echo "Base path: $BASE_PATH"
echo "Experiment: $EXPERIMENT"
echo "Workers per GPU: $WORKERS_PER_GPU"
echo "Allocated GPUs: $SLURM_GPUS_PER_NODE"
echo "Allocated Memory: $SLURM_MEM_PER_NODE MB"
echo "Log directory: $LOG_DIR"
echo "========================================"

# Setup Python environment (adjust as needed)
module load python/3.10
source /path/to/venv/bin/activate

# Optional: Setup CUDA MPS for better GPU sharing
export CUDA_MPS_PIPE_DIRECTORY="/tmp/nvidia-mps-${SLURM_JOB_ID}"
export CUDA_MPS_LOG_DIRECTORY="/tmp/nvidia-log-${SLURM_JOB_ID}"
mkdir -p "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"

cleanup() {
    echo "Cleaning up..."
    echo quit | nvidia-cuda-mps-control 2>/dev/null || true
    rm -rf "$CUDA_MPS_PIPE_DIRECTORY" "$CUDA_MPS_LOG_DIRECTORY"
}
trap cleanup EXIT

# Start CUDA MPS daemon
nvidia-cuda-mps-control -d

# Start launcher with enhanced logging
dr_exp --base-path "$BASE_PATH" \
       --experiment "$EXPERIMENT" \
       launcher \
       --workers-per-gpu "$WORKERS_PER_GPU" \
       --slurm-job-id "$SLURM_JOB_ID" \
       --node-name "$SLURMD_NODENAME" \
       --total-memory-mb "$SLURM_MEM_PER_NODE" \
       --log-dir "$LOG_DIR" \
       2>&1 | tee -a "$LOG_DIR/launcher.log"

echo "SLURM job completed at $(date)"
```

### Step 2.5.3: Add CLI Commands for SLURM Control

Add to `src/dr_exp/cli.py`:

```python
@cli.group()
def slurm():
    """SLURM job management commands."""
    pass

@slurm.command()
@click.pass_obj
def status(db):
    """Show status of all SLURM jobs for this experiment."""
    logs_dir = db.experiment_path / 'logs'
    if not logs_dir.exists():
        click.echo("No SLURM jobs found")
        return
    
    slurm_dirs = sorted([d for d in logs_dir.iterdir() if d.name.startswith('slurm_')])
    
    for slurm_dir in slurm_dirs:
        job_id = slurm_dir.name.replace('slurm_', '')
        status_file = slurm_dir / 'status.json'
        
        if status_file.exists():
            with open(status_file) as f:
                status = json.load(f)
            
            # Count alive workers
            alive = sum(1 for w in status['workers'].values() if w['alive'])
            total = len(status['workers'])
            
            runtime = status.get('runtime_hours', 0)
            job_stats = status.get('job_stats', {})
            
            click.echo(f"\nSLURM Job {job_id}")
            click.echo(f"  Node: {status.get('node', 'unknown')}")
            click.echo(f"  Runtime: {runtime:.1f} hours")
            click.echo(f"  Workers: {alive}/{total} alive")
            click.echo(f"  Jobs: {job_stats.get('running', 0)} running, "
                      f"{job_stats.get('queued', 0)} queued, "
                      f"{job_stats.get('completed', 0)} completed")
            
            if status.get('finish_after_current'):
                click.echo("  Status: FINISHING AFTER CURRENT JOBS")
        else:
            click.echo(f"\nSLURM Job {job_id}: No status available")

@slurm.command()
@click.argument('job_id')
@click.option('--finish-current', is_flag=True, help='Finish current jobs then stop')
@click.option('--stop-now', is_flag=True, help='Stop immediately')
@click.pass_obj  
def control(db, job_id, finish_current, stop_now):
    """Send control commands to a SLURM job."""
    control_file = db.experiment_path / 'control' / f'slurm_{job_id}.control'
    
    if finish_current:
        control_file.parent.mkdir(exist_ok=True)
        control_file.write_text('finish_current')
        click.echo(f"Sent finish_current command to SLURM job {job_id}")
    elif stop_now:
        control_file.parent.mkdir(exist_ok=True)
        control_file.write_text('stop_now')
        click.echo(f"Sent stop_now command to SLURM job {job_id}")
    else:
        click.echo("Specify either --finish-current or --stop-now")

@slurm.command()
@click.argument('job_id')
@click.option('--tail', default=50, help='Number of lines to show')
@click.pass_obj
def errors(db, job_id, tail):
    """View aggregated errors from a SLURM job."""
    error_log = db.experiment_path / 'logs' / f'slurm_{job_id}' / 'errors.log'
    
    if not error_log.exists():
        click.echo(f"No errors found for SLURM job {job_id}")
        return
    
    # Show last N lines
    with open(error_log) as f:
        lines = f.readlines()
        for line in lines[-tail:]:
            click.echo(line.rstrip())

@slurm.command()  
@click.argument('job_id')
@click.option('--worker', help='Specific worker ID')
@click.option('--tail', default=50, help='Number of lines to show')
@click.pass_obj
def logs(db, job_id, worker, tail):
    """View logs from a SLURM job."""
    if worker:
        # Specific worker log
        log_file = db.experiment_path / 'logs' / f'slurm_{job_id}' / 'workers' / f'{worker}.log'
    else:
        # Launcher log
        log_file = db.experiment_path / 'logs' / f'slurm_{job_id}' / 'launcher.log'
    
    if not log_file.exists():
        click.echo(f"Log file not found: {log_file}")
        return
    
    # Show last N lines
    with open(log_file) as f:
        lines = f.readlines()
        for line in lines[-tail:]:
            click.echo(line.rstrip())
```

### Step 2.5.4: Usage Examples

```bash
# Submit SLURM job with custom parameters
sbatch --export=BASE_PATH=/scratch/jane/exp,EXPERIMENT=resnet,WORKERS_PER_GPU=3 scripts/dr_exp_slurm.sbatch

# Check status of all SLURM jobs
dr_exp --base-path /scratch/jane/exp --experiment resnet slurm status

# View errors from specific job
dr_exp --base-path /scratch/jane/exp --experiment resnet slurm errors 123456

# Gracefully stop after current jobs
dr_exp --base-path /scratch/jane/exp --experiment resnet slurm control 123456 --finish-current

# View specific worker log
dr_exp --base-path /scratch/jane/exp --experiment resnet slurm logs 123456 --worker slurm123456_node042_gpu0_w1
```

### Key Benefits

1. **No conflicts**: Worker IDs include SLURM job ID
2. **Easy debugging**: All logs centralized under `logs/slurm_{job_id}/`
3. **Resource limits**: Memory properly divided among workers
4. **Graceful control**: Can stop cleanly via control files
5. **Error visibility**: Aggregated error log for quick debugging
6. **Multi-job support**: Run multiple SLURM jobs safely

## Next Phase

Once worker tests pass, proceed to Phase 3: Supabase Integration.
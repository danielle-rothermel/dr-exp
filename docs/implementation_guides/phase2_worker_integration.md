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

## Step 7: Create CLI Interface

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
    """Run a worker process."""
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
                click.echo("No jobs available, exiting")
                break
            
            jobs_run += 1
            click.echo(f"Completed job {job_id} ({jobs_run} total)")
            
            if max_jobs > 0 and jobs_run >= max_jobs:
                click.echo(f"Reached max jobs limit ({max_jobs})")
                break
    finally:
        worker.stop()
        click.echo(f"Worker {worker_id} stopped after {jobs_run} jobs")


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

## Step 8: Run Tests

```bash
# Run worker test
python test_worker.py

# Test CLI (after installation)
dr_exp --base-path /tmp/test --experiment cli_test submit test_config.yaml
dr_exp --base-path /tmp/test --experiment cli_test list
dr_exp --base-path /tmp/test --experiment cli_test worker --worker-id test_worker --max-jobs 1
```

## Validation Checklist

Before proceeding to Phase 3:

- [ ] Worker test passes successfully
- [ ] Background sync thread starts and processes items
- [ ] Job outputs are created in correct locations
- [ ] Heartbeat updates work during job execution
- [ ] No references to old worker code remain:
  ```bash
  grep -r "run_worker\|JobExecutor\|HeartbeatManager" src/
  ```

## Common Mistakes to Avoid

1. **DO NOT** implement actual Supabase uploads yet - just queue them
2. **DO NOT** add complex retry logic - keep it simple
3. **DO NOT** create separate sync services - embed in worker
4. **DO NOT** add configuration files - use constructor parameters
5. **DO NOT** implement distributed locking - single worker per job

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
- Run `dr_exp recover` periodically (e.g., in cron) to reset stale jobs
- Workers can be killed safely - jobs will return to queue

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
- Check for stale heartbeats: jobs running > 10 minutes with old heartbeat
- Monitor sync_queue size: large backlog indicates sync issues
- Watch for repeated failures: same job failing multiple times

### Running at Scale
```bash
# Start multiple workers per node (e.g., 2 per GPU)
for i in {0..3}; do
    dr_exp --base-path /scratch/exp --experiment my_exp worker \
        --worker-id node1_gpu${i/2}_worker${i} &
done

# Cron job for automatic recovery
*/5 * * * * dr_exp --base-path /scratch/exp --experiment my_exp recover
```

## Next Phase

Once worker tests pass, proceed to Phase 3: Supabase Integration.
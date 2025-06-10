"""Base worker implementation for job execution."""

import os
import time
import threading
import traceback
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from datetime import datetime

import hydra
from omegaconf import OmegaConf

from ..core.job_db import JobDB
from ..sync.queue import SyncQueue, SyncItem


class Worker:
    """Base worker that executes jobs from JobDB with background sync."""

    def __init__(
        self,
        job_db: JobDB,
        worker_id: str,
        working_dir: Optional[str] = None,
        sync_interval: int = 30,
        heartbeat_interval: int = 60,
        sync_enabled: bool = True,
    ):
        """Initialize worker.

        Args:
            job_db: JobDB instance to get jobs from
            worker_id: Unique identifier for this worker
            working_dir: Directory to run jobs in (defaults to current dir)
            sync_interval: Seconds between sync attempts
            heartbeat_interval: Seconds between heartbeats
            sync_enabled: Whether to enable background sync
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

        # Sync function (to be set by subclass or externally)
        self.sync_fn: Optional[Callable[[SyncItem], None]] = None

    def _sync_worker(self) -> None:
        """Background thread that processes sync queue."""
        print(f"[{self.worker_id}] Sync thread started")

        while not self.should_stop.wait(self.sync_interval):
            try:
                if self.sync_fn:
                    # Process a batch of items
                    results = self.sync_queue.process_queue(self.sync_fn, batch_size=5)

                    if results["success"] > 0 or results["failed"] > 0:
                        print(
                            f"[{self.worker_id}] Sync: {results['success']} success, "
                            f"{results['failed']} failed, {results['skipped']} pending"
                        )
                else:
                    # No sync function configured - just track items
                    stats = self.sync_queue.get_stats()
                    if stats["pending"] > 0:
                        print(
                            f"[{self.worker_id}] Sync pending: {stats['pending']} items"
                        )

            except Exception as e:
                print(f"[{self.worker_id}] Sync error: {e}")

        print(f"[{self.worker_id}] Sync thread stopped")

    def _heartbeat_worker(self) -> None:
        """Background thread that sends heartbeats for current job."""
        print(f"[{self.worker_id}] Heartbeat thread started")

        while not self.should_stop.wait(self.heartbeat_interval):
            try:
                if self.current_job_id:
                    success = self.job_db.heartbeat(self.current_job_id)
                    if not success:
                        print(
                            f"[{self.worker_id}] Failed to heartbeat job {self.current_job_id}"
                        )

            except Exception as e:
                print(f"[{self.worker_id}] Heartbeat error: {e}")

        print(f"[{self.worker_id}] Heartbeat thread stopped")

    def start_background_threads(self) -> None:
        """Start background sync and heartbeat threads."""
        if self.sync_enabled and not self.sync_thread:
            self.sync_thread = threading.Thread(
                target=self._sync_worker, name=f"{self.worker_id}_sync"
            )
            self.sync_thread.daemon = True
            self.sync_thread.start()

        if not self.heartbeat_thread:
            self.heartbeat_thread = threading.Thread(
                target=self._heartbeat_worker, name=f"{self.worker_id}_heartbeat"
            )
            self.heartbeat_thread.daemon = True
            self.heartbeat_thread.start()

    def stop_background_threads(self) -> None:
        """Stop background threads gracefully."""
        self.should_stop.set()

        # Wait for threads to finish
        if self.sync_thread and self.sync_thread.is_alive():
            self.sync_thread.join(timeout=5)

        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=5)

    def add_artifact_to_sync(
        self,
        job_id: str,
        file_path: str,
        file_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a file to the sync queue.

        Args:
            job_id: Job that created this file
            file_path: Path to file
            file_type: Type of file (metrics, logs, model, etc.)
            metadata: Optional metadata
        """
        if not self.sync_enabled:
            return

        # Create sync item
        sync_item = SyncItem(
            id=f"{job_id}_{file_type}_{int(time.time() * 1000)}",
            job_id=job_id,
            file_path=file_path,
            file_type=file_type,
            metadata=metadata or {},
            created_at=datetime.utcnow().isoformat(),
        )

        # Add to queue
        self.sync_queue.add_item(sync_item)

    def execute_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single job using Hydra.

        Args:
            job: Job data from JobDB

        Returns:
            Result dict with status and optional error
        """
        job_id = job["id"]
        config = job["config"]

        # Create job-specific working directory
        job_dir = self.working_dir / f"job_{job_id}"
        job_dir.mkdir(parents=True, exist_ok=True)

        # Change to job directory
        original_cwd = Path.cwd()
        os.chdir(job_dir)

        try:
            # Convert config to OmegaConf
            if isinstance(config, dict):
                config = OmegaConf.create(config)

            # Inject job metadata into config
            config.job_id = job_id
            config.worker_id = self.worker_id
            config.storage_path = str(self.job_db.get_storage_path(job_id))

            # Ensure storage directory exists
            storage_path = Path(config.storage_path)
            storage_path.mkdir(parents=True, exist_ok=True)

            # Execute using Hydra's call mechanism
            print(
                f"[{self.worker_id}] Executing job {job_id} with _target_={config._target_}"
            )
            result = hydra.utils.call(config)

            # Add any created artifacts to sync queue
            for file_path in storage_path.iterdir():
                if file_path.is_file():
                    # Determine file type from extension/name
                    if "metrics" in file_path.name or file_path.suffix == ".jsonl":
                        file_type = "metrics"
                    elif "model" in file_path.name or file_path.suffix in [
                        ".pt",
                        ".pth",
                    ]:
                        file_type = "model"
                    else:
                        file_type = "other"

                    self.add_artifact_to_sync(
                        job_id, str(file_path), file_type, {"filename": file_path.name}
                    )

            # Job succeeded
            return {
                "status": "success",
                "result": result,
                "completed_at": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            # Job failed
            error_msg = f"{type(e).__name__}: {str(e)}"
            tb = traceback.format_exc()

            print(f"[{self.worker_id}] Job {job_id} failed: {error_msg}")
            print(f"Traceback:\n{tb}")

            # Save error to file
            error_file = storage_path / "error.txt"
            error_file.write_text(f"{error_msg}\n\n{tb}")
            self.add_artifact_to_sync(job_id, str(error_file), "error")

            return {
                "status": "failed",
                "error": error_msg,
                "traceback": tb,
                "completed_at": datetime.utcnow().isoformat(),
            }

        finally:
            # Always return to original directory
            os.chdir(original_cwd)

    def run_one_job(self) -> str:
        """Claim and execute one job.

        Returns:
            Status: 'completed', 'failed', or 'no_job'
        """
        # Try to claim a job
        job = self.job_db.claim_next_job(self.worker_id)

        if not job:
            print(f"[{self.worker_id}] No jobs available")
            return "no_job"

        self.current_job_id = job["id"]
        print(
            f"[{self.worker_id}] Claimed job {job['id']} (priority={job['priority']})"
        )

        # Send initial heartbeat
        self.job_db.heartbeat(job["id"])

        # Execute the job
        result = self.execute_job(job)

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

        self.current_job_id = None
        return status

    def run(self, max_jobs: Optional[int] = None) -> Dict[str, int]:
        """Run worker until no more jobs or max_jobs reached.

        Args:
            max_jobs: Maximum number of jobs to execute (None = unlimited)

        Returns:
            Dict with counts of completed, failed, and total jobs
        """
        stats = {"completed": 0, "failed": 0, "total": 0}

        print(f"[{self.worker_id}] Worker started")

        # Start background threads
        self.start_background_threads()

        try:
            while max_jobs is None or stats["total"] < max_jobs:
                status = self.run_one_job()

                if status == "no_job":
                    break
                elif status == "completed":
                    stats["completed"] += 1
                elif status == "failed":
                    stats["failed"] += 1

                stats["total"] += 1
        finally:
            # Stop background threads
            self.stop_background_threads()

        print(f"[{self.worker_id}] Worker finished: {stats}")
        return stats

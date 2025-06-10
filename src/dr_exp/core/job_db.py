"""Simple file-based job database for ML experiments."""

import fcntl
import json
import time
import uuid
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class JobDB:
    """File-based job database with priority queue."""

    def __init__(self, base_path: str, experiment_name: str, validate: bool = True):
        """Initialize JobDB with base path and experiment name.

        Args:
            base_path: Base directory for all experiments (e.g., /scratch/users/jane/experiments)
            experiment_name: Name of this experiment (e.g., resnet_sweep)
            validate: Whether to validate directory structure exists
        """
        # Validate inputs
        assert base_path, "base_path cannot be empty"
        assert experiment_name, "experiment_name cannot be empty"
        assert "/" not in experiment_name, "experiment_name cannot contain '/'"

        self.base_path = Path(base_path)
        self.experiment_name = experiment_name
        self.experiment_path = self.base_path / experiment_name

        # Define directory structure
        self.jobs_dir = self.experiment_path / "jobs"
        self.storage_dir = self.experiment_path / "storage"
        self.sync_queue_dir = self.experiment_path / "sync_queue"
        self.logs_dir = self.experiment_path / "logs"
        self.control_dir = self.experiment_path / "control"

        if validate:
            # Check that experiment is initialized
            required_dirs = [
                self.jobs_dir,
                self.storage_dir,
                self.sync_queue_dir,
                self.logs_dir,
                self.control_dir,
            ]

            missing = [d for d in required_dirs if not d.exists()]
            if missing:
                missing_names = [d.name for d in missing]
                raise RuntimeError(
                    f"Experiment not initialized. Missing directories: {missing_names}\n"
                    f"Run: dr_exp --base-path {base_path} --experiment {experiment_name} init"
                )
        else:
            # Create directories if they don't exist (for init command)
            for dir_path in [
                self.jobs_dir,
                self.storage_dir,
                self.sync_queue_dir,
                self.logs_dir,
                self.control_dir,
            ]:
                dir_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"JobDB initialized for experiment '{experiment_name}' at {self.experiment_path}"
        )

    def create_job(self, config: Dict[str, Any], priority: int = 100) -> str:
        """Create a new job with given config and priority.

        Args:
            config: Job configuration dict (must include _target_ field)
            priority: Job priority (0-1000, higher runs first)

        Returns:
            job_id: Unique ID for the created job
        """
        # Validate priority
        assert 0 <= priority <= 1000, f"Priority must be 0-1000, got {priority}"

        # Validate _target_ exists
        assert "_target_" in config, "Config must include _target_ field"

        # Validate target is importable
        target = config["_target_"]
        module_path, func_name = target.rsplit(".", 1)
        try:
            import importlib

            importlib.import_module(module_path)
        except ImportError as e:
            assert False, f"Cannot import target module {module_path}: {e}"

        # Create job metadata
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "experiment_name": self.experiment_name,
            "config": config,
            "priority": priority,
            "status": "queued",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
            "attempts": 0,
            "worker_id": None,
            "error": None,
            "completed_at": None,
        }

        # Write to file
        job_path = self.jobs_dir / f"{job_id}.json"
        with open(job_path, "w") as f:
            json.dump(job_data, f, indent=2)

        logger.info(f"Created job {job_id} with priority {priority}")
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a job by ID.

        Args:
            job_id: Job ID to retrieve

        Returns:
            Job data dict or None if not found
        """
        job_path = self.jobs_dir / f"{job_id}.json"
        if not job_path.exists():
            return None

        with open(job_path, "r") as f:
            job_data: Dict[str, Any] = json.load(f)
            return job_data

    def get_storage_path(self, job_id: str) -> Path:
        """Get the storage path for a job's artifacts.

        Args:
            job_id: Job ID

        Returns:
            Path object for job's storage directory
        """
        return self.storage_dir / f"run_{job_id}"

    def _list_job_files(self) -> List[Path]:
        """List all job files sorted by priority (highest first) then creation time.

        Returns:
            List of job file paths
        """
        job_files = []
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file, "r") as f:
                    job_data = json.load(f)
                    # Only include queued jobs
                    if job_data.get("status") == "queued":
                        job_files.append(
                            (
                                job_file,
                                job_data.get("priority", 0),
                                job_data.get("created_at", ""),
                            )
                        )
            except (json.JSONDecodeError, IOError):
                # Skip corrupted files
                continue

        # Sort by priority (descending) then created_at (ascending)
        job_files.sort(key=lambda x: (-x[1], x[2]))
        return [f[0] for f in job_files]

    def claim_next_job(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Claim the next available job atomically.

        Uses file locking to ensure only one worker can claim a job.

        Args:
            worker_id: ID of the worker claiming the job

        Returns:
            Job data dict if claimed, None if no jobs available
        """
        # Get sorted list of queued jobs
        job_files = self._list_job_files()

        for job_file in job_files:
            try:
                # Open file with exclusive lock
                with open(job_file, "r+") as f:
                    # Try to acquire exclusive lock (non-blocking)
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                    try:
                        # Read current data
                        f.seek(0)
                        job_data: Dict[str, Any] = json.load(f)

                        # Double-check status (could have changed)
                        if job_data.get("status") != "queued":
                            continue

                        # Claim the job
                        job_data["status"] = "running"
                        job_data["worker_id"] = worker_id
                        job_data["started_at"] = datetime.now(UTC).isoformat()
                        job_data["updated_at"] = datetime.now(UTC).isoformat()
                        job_data["attempts"] = job_data.get("attempts", 0) + 1

                        # Write back atomically
                        f.seek(0)
                        f.truncate()
                        json.dump(job_data, f, indent=2)
                        f.flush()

                        # Release lock happens automatically when file closes
                        return job_data

                    finally:
                        # Ensure lock is released even if error occurs
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            except (IOError, BlockingIOError):
                # Lock is held by another process, try next job
                continue
            except Exception:
                # Skip corrupted files
                continue

        # No jobs available
        return None

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update a job atomically.

        Args:
            job_id: Job to update
            updates: Fields to update

        Returns:
            True if updated, False if job not found
        """
        job_path = self.jobs_dir / f"{job_id}.json"
        if not job_path.exists():
            return False

        try:
            with open(job_path, "r+") as f:
                # Acquire exclusive lock
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)

                try:
                    # Read current data
                    f.seek(0)
                    job_data = json.load(f)

                    # Apply updates
                    job_data.update(updates)
                    job_data["updated_at"] = datetime.now(UTC).isoformat()

                    # Write back atomically
                    f.seek(0)
                    f.truncate()
                    json.dump(job_data, f, indent=2)
                    f.flush()

                    return True

                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        except Exception:
            return False

    def complete_job(
        self, job_id: str, metrics: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Mark a job as completed successfully.

        Args:
            job_id: Job to complete
            metrics: Optional final metrics to store

        Returns:
            True if updated, False if job not found
        """
        updates: Dict[str, Any] = {
            "status": "completed",
            "completed_at": datetime.now(UTC).isoformat(),
            "error": None,
        }
        if metrics:
            updates["final_metrics"] = metrics

        return self.update_job(job_id, updates)

    def fail_job(self, job_id: str, error: str) -> bool:
        """Mark a job as failed.

        Args:
            job_id: Job to fail
            error: Error message

        Returns:
            True if updated, False if job not found
        """
        updates = {
            "status": "failed",
            "completed_at": datetime.now(UTC).isoformat(),
            "error": error,
        }

        return self.update_job(job_id, updates)

    def heartbeat(self, job_id: str) -> bool:
        """Update job heartbeat timestamp.

        Workers should call this periodically to indicate they're alive.

        Args:
            job_id: Job to heartbeat

        Returns:
            True if updated, False if job not found
        """
        updates = {"last_heartbeat": datetime.now(UTC).isoformat()}

        return self.update_job(job_id, updates)

    def list_jobs(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all jobs, optionally filtered by status.

        Args:
            status: Optional status filter (queued, running, completed, failed)

        Returns:
            List of job data dicts
        """
        jobs = []

        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file, "r") as f:
                    job_data = json.load(f)

                    if status is None or job_data.get("status") == status:
                        jobs.append(job_data)

            except (json.JSONDecodeError, IOError):
                # Skip corrupted files
                continue

        # Sort by creation time
        jobs.sort(key=lambda x: x.get("created_at", ""))
        return jobs

    def get_sync_queue_path(self) -> Path:
        """Get path to sync queue directory.

        Returns:
            Path to sync queue directory
        """
        return self.sync_queue_dir

    def add_to_sync_queue(
        self,
        job_id: str,
        file_path: str,
        file_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Add a file to the sync queue.

        Args:
            job_id: Job that created this file
            file_path: Path to file to sync
            file_type: Type of file (metrics, logs, model, etc.)
            metadata: Optional metadata about the file

        Returns:
            Sync item ID
        """
        sync_id = str(uuid.uuid4())
        sync_item = {
            "id": sync_id,
            "job_id": job_id,
            "file_path": file_path,
            "file_type": file_type,
            "metadata": metadata or {},
            "created_at": datetime.now(UTC).isoformat(),
            "status": "pending",
            "attempts": 0,
            "error": None,
        }

        # Write to sync queue with timestamp prefix for ordering
        timestamp = int(time.time() * 1000000)  # Microseconds
        sync_file = self.sync_queue_dir / f"{timestamp}_{sync_id}.json"

        with open(sync_file, "w") as f:
            json.dump(sync_item, f, indent=2)

        return sync_id

    def get_experiment_info(self) -> Dict[str, Any]:
        """Get information about this experiment.

        Returns:
            Dict with experiment metadata
        """
        jobs = self.list_jobs()

        # Count by status
        status_counts: Dict[str, int] = {}
        for job in jobs:
            status = job.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "experiment_name": self.experiment_name,
            "base_path": str(self.base_path),
            "experiment_path": str(self.experiment_path),
            "total_jobs": len(jobs),
            "status_counts": status_counts,
            "created_at": min(
                (j.get("created_at") for j in jobs if j.get("created_at")), default=None
            ),
        }

    def mark_job_failed(self, job_id: str, reason: str) -> bool:
        """Mark a running job as failed (kill it).

        Args:
            job_id: Job identifier
            reason: Reason for marking as failed

        Returns:
            True if job was marked failed, False if not found or not running
        """
        job = self.get_job(job_id)
        if job and job["status"] == "running":
            return self.update_job(
                job_id,
                {
                    "status": "failed",
                    "error": f"Killed: {reason}",
                    "completed_at": datetime.now(UTC).isoformat(),
                },
            )
        return False

    def recover_stale_jobs(self, heartbeat_timeout: int = 300) -> List[str]:
        """Reset jobs with stale heartbeats back to queued.

        Args:
            heartbeat_timeout: Seconds before considering heartbeat stale

        Returns:
            List of recovered job IDs
        """
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(seconds=heartbeat_timeout)
        recovered = []

        for job_file in self.jobs_dir.glob("*.json"):
            with open(job_file, "r") as f:
                job = json.load(f)

            if job["status"] == "running":
                heartbeat = job.get("last_heartbeat")
                if not heartbeat or datetime.fromisoformat(heartbeat) < cutoff:
                    # Reset to queued
                    self.update_job(
                        job["id"],
                        {
                            "status": "queued",
                            "worker_id": None,
                            "started_at": None,
                            "last_heartbeat": None,
                            "error": "Worker died - job reset to queue",
                        },
                    )
                    recovered.append(job["id"])

        return recovered

    def boost_priority(self, job_ids: List[str], new_priority: int) -> int:
        """Boost priority of multiple jobs.

        Args:
            job_ids: List of job IDs to boost
            new_priority: New priority value (0-1000)

        Returns:
            Number of jobs updated
        """
        assert 0 <= new_priority <= 1000, f"Priority must be 0-1000, got {new_priority}"

        updated = 0
        for job_id in job_ids:
            job = self.get_job(job_id)
            if job and job["status"] == "queued":
                self.update_job(job_id, {"priority": new_priority})
                updated += 1
                logger.info(f"Boosted job {job_id} to priority {new_priority}")

        return updated

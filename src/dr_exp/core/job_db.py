"""Simple file-based job database for ML experiments."""

import fcntl
import json
import random
import time
import uuid
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Priority constants
MAX_PRIORITY = 1000
MIN_PRIORITY = 0


class JobDB:
    """File-based job database with priority queue."""

    def __init__(
        self, base_path: str, experiment_name: str, validate: bool = True
    ) -> None:
        """Initialize JobDB with base path and experiment name.

        Args:
            base_path: Base directory for all experiments
                (e.g., /scratch/users/jane/experiments)
            experiment_name: Name of this experiment (e.g., resnet_sweep)
            validate: Whether to validate directory structure exists
        """
        # Validate inputs
        assert base_path, "base_path cannot be empty"
        assert experiment_name, "experiment_name cannot be empty"
        assert "/" not in experiment_name, "experiment_name cannot contain '/'"

        self.base_path = Path(base_path).resolve()
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
                    f"Experiment not initialized. "
                    f"Missing directories: {missing_names}\n"
                    f"Run: dr_exp --base-path {base_path} "
                    f"--experiment {experiment_name} init"
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

        # Remote read support (disabled by default)
        self.remote_enabled = False
        self.remote_client: Any | None = None
        self.remote_experiment_id: str | None = None

        logger.info(
            f"JobDB initialized for experiment '{experiment_name}' "
            f"at {self.experiment_path}"
        )

    def create_job(
        self,
        config: dict[str, Any],
        priority: int = 100,
        tags: list[str] | None = None,
    ) -> str:
        """Create a new job with given config and priority.

        Args:
            config: Job configuration dict (must include _target_ field)
            priority: Job priority (0-1000, higher runs first)
            tags: Optional list of tags for the job

        Returns:
            job_id: Unique ID for the created job
        """
        # Validate priority
        assert MIN_PRIORITY <= priority <= MAX_PRIORITY, (
            f"Priority must be {MIN_PRIORITY}-{MAX_PRIORITY}, got {priority}"
        )

        # Validate _target_ exists
        assert "_target_" in config, "Config must include _target_ field"

        # Validate target is importable
        target = config["_target_"]
        module_path, func_name = target.rsplit(".", 1)
        try:
            import importlib

            importlib.import_module(module_path)
        except ImportError as e:
            raise AssertionError(
                f"Cannot import target module {module_path}: {e}"
            ) from e

        # Create job metadata
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "experiment_name": self.experiment_name,
            "config": config,
            "priority": priority,
            "tags": tags or [],
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
        with job_path.open("w") as f:
            json.dump(job_data, f, indent=2)

        logger.info(f"Created job {job_id} with priority {priority}")
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Retrieve a job by ID.

        Args:
            job_id: Job ID to retrieve

        Returns:
            Job data dict or None if not found
        """
        job_path = self.jobs_dir / f"{job_id}.json"
        if not job_path.exists():
            return None

        with job_path.open() as f:
            job_data: dict[str, Any] = json.load(f)
            return job_data

    def get_storage_path(self, job_id: str) -> Path:
        """Get the storage path for a job's artifacts.

        Args:
            job_id: Job ID

        Returns:
            Path object for job's storage directory
        """
        return self.storage_dir / f"run_{job_id}"

    def _list_job_files(self) -> list[Path]:
        """List all job files sorted by priority (highest first) then creation time.

        Returns:
            List of job file paths
        """
        job_files = []
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with job_file.open() as f:
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
            except (OSError, json.JSONDecodeError):
                # Skip corrupted files
                continue

        # Sort by priority (descending) then created_at (ascending)
        job_files.sort(key=lambda x: (-x[1], x[2]))
        return [f[0] for f in job_files]

    def claim_next_job(self, worker_id: str) -> dict[str, Any] | None:
        """Claim the highest priority unclaimed job with enhanced locking."""
        # Use a lock file to ensure atomic priority scanning
        lock_file = self.jobs_dir / ".claim_lock"
        lock_file.touch(exist_ok=True)

        with lock_file.open("w") as lock_fd:
            # Exclusive lock with small random backoff to reduce contention
            max_attempts = 5
            for attempt in range(max_attempts):
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if attempt < max_attempts - 1:
                        # Using random for jitter to reduce lock contention
                        # Not cryptographic use - safe for this purpose
                        time.sleep(0.001 * random.uniform(0.5, 1.5))  # noqa: S311
                    else:
                        return None

            try:
                # Find highest priority unclaimed job, with creation time as tiebreaker
                best_job = None
                best_priority = -1
                best_created_at = None

                for job_file in self.jobs_dir.glob("*.json"):
                    if job_file.name == ".claim_lock":
                        continue

                    try:
                        with job_file.open() as f:
                            job_data = json.load(f)

                        if job_data["status"] == "queued":
                            priority = job_data["priority"]
                            created_at = job_data.get("created_at", "")

                            # Select if higher priority, or same priority but earlier creation
                            if priority > best_priority or (
                                priority == best_priority
                                and (
                                    best_created_at is None
                                    or created_at < best_created_at
                                )
                            ):
                                best_job = job_data
                                best_priority = priority
                                best_created_at = created_at

                    except (json.JSONDecodeError, KeyError):
                        continue

                if not best_job:
                    return None

                # Claim the best job
                job_file = self.jobs_dir / f"{best_job['id']}.json"

                # Re-read and update atomically
                with job_file.open() as f:
                    current_job: dict[str, Any] = json.load(f)

                # Double-check status
                if current_job["status"] != "queued":
                    return None

                # Update job
                current_job["status"] = "running"
                current_job["worker_id"] = worker_id
                current_job["started_at"] = datetime.now(UTC).isoformat()
                current_job["updated_at"] = datetime.now(UTC).isoformat()
                current_job["attempts"] = current_job.get("attempts", 0) + 1

                # Write atomically
                temp_file = job_file.with_suffix(".tmp")
                with temp_file.open("w") as f:
                    json.dump(current_job, f, indent=2)
                temp_file.replace(job_file)

                return current_job

            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)

    def update_job(self, job_id: str, updates: dict[str, Any]) -> bool:
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
            with job_path.open("r+") as f:
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

    def complete_job(self, job_id: str, metrics: dict[str, Any] | None = None) -> bool:
        """Mark a job as completed successfully.

        Args:
            job_id: Job to complete
            metrics: Optional final metrics to store

        Returns:
            True if updated, False if job not found
        """
        updates: dict[str, Any] = {
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

    def list_jobs(self, status: str | None = None) -> list[dict[str, Any]]:
        """List all jobs, optionally filtered by status.

        Args:
            status: Optional status filter (queued, running, completed, failed)

        Returns:
            List of job data dicts
        """
        jobs = []

        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with job_file.open() as f:
                    job_data = json.load(f)

                    if status is None or job_data.get("status") == status:
                        jobs.append(job_data)

            except (OSError, json.JSONDecodeError):
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
        metadata: dict[str, Any] | None = None,
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

        with sync_file.open("w") as f:
            json.dump(sync_item, f, indent=2)

        return sync_id

    def get_experiment_info(self) -> dict[str, Any]:
        """Get information about this experiment.

        Returns:
            Dict with experiment metadata
        """
        jobs = self.list_jobs()

        # Count by status
        status_counts: dict[str, int] = {}
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

    def recover_stale_jobs(self, heartbeat_timeout: int = 300) -> list[str]:
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
            with job_file.open() as f:
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

    def boost_priority(self, job_ids: list[str], new_priority: int) -> int:
        """Boost priority of multiple jobs.

        Args:
            job_ids: List of job IDs to boost
            new_priority: New priority value (0-1000)

        Returns:
            Number of jobs updated
        """
        assert MIN_PRIORITY <= new_priority <= MAX_PRIORITY, (
            f"Priority must be {MIN_PRIORITY}-{MAX_PRIORITY}, got {new_priority}"
        )

        updated = 0
        for job_id in job_ids:
            job = self.get_job(job_id)
            if job and job["status"] == "queued":
                self.update_job(job_id, {"priority": new_priority})
                updated += 1
                logger.info(f"Boosted job {job_id} to priority {new_priority}")

        return updated

    def reserve_job(self, job_id: str, worker_id: str) -> bool:
        """Reserve a specific job for a worker.

        This is used for special operations like run_one where we want to
        run a specific job immediately, bypassing the queue order.

        Args:
            job_id: Job to reserve
            worker_id: Worker that will run the job

        Returns:
            True if reserved successfully
        """
        job = self.get_job(job_id)
        if not job:
            return False

        # Only reserve if job is queued or failed
        if job["status"] not in ["queued", "failed"]:
            return False

        # Mark as reserved by updating with special fields
        return self.update_job(
            job_id,
            {
                "reserved_for": worker_id,
                "reservation_time": datetime.now(UTC).isoformat(),
            },
        )

    def claim_reserved_job(self, job_id: str, worker_id: str) -> dict[str, Any] | None:
        """Claim a previously reserved job.

        Args:
            job_id: Job to claim
            worker_id: Worker claiming the job (must match reservation)

        Returns:
            Job data if claimed successfully, None otherwise
        """
        job = self.get_job(job_id)
        if not job:
            return None

        # Check if reserved for this worker
        if job.get("reserved_for") != worker_id:
            return None

        # Check if still in claimable state
        if job["status"] not in ["queued", "failed"]:
            return None

        # Claim the job
        success = self.update_job(
            job_id,
            {
                "status": "running",
                "worker_id": worker_id,
                "started_at": datetime.now(UTC).isoformat(),
                "last_heartbeat": datetime.now(UTC).isoformat(),
                "reserved_for": None,  # Clear reservation
                "reservation_time": None,
            },
        )

        if success:
            return self.get_job(job_id)
        return None

    def enable_remote_read(
        self, supabase_url: str | None = None, supabase_key: str | None = None
    ) -> bool:
        """Enable remote read operations from Supabase.

        Args:
            supabase_url: Supabase URL (uses env var if not provided)
            supabase_key: Supabase key (uses env var if not provided)

        Returns:
            True if remote read enabled successfully
        """
        try:
            from dr_exp.sync.supabase_client import SupabaseClient

            self.remote_client = SupabaseClient(url=supabase_url, key=supabase_key)
            self.remote_experiment_id = self.remote_client.get_or_create_experiment(
                experiment_name=self.experiment_name, base_path=str(self.base_path)
            )
            self.remote_enabled = True
            return True

        except Exception as e:
            print(f"Failed to enable remote read: {e}")
            self.remote_client = None
            self.remote_experiment_id = None
            self.remote_enabled = False
            return False

    def list_jobs_remote(self, status: str | None = None) -> list[dict[str, Any]]:
        """List jobs from remote Supabase database.

        Args:
            status: Optional status filter

        Returns:
            List of job data dicts from Supabase
        """
        if not self.remote_enabled or not self.remote_client:
            return []

        try:
            return self.remote_client.get_experiment_jobs(  # type: ignore
                self.remote_experiment_id, status=status, limit=1000
            )
        except Exception as e:
            print(f"Failed to list remote jobs: {e}")
            return []

    def get_job_remote(self, job_id: str) -> dict[str, Any] | None:
        """Get a job from remote Supabase database.

        Args:
            job_id: Job ID to retrieve

        Returns:
            Job data dict or None if not found
        """
        if not self.remote_enabled or not self.remote_client:
            return None

        try:
            jobs = self.remote_client.get_experiment_jobs(  # type: ignore
                self.remote_experiment_id,
                limit=1000,  # Get more jobs to find the one we want
            )

            # Filter by ID (since we don't have direct ID query)
            for job in jobs:
                if job["id"] == job_id:
                    return job  # type: ignore

            return None

        except Exception as e:
            print(f"Failed to get remote job: {e}")
            return None

    def get_experiment_info_remote(self) -> dict[str, Any]:
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
                    "killed": stats.get("killed_jobs", 0),
                },
                "remote": True,
            }

        except Exception as e:
            print(f"Failed to get remote experiment info: {e}")
            return self.get_experiment_info()

    def download_job_artifacts(
        self, job_id: str, target_dir: Path | None = None
    ) -> list[Path]:
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
            return "remote"
        else:
            return "local"

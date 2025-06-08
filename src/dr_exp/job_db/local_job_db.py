import json
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

import portalocker

from .base_job_db import BaseJobDB, StaleJobInfo
from .config import JobDBConfig

logger = logging.getLogger(__name__)


class LocalJobDB(BaseJobDB):
    """Local filesystem-backed job database implementation.

    This class provides a development and testing job database implementation
    using local JSON files for job storage and the local filesystem for
    artifact storage. Ideal for local development, testing, and offline work.
    """

    def __init__(self, config: JobDBConfig) -> None:
        """Initialize the local job database from configuration.

        Creates the necessary directories for job storage, metrics, and artifacts.

        Parameters
        ----------
        config : JobDBConfig
            Configuration object with paths and settings.
        """
        config.validate()
        super().__init__(config.base_path, config.storage_path)
        self.config = config

        # Local-specific directories and files
        self.metrics_dir = os.path.join(self.jobs_dir, "metrics")
        self.errors_file = os.path.join(self.jobs_dir, "errors.jsonl")

        # Ensure local-specific directories exist
        os.makedirs(self.metrics_dir, exist_ok=True)
        Path(self.errors_file).touch(exist_ok=True)

    def _atomic_write(self, target_file_path: str, data: str) -> None:
        """Write data to a file atomically using a temporary file.

        Parameters
        ----------
        target_file_path : str
            Path where the final file should be written.
        data : str
            Content to write to the file.
        """
        target_dir = os.path.dirname(target_file_path)
        fd, temp_file_path = tempfile.mkstemp(
            dir=target_dir, prefix=os.path.basename(target_file_path) + "~"
        )
        try:
            with os.fdopen(fd, "w") as temp_file:
                temp_file.write(data)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.rename(temp_file_path, target_file_path)
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Return a list of all job records in the database.

        Returns
        -------
        list[dict[str, Any]]
            List of all job records stored as JSON files.
        """
        jobs: List[Dict[str, Any]] = []
        for job_file in os.listdir(self.jobs_dir):
            if not job_file.endswith(".json"):
                continue
            path = os.path.join(self.jobs_dir, job_file)
            try:
                with open(path, "r") as f:
                    jobs.append(json.load(f))
            except Exception as e:  # pragma: no cover - unexpected read error
                logger.error(f"Error reading job file {path}: {e}")
        return jobs

    # --- Interface methods based on docs/supabase_mock.md ---

    def claim_job(
        self, worker_id: Optional[str] = None, respect_reservations: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Atomically claim the highest priority available queued job.

        Looks for jobs with status='queued', sorts by priority (highest first),
        then by age (oldest first), and claims the first available job.
        Uses file-level locking for atomicity across processes.

        Parameters
        ----------
        worker_id : str, optional
            Identifier of the worker claiming the job. If not provided,
            a mock worker ID will be generated.

        Returns
        -------
        dict[str, Any] | None
            The claimed job record or None if no job is available.
        """
        # Collect all queued jobs with shared locks
        queued_jobs = []
        for job_file_name in os.listdir(self.jobs_dir):
            if not job_file_name.endswith(".json"):
                continue

            job_file_path = os.path.join(self.jobs_dir, job_file_name)
            try:
                with portalocker.Lock(
                    job_file_path, mode="r", flags=portalocker.LOCK_SH
                ):
                    with open(job_file_path, "r") as f:
                        job_data = json.load(f)
                    if job_data["status"] == "queued":  # Fail fast if status missing
                        # Check reservations if respect_reservations is True
                        if respect_reservations and job_data.get("reserved_for_worker"):
                            # Check if reservation has expired
                            if self._is_reservation_expired(job_data):
                                # Clear expired reservation
                                job_data.pop("reserved_for_worker", None)
                                job_data.pop("reservation_expires_at", None)
                                # Update the job file to clear reservation
                                try:
                                    with portalocker.Lock(
                                        job_file_path,
                                        mode="r+b",
                                        flags=portalocker.LOCK_EX,
                                    ):
                                        self._atomic_write(
                                            job_file_path,
                                            json.dumps(job_data, indent=4),
                                        )
                                except Exception as e:
                                    # Fail fast: log error with full context, not masked job_id
                                    logger.warning(
                                        f"Failed to clear expired reservation for job {job_data['job_id']}: {e}"
                                    )
                                    # Continue even if cleanup fails
                            elif job_data["reserved_for_worker"] != worker_id:
                                # Skip jobs reserved for other workers
                                continue

                        queued_jobs.append((job_file_path, job_data))
            except Exception as e:
                logger.error(f"Error reading job file {job_file_path}: {e}")
                continue

        if not queued_jobs:
            return None

        # Sort by priority (higher first), then by age (older first)
        queued_jobs.sort(
            key=lambda item: (
                -item[1]["priority"],  # Fail fast if priority missing
                item[1]["created_at"],  # Fail fast if created_at missing
            )
        )

        # Try to claim jobs in priority order
        for job_file_path, job_data in queued_jobs:
            try:
                with portalocker.Lock(
                    job_file_path, mode="r+b", flags=portalocker.LOCK_EX
                ):
                    # Re-read under exclusive lock to ensure status hasn't changed
                    with open(job_file_path, "r") as f:
                        current_job_data = json.load(f)

                    if current_job_data.get("status") == "queued":
                        # Claim the job
                        current_job_data["status"] = "running"
                        current_job_data["assigned_worker"] = worker_id or (
                            f"mock_worker_{uuid.uuid4().hex[:6]}"
                        )
                        current_job_data["heartbeat"] = (
                            datetime.now(UTC).isoformat() + "Z"
                        )
                        current_job_data["started_at"] = (
                            datetime.now(UTC).isoformat() + "Z"
                        )

                        self._atomic_write(
                            job_file_path, json.dumps(current_job_data, indent=4)
                        )
                        return current_job_data
            except Exception as e:
                logger.error(f"Error claiming job file {job_file_path}: {e}")
                continue

        return None

    def update_job(self, job_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update a job record with new data.

        Parameters
        ----------
        job_id : str
            Identifier of the job to update.
        data : dict[str, Any]
            Fields to update on the job record.

        Returns
        -------
        dict[str, Any]
            A dictionary describing the outcome of the update operation.
        """
        # Validate update data before proceeding
        self._validate_update_data(data)
        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        if not os.path.exists(job_file_path):
            # logger.debug(f"Job file not found for update: {job_file_path}")
            # In a real scenario, you might raise an error or return a status
            # For now, let's assume it might be created if it's a new job being fully defined
            # Or simply do nothing if it strictly means "update existing"
            # For robustness, let's assume we only update existing.
            return {"success": False, "message": "Job not found"}

        try:
            with portalocker.Lock(job_file_path, mode="r+b", flags=portalocker.LOCK_EX):
                with open(job_file_path, "r") as f:
                    existing_data = json.load(f)

                existing_data.update(data)
                if existing_data.get("status") == "running" and "heartbeat" not in data:
                    existing_data["heartbeat"] = datetime.now(UTC).isoformat() + "Z"

                self._atomic_write(job_file_path, json.dumps(existing_data, indent=4))
            return {"success": True, "message": "Job updated"}
        except Exception as e:
            logger.error(f"Error updating job {job_id}: {e}")
            return {"success": False, "message": str(e)}

    def log_metrics(self, job_id: str, metrics_list: List[Dict[str, Any]]) -> None:
        """Log metrics for a job by appending to its metrics file.

        Parameters
        ----------
        job_id : str
            Job identifier.
        metrics_list : list[dict[str, Any]]
            List of metrics dictionaries to log. Each metric will be
            written as a JSON line in the job's metrics file.
        """
        metric_file_path = os.path.join(self.metrics_dir, f"{job_id}.jsonl")
        try:
            with portalocker.Lock(
                metric_file_path, mode="a", flags=portalocker.LOCK_EX
            ) as f:
                for metrics in metrics_list:
                    metrics_to_log = metrics.copy()
                    if "timestamp" not in metrics_to_log:
                        metrics_to_log["timestamp"] = (
                            datetime.now(UTC).isoformat() + "Z"
                        )
                    f.write(json.dumps(metrics_to_log) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logger.error(f"Error logging metrics for job {job_id}: {e}")

    def record_failure(
        self,
        job_id: str,
        error_type: str,
        message: str,
        stacktrace: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record a failure event and mark the job as failed.

        Parameters
        ----------
        job_id : str
            Identifier of the job that failed.
        error_type : str
            Short error class or type description.
        message : str
            Human-readable error message.
        stacktrace : str, optional
            Stack trace to store for debugging.

        Returns
        -------
        dict[str, Any]
            Result of the failure recording operation.
        """
        error_entry = {
            "job_id": job_id,
            "error_type": error_type,
            "message": message,
            "stacktrace": stacktrace,
            "timestamp": datetime.now(UTC).isoformat() + "Z",
        }
        try:
            with portalocker.Lock(
                self.errors_file, mode="a", flags=portalocker.LOCK_EX
            ) as f:
                f.write(json.dumps(error_entry) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return {"success": True}
        except Exception as e:
            logger.error(f"Error recording failure for job {job_id}: {e}")
            return {"success": False, "message": str(e)}

    def upload_artifact(
        self, job_id: str, local_path: str, remote_path_suffix: str
    ) -> Dict[str, Any]:
        """Upload an artifact file or directory to local storage.

        Simulates cloud storage by copying artifacts to the local storage directory.
        Files are organized under run-specific directories.

        Parameters
        ----------
        job_id : str
            Job identifier.
        local_path : str
            Path to the local file or directory to upload.
        remote_path_suffix : str
            Relative path where the artifact should be stored.
            If it contains '/' or no '.', it goes under artifacts/ subdirectory.
            Simple files like 'metrics.jsonl' go in the run root.

        Returns
        -------
        dict[str, Any]
            Result of the upload operation including the storage path.
        """
        # Input validation for security - only reject dangerous relative paths
        if not local_path or ".." in local_path:
            logger.warning(f"Invalid local path provided: {local_path}")
            return {"success": False, "message": "Invalid local path"}

        if not os.path.exists(local_path):
            logger.warning(f"Local artifact not found: {local_path}")
            return {"success": False, "message": "Local artifact not found"}

        # Determine if it's a root file (like metrics.jsonl) or an artifact subdirectory file
        if (
            "/" not in remote_path_suffix and "." in remote_path_suffix
        ):  # Simple check for root files
            destination_path = os.path.join(
                self.storage_dir, f"run_{job_id}", remote_path_suffix
            )
        else:
            destination_path = os.path.join(
                self.storage_dir, f"run_{job_id}", "artifacts", remote_path_suffix
            )

        destination_dir = os.path.dirname(destination_path)
        os.makedirs(destination_dir, exist_ok=True)

        try:
            if os.path.isdir(local_path):
                # local_path is a directory; copy entire directory tree
                shutil.copytree(local_path, destination_path, dirs_exist_ok=True)
            else:
                # local_path is a file; copy the single file
                shutil.copy2(local_path, destination_path)
            return {"success": True, "storage_path": destination_path}
        except Exception as e:
            logger.error(f"Error uploading artifact for job {job_id}: {e}")
            return {"success": False, "message": str(e)}

    # --- Helper/Additional methods that would be needed ---
    def get_job_details(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full details for a specific job.

        Parameters
        ----------
        job_id : str
            Identifier of the job to fetch.

        Returns
        -------
        dict[str, Any] | None
            The job record if found, otherwise None.
        """
        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        if os.path.exists(job_file_path):
            with open(job_file_path, "r") as f:
                return json.load(f)
        return None

    def get_config_for_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return the configuration associated with a job.

        Parameters
        ----------
        job_id : str
            Job identifier whose config should be fetched.

        Returns
        -------
        dict[str, Any] | None
            The configuration dictionary or None if unavailable.
        """
        job_data = self.get_job_details(job_id)
        if job_data and "config_json" in job_data:
            return job_data["config_json"]
        # logger.debug(f"Config not found for job {job_id}")
        return None

    def add_job(
        self,
        job_config: Dict[str, Any],
        sweep_config_id: str,
        status: str = "queued",
        priority: int = 100,
    ) -> Dict[str, Any]:
        """Add a new job entry to the database.

        Parameters
        ----------
        job_config : dict[str, Any]
            The job configuration.
        sweep_config_id : str
            Identifier for the sweep configuration.
        status : str, optional
            Initial job status, by default "queued".
        priority : int, optional
            Job priority for queue ordering (0-1000), by default 100.
            Higher values indicate higher priority.

        Returns
        -------
        dict[str, Any]
            The created job record with generated job ID.
        """
        job_id = str(uuid.uuid4())
        # Validate priority is in valid range
        priority = self._validate_priority(priority)

        job_data = {
            "id": job_id,
            "config_id": sweep_config_id,  # This would be the ID of the entry in a sweep_configs table
            "status": status,
            "retry_index": 0,
            "priority": priority,
            "priority_boost_count": 0,
            "assigned_worker": "unassigned",
            "config_json": job_config,  # Storing the full config here for mock simplicity
            "created_at": datetime.now(UTC).isoformat() + "Z",
            # ... other fields will be populated as the job runs
        }
        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        with portalocker.Lock(job_file_path, mode="wb", flags=portalocker.LOCK_EX):
            self._atomic_write(job_file_path, json.dumps(job_data, indent=4))
        logger.info(f"Added new job {job_id}")
        logger.debug("Job Data: " + ", ".join(f"{k}={v}" for k, v in job_data.items()))
        return job_data

    # Priority management methods

    def update_job_priority(
        self,
        job_id: str,
        new_priority: int,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update the priority of a job.

        Parameters
        ----------
        job_id : str
            Identifier of the job to update.
        new_priority : int
            New priority value (0-1000). Higher values indicate higher priority.
        reason : str, optional
            Optional reason for the priority change, for audit purposes.

        Returns
        -------
        dict[str, Any]
            Result of the priority update operation.
        """
        # Validate priority is in valid range
        new_priority = self._validate_priority(new_priority)

        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        if not os.path.exists(job_file_path):
            return {"success": False, "message": "Job not found"}

        try:
            with portalocker.Lock(job_file_path, mode="r+b", flags=portalocker.LOCK_EX):
                with open(job_file_path, "r") as f:
                    job_data = json.load(f)

                old_priority = job_data["priority"]  # Fail fast if priority missing
                job_data["priority"] = new_priority

                # Add audit trail
                if "priority_changes" not in job_data:
                    job_data["priority_changes"] = []

                job_data["priority_changes"].append(
                    {
                        "timestamp": datetime.now(UTC).isoformat() + "Z",
                        "old_priority": old_priority,
                        "new_priority": new_priority,
                        "reason": reason,
                    }
                )

                self._atomic_write(job_file_path, json.dumps(job_data, indent=4))

            return {
                "success": True,
                "old_priority": old_priority,
                "new_priority": new_priority,
                "message": f"Priority updated from {old_priority} to {new_priority}",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def boost_job_priority(
        self,
        job_id: str,
        boost_amount: int = 100,
    ) -> Dict[str, Any]:
        """Boost the priority of a job by a specified amount.

        Parameters
        ----------
        job_id : str
            Identifier of the job to boost.
        boost_amount : int, optional
            Amount to add to the current priority, by default 100.
            Final priority will be clamped to valid range (0-1000).

        Returns
        -------
        dict[str, Any]
            Result of the priority boost operation including new priority.
        """
        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        if not os.path.exists(job_file_path):
            return {"success": False, "message": "Job not found"}

        try:
            with portalocker.Lock(job_file_path, mode="r+b", flags=portalocker.LOCK_EX):
                with open(job_file_path, "r") as f:
                    job_data = json.load(f)

                old_priority = job_data["priority"]  # Fail fast if priority missing
                new_priority = self._validate_priority(old_priority + boost_amount)
                job_data["priority"] = new_priority
                job_data["priority_boost_count"] = (
                    job_data.get("priority_boost_count", 0)
                    + 1  # Boost count can legitimately default to 0
                )

                # Add audit trail
                if "priority_changes" not in job_data:
                    job_data["priority_changes"] = []

                job_data["priority_changes"].append(
                    {
                        "timestamp": datetime.now(UTC).isoformat() + "Z",
                        "old_priority": old_priority,
                        "new_priority": new_priority,
                        "reason": f"Priority boost of +{boost_amount}",
                    }
                )

                self._atomic_write(job_file_path, json.dumps(job_data, indent=4))

            return {
                "success": True,
                "old_priority": old_priority,
                "new_priority": new_priority,
                "boost_amount": boost_amount,
                "message": f"Priority boosted from {old_priority} to {new_priority}",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def list_jobs_by_priority(
        self,
        status_filter: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List jobs ordered by priority (highest first).

        Parameters
        ----------
        status_filter : list[str], optional
            Filter jobs by status (e.g., ["queued", "running"]).
            If None, all jobs are returned.
        limit : int, optional
            Maximum number of jobs to return. If None, all matching jobs.

        Returns
        -------
        list[dict[str, Any]]
            List of job records ordered by priority (highest first),
            then by submission time (oldest first) for equal priorities.
        """
        jobs = self.list_jobs()

        # Apply status filter
        if status_filter:
            jobs = [job for job in jobs if job["status"] in status_filter]

        # Sort by priority (highest first), then by age (oldest first)
        jobs.sort(
            key=lambda job: (
                -job["priority"],  # Fail fast if priority missing
                job[
                    "created_at"
                ],  # Older jobs first at same priority - fail fast if missing
            )
        )

        # Apply limit
        if limit is not None:
            jobs = jobs[:limit]

        return jobs

    # Job reservation methods

    def _is_reservation_expired(self, job_data: Dict[str, Any]) -> bool:
        """Check if a job reservation has expired.

        Parameters
        ----------
        job_data : dict[str, Any]
            Job record to check.

        Returns
        -------
        bool
            True if the reservation has expired or no expiration is set.
        """
        expires_at_str = job_data.get("reservation_expires_at")
        if not expires_at_str:
            return False  # No expiration set, never expires

        try:
            expires_at_str = expires_at_str.rstrip("Z")
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            return datetime.now(UTC) >= expires_at
        except (ValueError, TypeError):
            return True  # Invalid timestamp, consider expired

    def add_reserved_job(
        self,
        job_config: Dict[str, Any],
        sweep_config_id: str,
        reserved_for_worker: str,
        reservation_timeout: Optional[int] = 300,
        priority: int = 100,
        status: str = "queued",
    ) -> Dict[str, Any]:
        """Add a new job entry reserved for a specific worker.

        Parameters
        ----------
        job_config : dict[str, Any]
            The job configuration.
        sweep_config_id : str
            Identifier for the sweep configuration.
        reserved_for_worker : str
            Worker ID that can claim this job.
        reservation_timeout : int, optional
            Reservation timeout in seconds, by default 300 (5 minutes).
            If None, reservation never expires.
        priority : int, optional
            Job priority for queue ordering (0-1000), by default 100.
        status : str, optional
            Initial job status, by default "queued".

        Returns
        -------
        dict[str, Any]
            The created job record with reservation information.
        """
        job_id = str(uuid.uuid4())
        # Validate priority is in valid range
        priority = self._validate_priority(priority)

        job_data = {
            "id": job_id,
            "config_id": sweep_config_id,
            "status": status,
            "retry_index": 0,
            "priority": priority,
            "priority_boost_count": 0,
            "assigned_worker": "unassigned",
            "config_json": job_config,
            "created_at": datetime.now(UTC).isoformat() + "Z",
            "reserved_for_worker": reserved_for_worker,
        }

        # Add expiration time if timeout is specified
        if reservation_timeout is not None:
            expires_at = datetime.now(UTC) + timedelta(seconds=reservation_timeout)
            job_data["reservation_expires_at"] = expires_at.isoformat() + "Z"

        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        with portalocker.Lock(job_file_path, mode="wb", flags=portalocker.LOCK_EX):
            self._atomic_write(job_file_path, json.dumps(job_data, indent=4))

        logger.info(f"Added reserved job {job_id} for worker {reserved_for_worker}")
        return job_data

    # =========================================================================
    # NEW STREAMLINED INTERFACE IMPLEMENTATIONS
    # =========================================================================

    def list_running_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs currently in 'running' status."""
        running_jobs = []
        try:
            for filename in os.listdir(self.jobs_dir):
                if not filename.endswith(".json"):
                    continue

                job_file_path = os.path.join(self.jobs_dir, filename)
                try:
                    with open(job_file_path, "r") as f:
                        job_data = json.load(f)

                    if job_data["status"] == "running":  # Fail fast if status missing
                        running_jobs.append(job_data)

                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Error reading job file {filename}: {e}")
                    continue

        except FileNotFoundError:
            # Jobs directory doesn't exist yet
            pass

        return running_jobs

    def get_stale_jobs(self, max_age_seconds: int) -> List[StaleJobInfo]:
        """Find jobs with heartbeats older than max_age_seconds."""
        stale_jobs = []
        now = datetime.now(UTC)

        running_jobs = self.list_running_jobs()

        for job in running_jobs:
            heartbeat_str = job.get(
                "heartbeat"
            )  # Optional field - legitimate use of .get()
            assigned_worker = job["assigned_worker"]  # Required field
            job_id = job["id"]  # Required field

            if not heartbeat_str or not assigned_worker or not job_id:
                continue

            try:
                # Parse heartbeat timestamp
                heartbeat_time = datetime.fromisoformat(heartbeat_str.replace("Z", ""))
                if heartbeat_time.tzinfo is None:
                    heartbeat_time = heartbeat_time.replace(tzinfo=UTC)

                # Calculate age
                age = now - heartbeat_time
                age_seconds = int(age.total_seconds())

                if age_seconds > max_age_seconds:
                    stale_jobs.append(
                        StaleJobInfo(
                            job_id=job_id,
                            assigned_worker=assigned_worker,
                            last_heartbeat=heartbeat_time,
                            age_seconds=age_seconds,
                        )
                    )

            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing heartbeat for job {job_id}: {e}")
                continue

        return stale_jobs

    def mark_jobs_failed(
        self, job_ids: List[str], reason: str = "worker_lost"
    ) -> Dict[str, bool]:
        """Mark multiple jobs as failed efficiently."""
        results = {}
        current_time = datetime.now(UTC).isoformat() + "Z"

        for job_id in job_ids:
            try:
                job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")

                # Read current job data
                with portalocker.Lock(
                    job_file_path, mode="r+b", flags=portalocker.LOCK_EX
                ):
                    try:
                        with open(job_file_path, "r") as f:
                            job_data = json.load(f)
                    except (FileNotFoundError, json.JSONDecodeError):
                        results[job_id] = False
                        continue

                    # Update job status
                    job_data.update(
                        {
                            "status": "failed",
                            "status_reason": reason,
                            "end_time": current_time,
                        }
                    )

                    # Write updated data
                    self._atomic_write(job_file_path, json.dumps(job_data, indent=4))
                    results[job_id] = True

            except Exception as e:
                logger.error(f"Error marking job {job_id} as failed: {e}")
                results[job_id] = False

        return results

    def has_queued_jobs(self) -> bool:
        """Check if there are any queued jobs available."""
        try:
            for filename in os.listdir(self.jobs_dir):
                if not filename.endswith(".json"):
                    continue

                job_file_path = os.path.join(self.jobs_dir, filename)
                try:
                    with open(job_file_path, "r") as f:
                        job_data = json.load(f)

                    if job_data["status"] == "queued":  # Fail fast if status missing
                        return True

                except (json.JSONDecodeError, KeyError):
                    continue

        except FileNotFoundError:
            # Jobs directory doesn't exist yet
            pass

        return False

    def get_queue_summary(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get summary of top queued jobs for logging."""
        try:
            # Get all queued jobs
            queued_jobs = []
            for filename in os.listdir(self.jobs_dir):
                if not filename.endswith(".json"):
                    continue

                job_file_path = os.path.join(self.jobs_dir, filename)
                try:
                    with open(job_file_path, "r") as f:
                        job_data = json.load(f)

                    if job_data["status"] == "queued":  # Fail fast if status missing
                        queued_jobs.append(
                            {
                                "id": job_data["id"],  # Required field
                                "priority": job_data[
                                    "priority"
                                ],  # Fail fast if priority missing
                                "created_at": job_data["created_at"],  # Required field
                            }
                        )

                except (json.JSONDecodeError, KeyError):
                    continue

            # Sort by priority (highest first), then by created_at (oldest first)
            queued_jobs.sort(key=lambda job: (-job["priority"], job["created_at"]))

            return queued_jobs[:limit]

        except FileNotFoundError:
            # Jobs directory doesn't exist yet
            return []

    def get_metrics(
        self, run_id: str, limit: Optional[int] = 500
    ) -> List[Dict[str, Any]]:
        """Get metrics for a specific run.

        Parameters
        ----------
        run_id : str
            Identifier of the run to load metrics for.
        limit : int, optional
            Maximum number of recent metrics to return, by default 500.
            If None, returns all metrics.

        Returns
        -------
        List[Dict[str, Any]]
            List of metrics records for the run.

        Raises
        ------
        FileNotFoundError
            If metrics for the run do not exist.
        """
        metrics_path = os.path.join(self.storage_dir, f"run_{run_id}", "metrics.jsonl")

        if not os.path.exists(metrics_path):
            raise FileNotFoundError(f"Metrics not found for run {run_id}")

        metrics = []
        with open(metrics_path, "r") as f:
            for line in f:
                if line.strip():
                    metrics.append(json.loads(line))

        # Apply limit if specified
        if limit is not None and len(metrics) > limit:
            metrics = metrics[-limit:]

        return metrics

    def finalize_job(
        self, job_id: str, final_status: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Finalize a job with the given status and metadata."""
        return self._default_finalize_job_logic(job_id, final_status, metadata)


__all__ = ["LocalJobDB"]

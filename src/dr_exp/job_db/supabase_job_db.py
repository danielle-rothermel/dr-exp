# Example: experiment_manager/core/supabase_client.py

import logging
import os
import shutil
import tempfile
from supabase import create_client, Client
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta

from .base_job_db import BaseJobDB, StaleJobInfo
from .config import JobDBConfig

logger = logging.getLogger(__name__)


class SupabaseJobDB(BaseJobDB):
    """Supabase-backed job database implementation.

    This class provides a production-ready job database implementation using
    Supabase as the backend for job storage, configuration management, and
    artifact storage.
    """

    def __init__(self, config: JobDBConfig) -> None:
        """Initialize the client and connect to Supabase.

        Parameters
        ----------
        config : JobDBConfig
            Configuration object with Supabase credentials and paths.

        Raises
        ------
        ValueError
            If Supabase URL or key is missing from config.
        """
        config.validate()
        # Initialize base class first
        super().__init__(config.base_path, config.storage_path)
        self.config = config

        if not config.supabase_url or not config.supabase_key:
            raise ValueError("Supabase URL and Key must be provided in config.")
        try:
            self.supabase: Client = create_client(
                config.supabase_url, config.supabase_key
            )
            logger.info("Successfully connected to Supabase.")
        except Exception as e:
            logger.error(f"Failed to connect to Supabase: {e}")
            raise

    def claim_job(
        self, worker_id: Optional[str] = None, respect_reservations: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Claim the next available queued job.

        Parameters
        ----------
        worker_id : str, optional
            Identifier of the worker claiming the job. If None,
            defaults to "unassigned_worker".
        respect_reservations : bool, optional
            Whether to respect job reservations, by default True.

        Returns
        -------
        dict[str, Any] | None
            The claimed job record or ``None`` if no job is available.

        Raises
        ------
        RuntimeError
            If database connection or RPC call fails.
        """
        # Handle None worker_id by providing default
        effective_worker_id = worker_id or "unassigned_worker"

        try:
            # Assumes a PostgreSQL function `claim_next_job(worker_id_input TEXT)` exists
            response = self.supabase.rpc(
                "claim_next_job", {"worker_id_input": effective_worker_id}
            ).execute()
            if response.data:
                return response.data[0]  # RPC might return a list with one item
            return None  # No jobs available - legitimate case
        except Exception as e:
            logger.error(f"Critical database error claiming job: {e}")
            raise RuntimeError(f"Database claim operation failed: {e}") from e

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
        try:
            response = (
                self.supabase.table("jobs").update(data).eq("id", job_id).execute()
            )
            if response.data:
                return {"success": True, "data": response.data[0]}
            # Handle cases where update might not return data but succeeded, or error
            # Check PostgREST spec for update returns if needed. Often update returns the updated rows.
            # If response.error is present, it failed.
            if hasattr(response, "error") and response.error:
                raise Exception(f"Supabase error: {response.error.message}")
            # If no data and no error, it might mean no row matched the filter.
            return {"success": False, "message": "Job not found or update failed."}
        except Exception as e:
            logger.error(f"Error updating job {job_id}: {e}")
            return {"success": False, "message": str(e)}

    def get_job_details(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full details for a specific job.

        Parameters
        ----------
        job_id : str
            Identifier of the job to fetch.

        Returns
        -------
        dict[str, Any] | None
            The job record if found, otherwise ``None``.

        Raises
        ------
        RuntimeError
            If database connection fails.
        """
        try:
            response = (
                self.supabase.table("jobs")
                .select("*, sweep_configs(config_json)")
                .eq("id", job_id)
                .maybe_single()
                .execute()
            )
            return response.data if response.data else None  # None = job not found
        except Exception as e:
            logger.error(
                f"Critical database error getting job details for {job_id}: {e}"
            )
            raise RuntimeError(f"Database query failed for job {job_id}: {e}") from e

    def get_config_for_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Return the configuration associated with ``job_id``.

        Parameters
        ----------
        job_id : str
            Job identifier whose config should be fetched.

        Returns
        -------
        dict[str, Any] | None
            The configuration dictionary or ``None`` if unavailable.

        Raises
        ------
        RuntimeError
            If database connection fails.
        """
        try:
            job_details = self.get_job_details(job_id)
            if (
                job_details and job_details["config_id"]
            ):  # Fail fast if config_id missing
                config_id = job_details["config_id"]
                response = (
                    self.supabase.table("sweep_configs")
                    .select("config_json")
                    .eq("id", config_id)
                    .single()
                    .execute()
                )
                if response.data:
                    return response.data[
                        "config_json"
                    ]  # Fail fast if config_json missing
            return None  # Job not found or no config_id - legitimate cases
        except RuntimeError:
            # Re-raise database errors from get_job_details
            raise
        except Exception as e:
            logger.error(
                f"Critical database error getting config for job {job_id}: {e}"
            )
            raise RuntimeError(f"Config lookup failed for job {job_id}: {e}") from e

    def log_metrics_file(
        self,
        job_id: str,
        local_metrics_file_path: str,
        remote_metrics_filename: str = "metrics.jsonl",
    ) -> Dict[str, Any]:
        """Upload a metrics file to Supabase Storage.

        Parameters
        ----------
        job_id : str
            Job identifier.
        local_metrics_file_path : str
            Path to the local ``metrics.jsonl`` file.
        remote_metrics_filename : str, optional
            Name to use when uploading the file, by default ``"metrics.jsonl"``.

        Returns
        -------
        dict[str, Any]
            Result of the upload operation including the storage path.
        """
        if not os.path.exists(local_metrics_file_path):
            return {
                "success": False,
                "message": f"Local metrics file not found: {local_metrics_file_path}",
            }

        remote_db_path = f"run_{job_id}/{remote_metrics_filename}"
        try:
            with open(local_metrics_file_path, "rb") as f:
                self.supabase.storage.from_("experiment-artifacts").upload(
                    file=f,
                    path=remote_db_path,
                    file_options={
                        "cache-control": "3600",
                        "upsert": True,
                    },  # upsert=True to overwrite if exists
                )
            # Update the job record with the path
            self.update_job(job_id, {"metrics_path": remote_db_path})
            return {"success": True, "storage_path": remote_db_path}
        except Exception as e:
            logger.error(f"Error uploading metrics file for job {job_id}: {e}")
            return {"success": False, "message": str(e)}

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
            Result of the insert/update operations.
        """
        failure_data = {
            "job_id": job_id,
            "error_type": error_type,
            "message": message,
            "stacktrace": stacktrace,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.supabase.table("errors").insert(failure_data).execute()
            # Also update job status
            self.update_job(
                job_id,
                {
                    "status": "failed",
                    "end_time": datetime.now(timezone.utc).isoformat(),
                },
            )
            return {"success": True}
        except Exception as e:
            logger.error(f"Error recording failure for job {job_id}: {e}")
            return {"success": False, "message": str(e)}

    def upload_artifact(
        self, job_id: str, local_path: str, remote_path_suffix: str
    ) -> Dict[str, Any]:
        """Upload an artifact file or directory to Supabase Storage.

        Parameters
        ----------
        job_id : str
            Job identifier.
        local_path : str
            Path to the local file or directory to upload.
        remote_path_suffix : str
            Relative path under the run directory where the artifact should be
            stored.

        Returns
        -------
        dict[str, Any]
            Result of the upload operation including the storage path.
        """
        if not os.path.exists(local_path):
            return {
                "success": False,
                "message": f"Local artifact not found: {local_path}",
            }

        # Determine full remote path based on suffix (root file vs. under 'artifacts/')
        if (
            "/" not in remote_path_suffix and "." in remote_path_suffix
        ):  # Simple check for root files like 'worker.log'
            remote_full_path = f"run_{job_id}/{remote_path_suffix}"
        else:  # Assumed to be an artifact to go into the 'artifacts' subdirectory
            remote_full_path = f"run_{job_id}/artifacts/{remote_path_suffix}"

        try:
            if os.path.isdir(local_path):
                base_name = (
                    os.path.basename(remote_path_suffix.rstrip("/")) or "artifacts"
                )
                temp_dir = tempfile.mkdtemp()
                archive_path = shutil.make_archive(
                    os.path.join(temp_dir, base_name), "zip", local_path
                )
                remote_full_path = f"{remote_full_path.rstrip('/')}.zip"
                with open(archive_path, "rb") as f:
                    self.supabase.storage.from_("experiment-artifacts").upload(
                        file=f,
                        path=remote_full_path,
                        file_options={"cache-control": "3600", "upsert": True},
                    )
                os.remove(archive_path)
                os.rmdir(temp_dir)
            else:  # It's a file
                with open(local_path, "rb") as f:
                    self.supabase.storage.from_("experiment-artifacts").upload(
                        file=f,
                        path=remote_full_path,
                        file_options={"cache-control": "3600", "upsert": True},
                    )
            return {"success": True, "storage_path": remote_full_path}
        except Exception as e:
            logger.error(
                f"Error uploading artifact '{local_path}' for job {job_id}: {e}"
            )
            return {"success": False, "message": str(e)}

    # --- Methods primarily for Config Generator ---

    def add_sweep_config_cluster(
        self, name: str, description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a sweep configuration cluster entry.

        Parameters
        ----------
        name : str
            Name of the cluster.
        description : str, optional
            Optional human description.

        Returns
        -------
        dict[str, Any]
            Newly created record.

        Raises
        ------
        RuntimeError
            If database insertion fails.
        """
        try:
            data = {"name": name}
            if description is not None:
                data["description"] = description
            response = (
                self.supabase.table("sweep_config_clusters").insert(data).execute()
            )
            if not response.data:
                raise RuntimeError("Database insertion returned no data")
            return response.data[0]
        except Exception as e:
            logger.error(f"Critical database error adding sweep config cluster: {e}")
            raise RuntimeError(f"Failed to create sweep config cluster: {e}") from e

    def check_sweep_config_exists(self, config_hash: str) -> Optional[Dict[str, Any]]:
        """Check whether a configuration with ``config_hash`` exists.

        Parameters
        ----------
        config_hash : str
            Hash of the configuration to check.

        Returns
        -------
        dict[str, Any] | None
            Configuration record if found, None if not found.

        Raises
        ------
        RuntimeError
            If database query fails.
        """
        try:
            response = (
                self.supabase.table("sweep_configs")
                .select("id, config_hash")
                .eq("config_hash", config_hash)
                .maybe_single()
                .execute()
            )
            return response.data if response.data else None  # None = not found
        except Exception as e:
            logger.error(
                f"Critical database error checking sweep config existence: {e}"
            )
            raise RuntimeError(
                f"Database query failed for config hash {config_hash}: {e}"
            ) from e

    def add_sweep_config(
        self,
        cluster_id: str,
        config_json: Dict[str, Any],
        config_hash: str,
        interface_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a new sweep configuration entry.

        Parameters
        ----------
        cluster_id : str
            Identifier of the cluster this config belongs to.
        config_json : dict[str, Any]
            Serialized Hydra configuration.
        config_hash : str
            SHA256 hash of ``config_json``.
        interface_version : str, optional
            Optional interface version string.

        Returns
        -------
        dict[str, Any]
            The created row.

        Raises
        ------
        RuntimeError
            If database insertion fails.
        """
        try:
            data = {
                "cluster_id": cluster_id,
                "config_json": config_json,
                "config_hash": config_hash,
                "interface_version": interface_version,
            }
            response = self.supabase.table("sweep_configs").insert(data).execute()
            if not response.data:
                raise RuntimeError("Database insertion returned no data")
            return response.data[0]
        except Exception as e:
            logger.error(f"Critical database error adding sweep config: {e}")
            raise RuntimeError(f"Failed to create sweep config: {e}") from e

    def add_job_entry(
        self,
        config_id: str,
        status: str = "queued",
        retry_index: int = 0,
        priority: int = 100,
        interface_version: Optional[str] = None,
        code_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new job for the given configuration.

        Parameters
        ----------
        config_id : str
            Identifier of the configuration to run.
        status : str, optional
            Initial status value, by default ``"queued"``.
        retry_index : int, optional
            Retry count, by default ``0``.
        priority : int, optional
            Job priority for queue ordering (0-1000), by default 100.
            Higher values indicate higher priority.
        interface_version : str, optional
            Version of the training interface.
        code_version : str, optional
            Version of the code to execute.

        Returns
        -------
        dict[str, Any]
            Newly created job row.

        Raises
        ------
        ValueError
            If priority is invalid.
        RuntimeError
            If database insertion fails.
        """
        try:
            # Validate priority is in valid range - this already raises ValueError
            priority = self._validate_priority(priority)

            data = {
                "config_id": config_id,
                "status": status,
                "retry_index": retry_index,
                "priority": priority,
                "interface_version": interface_version,
                "code_version": code_version,
                # created_at is handled by DB default
            }
            response = self.supabase.table("jobs").insert(data).execute()
            if not response.data:
                raise RuntimeError("Database insertion returned no data")
            return response.data[0]
        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.error(f"Critical database error adding job entry: {e}")
            raise RuntimeError(f"Failed to create job: {e}") from e

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

        try:
            # Update job priority
            update_data = {"priority": new_priority}
            response = (
                self.supabase.table("jobs")
                .update(update_data)
                .eq("id", job_id)
                .execute()
            )

            if response.data:
                return {
                    "success": True,
                    "new_priority": new_priority,
                    "message": f"Priority updated to {new_priority}",
                }
            else:
                return {"success": False, "message": "Job not found or update failed"}

        except Exception as e:
            logger.error(f"Error updating job priority for {job_id}: {e}")
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
        try:
            # Get current priority
            response = (
                self.supabase.table("jobs")
                .select("priority")
                .eq("id", job_id)
                .single()
                .execute()
            )

            if not response.data:
                return {"success": False, "message": "Job not found"}

            old_priority = response.data["priority"]  # Fail fast if priority missing
            new_priority = self._validate_priority(old_priority + boost_amount)

            # Update priority
            update_response = (
                self.supabase.table("jobs")
                .update({"priority": new_priority})
                .eq("id", job_id)
                .execute()
            )

            if update_response.data:
                return {
                    "success": True,
                    "old_priority": old_priority,
                    "new_priority": new_priority,
                    "boost_amount": boost_amount,
                    "message": f"Priority boosted from {old_priority} to {new_priority}",
                }
            else:
                return {"success": False, "message": "Priority boost failed"}

        except Exception as e:
            logger.error(f"Error boosting job priority for {job_id}: {e}")
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
        try:
            query = self.supabase.table("jobs").select("*")

            # Apply status filter
            if status_filter:
                query = query.in_("status", status_filter)

            # Order by priority (descending), then by created_at (ascending)
            query = query.order("priority", desc=True).order("created_at", desc=False)

            # Apply limit
            if limit is not None:
                query = query.limit(limit)

            response = query.execute()
            return response.data if response.data else []

        except Exception as e:
            logger.error(f"Error listing jobs by priority: {e}")
            return []

    # Job reservation methods

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
        # Validate priority is in valid range
        priority = self._validate_priority(priority)

        data = {
            "config_id": sweep_config_id,
            "status": status,
            "retry_index": 0,
            "priority": priority,
            "reserved_for_worker": reserved_for_worker,
            # created_at is handled by DB default
        }

        # Add expiration time if timeout is specified
        if reservation_timeout is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=reservation_timeout
            )
            data["reservation_expires_at"] = expires_at.isoformat()

        try:
            response = self.supabase.table("jobs").insert(data).execute()
            if response.data:
                job_record = response.data[0]
                # Add the config_json to the response for consistency with LocalJobDB
                job_record["config_json"] = job_config
                logger.info(
                    f"Added reserved job {job_record['id']} for worker {reserved_for_worker}"
                )
                return job_record
            else:
                raise Exception("No data returned from insert")
        except Exception as e:
            logger.error(f"Error adding reserved job: {e}")
            return {"success": False, "message": str(e)}

    # =========================================================================
    # NEW STREAMLINED INTERFACE IMPLEMENTATIONS
    # =========================================================================

    def list_running_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs currently in 'running' status."""
        try:
            response = (
                self.supabase.table("jobs")
                .select("*")
                .eq("status", "running")
                .execute()
            )
            return response.data or []
        except Exception as e:
            logger.error(f"Error listing running jobs: {e}")
            return []

    def get_stale_jobs(self, max_age_seconds: int) -> List[StaleJobInfo]:
        """Find jobs with heartbeats older than max_age_seconds."""
        try:
            # Calculate cutoff time
            cutoff_time = datetime.now(timezone.utc) - timedelta(
                seconds=max_age_seconds
            )

            response = (
                self.supabase.table("jobs")
                .select("id, assigned_worker, heartbeat")
                .eq("status", "running")
                .not_.is_("heartbeat", "null")
                .not_.is_("assigned_worker", "null")
                .lt("heartbeat", cutoff_time.isoformat())
                .execute()
            )

            stale_jobs = []
            now = datetime.now(timezone.utc)

            for job in response.data or []:
                try:
                    heartbeat_str = job.get("heartbeat")
                    if heartbeat_str:
                        heartbeat_time = datetime.fromisoformat(
                            heartbeat_str.replace("Z", "")
                        )
                        if heartbeat_time.tzinfo is None:
                            heartbeat_time = heartbeat_time.replace(tzinfo=timezone.utc)

                        age_seconds = int((now - heartbeat_time).total_seconds())

                        stale_jobs.append(
                            StaleJobInfo(
                                job_id=job["id"],
                                assigned_worker=job["assigned_worker"],
                                last_heartbeat=heartbeat_time,
                                age_seconds=age_seconds,
                            )
                        )
                except (ValueError, TypeError) as e:
                    logger.error(
                        f"Error parsing heartbeat for job {job.get('id')}: {e}"
                    )
                    continue

            return stale_jobs

        except Exception as e:
            logger.error(f"Error getting stale jobs: {e}")
            return []

    def mark_jobs_failed(
        self, job_ids: List[str], reason: str = "worker_lost"
    ) -> Dict[str, bool]:
        """Mark multiple jobs as failed efficiently."""
        if not job_ids:
            return {}

        results = {}
        current_time = datetime.now(timezone.utc).isoformat()

        try:
            # Batch update using Supabase
            response = (
                self.supabase.table("jobs")
                .update(
                    {
                        "status": "failed",
                        "status_reason": reason,
                        "end_time": current_time,
                    }
                )
                .in_("id", job_ids)
                .execute()
            )

            # Mark all as successful if the batch update worked
            updated_jobs = response.data or []
            updated_job_ids = {job["id"] for job in updated_jobs}

            for job_id in job_ids:
                results[job_id] = job_id in updated_job_ids

        except Exception as e:
            logger.warning(
                f"Error in batch update, falling back to individual updates: {e}"
            )

            # Fallback: individual updates
            for job_id in job_ids:
                try:
                    response = (
                        self.supabase.table("jobs")
                        .update(
                            {
                                "status": "failed",
                                "status_reason": reason,
                                "end_time": current_time,
                            }
                        )
                        .eq("id", job_id)
                        .execute()
                    )
                    results[job_id] = bool(response.data)
                except Exception as e:
                    logger.error(f"Error marking job {job_id} as failed: {e}")
                    results[job_id] = False

        return results

    def has_queued_jobs(self) -> bool:
        """Check if there are any queued jobs available."""
        try:
            response = (
                self.supabase.table("jobs")
                .select("id")
                .eq("status", "queued")
                .limit(1)
                .execute()
            )
            return len(response.data or []) > 0
        except Exception as e:
            logger.error(f"Error checking for queued jobs: {e}")
            return False

    def get_queue_summary(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get summary of top queued jobs for logging."""
        try:
            response = (
                self.supabase.table("jobs")
                .select("id, priority, created_at")
                .eq("status", "queued")
                .order("priority", desc=True)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )

            return response.data or []

        except Exception as e:
            logger.error(f"Error getting queue summary: {e}")
            return []

    def get_metrics(
        self, run_id: str, limit: Optional[int] = 500
    ) -> List[Dict[str, Any]]:
        """Get metrics for a specific run.

        For Supabase, this first checks local storage for faster access,
        then downloads from Supabase storage bucket with retry logic.

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
            If metrics for the run do not exist in local or remote storage.
        """
        import json
        import os

        # Try local storage first (faster)
        local_metrics_path = os.path.join(
            self.storage_dir, f"run_{run_id}", "metrics.jsonl"
        )

        if os.path.exists(local_metrics_path):
            metrics = []
            with open(local_metrics_path, "r") as f:
                for line in f:
                    if line.strip():
                        metrics.append(json.loads(line))

            # Apply limit if specified
            if limit is not None and len(metrics) > limit:
                metrics = metrics[-limit:]

            return metrics

        # Implement Supabase storage download with retry logic
        storage_path = f"run_{run_id}/metrics.jsonl"
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # Download from Supabase storage bucket
                response = self.supabase.storage.from_("experiment-artifacts").download(
                    storage_path
                )

                if response:
                    metrics = []
                    # Parse the downloaded content line by line
                    content = response.decode("utf-8")
                    for line in content.strip().split("\n"):
                        if line.strip():
                            try:
                                metrics.append(json.loads(line))
                            except json.JSONDecodeError as e:
                                logger.warning(
                                    f"Failed to parse metrics line: {line[:100]}... Error: {e}"
                                )
                                continue

                    # Apply limit if specified
                    if limit is not None and len(metrics) > limit:
                        metrics = metrics[-limit:]

                    logger.info(
                        f"Successfully downloaded {len(metrics)} metrics from Supabase storage for run {run_id}"
                    )
                    return metrics
                else:
                    raise FileNotFoundError(
                        f"Metrics file not found in Supabase storage for run {run_id}"
                    )

            except Exception as e:
                if attempt == max_retries - 1:
                    # Last attempt failed
                    logger.error(
                        f"Error downloading metrics from Supabase storage for run {run_id} after {max_retries} attempts: {e}"
                    )
                    raise FileNotFoundError(
                        f"Could not retrieve metrics from storage: {e}"
                    )
                else:
                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} for downloading metrics from Supabase storage for run {run_id}: {e}"
                    )
                    continue

    def finalize_job(
        self, job_id: str, final_status: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Finalize a job with the given status and metadata."""
        return self._default_finalize_job_logic(job_id, final_status, metadata)


__all__ = ["SupabaseJobDB"]

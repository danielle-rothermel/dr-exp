import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any

import portalocker

from .base_job_db import BaseJobDB


class LocalJobDB(BaseJobDB):
    """Local filesystem-backed job database implementation.
    
    This class provides a development and testing job database implementation
    using local JSON files for job storage and the local filesystem for
    artifact storage. Ideal for local development, testing, and offline work.
    """

    def __init__(self, base_path: str = ".", storage_path: str = "./storage") -> None:
        """Initialize the local job database.

        Creates the necessary directories for job storage, metrics, and artifacts.
        
        Parameters
        ----------
        base_path : str, optional
            Base directory under which job data is stored, by default ".".
            The jobs_dir will be created as base_path/job_data.
        storage_path : str, optional
            Directory for artifact and run output storage, by default "./storage".
        """
        # Location for finalized outputs
        self.storage_dir = storage_path
        # Location to write in-progress logs
        self.jobs_dir = os.path.join(base_path, "job_data")
        self.metrics_dir = os.path.join(self.jobs_dir, "metrics")
        self.errors_file = os.path.join(self.jobs_dir, "errors.jsonl")

        # Ensure directories exist (idempotent)
        os.makedirs(self.jobs_dir, exist_ok=True)
        os.makedirs(self.metrics_dir, exist_ok=True)
        os.makedirs(self.storage_dir, exist_ok=True)
        if not os.path.exists(self.errors_file):
            with open(self.errors_file, "w"):
                pass  # Create empty file

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
                print(f"Error reading job file {path}: {e}")
        return jobs

    # --- Interface methods based on docs/supabase_mock.md ---

    def claim_job(self, worker_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Atomically claim the next available queued job.
        
        Looks for a job with status='queued' and updates it to 'running'.
        Uses file-level locking for atomicity across processes.
        
        Parameters
        ----------
        worker_id : str, optional
            Identifier of the worker claiming the job. If not provided,
            a random worker ID will be generated.
            
        Returns
        -------
        dict[str, Any] | None
            The claimed job record or None if no job is available.
        """
        for job_file_name in os.listdir(self.jobs_dir):
            if not job_file_name.endswith(".json"):
                continue

            job_file_path = os.path.join(self.jobs_dir, job_file_name)
            try:
                with portalocker.Lock(
                    job_file_path, mode="r+b", flags=portalocker.LOCK_EX
                ):
                    with open(job_file_path, "r") as f:
                        job_data = json.load(f)

                    if job_data.get("status") == "queued":
                        job_data["status"] = "running"
                        job_data["assigned_worker"] = worker_id or (
                            f"mock_worker_{uuid.uuid4().hex[:6]}"
                        )
                        job_data["heartbeat"] = datetime.now(UTC).isoformat() + "Z"

                        self._atomic_write(
                            job_file_path, json.dumps(job_data, indent=4)
                        )
                        return job_data
            except Exception as e:
                print(
                    f"Error processing job file {job_file_path}: {e}"
                )  # Should go to a logger
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
        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        if not os.path.exists(job_file_path):
            # print(f"Job file not found for update: {job_file_path}") # Debug
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
            print(f"Error updating job {job_id}: {e}")
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
            print(f"Error logging metrics for job {job_id}: {e}")

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
            print(f"Error recording failure for job {job_id}: {e}")
            return {"success": False, "message": str(e)}

    def finalize_job(self, job_id: str, final_status: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Finalize a job with the given status and metadata.
        
        Parameters
        ----------
        job_id : str
            Identifier of the job.
        final_status : str
            Final status string to record.
        metadata : dict[str, Any]
            Additional fields to store on the job record.
            
        Returns
        -------
        dict[str, Any]
            Result of the finalization operation.
        """
        update_data = {
            "status": final_status,
            "end_time": datetime.now(UTC).isoformat() + "Z",
        }
        update_data.update(metadata)  # e.g., upload_complete_at, finalize_success
        result = self.update_job(job_id, update_data)
        if result.get("success"):
            self._write_finished_flag(job_id)
        return result

    def _write_finished_flag(self, job_id: str) -> None:
        """Create an empty finished.flag file for a completed job.
        
        Parameters
        ----------
        job_id : str
            Job identifier for which to create the finished flag.
        """
        run_dir = os.path.join(self.storage_dir, f"run_{job_id}")
        os.makedirs(run_dir, exist_ok=True)
        flag_path = os.path.join(run_dir, "finished.flag")
        try:
            with open(flag_path, "w"):
                pass
        except Exception as e:
            print(f"Error writing finished flag for job {job_id}: {e}")

    def upload_artifact(self, job_id: str, local_path: str, remote_path_suffix: str) -> Dict[str, Any]:
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
        if not os.path.exists(local_path):
            print(f"Local artifact not found: {local_path}")
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
            print(f"Error uploading artifact for job {job_id}: {e}")
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
        # print(f"Config not found for job {job_id}") # Debug
        return None

    def add_job(
        self, job_config: Dict[str, Any], sweep_config_id: str, status: str = "queued"
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
            
        Returns
        -------
        dict[str, Any]
            The created job record with generated job ID.
        """
        job_id = str(uuid.uuid4())
        job_data = {
            "id": job_id,
            "config_id": sweep_config_id,  # This would be the ID of the entry in a sweep_configs table
            "status": status,
            "retry_index": 0,
            "assigned_worker": "unassigned",
            "config_json": job_config,  # Storing the full config here for mock simplicity
            "created_at": datetime.now(UTC).isoformat() + "Z",
            # ... other fields will be populated as the job runs
        }
        job_file_path = os.path.join(self.jobs_dir, f"{job_id}.json")
        with portalocker.Lock(job_file_path, mode="wb", flags=portalocker.LOCK_EX):
            self._atomic_write(job_file_path, json.dumps(job_data, indent=4))
        print(f"Added new job {job_id}")  # Debug
        print("Job Data:")
        for k, v in job_data.items():
            print(f" - {k + ':':20} {v}")
        return job_data


__all__ = ["LocalJobDB"]

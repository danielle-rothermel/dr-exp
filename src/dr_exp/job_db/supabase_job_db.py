# Example: experiment_manager/core/supabase_client.py

import os
import shutil
import tempfile
from supabase import create_client, Client
from typing import Optional, Dict, Any
from datetime import datetime, timezone


class SupabaseClient:
    """Wrapper around :mod:`supabase` providing convenience helpers."""

    def __init__(
        self, supabase_url: str, supabase_key: str, base_path: str = "."
    ) -> None:
        """Initialise the client and connect to Supabase.

        Parameters
        ----------
        supabase_url : str
            URL of the Supabase project.
        supabase_key : str
            API key with permissions for backend operations.

        Raises
        ------
        ValueError
            If ``supabase_url`` or ``supabase_key`` is missing.
        """
        if not supabase_url or not supabase_key:
            raise ValueError("Supabase URL and Key must be provided.")
        try:
            self.supabase: Client = create_client(supabase_url, supabase_key)
            print("Successfully connected to Supabase.")
        except Exception as e:
            print(f"Failed to connect to Supabase: {e}")
            raise

        # Where to write any local data
        self.storage_dir = f"{base_path}/storage"
        os.makedirs(self.storage_dir, exist_ok=True)

    def claim_job(
        self, worker_id: str = "unassigned_worker"
    ) -> Optional[Dict[str, Any]]:
        """Claim the next available queued job.

        Parameters
        ----------
        worker_id : str, optional
            Identifier of the worker claiming the job. Defaults to
            ``"unassigned_worker"``.

        Returns
        -------
        dict[str, Any] | None
            The claimed job record or ``None`` if no job is available.
        """
        try:
            # Assumes a PostgreSQL function `claim_next_job(worker_id_input TEXT)` exists
            response = self.supabase.rpc(
                "claim_next_job", {"worker_id_input": worker_id}
            ).execute()
            if response.data:
                return response.data[0]  # RPC might return a list with one item
            return None
        except Exception as e:
            print(f"Error claiming job: {e}")
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
            print(f"Error updating job {job_id}: {e}")
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
        """
        try:
            response = (
                self.supabase.table("jobs")
                .select("*, sweep_configs(config_json)")
                .eq("id", job_id)
                .maybe_single()
                .execute()
            )
            return response.data if response.data else None
        except Exception as e:
            print(f"Error getting job details for {job_id}: {e}")
            return None

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
        """
        try:
            job_details = self.get_job_details(job_id)
            if job_details and job_details.get("config_id"):
                config_id = job_details["config_id"]
                response = (
                    self.supabase.table("sweep_configs")
                    .select("config_json")
                    .eq("id", config_id)
                    .single()
                    .execute()
                )
                if response.data:
                    return response.data.get("config_json")
            return None
        except Exception as e:
            print(f"Error getting config for job {job_id}: {e}")
            return None

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
            print(f"Error uploading metrics file for job {job_id}: {e}")
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
            print(f"Error recording failure for job {job_id}: {e}")
            return {"success": False, "message": str(e)}

    def finalize_job(
        self, job_id: str, final_status: str, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
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
            Result of the update operation.
        """
        update_data = {"status": final_status}
        if "end_time" not in metadata:  # Add end_time if not already provided
            update_data["end_time"] = datetime.now(timezone.utc).isoformat()
        update_data.update(metadata)
        result = self.update_job(job_id, update_data)
        if result.get("success"):
            self._write_finished_flag(job_id)
        return result

    def _write_finished_flag(self, job_id: str) -> None:
        """Create an empty ``finished.flag`` file for ``job_id`` in local storage."""
        run_dir = os.path.join(self.storage_dir, f"run_{job_id}")
        os.makedirs(run_dir, exist_ok=True)
        flag_path = os.path.join(run_dir, "finished.flag")
        try:
            with open(flag_path, "w"):
                pass
        except Exception as e:  # pragma: no cover - unexpected disk error
            print(f"Error writing finished flag for job {job_id}: {e}")

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
            print(f"Error uploading artifact '{local_path}' for job {job_id}: {e}")
            return {"success": False, "message": str(e)}

    # --- Methods primarily for Config Generator ---

    def add_sweep_config_cluster(
        self, name: str, description: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a sweep configuration cluster entry.

        Parameters
        ----------
        name : str
            Name of the cluster.
        description : str, optional
            Optional human description.

        Returns
        -------
        dict[str, Any] | None
            Newly created record or ``None`` on failure.
        """
        try:
            data = {"name": name}
            if description is not None:
                data["description"] = description
            response = (
                self.supabase.table("sweep_config_clusters").insert(data).execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error adding sweep config cluster: {e}")
            return None

    def check_sweep_config_exists(self, config_hash: str) -> Optional[Dict[str, Any]]:
        """Check whether a configuration with ``config_hash`` exists."""
        try:
            response = (
                self.supabase.table("sweep_configs")
                .select("id, config_hash")
                .eq("config_hash", config_hash)
                .maybe_single()
                .execute()
            )
            return response.data if response.data else None
        except Exception as e:
            print(f"Error checking sweep config existence: {e}")
            return None

    def add_sweep_config(
        self,
        cluster_id: str,
        config_json: Dict[str, Any],
        config_hash: str,
        interface_version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
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
        dict[str, Any] | None
            The created row or ``None`` if insertion failed.
        """
        try:
            data = {
                "cluster_id": cluster_id,
                "config_json": config_json,
                "config_hash": config_hash,
                "interface_version": interface_version,
            }
            response = self.supabase.table("sweep_configs").insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error adding sweep config: {e}")
            return None

    def add_job_entry(
        self,
        config_id: str,
        status: str = "queued",
        retry_index: int = 0,
        interface_version: Optional[str] = None,
        code_version: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a new job for the given configuration.

        Parameters
        ----------
        config_id : str
            Identifier of the configuration to run.
        status : str, optional
            Initial status value, by default ``"queued"``.
        retry_index : int, optional
            Retry count, by default ``0``.
        interface_version : str, optional
            Version of the training interface.
        code_version : str, optional
            Version of the code to execute.

        Returns
        -------
        dict[str, Any] | None
            Newly created job row or ``None`` on failure.
        """
        try:
            data = {
                "config_id": config_id,
                "status": status,
                "retry_index": retry_index,
                "interface_version": interface_version,
                "code_version": code_version,
                # created_at is handled by DB default
            }
            response = self.supabase.table("jobs").insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error adding job entry: {e}")
            return None

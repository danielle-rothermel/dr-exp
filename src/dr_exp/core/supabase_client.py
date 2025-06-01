# Example: experiment_manager/core/supabase_client.py

import os
from supabase import create_client, Client
from typing import Optional, Dict, Any
from datetime import datetime, timezone


class SupabaseClient:
    def __init__(self, supabase_url: str, supabase_key: str):
        """
        Initializes the client and connects to Supabase.
        :param supabase_url: Your Supabase project URL.
        :param supabase_key: Your Supabase service_role key (recommended for backend operations) or anon key.
        """
        if not supabase_url or not supabase_key:
            raise ValueError("Supabase URL and Key must be provided.")
        try:
            self.supabase: Client = create_client(supabase_url, supabase_key)
            print("Successfully connected to Supabase.")
        except Exception as e:
            print(f"Failed to connect to Supabase: {e}")
            raise

    def claim_job(
        self, worker_id: str = "unassigned_worker"
    ) -> Optional[Dict[str, Any]]:
        """
        Atomically claims the next available 'queued' job.
        This typically uses a database function for atomicity.
        """
        try:
            # Assumes a PostgreSQL function `claim_next_job(worker_id_input TEXT)` exists:
            # SQL for function (create this in your Supabase SQL editor):
            # CREATE OR REPLACE FUNCTION claim_next_job(worker_id_input TEXT)
            # RETURNS SETOF jobs AS $$
            # DECLARE
            #   claimed_job_id UUID;
            # BEGIN
            #   SELECT id INTO claimed_job_id
            #   FROM jobs
            #   WHERE status = 'queued'
            #   ORDER BY created_at ASC -- Or your preferred ordering
            #   FOR UPDATE SKIP LOCKED
            #   LIMIT 1;
            #
            #   IF claimed_job_id IS NOT NULL THEN
            #     RETURN QUERY
            #     UPDATE jobs
            #     SET status = 'running',
            #         assigned_worker = worker_id_input,
            #         heartbeat = now()
            #     WHERE id = claimed_job_id
            #     RETURNING *;
            #   END IF;
            # END;
            # $$ LANGUAGE plpgsql;
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
        """Updates a job record with new data."""
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
        """Retrieves full details for a specific job."""
        try:
            # Example of fetching related data (config_json) directly if needed often
            # response = self.supabase.table("jobs").select("*, sweep_configs(config_json)").eq("id", job_id).maybe_single().execute()
            response = (
                self.supabase.table("jobs")
                .select("*")
                .eq("id", job_id)
                .maybe_single()
                .execute()
            )
            return response.data if response.data else None
        except Exception as e:
            print(f"Error getting job details for {job_id}: {e}")
            return None

    def get_config_for_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves the 'config_json' for a given job by looking up its config_id."""
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
        """
        Uploads a local metrics.jsonl file to Supabase Storage for the given job.
        Updates the job record with the path to this file.
        Note: Interface changed from mock (list of metrics) to path of pre-written file.
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
        """Records a failure event in the 'errors' table and updates the job status."""
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
        """Finalizes a job, typically setting its status, end_time, and other result metadata."""
        update_data = {"status": final_status}
        if "end_time" not in metadata:  # Add end_time if not already provided
            update_data["end_time"] = datetime.now(timezone.utc).isoformat()
        update_data.update(metadata)
        return self.update_job(job_id, update_data)

    def upload_artifact(
        self, job_id: str, local_path: str, remote_path_suffix: str
    ) -> Dict[str, Any]:
        """
        Uploads a single artifact file or directory to Supabase Storage.
        remote_path_suffix is relative to the job's specific storage location.
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
                # supabase-py storage client currently does not have a direct 'upload_folder' method.
                # You'd need to iterate and upload files individually or zip then upload the zip.
                # For simplicity, this example will raise an error for directory uploads.
                # Consider zipping the directory and uploading the zip file.
                return {
                    "success": False,
                    "message": "Directory upload not directly supported; please zip or upload files individually.",
                }
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
        """Adds a new sweep_config_cluster."""
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
        """Checks if a sweep_config with the given hash already exists."""
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
        """Adds a new sweep_config."""
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
        """Adds a new job entry linked to a sweep_config."""
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


# Example Usage (Illustrative - not part of the class)
if __name__ == "__main__":
    # These would typically come from environment variables or a config file
    # SUPABASE_URL = os.environ.get("SUPABASE_URL")
    # SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") # Use service role for backend operations

    # try:
    #     # client = SupabaseClient(SUPABASE_URL, SUPABASE_KEY)
    #     # print("Client initialized.")
    #     # Example: claimed_job = client.claim_job(worker_id="test_worker_01")
    #     # if claimed_job:
    #     #     print("Claimed job:", claimed_job)
    #     # else:
    #     #     print("No job claimed.")
    # except ValueError as ve:
    #     print(ve)
    # except Exception as e:
    #     print(f"An unexpected error occurred during example usage: {e}")
    pass
